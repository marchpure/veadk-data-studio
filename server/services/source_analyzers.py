from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from server.models.connections import Connection
from server.models.datasets import Dataset
from server.models.knowledge_resources import EvidenceFragment, KnowledgeResource
from server.models.semantic_models import (
    SemanticModel,
    SemanticModelAuditEvent,
    SemanticModelDimension,
    SemanticModelEntity,
    SemanticModelField,
    SemanticModelMetric,
    SemanticModelRelationship,
)
from server.models.source_resources import SourceResource
from server.models.source_snapshots import SourceSnapshot
from server.models.source_understanding import SourceSkillCandidate, SourceUnderstandingRun
from server.services.connections import ConnectionService
from server.services.semantic_model_service import SemanticModelService


DATABASE_ANALYZER_VERSION = "database-source-analyzer-v1"
DATABASE_CONNECTION_TYPES = {"oracle", "pg", "mysql"}


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _json_hash(value: Any) -> str:
    payload = _json_dump(value).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _slugify(value: str, fallback: str = "item") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or fallback


def _snake(value: str, fallback: str = "item") -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or fallback


def _display(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").title()


@dataclass(frozen=True)
class SourceAnalyzerRequest:
    datasource_id: str
    tenant_id: UUID
    user_id: UUID | None
    refresh_schema: bool = False
    scope: tuple[str, ...] = ()


@dataclass(frozen=True)
class NormalizedColumn:
    name: str
    data_type: str
    nullable: bool
    role: str
    description: str = ""
    profile: dict[str, Any] | None = None


@dataclass(frozen=True)
class NormalizedRelationship:
    from_table: str
    from_columns: tuple[str, ...]
    to_table: str
    to_columns: tuple[str, ...]
    source: str
    confidence: float
    validation: dict[str, Any]


@dataclass(frozen=True)
class NormalizedTable:
    catalog: str
    schema: str
    name: str
    table_type: str
    category: str
    description: str
    row_count: int | None
    primary_key: tuple[str, ...]
    columns: tuple[NormalizedColumn, ...]
    foreign_keys: tuple[NormalizedRelationship, ...]
    indexes: tuple[dict[str, Any], ...]
    sample_rows: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class NormalizedDatabaseSchema:
    datasource_name: str
    datasource_type: str
    catalog: str
    schema: str
    tables: tuple[NormalizedTable, ...]
    raw_schema: dict[str, Any]


class SourceAnalyzer(Protocol):
    provider: str
    supported_connection_types: set[str]

    async def analyze(
        self,
        *,
        session: AsyncSession,
        request: SourceAnalyzerRequest,
    ) -> dict[str, Any]:
        ...


class DatabaseSourceAnalyzer:
    provider = "database"
    supported_connection_types = DATABASE_CONNECTION_TYPES

    async def analyze(
        self,
        *,
        session: AsyncSession,
        request: SourceAnalyzerRequest,
    ) -> dict[str, Any]:
        service = SourceUnderstandingService()
        return await service.analyze_database(
            session=session,
            datasource_id=request.datasource_id,
            tenant_id=request.tenant_id,
            user_id=request.user_id,
            refresh_schema=request.refresh_schema,
            scope=list(request.scope),
        )


class SourceUnderstandingService:
    async def get_understanding(
        self,
        *,
        session: AsyncSession,
        datasource_id: str,
        tenant_id: UUID,
    ) -> dict[str, Any]:
        connection = await self._resolve_connection(session=session, datasource_id=datasource_id, tenant_id=tenant_id)
        latest_run = await self._latest_run(session=session, datasource_id=datasource_id, tenant_id=tenant_id)
        resources = await self._list_database_resources(session=session, connection_id=connection.id, tenant_id=tenant_id)
        candidates = await self._list_candidates(session=session, run_id=latest_run.id if latest_run else None)
        evidence = await self._evidence_by_ids(
            session=session,
            evidence_ids={
                str(evidence_id)
                for candidate in candidates
                for evidence_id in (candidate.evidence_ids_json or [])
            },
            tenant_id=tenant_id,
        )
        evidence_by_id = {str(item.id): item for item in evidence}

        return {
            "datasource_id": datasource_id,
            "datasource_name": connection.name or f"{connection.type.upper()} datasource",
            "datasource_type": connection.type,
            "latest_run": self._run_to_payload(latest_run) if latest_run else None,
            "resources": [self._resource_to_payload(resource) for resource in resources],
            "candidates": [
                self._candidate_to_payload(
                    candidate,
                    [evidence_by_id[str(item)] for item in candidate.evidence_ids_json or [] if str(item) in evidence_by_id],
                )
                for candidate in candidates
            ],
            "evidence": [self._evidence_to_payload(item) for item in evidence],
            "overview": self._overview_payload(connection=connection, latest_run=latest_run, resources=resources, candidates=candidates),
            "profile": self._profile_payload(latest_run),
            "quality": self._quality_payload(candidates),
            "sync_drift": self._sync_drift_payload(latest_run),
        }

    async def analyze_database(
        self,
        *,
        session: AsyncSession,
        datasource_id: str,
        tenant_id: UUID,
        user_id: UUID | None,
        refresh_schema: bool = False,
        scope: list[str] | None = None,
    ) -> dict[str, Any]:
        connection = await self._resolve_connection(session=session, datasource_id=datasource_id, tenant_id=tenant_id)
        if connection.type not in DATABASE_CONNECTION_TYPES:
            raise ValueError("Source Understanding currently supports Oracle, PostgreSQL, and MySQL connections")

        schema = await self._load_schema(session=session, connection=connection, refresh_schema=refresh_schema)
        normalized = self._normalize_schema(connection=connection, schema=schema, scope=scope or [])
        previous_hashes = await self._previous_snapshot_hashes(
            session=session,
            tenant_id=tenant_id,
            datasource_id=datasource_id,
        )

        run = SourceUnderstandingRun(
            tenant_id=tenant_id,
            connection_id=connection.id,
            datasource_id=datasource_id,
            provider="database",
            status="running",
            analyzer_version=DATABASE_ANALYZER_VERSION,
            source_snapshot_ids_json=[],
            summary_json={},
            drift_json={},
        )
        session.add(run)
        await session.flush()

        drift_events: list[dict[str, Any]] = []
        snapshot_ids: list[str] = []
        evidence_by_table: dict[str, dict[str, Any]] = {}
        table_snapshots: dict[str, SourceSnapshot] = {}
        table_resources: dict[str, SourceResource] = {}

        catalog_resource, catalog_snapshot = await self._snapshot_resource(
            session=session,
            tenant_id=tenant_id,
            connection_id=connection.id,
            resource_type="database_catalog",
            external_id=f"database:{connection.id}:catalog:{normalized.catalog}",
            name=normalized.catalog,
            payload={
                "catalog": normalized.catalog,
                "datasource_type": normalized.datasource_type,
                "tables": [table.name for table in normalized.tables],
            },
            previous_content_hash=previous_hashes.get(f"database:{connection.id}:catalog:{normalized.catalog}"),
            drift_events=drift_events,
        )
        snapshot_ids.append(str(catalog_snapshot.id))

        schema_resource, schema_snapshot = await self._snapshot_resource(
            session=session,
            tenant_id=tenant_id,
            connection_id=connection.id,
            resource_type="database_schema",
            external_id=f"database:{connection.id}:schema:{normalized.schema}",
            name=f"{normalized.catalog}.{normalized.schema}",
            payload={
                "catalog": normalized.catalog,
                "schema": normalized.schema,
                "table_count": len(normalized.tables),
            },
            previous_content_hash=previous_hashes.get(f"database:{connection.id}:schema:{normalized.schema}"),
            drift_events=drift_events,
        )
        snapshot_ids.append(str(schema_snapshot.id))

        await self._create_knowledge_and_evidence(
            session=session,
            tenant_id=tenant_id,
            resource=catalog_resource,
            snapshot=catalog_snapshot,
            fragments=[
                {
                    "fragment_type": "database_catalog",
                    "title_path": [normalized.catalog],
                    "text": f"Catalog {normalized.catalog} contains {len(normalized.tables)} analyzed tables.",
                    "locator_json": {
                        "kind": "database_catalog",
                        "datasource_id": datasource_id,
                        "connection_id": str(connection.id),
                        "catalog": normalized.catalog,
                    },
                    "confidence": "high",
                }
            ],
        )
        await self._create_knowledge_and_evidence(
            session=session,
            tenant_id=tenant_id,
            resource=schema_resource,
            snapshot=schema_snapshot,
            fragments=[
                {
                    "fragment_type": "database_schema",
                    "title_path": [normalized.catalog, normalized.schema],
                    "text": f"Schema {normalized.schema} has {len(normalized.tables)} analyzed tables.",
                    "locator_json": {
                        "kind": "database_schema",
                        "datasource_id": datasource_id,
                        "connection_id": str(connection.id),
                        "catalog": normalized.catalog,
                        "schema": normalized.schema,
                    },
                    "confidence": "high",
                }
            ],
        )

        for table in normalized.tables:
            table_resource, table_snapshot = await self._snapshot_resource(
                session=session,
                tenant_id=tenant_id,
                connection_id=connection.id,
                resource_type="database_table",
                external_id=f"database:{connection.id}:table:{table.schema}.{table.name}",
                name=f"{table.schema}.{table.name}",
                payload=self._table_snapshot_payload(table),
                previous_content_hash=previous_hashes.get(f"database:{connection.id}:table:{table.schema}.{table.name}"),
                drift_events=drift_events,
            )
            table_resources[table.name] = table_resource
            table_snapshots[table.name] = table_snapshot
            snapshot_ids.append(str(table_snapshot.id))
            fragments = self._table_evidence_fragments(
                datasource_id=datasource_id,
                connection_id=connection.id,
                table=table,
            )
            evidence_by_table[table.name] = await self._create_knowledge_and_evidence(
                session=session,
                tenant_id=tenant_id,
                resource=table_resource,
                snapshot=table_snapshot,
                fragments=fragments,
            )

        candidates = self._build_candidates(normalized, evidence_by_table)
        for candidate in candidates:
            table_name = candidate["table"]
            table_resource = table_resources[table_name]
            table_snapshot = table_snapshots[table_name]
            session.add(
                SourceSkillCandidate(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    resource_id=table_resource.id,
                    snapshot_id=table_snapshot.id,
                    candidate_type=candidate["candidate_type"],
                    title=candidate["title"],
                    statement=candidate["statement"],
                    structured_payload_json={
                        **candidate["structured_payload"],
                        "source_snapshot_id": str(table_snapshot.id),
                        "source_resource_id": str(table_resource.id),
                    },
                    evidence_ids_json=candidate["evidence_ids"],
                    confidence=candidate["confidence"],
                    validation_status=candidate["validation_status"],
                    validation_json=candidate["validation"],
                    review_status="suggested",
                )
            )

        if drift_events:
            await self._mark_previous_verified_stale(
                session=session,
                tenant_id=tenant_id,
                datasource_id=datasource_id,
                current_run_id=run.id,
            )

        run.status = "completed"
        run.completed_at = datetime.utcnow()
        run.source_snapshot_ids_json = snapshot_ids
        run.summary_json = self._summary_payload(normalized, candidates)
        run.drift_json = {
            "status": "drift_detected" if drift_events else "stable",
            "events": drift_events,
            "resource_count": len(snapshot_ids),
            "checked_at": datetime.utcnow().isoformat(),
        }
        await session.commit()

        return await self.get_understanding(session=session, datasource_id=datasource_id, tenant_id=tenant_id)

    async def review_candidate(
        self,
        *,
        session: AsyncSession,
        datasource_id: str,
        candidate_id: str,
        tenant_id: UUID,
        action: str,
        title: str | None = None,
        statement: str | None = None,
        structured_payload: dict[str, Any] | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        await self._resolve_connection(session=session, datasource_id=datasource_id, tenant_id=tenant_id)
        candidate = await self._get_candidate(session=session, candidate_id=candidate_id, tenant_id=tenant_id)
        if candidate is None or candidate.run.datasource_id != datasource_id:
            raise ValueError("Source Skill candidate not found")
        if action == "reject":
            candidate.review_status = "rejected"
        elif action in {"accept", "edit"}:
            if action == "edit":
                if title:
                    candidate.title = title
                if statement:
                    candidate.statement = statement
                if structured_payload:
                    candidate.structured_payload_json = {
                        **candidate.structured_payload_json,
                        **structured_payload,
                        "edited": True,
                    }
            candidate.review_status = "verified"
        else:
            raise ValueError("Unsupported review action")
        candidate.review_note = note
        candidate.reviewed_at = datetime.utcnow()
        await session.commit()
        return await self.get_understanding(session=session, datasource_id=datasource_id, tenant_id=tenant_id)

    async def create_or_update_semantic_model_from_verified(
        self,
        *,
        session: AsyncSession,
        datasource_id: str,
        tenant_id: UUID,
        user_id: UUID | None,
        model_id: str | None,
        name: str | None,
        domain: str,
        owner: str,
        candidate_ids: list[UUID],
    ) -> dict[str, Any]:
        connection = await self._resolve_connection(session=session, datasource_id=datasource_id, tenant_id=tenant_id)
        candidates = await self._verified_candidates(
            session=session,
            datasource_id=datasource_id,
            tenant_id=tenant_id,
            candidate_ids={str(item) for item in candidate_ids},
        )
        if not candidates:
            raise ValueError("No verified Source Skill candidates selected")

        slug = model_id or _slugify(name or f"{connection.name or connection.type} semantic model")
        model = await SemanticModelService._load_model(session, tenant_id, slug)
        if model is None:
            model = SemanticModel(
                tenant_id=tenant_id,
                created_by=user_id,
                slug=slug,
                name=name or f"{connection.name or connection.type.upper()} Semantic Model",
                domain=domain,
                owner=owner,
                datasource_id=datasource_id,
                datasource_name=connection.name or f"{connection.type.upper()} datasource",
                datasource_kind=connection.type,
                description="Draft initialized from verified database Source Understanding candidates.",
                status="Draft",
                draft_revision="draft-source-1",
                published_version="v0",
                readiness=35,
                readiness_level="blocked",
                consumers_json="{}",
                explore_json="{}",
                review_json=_json_dump({"sourceUnderstandingLineage": []}),
                mcp_json=_json_dump({"exposedVersion": "draft", "rawSqlFallback": False}),
                validation_log_json="[]",
            )
            session.add(model)
            await session.flush()
        else:
            model.status = "Draft"
            model.draft_revision = "draft-source-updated"
            model.datasource_id = datasource_id
            model.datasource_name = connection.name or model.datasource_name
            model.datasource_kind = connection.type
        loaded_model = await SemanticModelService._load_model(session, tenant_id, slug)
        if loaded_model is not None:
            model = loaded_model

        applied_ids: list[UUID] = []
        lineage_entries: list[dict[str, Any]] = []
        for candidate in candidates:
            payload = candidate.structured_payload_json or {}
            lineage = self._candidate_lineage(candidate)
            lineage_entries.append(lineage)
            if candidate.candidate_type == "schema_map":
                await self._apply_schema_map(session=session, model=model, payload=payload, lineage=lineage)
            elif candidate.candidate_type == "relationship":
                await self._apply_relationship(session=session, model=model, payload=payload, lineage=lineage)
            elif candidate.candidate_type == "data_truth":
                await self._apply_metric(session=session, model=model, payload=payload, lineage=lineage)
            applied_ids.append(candidate.id)

        await self._apply_dimensions_from_entities(session=session, model=model)
        review = json.loads(model.review_json or "{}")
        review["sourceUnderstandingLineage"] = lineage_entries
        model.review_json = _json_dump(review)
        model.validation_log_json = _json_dump(
            [
                f"Applied {len(applied_ids)} verified Source Understanding candidates.",
                *json.loads(model.validation_log_json or "[]"),
            ]
        )
        model.readiness = max(model.readiness, 55)
        model.readiness_level = "warning"
        session.add(
            SemanticModelAuditEvent(
                tenant_id=tenant_id,
                model_id=model.id,
                user_id=user_id,
                action="source_understanding_applied",
                details_json=_json_dump({"candidate_ids": [str(item) for item in applied_ids], "datasource_id": datasource_id}),
            )
        )
        await session.commit()
        refreshed = await SemanticModelService._load_model(session, tenant_id, model.slug)
        return {
            "model": SemanticModelService.model_to_payload(refreshed or model),
            "applied_candidate_ids": applied_ids,
            "lineage": {
                "datasource_id": datasource_id,
                "connection_id": str(connection.id),
                "candidates": lineage_entries,
            },
        }

    async def _resolve_connection(
        self,
        *,
        session: AsyncSession,
        datasource_id: str,
        tenant_id: UUID,
    ) -> Connection:
        try:
            parsed_id = UUID(str(datasource_id))
        except ValueError:
            raise ValueError("Datasource must be a database connection or connection-backed dataset")

        connection = await session.get(Connection, parsed_id)
        if connection is not None:
            if connection.tenant_id != tenant_id:
                raise ValueError("Datasource not found")
            return connection

        dataset = await session.get(Dataset, parsed_id)
        if dataset is None or dataset.tenant_id != tenant_id or dataset.type != "connection" or dataset.connection_id is None:
            raise ValueError("Datasource must be a database connection or connection-backed dataset")
        connection = await session.get(Connection, dataset.connection_id)
        if connection is None or connection.tenant_id != tenant_id:
            raise ValueError("Datasource connection not found")
        return connection

    async def _load_schema(
        self,
        *,
        session: AsyncSession,
        connection: Connection,
        refresh_schema: bool,
    ) -> dict[str, Any]:
        await session.refresh(connection)
        if refresh_schema or not connection.schema_cache:
            _, schema = await ConnectionService.refresh_connection_schema(str(connection.id), session)
            return schema
        cached = ConnectionService.get_cached_schema(connection)
        if cached:
            return cached
        _, schema = await ConnectionService.refresh_connection_schema(str(connection.id), session)
        return schema

    def _normalize_schema(
        self,
        *,
        connection: Connection,
        schema: dict[str, Any],
        scope: list[str],
    ) -> NormalizedDatabaseSchema:
        root = schema if isinstance(schema, dict) else {}
        raw_tables = root.get("schema") if isinstance(root.get("schema"), dict) else root
        datasource_type = str(root.get("datasource_type") or root.get("database_type") or connection.type)
        datasource_name = str(root.get("datasource_name") or root.get("database_name") or connection.name or connection.type)
        catalog = str(root.get("database_name") or root.get("datasource_name") or connection.name or connection.id)
        default_schema = str(root.get("selected_schema") or ("public" if connection.type == "pg" else datasource_type))
        wanted = {item.upper() for item in scope if item}

        tables: list[NormalizedTable] = []
        for table_name, table_info in sorted(raw_tables.items(), key=lambda item: str(item[0]).lower()):
            if wanted and str(table_name).upper() not in wanted:
                continue
            if not isinstance(table_info, dict):
                table_info = {"columns": table_info if isinstance(table_info, list) else []}
            table_schema = str(table_info.get("schema") or default_schema)
            columns = self._normalize_columns(table_info)
            primary_key = tuple(self._normalize_primary_key(table_info, columns))
            category = self._classify_table(str(table_name), columns, primary_key)
            sample_rows = tuple(row for row in table_info.get("sample_rows") or table_info.get("sample_data") or [] if isinstance(row, dict))
            table = NormalizedTable(
                catalog=catalog,
                schema=table_schema,
                name=str(table_name),
                table_type=str(table_info.get("type") or "table"),
                category=category,
                description=str(table_info.get("description") or table_info.get("comment") or ""),
                row_count=self._coerce_int(
                    table_info.get("row_count")
                    or table_info.get("rowCount")
                    or (table_info.get("profile") or {}).get("row_count")
                    or (table_info.get("stats") or {}).get("row_count")
                ),
                primary_key=primary_key,
                columns=tuple(columns),
                foreign_keys=(),
                indexes=tuple(item for item in table_info.get("indexes") or [] if isinstance(item, dict)),
                sample_rows=sample_rows,
            )
            tables.append(table)

        table_by_name = {table.name.lower(): table for table in tables}
        pk_by_table = {table.name.lower(): table.primary_key for table in tables}
        with_relationships = []
        for table in tables:
            table_info = raw_tables.get(table.name) if isinstance(raw_tables.get(table.name), dict) else {}
            relationships = self._normalize_relationships(table=table, table_info=table_info, table_by_name=table_by_name, pk_by_table=pk_by_table)
            with_relationships.append(
                NormalizedTable(
                    catalog=table.catalog,
                    schema=table.schema,
                    name=table.name,
                    table_type=table.table_type,
                    category=table.category,
                    description=table.description,
                    row_count=table.row_count,
                    primary_key=table.primary_key,
                    columns=table.columns,
                    foreign_keys=tuple(relationships),
                    indexes=table.indexes,
                    sample_rows=table.sample_rows,
                )
            )

        return NormalizedDatabaseSchema(
            datasource_name=datasource_name,
            datasource_type=datasource_type,
            catalog=catalog,
            schema=default_schema,
            tables=tuple(with_relationships),
            raw_schema=root,
        )

    def _normalize_columns(self, table_info: dict[str, Any]) -> list[NormalizedColumn]:
        raw_columns = table_info.get("columns") or []
        if isinstance(raw_columns, dict):
            raw_columns = [{"name": name, **(info if isinstance(info, dict) else {"type": str(info)})} for name, info in raw_columns.items()]
        columns: list[NormalizedColumn] = []
        for raw in raw_columns:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name") or raw.get("column_name") or "")
            if not name:
                continue
            data_type = str(raw.get("type") or raw.get("data_type") or raw.get("database_type") or "unknown")
            nullable = bool(raw.get("nullable", raw.get("is_nullable", True)))
            profile = {
                key: raw[key]
                for key in ("null_rate", "nullRate", "distinct_count", "distinctCount", "min", "max", "top_values", "topValues")
                if key in raw
            }
            columns.append(
                NormalizedColumn(
                    name=name,
                    data_type=data_type,
                    nullable=nullable,
                    role=self._classify_column(name, data_type),
                    description=str(raw.get("description") or raw.get("comment") or ""),
                    profile=profile,
                )
            )
        return columns

    def _normalize_primary_key(self, table_info: dict[str, Any], columns: list[NormalizedColumn]) -> list[str]:
        raw_pk = table_info.get("primary_key") or table_info.get("primaryKey") or table_info.get("pk") or []
        if isinstance(raw_pk, str):
            raw_pk = [raw_pk]
        if raw_pk:
            return [str(item) for item in raw_pk]
        id_columns = [column.name for column in columns if column.name.lower() in {"id", "uuid"} or column.name.lower().endswith("_id")]
        return id_columns[:1]

    def _normalize_relationships(
        self,
        *,
        table: NormalizedTable,
        table_info: dict[str, Any],
        table_by_name: dict[str, NormalizedTable],
        pk_by_table: dict[str, tuple[str, ...]],
    ) -> list[NormalizedRelationship]:
        relationships: list[NormalizedRelationship] = []
        for fk in table_info.get("foreign_keys") or table_info.get("foreignKeys") or []:
            if not isinstance(fk, dict):
                continue
            from_columns = fk.get("column") or fk.get("columns") or fk.get("constrained_columns") or fk.get("from")
            to_table = fk.get("ref_table") or fk.get("referred_table") or fk.get("foreign_table_name") or fk.get("to_table")
            to_columns = fk.get("ref_column") or fk.get("referred_columns") or fk.get("to")
            if isinstance(from_columns, str):
                from_columns = [from_columns]
            if isinstance(to_columns, str):
                to_columns = [to_columns]
            if not to_table:
                continue
            if not to_columns:
                to_columns = list(pk_by_table.get(str(to_table).lower(), ()))
            relationships.append(
                NormalizedRelationship(
                    from_table=table.name,
                    from_columns=tuple(str(item) for item in from_columns or []),
                    to_table=str(to_table),
                    to_columns=tuple(str(item) for item in to_columns or []),
                    source="explicit_fk",
                    confidence=0.95,
                    validation={
                        "status": "passed",
                        "method": "database_constraint",
                        "constraint_name": fk.get("constraint_name"),
                        "orphan_rate": fk.get("orphan_rate", 0),
                        "unique_rate": fk.get("unique_rate", 100),
                    },
                )
            )

        existing = {(rel.from_table.lower(), tuple(col.lower() for col in rel.from_columns), rel.to_table.lower()) for rel in relationships}
        for column in table.columns:
            lower = column.name.lower()
            if not lower.endswith("_id") or lower in {col.lower() for col in table.primary_key}:
                continue
            stem = lower[:-3]
            candidates = {stem, stem + "s", stem.replace("_", "") + "s"}
            for target_name, target in table_by_name.items():
                if target_name not in candidates:
                    continue
                target_pk = pk_by_table.get(target_name, ())
                key = (table.name.lower(), (lower,), target.name.lower())
                if key in existing:
                    break
                relationships.append(
                    NormalizedRelationship(
                        from_table=table.name,
                        from_columns=(column.name,),
                        to_table=target.name,
                        to_columns=target_pk[:1] or (column.name,),
                        source="name_match",
                        confidence=0.72,
                        validation={
                            "status": "warning",
                            "method": "column_name_match",
                            "message": "Needs sampled join validation before publishing.",
                            "orphan_rate": None,
                            "unique_rate": None,
                        },
                    )
                )
                break
        return relationships

    def _classify_column(self, name: str, data_type: str) -> str:
        lower = name.lower()
        type_lower = data_type.lower()
        if any(token in lower for token in ("email", "phone", "address", "ssn")):
            return "pii"
        if lower in {"id", "uuid"} or lower.endswith("_id"):
            return "id"
        if any(token in lower for token in ("date", "time", "_at", "month", "year")) or "date" in type_lower or "time" in type_lower:
            return "time"
        if any(token in lower for token in ("amount", "revenue", "price", "cost", "total", "target", "quantity")):
            return "measure" if "quantity" in lower else "amount"
        if any(token in lower for token in ("status", "state", "code", "type")):
            return "status"
        return "attribute"

    def _classify_table(self, table_name: str, columns: list[NormalizedColumn], primary_key: tuple[str, ...]) -> str:
        lower = table_name.lower()
        id_count = sum(1 for column in columns if column.role == "id")
        has_amount = any(column.role in {"amount", "measure"} for column in columns)
        has_time = any(column.role == "time" for column in columns)
        if any(token in lower for token in ("log", "event", "audit")):
            return "log"
        if any(token in lower for token in ("item", "bridge", "map", "link")) or id_count >= 3:
            return "bridge"
        if has_amount and has_time:
            return "fact"
        if any(token in lower for token in ("order", "sale", "refund", "target", "transaction")):
            return "fact"
        return "dimension" if primary_key else "unknown"

    def _build_candidates(self, normalized: NormalizedDatabaseSchema, evidence_by_table: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        table_by_name = {table.name: table for table in normalized.tables}
        for table in normalized.tables:
            evidence = evidence_by_table.get(table.name, {})
            table_evidence = [evidence.get("table"), *evidence.get("columns", []), *evidence.get("constraints", [])]
            table_evidence_ids = [str(item.id) for item in table_evidence if item is not None]
            fields = [
                {
                    "name": _snake(column.name),
                    "source_field": column.name,
                    "type": column.data_type,
                    "role": column.role,
                    "nullable": column.nullable,
                    "description": column.description,
                    "profile": column.profile or {},
                }
                for column in table.columns
            ]
            candidates.append(
                {
                    "table": table.name,
                    "candidate_type": "schema_map",
                    "title": f"Map {table.name} as {_display(table.category)} Entity",
                    "statement": f"{table.name} is classified as a {table.category} table with {len(table.columns)} columns.",
                    "structured_payload": {
                        "table": table.name,
                        "schema": table.schema,
                        "catalog": table.catalog,
                        "category": table.category,
                        "entity_slug": _snake(table.name),
                        "entity_name": _display(table.name),
                        "description": table.description or f"Source table {table.name}.",
                        "primary_key": list(table.primary_key),
                        "fields": fields,
                    },
                    "evidence_ids": table_evidence_ids,
                    "confidence": 0.88 if table.primary_key else 0.68,
                    "validation_status": "passed" if table.primary_key else "warning",
                    "validation": {
                        "status": "passed" if table.primary_key else "warning",
                        "checks": ["schema_present", "columns_present", "primary_key_detected" if table.primary_key else "primary_key_missing"],
                    },
                }
            )
            candidates.append(
                {
                    "table": table.name,
                    "candidate_type": "data_profile",
                    "title": f"Profile {table.name}",
                    "statement": f"{table.name} profile covers {len(table.columns)} columns and {len(table.sample_rows)} safe sample rows.",
                    "structured_payload": {
                        "table": table.name,
                        "row_count": table.row_count,
                        "column_count": len(table.columns),
                        "sample_rows": list(table.sample_rows[:5]),
                        "columns": fields,
                    },
                    "evidence_ids": [str(item.id) for item in [evidence.get("table"), evidence.get("sample")] if item is not None] + [str(item.id) for item in evidence.get("columns", [])],
                    "confidence": 0.86 if table.sample_rows or any(column.profile for column in table.columns) else 0.71,
                    "validation_status": "passed" if table.columns else "failed",
                    "validation": {"status": "passed" if table.columns else "failed", "sample_rows": len(table.sample_rows)},
                }
            )
            pii_columns = [column.name for column in table.columns if column.role == "pii"]
            nullable_pk = [column.name for column in table.columns if column.name in table.primary_key and column.nullable]
            missing_pk = not bool(table.primary_key)
            if pii_columns or nullable_pk or missing_pk:
                risks = []
                if pii_columns:
                    risks.append(f"PII columns detected: {', '.join(pii_columns)}")
                if nullable_pk:
                    risks.append(f"Primary key columns nullable: {', '.join(nullable_pk)}")
                if missing_pk:
                    risks.append("No primary key found in schema metadata")
                candidates.append(
                    {
                        "table": table.name,
                        "candidate_type": "quality_gotcha",
                        "title": f"Quality checks for {table.name}",
                        "statement": "; ".join(risks),
                        "structured_payload": {
                            "table": table.name,
                            "risks": risks,
                            "pii_columns": pii_columns,
                            "nullable_primary_key": nullable_pk,
                            "missing_primary_key": missing_pk,
                            "policy": "mask_pii_and_require_key_review",
                        },
                        "evidence_ids": table_evidence_ids,
                        "confidence": 0.93 if pii_columns else 0.76,
                        "validation_status": "warning",
                        "validation": {"status": "warning", "risk_count": len(risks)},
                    }
                )

            for column in table.columns:
                if column.role not in {"amount", "measure"}:
                    continue
                metric_slug = _snake(f"{table.name}_{column.name}")
                time_field = next((field.name for field in table.columns if field.role == "time"), "")
                candidates.append(
                    {
                        "table": table.name,
                        "candidate_type": "data_truth",
                        "title": f"Candidate metric: {_display(metric_slug)}",
                        "statement": f"Measure candidate from {table.name}.{column.name}; requires business review before publication.",
                        "structured_payload": {
                            "metric_slug": metric_slug,
                            "business_name": _display(metric_slug),
                            "definition": f"Sum of {table.name}.{column.name}.",
                            "kind": "measure",
                            "formula": f"SUM({_snake(table.name)}.{_snake(column.name)})",
                            "filter": "",
                            "time_field": f"{_snake(table.name)}.{_snake(time_field)}" if time_field else "",
                            "default_grain": "month",
                            "unit": "%" if "rate" in column.name.lower() else "",
                            "owner": "Data Team",
                            "lineage": [f"{table.name}.{column.name}"],
                        },
                        "evidence_ids": [str(item.id) for item in [evidence.get("table"), *evidence.get("columns", [])] if item is not None],
                        "confidence": 0.78,
                        "validation_status": "warning",
                        "validation": {"status": "warning", "reason": "Needs reviewer confirmation of business definition."},
                    }
                )

        for table in normalized.tables:
            evidence = evidence_by_table.get(table.name, {})
            for relationship in table.foreign_keys:
                target = table_by_name.get(relationship.to_table)
                confidence = relationship.confidence
                validation_status = "passed" if relationship.validation.get("status") == "passed" else "warning"
                candidates.append(
                    {
                        "table": table.name,
                        "candidate_type": "relationship",
                        "title": f"Join {table.name} to {relationship.to_table}",
                        "statement": f"{table.name}.{', '.join(relationship.from_columns)} joins to {relationship.to_table}.{', '.join(relationship.to_columns)} using {relationship.source} evidence.",
                        "structured_payload": {
                            "relationship_slug": _snake(f"{table.name}_{relationship.to_table}"),
                            "from_entity": _snake(table.name),
                            "to_entity": _snake(relationship.to_table),
                            "label": f"{_display(table.name)} -> {_display(relationship.to_table)}",
                            "join_fields": [
                                {"from": f"{table.name}.{src}", "to": f"{relationship.to_table}.{dst}"}
                                for src, dst in zip(relationship.from_columns, relationship.to_columns, strict=False)
                            ],
                            "cardinality": "many-to-one" if target and target.category == "dimension" else "one-to-many",
                            "fk_evidence": relationship.source,
                            "unique_rate": relationship.validation.get("unique_rate"),
                            "orphan_rate": relationship.validation.get("orphan_rate"),
                            "fanout_risk": "low" if target and target.category == "dimension" else "medium",
                        },
                        "evidence_ids": [str(item.id) for item in [evidence.get("table"), *evidence.get("constraints", [])] if item is not None],
                        "confidence": confidence,
                        "validation_status": validation_status,
                        "validation": relationship.validation,
                    }
                )

        return candidates

    async def _snapshot_resource(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        connection_id: UUID,
        resource_type: str,
        external_id: str,
        name: str,
        payload: dict[str, Any],
        previous_content_hash: str | None = None,
        drift_events: list[dict[str, Any]],
    ) -> tuple[SourceResource, SourceSnapshot]:
        previous_hash: str | None = previous_content_hash
        result = await session.execute(
            select(SourceResource).where(
                SourceResource.tenant_id == tenant_id,
                SourceResource.connection_id == connection_id,
                SourceResource.resource_type == resource_type,
                SourceResource.external_id == external_id,
            )
        )
        resource = result.scalar_one_or_none()
        if resource is None:
            result = await session.execute(
                select(SourceResource).where(
                    SourceResource.tenant_id == tenant_id,
                    SourceResource.resource_type == resource_type,
                    SourceResource.external_id == external_id,
                )
            )
            resource = result.scalar_one_or_none()
            if resource is not None and resource.connection_id is None:
                resource.connection_id = connection_id
        if resource is None:
            resource = SourceResource(
                tenant_id=tenant_id,
                connection_id=connection_id,
                resource_type=resource_type,
                name=name,
                external_id=external_id,
                visibility="workspace",
                sync_mode="manual",
                status="understanding",
            )
            session.add(resource)
            await session.flush()
        else:
            previous = await session.scalar(
                select(SourceSnapshot)
                .where(SourceSnapshot.resource_id == resource.id)
                .order_by(SourceSnapshot.captured_at.desc(), SourceSnapshot.id.desc())
            )
            previous_hash = previous_hash or (previous.content_hash if previous else None)

        content_hash = _json_hash(payload)
        snapshot = SourceSnapshot(
            tenant_id=tenant_id,
            resource_id=resource.id,
            external_revision=content_hash,
            content_hash=content_hash,
            raw_storage_uri=f"db://{connection_id}/{external_id}",
            parser_version=DATABASE_ANALYZER_VERSION,
            metadata_json=payload,
            status="indexed",
        )
        session.add(snapshot)
        await session.flush()
        resource.latest_snapshot_id = snapshot.id
        resource.status = "ready"
        if previous_hash and previous_hash != content_hash:
            drift_events.append(
                {
                    "resource_id": str(resource.id),
                    "resource_type": resource.resource_type,
                    "name": resource.name,
                    "previous_hash": previous_hash,
                    "current_hash": content_hash,
                }
            )
        return resource, snapshot

    async def _previous_snapshot_hashes(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        datasource_id: str,
    ) -> dict[str, str]:
        previous_run = await self._latest_run(session=session, datasource_id=datasource_id, tenant_id=tenant_id)
        if previous_run is None:
            return {}
        snapshot_ids: list[UUID] = []
        for value in previous_run.source_snapshot_ids_json or []:
            try:
                snapshot_ids.append(UUID(str(value)))
            except ValueError:
                continue
        if not snapshot_ids:
            return {}
        result = await session.execute(
            select(SourceSnapshot, SourceResource.external_id)
            .join(SourceResource, SourceSnapshot.resource_id == SourceResource.id)
            .where(
                SourceSnapshot.tenant_id == tenant_id,
                SourceSnapshot.id.in_(snapshot_ids),
                SourceResource.external_id.is_not(None),
            )
        )
        return {str(external_id): snapshot.content_hash for snapshot, external_id in result.all() if external_id}

    async def _create_knowledge_and_evidence(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        resource: SourceResource,
        snapshot: SourceSnapshot,
        fragments: list[dict[str, Any]],
    ) -> dict[str, Any]:
        knowledge_resource = KnowledgeResource(
            tenant_id=tenant_id,
            resource_id=resource.id,
            snapshot_id=snapshot.id,
            provider="database",
            provider_resource_id=resource.external_id,
            parse_status="parsed",
            index_status="indexed",
            completeness_score=0.9,
        )
        session.add(knowledge_resource)
        await session.flush()
        created: dict[str, Any] = {"columns": [], "constraints": []}
        for fragment in fragments:
            evidence = EvidenceFragment(
                tenant_id=tenant_id,
                knowledge_resource_id=knowledge_resource.id,
                snapshot_id=snapshot.id,
                fragment_type=fragment["fragment_type"],
                title_path=fragment.get("title_path"),
                text=fragment["text"],
                locator_json=fragment["locator_json"],
                confidence=fragment.get("confidence"),
                content_hash=_json_hash(fragment),
            )
            session.add(evidence)
            await session.flush()
            if fragment["fragment_type"] == "database_table":
                created["table"] = evidence
            elif fragment["fragment_type"] == "database_column":
                created["columns"].append(evidence)
            elif fragment["fragment_type"] == "database_constraint":
                created["constraints"].append(evidence)
            elif fragment["fragment_type"] == "database_sample":
                created["sample"] = evidence
            else:
                created.setdefault("other", []).append(evidence)
        return created

    def _table_evidence_fragments(
        self,
        *,
        datasource_id: str,
        connection_id: UUID,
        table: NormalizedTable,
    ) -> list[dict[str, Any]]:
        base_locator = {
            "datasource_id": datasource_id,
            "connection_id": str(connection_id),
            "catalog": table.catalog,
            "schema": table.schema,
            "table": table.name,
        }
        fragments = [
            {
                "fragment_type": "database_table",
                "title_path": [table.catalog, table.schema, table.name],
                "text": f"Table {table.name} has {len(table.columns)} columns, category {table.category}, and primary key {', '.join(table.primary_key) or 'not detected'}.",
                "locator_json": {"kind": "database_table", **base_locator},
                "confidence": "high" if table.primary_key else "medium",
            }
        ]
        for column in table.columns:
            fragments.append(
                {
                    "fragment_type": "database_column",
                    "title_path": [table.catalog, table.schema, table.name, column.name],
                    "text": f"Column {table.name}.{column.name} type {column.data_type}, nullable={column.nullable}, role={column.role}.",
                    "locator_json": {"kind": "database_column", **base_locator, "column": column.name},
                    "confidence": "high" if column.role in {"id", "time", "amount", "pii"} else "medium",
                }
            )
        if table.primary_key:
            fragments.append(
                {
                    "fragment_type": "database_constraint",
                    "title_path": [table.catalog, table.schema, table.name, "primary_key"],
                    "text": f"Primary key for {table.name}: {', '.join(table.primary_key)}.",
                    "locator_json": {"kind": "database_constraint", **base_locator, "constraint": "primary_key", "columns": list(table.primary_key)},
                    "confidence": "high",
                }
            )
        for relationship in table.foreign_keys:
            fragments.append(
                {
                    "fragment_type": "database_constraint",
                    "title_path": [table.catalog, table.schema, table.name, "foreign_key", relationship.to_table],
                    "text": f"Foreign key candidate {table.name}.{', '.join(relationship.from_columns)} -> {relationship.to_table}.{', '.join(relationship.to_columns)} from {relationship.source}.",
                    "locator_json": {
                        "kind": "database_constraint",
                        **base_locator,
                        "constraint": "foreign_key",
                        "columns": list(relationship.from_columns),
                        "ref_table": relationship.to_table,
                        "ref_columns": list(relationship.to_columns),
                    },
                    "confidence": "high" if relationship.source == "explicit_fk" else "medium",
                }
            )
        if table.sample_rows:
            fragments.append(
                {
                    "fragment_type": "database_sample",
                    "title_path": [table.catalog, table.schema, table.name, "sample"],
                    "text": f"Safe sample for {table.name} includes {len(table.sample_rows)} rows.",
                    "locator_json": {"kind": "database_sample", **base_locator, "row_count": len(table.sample_rows)},
                    "confidence": "medium",
                }
            )
        return fragments

    def _table_snapshot_payload(self, table: NormalizedTable) -> dict[str, Any]:
        return {
            "catalog": table.catalog,
            "schema": table.schema,
            "table": table.name,
            "type": table.table_type,
            "category": table.category,
            "description": table.description,
            "row_count": table.row_count,
            "primary_key": list(table.primary_key),
            "columns": [
                {
                    "name": column.name,
                    "type": column.data_type,
                    "nullable": column.nullable,
                    "role": column.role,
                    "description": column.description,
                    "profile": column.profile or {},
                }
                for column in table.columns
            ],
            "foreign_keys": [
                {
                    "from_columns": list(rel.from_columns),
                    "to_table": rel.to_table,
                    "to_columns": list(rel.to_columns),
                    "source": rel.source,
                    "validation": rel.validation,
                }
                for rel in table.foreign_keys
            ],
            "indexes": list(table.indexes),
            "sample_rows": list(table.sample_rows[:5]),
        }

    async def _latest_run(self, *, session: AsyncSession, datasource_id: str, tenant_id: UUID) -> SourceUnderstandingRun | None:
        result = await session.execute(
            select(SourceUnderstandingRun)
            .where(SourceUnderstandingRun.tenant_id == tenant_id, SourceUnderstandingRun.datasource_id == datasource_id)
            .order_by(
                SourceUnderstandingRun.completed_at.desc().nullslast(),
                SourceUnderstandingRun.created_at.desc(),
                SourceUnderstandingRun.id.desc(),
            )
        )
        return result.scalars().first()

    async def _list_database_resources(self, *, session: AsyncSession, connection_id: UUID, tenant_id: UUID) -> list[SourceResource]:
        result = await session.execute(
            select(SourceResource)
            .where(
                SourceResource.tenant_id == tenant_id,
                SourceResource.connection_id == connection_id,
                SourceResource.resource_type.in_(("database_catalog", "database_schema", "database_table")),
            )
            .order_by(SourceResource.resource_type.asc(), SourceResource.name.asc())
        )
        return list(result.scalars().all())

    async def _list_candidates(self, *, session: AsyncSession, run_id: UUID | None) -> list[SourceSkillCandidate]:
        if run_id is None:
            return []
        result = await session.execute(
            select(SourceSkillCandidate)
            .where(SourceSkillCandidate.run_id == run_id)
            .order_by(SourceSkillCandidate.candidate_type.asc(), SourceSkillCandidate.title.asc())
        )
        return list(result.scalars().all())

    async def _get_candidate(self, *, session: AsyncSession, candidate_id: str, tenant_id: UUID) -> SourceSkillCandidate | None:
        try:
            parsed = UUID(str(candidate_id))
        except ValueError:
            return None
        result = await session.execute(
            select(SourceSkillCandidate)
            .where(SourceSkillCandidate.id == parsed, SourceSkillCandidate.tenant_id == tenant_id)
            .options(selectinload(SourceSkillCandidate.run))
        )
        return result.scalar_one_or_none()

    async def _evidence_by_ids(
        self,
        *,
        session: AsyncSession,
        evidence_ids: set[str],
        tenant_id: UUID,
    ) -> list[EvidenceFragment]:
        parsed = []
        for evidence_id in evidence_ids:
            try:
                parsed.append(UUID(str(evidence_id)))
            except ValueError:
                continue
        if not parsed:
            return []
        result = await session.execute(
            select(EvidenceFragment).where(EvidenceFragment.tenant_id == tenant_id, EvidenceFragment.id.in_(parsed))
        )
        return list(result.scalars().all())

    async def _mark_previous_verified_stale(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        datasource_id: str,
        current_run_id: UUID,
    ) -> None:
        result = await session.execute(
            select(SourceSkillCandidate)
            .join(SourceUnderstandingRun, SourceSkillCandidate.run_id == SourceUnderstandingRun.id)
            .where(
                SourceSkillCandidate.tenant_id == tenant_id,
                SourceUnderstandingRun.datasource_id == datasource_id,
                SourceSkillCandidate.run_id != current_run_id,
                SourceSkillCandidate.review_status == "verified",
            )
        )
        for candidate in result.scalars().all():
            candidate.review_status = "stale"
            candidate.review_note = "Source drift detected in a newer analysis run."

    async def _verified_candidates(
        self,
        *,
        session: AsyncSession,
        datasource_id: str,
        tenant_id: UUID,
        candidate_ids: set[str],
    ) -> list[SourceSkillCandidate]:
        stmt = (
            select(SourceSkillCandidate)
            .join(SourceUnderstandingRun, SourceSkillCandidate.run_id == SourceUnderstandingRun.id)
            .where(
                SourceSkillCandidate.tenant_id == tenant_id,
                SourceUnderstandingRun.datasource_id == datasource_id,
                SourceSkillCandidate.review_status == "verified",
            )
            .order_by(SourceSkillCandidate.created_at.asc())
        )
        if candidate_ids:
            parsed = [UUID(item) for item in candidate_ids]
            stmt = stmt.where(SourceSkillCandidate.id.in_(parsed))
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def _apply_schema_map(
        self,
        *,
        session: AsyncSession,
        model: SemanticModel,
        payload: dict[str, Any],
        lineage: dict[str, Any],
    ) -> None:
        entity_slug = payload.get("entity_slug") or _snake(payload.get("table", "entity"))
        entity = await session.scalar(
            select(SemanticModelEntity)
            .where(SemanticModelEntity.model_id == model.id, SemanticModelEntity.slug == entity_slug)
            .options(selectinload(SemanticModelEntity.fields))
        )
        if entity is None:
            count = len(
                (
                    await session.execute(select(SemanticModelEntity.id).where(SemanticModelEntity.model_id == model.id))
                )
                .scalars()
                .all()
            )
            entity = SemanticModelEntity(
                model_id=model.id,
                slug=entity_slug,
                name=entity_slug,
                business_name=payload.get("entity_name") or _display(entity_slug),
                table_name=payload.get("table") or entity_slug,
                description=payload.get("description") or "",
                primary_key=", ".join(payload.get("primary_key") or []),
                entity_type=payload.get("category") or "dimension",
                validation_status="valid" if payload.get("primary_key") else "warning",
                profile_json=_json_dump(payload),
                lineage_json=_json_dump([lineage]),
                permission_json=_json_dump({"source_understanding": "verified"}),
                sort_order=count,
            )
            session.add(entity)
            await session.flush()
        else:
            entity.description = payload.get("description") or entity.description
            entity.lineage_json = _json_dump([*json.loads(entity.lineage_json or "[]"), lineage])

        existing_fields = {
            source_field.lower()
            for source_field in (
                await session.execute(
                    select(SemanticModelField.source_field).where(SemanticModelField.entity_id == entity.id)
                )
            )
            .scalars()
            .all()
        }
        for idx, field in enumerate(payload.get("fields") or []):
            source_field = field.get("source_field") or field.get("name")
            if not source_field:
                continue
            if source_field.lower() in existing_fields:
                continue
            session.add(
                SemanticModelField(
                    entity_id=entity.id,
                    name=field.get("name") or _snake(source_field),
                    source_field=source_field,
                    data_type=field.get("type") or "unknown",
                    role=field.get("role") or "attribute",
                    nullable=bool(field.get("nullable", True)),
                    profile_json=_json_dump(field.get("profile") or {}),
                    sort_order=idx,
                )
            )

    async def _apply_relationship(
        self,
        *,
        session: AsyncSession,
        model: SemanticModel,
        payload: dict[str, Any],
        lineage: dict[str, Any],
    ) -> None:
        slug = payload.get("relationship_slug") or _snake(payload.get("label", "relationship"))
        existing = await session.scalar(
            select(SemanticModelRelationship).where(
                SemanticModelRelationship.model_id == model.id,
                SemanticModelRelationship.slug == slug,
            )
        )
        if existing:
            existing.evidence_json = _json_dump([*json.loads(existing.evidence_json or "[]"), lineage])
            return
        count = len(
            (
                await session.execute(
                    select(SemanticModelRelationship.id).where(SemanticModelRelationship.model_id == model.id)
                )
            )
            .scalars()
            .all()
        )
        session.add(
            SemanticModelRelationship(
                model_id=model.id,
                slug=slug,
                from_entity=payload.get("from_entity") or "",
                to_entity=payload.get("to_entity") or "",
                label=payload.get("label") or _display(slug),
                join_fields_json=_json_dump(payload.get("join_fields") or []),
                cardinality=payload.get("cardinality") or "many-to-one",
                fk_evidence=payload.get("fk_evidence") or "verified_source_understanding",
                unique_rate=float(payload.get("unique_rate") or 0),
                orphan_rate=float(payload.get("orphan_rate") or 0),
                fanout_risk=payload.get("fanout_risk") or "medium",
                validation_status="valid",
                status="confirmed",
                validation_message="Created from verified Source Understanding evidence.",
                evidence_json=_json_dump([lineage]),
                sort_order=count,
            )
        )

    async def _apply_metric(
        self,
        *,
        session: AsyncSession,
        model: SemanticModel,
        payload: dict[str, Any],
        lineage: dict[str, Any],
    ) -> None:
        slug = payload.get("metric_slug") or _snake(payload.get("business_name", "metric"))
        existing = await session.scalar(
            select(SemanticModelMetric).where(
                SemanticModelMetric.model_id == model.id,
                SemanticModelMetric.slug == slug,
            )
        )
        if existing:
            existing.lineage_json = _json_dump([*json.loads(existing.lineage_json or "[]"), lineage])
            return
        count = len(
            (
                await session.execute(select(SemanticModelMetric.id).where(SemanticModelMetric.model_id == model.id))
            )
            .scalars()
            .all()
        )
        session.add(
            SemanticModelMetric(
                model_id=model.id,
                slug=slug,
                name=slug,
                business_name=payload.get("business_name") or _display(slug),
                definition=payload.get("definition") or "",
                kind=payload.get("kind") or "measure",
                formula=payload.get("formula") or "",
                filter_expr=payload.get("filter") or "",
                time_field=payload.get("time_field") or "",
                default_grain=payload.get("default_grain") or "month",
                dimensions_json="[]",
                unit=payload.get("unit") or "",
                owner=payload.get("owner") or "Data Team",
                certification="draft",
                lineage_json=_json_dump([lineage, *(payload.get("lineage") or [])]),
                preview_json=_json_dump({"validation": "Created from verified Source Understanding evidence."}),
                compiled_sql="",
                validation_status="warning",
                sort_order=count,
            )
        )

    async def _apply_dimensions_from_entities(self, *, session: AsyncSession, model: SemanticModel) -> None:
        existing = set(
            (
                await session.execute(select(SemanticModelDimension.slug).where(SemanticModelDimension.model_id == model.id))
            )
            .scalars()
            .all()
        )
        entities = (
            (
                await session.execute(
                    select(SemanticModelEntity)
                    .where(SemanticModelEntity.model_id == model.id)
                    .options(selectinload(SemanticModelEntity.fields))
                )
            )
            .scalars()
            .all()
        )
        for entity in entities:
            for field in entity.fields:
                if field.role not in {"attribute", "status", "time"}:
                    continue
                slug = _snake(f"{entity.slug}_{field.name}")
                if slug in existing:
                    continue
                existing.add(slug)
                session.add(
                    SemanticModelDimension(
                        model_id=model.id,
                        slug=slug,
                        name=_display(slug),
                        entity_slug=entity.slug,
                        field=field.name,
                        description=f"{field.name} from {entity.business_name}.",
                        sort_order=len(existing),
                    )
                )

    def _candidate_lineage(self, candidate: SourceSkillCandidate) -> dict[str, Any]:
        return {
            "candidate_id": str(candidate.id),
            "candidate_type": candidate.candidate_type,
            "source_resource_id": str(candidate.resource_id),
            "source_snapshot_id": str(candidate.snapshot_id),
            "evidence_ids": [str(item) for item in candidate.evidence_ids_json or []],
            "confidence": candidate.confidence,
            "validation": candidate.validation_json,
        }

    def _summary_payload(self, normalized: NormalizedDatabaseSchema, candidates: list[dict[str, Any]]) -> dict[str, Any]:
        candidate_counts: dict[str, int] = {}
        for candidate in candidates:
            candidate_counts[candidate["candidate_type"]] = candidate_counts.get(candidate["candidate_type"], 0) + 1
        return {
            "datasource_name": normalized.datasource_name,
            "datasource_type": normalized.datasource_type,
            "catalog": normalized.catalog,
            "schema": normalized.schema,
            "tables": len(normalized.tables),
            "columns": sum(len(table.columns) for table in normalized.tables),
            "relationships": sum(len(table.foreign_keys) for table in normalized.tables),
            "candidate_counts": candidate_counts,
            "readiness": min(95, 45 + len(normalized.tables) * 4 + candidate_counts.get("relationship", 0) * 3),
        }

    def _overview_payload(
        self,
        *,
        connection: Connection,
        latest_run: SourceUnderstandingRun | None,
        resources: list[SourceResource],
        candidates: list[SourceSkillCandidate],
    ) -> dict[str, Any]:
        verified = sum(1 for item in candidates if item.review_status == "verified")
        rejected = sum(1 for item in candidates if item.review_status == "rejected")
        suggested = sum(1 for item in candidates if item.review_status == "suggested")
        summary = latest_run.summary_json if latest_run else {}
        return {
            "connection_id": str(connection.id),
            "status": latest_run.status if latest_run else "not_analyzed",
            "resource_count": len(resources),
            "snapshot_count": len(latest_run.source_snapshot_ids_json) if latest_run else 0,
            "candidate_count": len(candidates),
            "verified_count": verified,
            "suggested_count": suggested,
            "rejected_count": rejected,
            "readiness": summary.get("readiness", 0),
            "last_analyzed_at": latest_run.completed_at.isoformat() if latest_run and latest_run.completed_at else None,
        }

    def _profile_payload(self, latest_run: SourceUnderstandingRun | None) -> dict[str, Any]:
        summary = latest_run.summary_json if latest_run else {}
        return {
            "table_count": summary.get("tables", 0),
            "column_count": summary.get("columns", 0),
            "relationship_count": summary.get("relationships", 0),
            "candidate_counts": summary.get("candidate_counts", {}),
        }

    def _quality_payload(self, candidates: list[SourceSkillCandidate]) -> dict[str, Any]:
        quality = [item for item in candidates if item.candidate_type == "quality_gotcha"]
        blockers = [item for item in quality if item.validation_status == "failed"]
        warnings = [item for item in quality if item.validation_status == "warning"]
        return {
            "blockers": len(blockers),
            "warnings": len(warnings),
            "items": [
                {
                    "id": str(item.id),
                    "title": item.title,
                    "statement": item.statement,
                    "review_status": item.review_status,
                }
                for item in quality
            ],
        }

    def _sync_drift_payload(self, latest_run: SourceUnderstandingRun | None) -> dict[str, Any]:
        if latest_run is None:
            return {"status": "not_analyzed", "events": []}
        return latest_run.drift_json or {"status": "stable", "events": []}

    def _run_to_payload(self, run: SourceUnderstandingRun | None) -> dict[str, Any] | None:
        if run is None:
            return None
        return {
            "id": run.id,
            "datasource_id": run.datasource_id,
            "connection_id": run.connection_id,
            "provider": run.provider,
            "status": run.status,
            "analyzer_version": run.analyzer_version,
            "source_snapshot_ids_json": run.source_snapshot_ids_json or [],
            "summary_json": run.summary_json or {},
            "drift_json": run.drift_json or {},
            "error_json": run.error_json,
            "created_at": run.created_at,
            "completed_at": run.completed_at,
        }

    def _resource_to_payload(self, resource: SourceResource) -> dict[str, Any]:
        return {
            "id": resource.id,
            "resource_type": resource.resource_type,
            "name": resource.name,
            "external_id": resource.external_id,
            "latest_snapshot_id": resource.latest_snapshot_id,
            "status": resource.status,
        }

    def _candidate_to_payload(self, candidate: SourceSkillCandidate, evidence: list[EvidenceFragment]) -> dict[str, Any]:
        return {
            "id": candidate.id,
            "run_id": candidate.run_id,
            "resource_id": candidate.resource_id,
            "snapshot_id": candidate.snapshot_id,
            "candidate_type": candidate.candidate_type,
            "title": candidate.title,
            "statement": candidate.statement,
            "structured_payload_json": candidate.structured_payload_json or {},
            "evidence_ids_json": candidate.evidence_ids_json or [],
            "evidence": [self._evidence_to_payload(item) for item in evidence],
            "confidence": candidate.confidence,
            "validation_status": candidate.validation_status,
            "validation_json": candidate.validation_json or {},
            "review_status": candidate.review_status,
            "reviewed_at": candidate.reviewed_at,
            "review_note": candidate.review_note,
            "created_at": candidate.created_at,
            "updated_at": candidate.updated_at,
        }

    def _evidence_to_payload(self, evidence: EvidenceFragment) -> dict[str, Any]:
        return {
            "id": evidence.id,
            "fragment_type": evidence.fragment_type,
            "title_path": evidence.title_path,
            "text": evidence.text,
            "locator_json": evidence.locator_json,
            "confidence": evidence.confidence,
        }

    def _coerce_int(self, value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
