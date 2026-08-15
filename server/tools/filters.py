"""Filter tools for dashboard dynamic filtering."""

import json
import re
from datetime import UTC, date, datetime
from typing import Any

from agents import function_tool
from agents.run_context import RunContextWrapper
from pydantic import BaseModel, Field

from server.auth.tenant_context import set_tenant_id
from server.db.session import get_async_session
from server.repositories.connections import ConnectionRepository
from server.repositories.notebooks import NotebookRepository
from server.repositories.queries import QueryRepository
from server.services.dataset import DatasetService
from server.services.file_operations import DataFrameFileService
from server.services.filter_config_service import (
    get_default_operator,
    harmonize_filter_definitions,
    infer_filter_type,
    normalize_filter_id,
    sync_query_filter_contracts,
)
from server.services.raw_query import AsyncRawQueryService
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)


FILTER_OPTIONS_TIMEOUT_SECONDS = 12
FILTER_OPERATOR_MAP = {
    "select": ["eq"],
    "multiselect": ["in"],
    "date_range": ["between", "gte", "lte"],
    "number_range": ["between", "gte", "lte"],
    "text": ["contains", "like"],
}


def _quote_sql_identifier(identifier: str, db_type: str) -> str:
    token = str(identifier or "").strip()
    if db_type == "mysql":
        return f"`{token.replace('`', '``')}`"
    if db_type == "mssql":
        return f"[{token.replace(']', ']]')}]"
    return f'"{token.replace(chr(34), chr(34) * 2)}"'


def _quote_sql_reference(reference: str, db_type: str) -> str:
    parts = [part.strip() for part in str(reference or "").split(".") if part.strip()]
    if not parts:
        return _quote_sql_identifier(reference, db_type)
    return ".".join(_quote_sql_identifier(part, db_type) for part in parts)


def _to_json_safe_option(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _normalize_options(raw_values: list[Any], limit: int) -> tuple[list[Any], int]:
    options: list[Any] = []
    null_count = 0
    seen: set[str] = set()

    for raw in raw_values:
        if raw is None:
            null_count += 1
            continue

        value = _to_json_safe_option(raw)
        if value is None:
            null_count += 1
            continue

        signature = json.dumps(value, sort_keys=True, default=str)
        if signature in seen:
            continue

        seen.add(signature)
        options.append(value)

        if len(options) >= limit:
            break

    return options, null_count


def _clean_filter_options(raw_options: Any) -> list[Any] | None:
    if not isinstance(raw_options, list):
        return None

    cleaned: list[Any] = []
    seen: set[str] = set()
    for option in raw_options:
        if isinstance(option, dict) and "label" in option and "value" in option:
            label = option.get("label")
            value = option.get("value")
            if label is None or value is None:
                continue
            if isinstance(label, str):
                label = label.strip()
            if isinstance(value, str):
                value = value.strip()
            if not label or not value:
                continue
            option_obj = {"label": label, "value": value}
            signature = json.dumps(option_obj, sort_keys=True, default=str)
            if signature in seen:
                continue
            seen.add(signature)
            cleaned.append(option_obj)
        else:
            value = _to_json_safe_option(option)
            if value is None:
                continue
            if isinstance(value, str):
                value = value.strip()
                if not value:
                    continue

            signature = json.dumps(value, sort_keys=True, default=str)
            if signature in seen:
                continue
            seen.add(signature)
            cleaned.append(value)

    return cleaned or None


def _normalize_filter_definition_payload(filter_definition: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(filter_definition)

    filter_type = str(normalized.get("filter_type", "")).strip().lower()
    operator = str(normalized.get("operator", "")).strip().lower()
    if filter_type:
        normalized["filter_type"] = filter_type
    if operator:
        normalized["operator"] = operator

    cleaned_options = _clean_filter_options(normalized.get("options"))
    if "options" in normalized:
        normalized["options"] = cleaned_options

    if filter_type in {"select", "multiselect"} and not cleaned_options:
        # Empty dropdown options render as blank choices in UI; degrade to text search.
        filter_type = "text"
        normalized["filter_type"] = "text"
        normalized["operator"] = "contains"
        normalized["options"] = None
    elif filter_type not in {"select", "multiselect"}:
        normalized["options"] = None

    valid_operators = FILTER_OPERATOR_MAP.get(filter_type, [])
    current_operator = str(normalized.get("operator", "")).lower()
    if valid_operators and current_operator not in valid_operators:
        normalized["operator"] = get_default_operator(filter_type)

    return normalized


def _timeout_fallback_filter_options_response(
    column_name: str,
    table_name: str,
    timeout_seconds: int,
) -> str:
    return json.dumps(
        {
            "success": True,
            "timed_out": True,
            "warning": (
                "Option discovery timed out. Falling back to text filter recommendation. "
                "Proceed with define_dashboard_filters using filter_type='text' and operator='contains'."
            ),
            "column": column_name,
            "table": table_name,
            "distinct_count": 0,
            "has_nulls": False,
            "null_count": 0,
            "data_type": "unknown",
            "options": [],
            "recommended_filter_type": "text",
            "recommended_operator": "contains",
            "timeout_seconds": timeout_seconds,
        }
    )


def _normalize_query_field_identity(filter_obj: dict[str, Any]) -> tuple[str, str]:
    query_id = str(filter_obj.get("query_id", "")).strip()
    field_name = str(filter_obj.get("field_name", "")).strip().lower()
    return query_id, field_name


def _generate_filter_id(filter_obj: dict[str, Any]) -> str:
    query_id = str(filter_obj.get("query_id", "")).strip()
    raw_field_name = str(filter_obj.get("field_name", "")).strip()
    if raw_field_name:
        return normalize_filter_id(query_id, raw_field_name)

    fallback_seed = re.sub(r"[^a-zA-Z0-9_]+", "_", query_id)[:12] or "field"
    return f"filter_{fallback_seed}"


def _upsert_filters_by_identity(
    existing_filters: list[dict[str, Any]],
    incoming_filters: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int, int]:
    """
    Merge incoming filters into existing filters using (query_id, field_name) identity.

    Returns: (merged_filters, created_count, updated_count)
    """
    merged: list[dict[str, Any]] = []
    identity_to_index: dict[tuple[str, str], int] = {}

    # Keep first occurrence of each identity from existing config.
    for item in existing_filters:
        if not isinstance(item, dict):
            continue
        identity = _normalize_query_field_identity(item)
        if not identity[0] or not identity[1]:
            continue
        if identity in identity_to_index:
            continue
        identity_to_index[identity] = len(merged)
        merged.append(dict(item))

    created_count = 0
    updated_count = 0

    for incoming in incoming_filters:
        if not isinstance(incoming, dict):
            continue
        identity = _normalize_query_field_identity(incoming)
        if not identity[0] or not identity[1]:
            continue

        incoming_copy = dict(incoming)
        if not incoming_copy.get("id"):
            incoming_copy["id"] = _generate_filter_id(incoming_copy)

        existing_index = identity_to_index.get(identity)
        if existing_index is None:
            identity_to_index[identity] = len(merged)
            merged.append(incoming_copy)
            created_count += 1
            continue

        existing_item = merged[existing_index]
        # Preserve stable ID to avoid breaking persisted filter values in the UI.
        stable_id = existing_item.get("id") or incoming_copy.get("id")
        merged_item = {**existing_item, **incoming_copy}
        merged_item["id"] = stable_id
        merged[existing_index] = merged_item
        updated_count += 1

    return merged, created_count, updated_count


def _apply_updates_to_filters_by_id(
    filters: list[dict[str, Any]],
    filter_id: str,
    updates: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    """Apply updates to all filters sharing the same logical filter_id."""
    updated_filters: list[dict[str, Any]] = []
    updated_count = 0

    for item in filters:
        if not isinstance(item, dict):
            continue
        next_item = dict(item)
        if next_item.get("id") == filter_id:
            next_item.update(updates)
            updated_count += 1
        updated_filters.append(next_item)

    return updated_filters, updated_count


class FilterDefinition(BaseModel):
    """Schema for defining a dashboard filter."""

    id: str | None = Field(
        None, description="Unique filter ID (e.g., 'filter_category'). Auto-generated if not provided."
    )
    query_id: str = Field(..., description="ID of saved query this filter applies to")
    field_name: str = Field(..., description="Source table column name to filter on (not aliases or aggregates)")
    display_label: str = Field(..., description="User-friendly label (e.g., 'Product Category')")
    filter_type: str = Field(
        ..., description="Filter UI type: 'select', 'multiselect', 'date_range', 'number_range', 'text'"
    )
    operator: str = Field(..., description="Filter operator: 'eq', 'in', 'between', 'like', 'gte', 'lte', 'contains'")
    options: list[str] | None = Field(None, description="List of values for select/multiselect filters")
    default_value: str | None = Field(None, description="Optional default value for the filter")


class FilterUpdate(BaseModel):
    """Schema for updating an existing filter."""

    display_label: str | None = Field(None, description="New display label")
    filter_type: str | None = Field(None, description="New filter type")
    operator: str | None = Field(None, description="New operator")
    options: list[str] | None = Field(None, description="New options list")
    default_value: str | None = Field(None, description="New default value")


@function_tool
async def get_filter_options(
    ctx: RunContextWrapper[Any],
    connection_id: str,
    table_name: str,
    column_name: str,
    limit: int = 100,
) -> str:
    """
    Get distinct values for a column to create a dropdown filter in the dashboard.

    Use this tool when:
    - Creating a dashboard and you want to add filter dropdowns for categorical columns
    - User asks to add a filter for a specific column (e.g., "add a category filter")
    - You need to know what options to show in a filter dropdown before generating filter UI

    This queries the database for DISTINCT values and provides recommendations.

    Args:
        connection_id: Database connection ID (from get_database_schema)
        table_name: Table name containing the column
        column_name: Column to get filter options for
        limit: Max options to return (default 100)

    Returns:
        JSON with:
        - options: array of distinct values (up to limit, excludes NULL/None)
        - distinct_count: total unique values (excluding NULLs)
        - has_nulls: boolean indicating if NULL values exist
        - null_count: count of NULL values found
        - data_type: Python type of the values
        - recommended_filter_type: suggested UI type (select/multiselect/date_range/number_range/text)
        - recommended_operator: correct operator for the filter_type (eq/in/between/contains)

    NOTE: NULL values are excluded from the options array but reported separately.
    If has_nulls is true, consider adding a "Show NULL values" checkbox in the UI.

    IMPORTANT: Use your semantic understanding to choose the best filter type:
    - The recommendation is based on data characteristics (count, type)
    - You should consider the column name and value semantics
    - Override the recommendation if it doesn't make sense for the data:
      * "status", "category", "type" columns → usually "select" or "multiselect"
      * "user_id", "order_id", numeric IDs → usually "text" search, not dropdown
      * "price", "amount", "quantity" → "number_range"
      * Boolean/binary values → "select" with 2 options
    """
    tenant_id = ctx.context.get("tenant_id")

    async for session in get_async_session():
        try:
            set_tenant_id(tenant_id)
            normalized_limit = max(1, min(int(limit or 100), 200))

            conn_repo = ConnectionRepository(session)
            connection = await conn_repo.get(connection_id)

            if not connection:
                datasets = await DatasetService.get_datasets_by_notebook(session, ctx.context.get("notebook_id"))
                for ds in datasets:
                    if str(ds.id) == connection_id:
                        quoted_column = _quote_sql_reference(column_name, "duckdb")
                        quoted_table = _quote_sql_reference(table_name, "duckdb")
                        query = f"SELECT DISTINCT {quoted_column} AS __value FROM {quoted_table} WHERE {quoted_column} IS NOT NULL"

                        connection_obj = {"dataset_id": str(ds.id), "dataset_type": "file", "db_type": "duckdb"}
                        result = await DataFrameFileService.execute_duckdb_query(
                            connection_obj,
                            query,
                            limit=normalized_limit,
                            timeout=FILTER_OPTIONS_TIMEOUT_SECONDS,
                        )
                        if result.get("timeout"):
                            return _timeout_fallback_filter_options_response(
                                column_name=column_name,
                                table_name=table_name,
                                timeout_seconds=FILTER_OPTIONS_TIMEOUT_SECONDS,
                            )
                        if not result.get("success"):
                            return json.dumps(
                                {
                                    "success": False,
                                    "error": result.get("error", "Failed to discover filter options"),
                                }
                            )

                        rows = result.get("result", [])
                        all_values = [row.get("__value") for row in rows if isinstance(row, dict)]
                        options, null_count = _normalize_options(all_values, normalized_limit)

                        recommended = infer_filter_type(options, column_name)
                        recommended_operator = get_default_operator(recommended)
                        return json.dumps(
                            {
                                "success": True,
                                "column": column_name,
                                "table": table_name,
                                "distinct_count": len(options),
                                "has_nulls": null_count > 0,
                                "null_count": null_count,
                                "data_type": type(options[0]).__name__ if options else "unknown",
                                "options": options,
                                "recommended_filter_type": recommended,
                                "recommended_operator": recommended_operator,
                            }
                        )

                return json.dumps({"success": False, "error": f"Connection '{connection_id}' not found"})

            db_type = connection.type.lower()
            connection_obj = await connection.get_decrypted_connection_obj(session)

            if not connection_obj:
                return json.dumps({"success": False, "error": "Failed to decrypt connection"})

            if db_type == "mongo":
                mongo_column = "_id" if column_name.lower() == "id" else column_name
                query = f"db.{table_name}.distinct('{mongo_column}')"
            else:
                quoted_column = _quote_sql_reference(column_name, db_type)
                quoted_table = _quote_sql_reference(table_name, db_type)
                query = (
                    f"SELECT DISTINCT {quoted_column} AS __value FROM {quoted_table} WHERE {quoted_column} IS NOT NULL"
                )

            result = await AsyncRawQueryService.execute_raw_query(
                query=query,
                db_type=db_type,
                connection_id=connection_id,
                connection_obj=connection_obj,
                limit=normalized_limit,
                timeout=FILTER_OPTIONS_TIMEOUT_SECONDS,
            )

            if result.get("timeout"):
                return _timeout_fallback_filter_options_response(
                    column_name=column_name,
                    table_name=table_name,
                    timeout_seconds=FILTER_OPTIONS_TIMEOUT_SECONDS,
                )

            if not result.get("success"):
                return json.dumps({"success": False, "error": result.get("error", "Query failed")})

            raw_result = result.get("result", [])

            if db_type == "mongo":
                all_values = raw_result if isinstance(raw_result, list) else []
                options, null_count = _normalize_options(all_values, normalized_limit)
            else:
                all_values = [row.get("__value") for row in raw_result if isinstance(row, dict)]
                options, null_count = _normalize_options(all_values, normalized_limit)

            recommended = infer_filter_type(options, column_name)
            recommended_operator = get_default_operator(recommended)

            return json.dumps(
                {
                    "success": True,
                    "column": column_name,
                    "table": table_name,
                    "distinct_count": len(options),
                    "has_nulls": null_count > 0,
                    "null_count": null_count,
                    "data_type": type(options[0]).__name__ if options else "unknown",
                    "options": options,
                    "recommended_filter_type": recommended,
                    "recommended_operator": recommended_operator,
                }
            )

        except Exception as e:
            logger.error(f"Error in get_filter_options: {e}", exc_info=True)
            return json.dumps({"success": False, "error": str(e)})

    return json.dumps({"success": False, "error": "Failed to get database session"})


@function_tool
async def define_dashboard_filters(ctx: RunContextWrapper[Any], filters_json: str) -> str:
    """
    Save filter configuration for the dashboard. Call this after get_filter_options.

    Use this tool when:
    - After calling get_filter_options, you need to save the filter definitions
    - Creating a dashboard with filter controls (dropdowns, date pickers)
    - User wants to add filters to an existing dashboard

    This stores the filter config in the notebook. Without calling this tool,
    filter UI will be cosmetic-only and won't actually filter data.

    IMPORTANT: Use the recommended_operator from get_filter_options response.
    Operator MUST match filter_type:
    - "select" → use "eq" operator
    - "multiselect" → use "in" operator
    - "date_range" / "number_range" → use "between", "gte", or "lte"
    - "text" → use "contains" or "like"

    Args:
        filters_json: JSON string with filter definitions. Examples:
            Single table: '[{"query_id": "uuid", "field_name": "category", "display_label": "Category",
              "filter_type": "select", "operator": "eq", "options": ["A", "B"]}]'
            JOIN query: '[{"query_id": "uuid", "field_name": "g.name", "display_label": "Genre",
              "filter_type": "select", "operator": "eq", "options": ["Rock", "Jazz"]}]'

            Required fields per filter:
            - query_id: ID of saved query this filter applies to
            - field_name: Source table column name (use table-qualified like "g.name" for JOINs, not SELECT aliases)
            - display_label: User-friendly label
            - filter_type: "select", "multiselect", "date_range", "number_range", or "text"
            - operator: Use the recommended_operator from get_filter_options
            - options: List of values for select/multiselect filters (optional for range/text)

    Returns:
        JSON with success status and created filter IDs
    """
    notebook_id = ctx.context.get("notebook_id")
    tenant_id = ctx.context.get("tenant_id")

    async for session in get_async_session():
        try:
            set_tenant_id(tenant_id)

            notebook_repo = NotebookRepository(session)
            query_repo = QueryRepository(session)
            notebook = await notebook_repo.get(notebook_id)

            if not notebook:
                return json.dumps({"success": False, "error": f"Notebook '{notebook_id}' not found"})

            active_query_rows = await query_repo.get_by_notebook_id(notebook_id)
            active_query_ids = {str(query_id) for query_id, _ in active_query_rows}

            previous_query_ids: set[str] = set()
            existing_filters: list[dict[str, Any]] = []
            existing_version = 1
            existing_created_at = datetime.now(UTC).isoformat()
            if notebook.filters_config:
                try:
                    previous_config = json.loads(notebook.filters_config)
                    existing_version = int(previous_config.get("version", 1) or 1)
                    existing_created_at = str(previous_config.get("created_at") or existing_created_at)
                    raw_existing_filters = previous_config.get("filters", [])
                    for old_filter in raw_existing_filters:
                        if isinstance(old_filter, dict) and old_filter.get("query_id"):
                            query_id = str(old_filter["query_id"])
                            previous_query_ids.add(query_id)
                            if query_id in active_query_ids:
                                existing_filters.append(old_filter)
                except json.JSONDecodeError:
                    previous_query_ids = set()
                    existing_filters = []

            try:
                filters = json.loads(filters_json)
            except json.JSONDecodeError as e:
                return json.dumps({"success": False, "error": f"Invalid JSON: {e}"})

            if not isinstance(filters, list):
                return json.dumps({"success": False, "error": "filters_json must be a JSON array"})

            normalized_filters = [_normalize_filter_definition_payload(f) for f in filters if isinstance(f, dict)]

            for f in normalized_filters:
                filter_type = f.get("filter_type")
                operator = f.get("operator")
                field_name = f.get("field_name", "unknown")

                if filter_type and operator:
                    valid_operators = FILTER_OPERATOR_MAP.get(filter_type, [])
                    if valid_operators and operator not in valid_operators:
                        return json.dumps(
                            {
                                "success": False,
                                "error": f"Invalid operator '{operator}' for filter_type '{filter_type}' on field '{field_name}'. "
                                f"Valid operators for '{filter_type}': {', '.join(valid_operators)}. "
                                f"Use the recommended_operator from get_filter_options response.",
                            }
                        )

            filters_list = []
            for f in normalized_filters:
                query_id = str(f.get("query_id", "")).strip()
                if not query_id or query_id not in active_query_ids:
                    continue
                if "id" not in f or not f["id"]:
                    f["id"] = _generate_filter_id(f)
                filters_list.append(dict(f))

            merged_filters, created_count, updated_count = _upsert_filters_by_identity(existing_filters, filters_list)
            merged_filters = harmonize_filter_definitions(merged_filters)

            filters_config = {
                "filters": merged_filters,
                "created_at": existing_created_at,
                "version": existing_version + 1,
            }

            notebook.filters_config = json.dumps(filters_config)
            new_query_ids = {str(f.get("query_id")) for f in merged_filters if f.get("query_id")}
            cleared_query_ids = previous_query_ids - new_query_ids
            updated_query_contracts = await sync_query_filter_contracts(
                session=session,
                filters_list=merged_filters,
                clear_query_ids=cleared_query_ids,
            )

            await session.commit()

            logger.info(
                "Defined dashboard filters for notebook %s (created=%s, updated=%s, total=%s)",
                notebook_id,
                created_count,
                updated_count,
                len(merged_filters),
            )

            return json.dumps(
                {
                    "success": True,
                    "message": (
                        f"Saved filters for dashboard "
                        f"(created {created_count}, updated {updated_count}, total {len(merged_filters)})"
                    ),
                    "filter_ids": [f["id"] for f in merged_filters if isinstance(f, dict) and f.get("id")],
                    "notebook_id": str(notebook_id),
                    "updated_query_contracts": updated_query_contracts,
                    "created_count": created_count,
                    "updated_count": updated_count,
                    "total_filters": len(merged_filters),
                }
            )

        except Exception as e:
            logger.error(f"Error in define_dashboard_filters: {e}", exc_info=True)
            return json.dumps({"success": False, "error": str(e)})

    return json.dumps({"success": False, "error": "Failed to get database session"})


@function_tool
async def update_dashboard_filter(ctx: RunContextWrapper[Any], filter_id: str, updates_json: str) -> str:
    """
    Update an existing filter's properties (label, type, options, etc.).

    Use this tool when:
    - User asks to change a filter's display label or options
    - You need to change the filter type (e.g., from select to multiselect)
    - Updating filter options after data changes

    Args:
        filter_id: ID of filter to update (e.g., "filter_category")
        updates_json: JSON object string with fields to update.
            Supported keys: display_label, filter_type, operator, options, default_value.

    Returns:
        JSON with success status and updated filter
    """
    notebook_id = ctx.context.get("notebook_id")
    tenant_id = ctx.context.get("tenant_id")

    async for session in get_async_session():
        try:
            set_tenant_id(tenant_id)

            notebook_repo = NotebookRepository(session)
            notebook = await notebook_repo.get(notebook_id)

            if not notebook:
                return json.dumps({"success": False, "error": f"Notebook '{notebook_id}' not found"})

            if not notebook.filters_config:
                return json.dumps({"success": False, "error": "No filters defined for this dashboard"})

            config = json.loads(notebook.filters_config)
            filters = config.get("filters", [])

            try:
                raw_updates = json.loads(updates_json)
            except json.JSONDecodeError as e:
                return json.dumps({"success": False, "error": f"Invalid updates_json: {e}"})

            if not isinstance(raw_updates, dict):
                return json.dumps({"success": False, "error": "updates_json must be a JSON object"})

            updates = FilterUpdate.model_validate(raw_updates)
            updates_dict = updates.model_dump(exclude_none=True)
            if not updates_dict:
                return json.dumps({"success": False, "error": "No valid update fields provided"})

            updated_filters, updated_count = _apply_updates_to_filters_by_id(filters, filter_id, updates_dict)
            updated_filters = [
                _normalize_filter_definition_payload(filter_obj)
                for filter_obj in updated_filters
                if isinstance(filter_obj, dict)
            ]

            if updated_count == 0:
                return json.dumps({"success": False, "error": f"Filter '{filter_id}' not found"})

            harmonized_filters = harmonize_filter_definitions(updated_filters)
            updated_filter = next((f for f in harmonized_filters if f.get("id") == filter_id), None)

            config["filters"] = harmonized_filters
            config["version"] = config.get("version", 1) + 1
            notebook.filters_config = json.dumps(config)
            updated_query_contracts = await sync_query_filter_contracts(
                session=session,
                filters_list=harmonized_filters,
            )
            await session.commit()

            logger.info(f"Updated filter {filter_id} for notebook {notebook_id}")

            return json.dumps(
                {
                    "success": True,
                    "message": f"Updated filter '{filter_id}'",
                    "filter": updated_filter,
                    "updated_count": updated_count,
                    "version": config["version"],
                    "updated_query_contracts": updated_query_contracts,
                }
            )

        except Exception as e:
            logger.error(f"Error in update_dashboard_filter: {e}", exc_info=True)
            return json.dumps({"success": False, "error": str(e)})

    return json.dumps({"success": False, "error": "Failed to get database session"})


@function_tool
async def remove_dashboard_filter(ctx: RunContextWrapper[Any], filter_id: str) -> str:
    """
    Remove a filter from the dashboard configuration.

    Use this tool when:
    - User asks to remove a specific filter from the dashboard
    - A filter is no longer needed or relevant

    Args:
        filter_id: ID of filter to remove (e.g., "filter_category")

    Returns:
        JSON with success status and count of remaining filters
    """
    notebook_id = ctx.context.get("notebook_id")
    tenant_id = ctx.context.get("tenant_id")

    async for session in get_async_session():
        try:
            set_tenant_id(tenant_id)

            notebook_repo = NotebookRepository(session)
            notebook = await notebook_repo.get(notebook_id)

            if not notebook:
                return json.dumps({"success": False, "error": f"Notebook '{notebook_id}' not found"})

            if not notebook.filters_config:
                return json.dumps({"success": False, "error": "No filters defined for this dashboard"})

            config = json.loads(notebook.filters_config)
            previous_query_ids = {
                str(f.get("query_id")) for f in config.get("filters", []) if isinstance(f, dict) and f.get("query_id")
            }
            original_count = len(config.get("filters", []))
            config["filters"] = [f for f in config.get("filters", []) if f.get("id") != filter_id]

            if len(config["filters"]) == original_count:
                return json.dumps({"success": False, "error": f"Filter '{filter_id}' not found"})

            config["version"] = config.get("version", 1) + 1
            config["filters"] = harmonize_filter_definitions(config.get("filters", []))
            notebook.filters_config = json.dumps(config)
            new_query_ids = {
                str(f.get("query_id")) for f in config.get("filters", []) if isinstance(f, dict) and f.get("query_id")
            }
            updated_query_contracts = await sync_query_filter_contracts(
                session=session,
                filters_list=config.get("filters", []),
                clear_query_ids=previous_query_ids - new_query_ids,
            )
            await session.commit()

            logger.info(f"Removed filter {filter_id} from notebook {notebook_id}")

            return json.dumps(
                {
                    "success": True,
                    "message": f"Removed filter '{filter_id}'",
                    "remaining_filters": len(config["filters"]),
                    "version": config["version"],
                    "updated_query_contracts": updated_query_contracts,
                }
            )

        except Exception as e:
            logger.error(f"Error in remove_dashboard_filter: {e}", exc_info=True)
            return json.dumps({"success": False, "error": str(e)})

    return json.dumps({"success": False, "error": "Failed to get database session"})


@function_tool
async def get_dashboard_filter_config(ctx: RunContextWrapper[Any]) -> str:
    """
    Get the current filter configuration saved for this dashboard.

    Use this tool when:
    - Checking what filters are already defined before adding new ones
    - Regenerating dashboard HTML and need to include existing filter definitions
    - User asks what filters are currently configured

    Returns:
        JSON with has_filters boolean, filters array, and version number
    """
    notebook_id = ctx.context.get("notebook_id")
    tenant_id = ctx.context.get("tenant_id")

    async for session in get_async_session():
        try:
            set_tenant_id(tenant_id)

            notebook_repo = NotebookRepository(session)
            notebook = await notebook_repo.get(notebook_id)

            if not notebook:
                return json.dumps({"success": False, "error": f"Notebook '{notebook_id}' not found"})

            if not notebook.filters_config:
                return json.dumps(
                    {
                        "success": True,
                        "has_filters": False,
                        "filters": [],
                        "message": "No filters defined for this dashboard",
                    }
                )

            config = json.loads(notebook.filters_config)
            filters = config.get("filters", [])

            return json.dumps(
                {
                    "success": True,
                    "has_filters": len(filters) > 0,
                    "filters": filters,
                    "version": config.get("version", 1),
                    "message": f"Found {len(filters)} filter(s)",
                }
            )

        except Exception as e:
            logger.error(f"Error in get_dashboard_filter_config: {e}", exc_info=True)
            return json.dumps({"success": False, "error": str(e)})

    return json.dumps({"success": False, "error": "Failed to get database session"})


def get_filter_tools() -> list:
    """Return all filter tools for registration."""
    return [
        get_filter_options,
        define_dashboard_filters,
        update_dashboard_filter,
        remove_dashboard_filter,
        get_dashboard_filter_config,
    ]
