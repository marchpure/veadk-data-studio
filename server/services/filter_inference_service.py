from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

import sqlglot
from sqlalchemy.ext.asyncio import AsyncSession
from sqlglot import exp

from server.repositories.notebooks import NotebookRepository
from server.repositories.queries import QueryRepository
from server.services.filter_config_service import (
    get_default_operator,
    harmonize_filter_definitions,
    infer_data_type,
    infer_filter_type,
    merge_filters_non_destructive,
    normalize_filter_id,
    sync_query_filter_contracts,
)
from server.services.raw_query import AsyncRawQueryService
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)


class DashboardFilterInferenceService:
    MAX_AUTO_FILTERS_PER_QUERY = 4
    MAX_CANDIDATES_TO_PROBE = 8
    MAX_OPTIONS_PER_FILTER = 100
    PROBE_TIMEOUT_SECONDS = 6
    IDENTIFIER_FIELD_PATTERN = re.compile(r"(?:^|_)(id|uuid|guid|key|hash)$", re.IGNORECASE)

    @staticmethod
    def _sqlglot_dialect(db_type: str) -> str:
        mapping = {
            "pg": "postgres",
            "postgres": "postgres",
            "postgresql": "postgres",
            "mysql": "mysql",
            "sqlite": "sqlite",
            "mssql": "tsql",
            "duckdb": "duckdb",
        }
        return mapping.get((db_type or "pg").lower(), "postgres")

    @staticmethod
    def _quote_identifier(identifier: str, db_type: str) -> str:
        if db_type == "mysql":
            return f"`{str(identifier).replace('`', '``')}`"
        if db_type == "mssql":
            return f"[{str(identifier).replace(']', ']]')}]"
        escaped = str(identifier).replace('"', '""')
        return f'"{escaped}"'

    @staticmethod
    def _humanize_label(name: str) -> str:
        cleaned = str(name).replace(".", " ").replace("_", " ").strip()
        return " ".join(piece.capitalize() for piece in cleaned.split())

    @staticmethod
    def _looks_like_identifier_field(name: str) -> bool:
        normalized = str(name).strip().lower()
        if not normalized:
            return False
        if normalized in {"id", "_id"}:
            return True
        return bool(DashboardFilterInferenceService.IDENTIFIER_FIELD_PATTERN.search(normalized))

    @staticmethod
    def infer_sql_filter_candidates(query: str, db_type: str) -> list[dict[str, str]]:
        dialect = DashboardFilterInferenceService._sqlglot_dialect(db_type)
        try:
            parsed = sqlglot.parse_one(query, read=dialect)
        except Exception as exc:
            logger.warning(f"Auto filter inference: failed to parse SQL query: {exc}")
            return []

        select_node = parsed if isinstance(parsed, exp.Select) else parsed.find(exp.Select)
        if not select_node:
            return []

        candidates: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()

        for projection in select_node.expressions:
            output_name = projection.alias_or_name
            underlying = projection.this if isinstance(projection, exp.Alias) else projection

            if isinstance(underlying, exp.Column):
                source_field = f"{underlying.table}.{underlying.name}" if underlying.table else underlying.name
                output_field = output_name or underlying.name
            else:
                continue

            if not source_field or not output_field:
                continue

            dedupe_key = (source_field, output_field)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            candidates.append(
                {
                    "field_name": source_field,
                    "output_name": output_field,
                    "display_label": DashboardFilterInferenceService._humanize_label(output_field),
                }
            )

        return candidates

    @staticmethod
    async def _resolve_execution_context(
        saved_query, session: AsyncSession
    ) -> tuple[str | None, str | None, dict[str, Any] | None]:
        dataset = saved_query.dataset
        if not dataset:
            return None, None, None

        if dataset.type == "connection" and dataset.connection:
            connection_obj = await dataset.connection.get_decrypted_connection_obj(session)
            if not connection_obj:
                return None, None, None
            return str(dataset.connection.id), str(dataset.connection.type).lower(), connection_obj

        if dataset.type == "file":
            dataset_files = list(dataset.files or [])
            connection_obj = {
                "dataset_id": str(dataset.id),
                "dataset_type": "file",
                "db_type": "duckdb",
                "files": [{"id": str(f.id), "name": f.name, "type": f.type, "size": f.size} for f in dataset_files],
            }
            return str(dataset.id), "duckdb", connection_obj

        return None, None, None

    @staticmethod
    async def _probe_field_options(
        query: str,
        output_name: str,
        db_type: str,
        connection_id: str,
        connection_obj: dict[str, Any],
    ) -> list[Any]:
        quoted_output = DashboardFilterInferenceService._quote_identifier(output_name, db_type)
        probe_query = (
            f'SELECT {quoted_output} AS "__value", COUNT(*) AS "__freq" '
            f'FROM ({query}) AS "__auto_filter_base" '
            f"GROUP BY {quoted_output} ORDER BY __freq DESC"
        )

        result = await AsyncRawQueryService.execute_raw_query(
            query=probe_query,
            db_type=db_type,
            connection_id=connection_id,
            connection_obj=connection_obj,
            limit=DashboardFilterInferenceService.MAX_OPTIONS_PER_FILTER,
            timeout=DashboardFilterInferenceService.PROBE_TIMEOUT_SECONDS,
        )
        if not result.get("success"):
            raise ValueError(result.get("error", "Unknown probe error"))

        rows = result.get("result") or []
        values = [row.get("__value") for row in rows if isinstance(row, dict)]
        return [value for value in values if value is not None]

    @staticmethod
    async def bootstrap_for_saved_query(
        session: AsyncSession,
        notebook_id: str,
        query_id: str,
    ) -> dict[str, Any]:
        query_repo = QueryRepository(session)
        notebook_repo = NotebookRepository(session)
        saved_query = await query_repo.get_with_relations(query_id)

        if not saved_query:
            return {"status": "error", "message": f"Query '{query_id}' not found", "added_count": 0, "filters": []}

        if saved_query.query_type == "api":
            return {
                "status": "skipped",
                "message": "Auto filters skipped for API queries",
                "added_count": 0,
                "filters": [],
            }

        notebook = await notebook_repo.get(notebook_id)
        if not notebook:
            return {
                "status": "error",
                "message": f"Notebook '{notebook_id}' not found for filter bootstrap",
                "added_count": 0,
                "filters": [],
            }

        connection_id, db_type, connection_obj = await DashboardFilterInferenceService._resolve_execution_context(
            saved_query, session
        )
        if not connection_id or not db_type or not connection_obj:
            return {
                "status": "skipped",
                "message": "Could not resolve datasource context",
                "added_count": 0,
                "filters": [],
            }

        if db_type == "mongo":
            return {
                "status": "skipped",
                "message": "Mongo auto filter inference not enabled yet",
                "added_count": 0,
                "filters": [],
            }

        candidates = DashboardFilterInferenceService.infer_sql_filter_candidates(saved_query.query, db_type)
        if not candidates:
            return {
                "status": "skipped",
                "message": "No filterable SQL columns inferred",
                "added_count": 0,
                "filters": [],
            }

        auto_filters: list[dict[str, Any]] = []
        for candidate in candidates[: DashboardFilterInferenceService.MAX_CANDIDATES_TO_PROBE]:
            if len(auto_filters) >= DashboardFilterInferenceService.MAX_AUTO_FILTERS_PER_QUERY:
                break

            output_name = candidate["output_name"]
            field_name = candidate["field_name"]

            # Skip likely identifier-like fields before probing to avoid expensive/low-value filters.
            field_leaf = str(field_name).split(".")[-1]
            if DashboardFilterInferenceService._looks_like_identifier_field(
                output_name
            ) or DashboardFilterInferenceService._looks_like_identifier_field(field_leaf):
                continue
            try:
                options = await DashboardFilterInferenceService._probe_field_options(
                    query=saved_query.query,
                    output_name=output_name,
                    db_type=db_type,
                    connection_id=connection_id,
                    connection_obj=connection_obj,
                )
            except Exception as probe_error:
                logger.info(
                    "Auto filter bootstrap probe failed for %s (%s): %s",
                    field_name,
                    query_id,
                    probe_error,
                )
                continue

            if not options:
                continue

            filter_type = infer_filter_type(options, field_name)
            if DashboardFilterInferenceService._looks_like_identifier_field(output_name) and len(options) > 20:
                continue

            operator = get_default_operator(filter_type)
            filter_def: dict[str, Any] = {
                "id": normalize_filter_id(str(saved_query.id), field_name),
                "query_id": str(saved_query.id),
                "field_name": field_name,
                "display_label": candidate["display_label"],
                "filter_type": filter_type,
                "operator": operator,
                "options": options if filter_type in {"select", "multiselect"} else None,
                "data_type": infer_data_type(filter_type, options),
                "source": "auto",
                "auto_generated": True,
                "created_at": datetime.now(UTC).isoformat(),
            }
            auto_filters.append(filter_def)

        if not auto_filters:
            return {
                "status": "skipped",
                "message": "No suitable auto filters found after probing",
                "added_count": 0,
                "filters": [],
            }

        existing_config: dict[str, Any]
        try:
            existing_config = json.loads(notebook.filters_config) if notebook.filters_config else {}
            if not isinstance(existing_config, dict):
                existing_config = {}
        except json.JSONDecodeError:
            existing_config = {}

        existing_filters = existing_config.get("filters", [])
        if not isinstance(existing_filters, list):
            existing_filters = []

        merged_filters = merge_filters_non_destructive(existing_filters, auto_filters)
        merged_filters = harmonize_filter_definitions(merged_filters)
        existing_keys = {
            (str(item.get("query_id", "")).strip(), str(item.get("field_name", "")).strip())
            for item in existing_filters
            if isinstance(item, dict)
        }
        added_filters = [
            item
            for item in merged_filters
            if isinstance(item, dict)
            and (str(item.get("query_id", "")).strip(), str(item.get("field_name", "")).strip()) not in existing_keys
        ]

        if not added_filters:
            return {"status": "skipped", "message": "No new filters to add", "added_count": 0, "filters": []}

        notebook.filters_config = json.dumps(
            {
                "filters": merged_filters,
                "created_at": existing_config.get("created_at", datetime.now(UTC).isoformat()),
                "version": int(existing_config.get("version", 0)) + 1,
            }
        )
        updated_query_contracts = await sync_query_filter_contracts(session=session, filters_list=merged_filters)
        await session.commit()

        return {
            "status": "added",
            "message": f"Added {len(added_filters)} inferred filter(s)",
            "added_count": len(added_filters),
            "filters": [
                {
                    "id": item.get("id"),
                    "query_id": item.get("query_id"),
                    "field_name": item.get("field_name"),
                    "display_label": item.get("display_label"),
                    "filter_type": item.get("filter_type"),
                }
                for item in added_filters
            ],
            "updated_query_contracts": updated_query_contracts,
        }
