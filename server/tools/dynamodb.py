"""DynamoDB tool for agents - supports PartiQL and Native API query modes."""

import json
import re
from typing import Any

from agents import function_tool
from agents.run_context import RunContextWrapper

from server.auth.tenant_context import set_tenant_id
from server.db.session import get_async_session
from server.repositories.connections import ConnectionRepository
from server.services.database_operations import AsyncDatabaseService, DatabaseOperationsService
from server.tools.plan_tools import check_plan_gate
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)

PARTIQL_WRITE_PATTERN = re.compile(r"^\s*(INSERT|UPDATE|DELETE)\b", re.IGNORECASE)

NATIVE_READ_OPERATIONS = {"get_item", "query", "scan", "batch_get_item", "describe_table"}


def is_partiql_write(statement: str) -> tuple[bool, str]:
    if PARTIQL_WRITE_PATTERN.match(statement):
        match = PARTIQL_WRITE_PATTERN.match(statement)
        keyword = match.group(1).upper() if match else "WRITE"
        return True, f"Write operation '{keyword}' is not allowed. Only SELECT statements are permitted."
    return False, ""


def is_native_write(query_spec: dict) -> tuple[bool, str]:
    operation = query_spec.get("operation", "").lower()
    if operation not in NATIVE_READ_OPERATIONS:
        allowed = ", ".join(sorted(NATIVE_READ_OPERATIONS))
        return True, f"Operation '{operation}' is not allowed. Only these read operations are permitted: {allowed}"
    return False, ""


def _infer_result_schema(items: list[dict]) -> dict[str, Any]:
    if not items:
        return {"type": "object", "properties": {}}

    merged_schema: dict[str, Any] | None = None
    for item in items:
        if isinstance(item, dict):
            schema_part = DatabaseOperationsService._infer_schema_from_value(item)
            merged_schema = (
                schema_part
                if merged_schema is None
                else DatabaseOperationsService._merge_json_schemas(merged_schema, schema_part)
            )

    return merged_schema or {"type": "object", "properties": {}}


@function_tool
async def execute_dynamodb_query(
    ctx: RunContextWrapper[Any],
    connection_id: str,
    query: str,
    limit: int = 5,
    timeout: int = 30,
) -> str:
    """
    Execute a DynamoDB read-only query. Supports both PartiQL and Native API modes based on connection configuration.

    IMPORTANT: This is a READ-ONLY tool. Write operations are strictly prohibited.

    Args:
        ctx: Run context wrapper
        connection_id: DynamoDB connection ID to use for query execution
        query: For PartiQL mode: SQL-like statement
               Examples:
               - SELECT * FROM "Users" WHERE "userId" = 'abc123'
               - SELECT "name", "email" FROM "Users"
               - SELECT * FROM "Orders" WHERE "status" = 'completed'
               For Native mode: JSON string with operation specification
               Examples:
               - {"operation": "scan", "table": "Users"}
               - {"operation": "query", "table": "Orders", "key_condition_expression": "userId = :uid", "expression_attribute_values": {":uid": {"S": "abc123"}}}
               - {"operation": "get_item", "table": "Users", "key": {"userId": {"S": "abc123"}}}
               - {"operation": "describe_table", "table": "Users"}
        limit: Maximum number of items to return (max 50)
        timeout: Query execution timeout in seconds (default 30)

    Returns:
        JSON string containing:
        - success: Boolean indicating if query executed successfully
        - data: Array of query results (on success)
        - schema: Inferred type schema (on success)
        - count: Number of items returned (on success)
        - error: Error message (on failure)
        - connection_id: Connection identifier used
    """
    if gate_error := check_plan_gate(ctx):
        return gate_error

    if limit > 50:
        limit = 50

    logger.info(
        f"Executing DynamoDB query with connection_id={connection_id}: {query[:100]}... (limit: {limit}, timeout: {timeout}s)"
    )

    async for session in get_async_session():
        try:
            tenant_id = ctx.context.get("tenant_id")
            set_tenant_id(tenant_id)
            conn_repo = ConnectionRepository(session)
            connection = await conn_repo.get(connection_id)

            if not connection:
                return json.dumps(
                    {
                        "success": False,
                        "error": f"Connection with ID '{connection_id}' not found",
                        "connection_id": connection_id,
                    },
                    indent=2,
                )

            if connection.type.lower() != "dynamodb":
                return json.dumps(
                    {
                        "success": False,
                        "error": f"Connection '{connection_id}' is not a DynamoDB connection (type: {connection.type})",
                        "connection_id": connection_id,
                    },
                    indent=2,
                )

            connection_obj = await connection.get_decrypted_connection_obj(session)

            if not connection_obj:
                return json.dumps(
                    {
                        "success": False,
                        "error": "Failed to decrypt connection credentials",
                        "connection_id": connection_id,
                    },
                    indent=2,
                )
        finally:
            await session.close()
        break

    try:
        query_mode = connection_obj.get("query_mode", "partiql")

        if query_mode == "partiql":
            is_write, reason = is_partiql_write(query)
            if is_write:
                return json.dumps(
                    {"success": False, "error": reason, "connection_id": connection_id},
                    indent=2,
                )

            redaction_rules = ctx.context.get("redaction_rules", {})
            conn_rules = redaction_rules.get(connection_id, {})
            if conn_rules:
                redacted_tables = set(conn_rules.get("tables", []))
                for table in redacted_tables:
                    if re.search(rf"\b{re.escape(table)}\b", query, re.IGNORECASE):
                        return json.dumps(
                            {
                                "success": False,
                                "error": "Access denied: this table is restricted and cannot be queried",
                                "connection_id": connection_id,
                            },
                            indent=2,
                        )

            connector = await AsyncDatabaseService.get_or_create_dynamodb_connector(connection_id, connection_obj)
            result = await connector.execute_partiql_query(query, limit=limit, timeout=timeout)

        else:
            try:
                query_spec = json.loads(query)
            except json.JSONDecodeError:
                return json.dumps(
                    {
                        "success": False,
                        "error": "Invalid JSON query specification for native mode. Expected JSON object with 'operation' and 'table' fields.",
                        "connection_id": connection_id,
                    },
                    indent=2,
                )

            is_write, reason = is_native_write(query_spec)
            if is_write:
                return json.dumps(
                    {"success": False, "error": reason, "connection_id": connection_id},
                    indent=2,
                )

            table_name = query_spec.get("table", "")
            redaction_rules = ctx.context.get("redaction_rules", {})
            conn_rules = redaction_rules.get(connection_id, {})
            if conn_rules:
                redacted_tables = set(conn_rules.get("tables", []))
                if table_name in redacted_tables:
                    return json.dumps(
                        {
                            "success": False,
                            "error": "Access denied: this table is restricted and cannot be queried",
                            "connection_id": connection_id,
                        },
                        indent=2,
                    )

            connector = await AsyncDatabaseService.get_or_create_dynamodb_connector(connection_id, connection_obj)
            result = await connector.execute_native_query(query_spec, limit=limit, timeout=timeout)

        if result.get("success"):
            items = result.get("result", [])

            redaction_rules = ctx.context.get("redaction_rules", {})
            conn_rules = redaction_rules.get(connection_id, {})
            if conn_rules:
                from server.services.redaction_service import RedactionService

                redacted_cols = {t: set(cols) for t, cols in conn_rules.get("columns", {}).items()}
                redacted_tbls = set(conn_rules.get("tables", []))
                if redacted_cols or redacted_tbls:
                    items = RedactionService.redact_result_rows(items, redacted_cols, redacted_tbls, table_name="")

            item_count = len(items) if isinstance(items, list) else 1
            inferred_schema = _infer_result_schema(items if isinstance(items, list) else [])

            response = {
                "success": True,
                "data": items,
                "schema": inferred_schema,
                "count": item_count,
                "connection_id": connection_id,
                "query_mode": query_mode,
            }
            return json.dumps(response, indent=2, default=str)
        else:
            return json.dumps(
                {
                    "success": False,
                    "error": f"Error executing DynamoDB query: {result.get('error', 'Unknown error')}",
                    "connection_id": connection_id,
                },
                indent=2,
            )

    except Exception as e:
        logger.error(f"DynamoDB query execution error: {str(e)}", exc_info=True)
        return json.dumps(
            {
                "success": False,
                "error": f"Error executing DynamoDB query: {str(e)}",
                "query": query[:100] + "..." if len(query) > 100 else query,
                "connection_id": connection_id,
            },
            indent=2,
        )


def get_dynamodb_tools():
    return [execute_dynamodb_query]
