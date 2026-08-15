"""MongoDB tool for agents - supports both sync and async operations."""

import json
from typing import Any

from agents import function_tool
from agents.run_context import RunContextWrapper

from server.auth.tenant_context import set_tenant_id
from server.db.session import get_async_session
from server.repositories.connections import ConnectionRepository
from server.services.database_operations import (
    AsyncDatabaseService,
    DatabaseOperationsService,
    MongoConnector,
)
from server.tools.plan_tools import check_plan_gate
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)


def is_write_operation(query_data: Any) -> tuple[bool, str]:
    write_operators = {
        "$set",
        "$unset",
        "$inc",
        "$dec",
        "$mul",
        "$rename",
        "$min",
        "$max",
        "$currentDate",
        "$addToSet",
        "$pop",
        "$pull",
        "$pullAll",
        "$push",
        "$pushAll",
        "$each",
        "$slice",
        "$sort",
        "$position",
        "$bit",
        "$[",
        "$[]",
        "$out",
        "$merge",
        "$mod",
    }

    def check_dict(data: dict, path: str = "") -> tuple[bool, str]:
        for key, value in data.items():
            current_path = f"{path}.{key}" if path else key

            if key in write_operators:
                return True, f"Write operation detected: '{key}' at {current_path}"
            if isinstance(value, dict):
                is_write, reason = check_dict(value, current_path)
                if is_write:
                    return is_write, reason
            elif isinstance(value, list):
                is_write, reason = check_list(value, current_path)
                if is_write:
                    return is_write, reason

        return False, ""

    def check_list(data: list, path: str = "") -> tuple[bool, str]:
        for i, item in enumerate(data):
            current_path = f"{path}[{i}]"

            if isinstance(item, dict):
                is_write, reason = check_dict(item, current_path)
                if is_write:
                    return is_write, reason
            elif isinstance(item, list):
                is_write, reason = check_list(item, current_path)
                if is_write:
                    return is_write, reason

        return False, ""

    try:
        if isinstance(query_data, str):
            query_lower = query_data.lower()
            write_patterns = ["$set", "$unset", "$inc", "$push", "$pull", "$addtoset", "$rename", "$out", "$merge"]
            for pattern in write_patterns:
                if pattern in query_lower:
                    return True, f"Write operation detected in query string: '{pattern}'"
            try:
                query_data = json.loads(query_data)
            except json.JSONDecodeError:
                return False, ""
        if isinstance(query_data, dict):
            return check_dict(query_data)
        elif isinstance(query_data, list):
            return check_list(query_data)

        return False, ""

    except Exception as e:
        return True, f"Could not validate query safety: {str(e)}"


def _infer_result_schema(documents: list[dict]) -> dict[str, Any]:
    """
    Infer schema from query result documents.

    Args:
        documents: List of MongoDB documents

    Returns:
        Inferred schema with field types
    """
    if not documents:
        return {"type": "object", "properties": {}}

    merged_schema: dict[str, Any] | None = None
    for doc in documents:
        if isinstance(doc, dict):
            schema_part = DatabaseOperationsService._infer_schema_from_value(doc)
            merged_schema = (
                schema_part
                if merged_schema is None
                else DatabaseOperationsService._merge_json_schemas(merged_schema, schema_part)
            )

    return merged_schema or {"type": "object", "properties": {}}


@function_tool
async def execute_mongo_query(
    ctx: RunContextWrapper[Any],
    connection_id: str,
    query: str,
    limit: int = 5,
    timeout: int = 30,
) -> str:
    """
    Execute a MongoDB read-only query using standard MongoDB query syntax.

    IMPORTANT: This is a READ-ONLY tool. Only read operations are allowed (find, findOne, count,
    countDocuments, estimatedDocumentCount, distinct, aggregate). Write operations are strictly prohibited.

    Args:
        ctx: Run context wrapper
        connection_id: MongoDB connection ID to use for query execution
        query: Raw MongoDB query string in standard MongoDB syntax
               Examples:
               - db.inventory.find({})
               - db.users.findOne({_id: ObjectId("507f1f77bcf86cd799439011")})
               - db.products.find({category: "electronics"}).limit(3)
               - db.orders.count({status: "completed"})
               - db.faqs.aggregate([{$match: {category: "Account"}}])
        limit: Maximum number of documents to return (max 50 for testing)
        timeout: Query execution timeout in seconds (default 30)

    Returns:
        JSON string containing:
        - success: Boolean indicating if query executed successfully
        - data: Array of query results (on success)
        - schema: Inferred type schema with BSON types (objectId, date, string, etc.) (on success)
        - count: Number of documents returned (on success)
        - timeout: Boolean indicating if query timed out (on timeout)
        - timeout_seconds: Configured timeout value (on timeout)
        - execution_time_seconds: Actual execution time before timeout (on timeout)
        - error: Error message (on failure)
        - connection_id: Connection identifier used
        - Additional context fields based on the operation
    """
    if gate_error := check_plan_gate(ctx):
        return gate_error

    # Enforce maximum limit to prevent context overflow
    if limit > 50:
        limit = 50

    logger.info(
        f"Executing MongoDB query with connection_id={connection_id}: {query[:100]}... (limit: {limit}, timeout: {timeout}s)"
    )

    # Fetch connection from database using connection_id
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

            # Verify it's a MongoDB connection
            if connection.type.lower() != "mongo":
                return json.dumps(
                    {
                        "success": False,
                        "error": f"Connection '{connection_id}' is not a MongoDB connection (type: {connection.type})",
                        "connection_id": connection_id,
                    },
                    indent=2,
                )

            # Get decrypted connection object
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

        # Continue with query execution outside session
        break

    try:
        # Parse the MongoDB query using MongoConnector (same as raw-query endpoint)
        temp_connector = MongoConnector(connection_obj)
        parsed = temp_connector._parse_query(query.strip())

        if not parsed:
            return json.dumps(
                {
                    "success": False,
                    "error": "Failed to parse MongoDB query. Please check your query syntax.",
                    "query": query[:100] + "..." if len(query) > 100 else query,
                    "connection_id": connection_id,
                },
                indent=2,
            )

        if parsed.get("error"):
            return json.dumps(
                {
                    "success": False,
                    "error": parsed["error"],
                    "query": query[:100] + "..." if len(query) > 100 else query,
                    "connection_id": connection_id,
                },
                indent=2,
            )

        # Check if it's a write operation
        if parsed.get("is_write_operation"):
            blocked_stage = parsed.get("blocked_stage")
            if blocked_stage:
                return json.dumps(
                    {
                        "success": False,
                        "error": f"Write operations are not allowed (blocked stage: {blocked_stage}). This is a read-only tool.",
                        "operation": parsed.get("operation"),
                        "blocked_stage": blocked_stage,
                        "connection_id": connection_id,
                    },
                    indent=2,
                )
            else:
                return json.dumps(
                    {
                        "success": False,
                        "error": f"Write operation '{parsed['operation']}' is not allowed. This is a read-only tool.",
                        "operation": parsed.get("operation"),
                        "connection_id": connection_id,
                    },
                    indent=2,
                )

        # Validate that operation is a read operation
        operation = parsed["operation"]
        if operation not in MongoConnector.READ_OPERATIONS:
            allowed_ops = ", ".join(sorted(MongoConnector.READ_OPERATIONS))
            return json.dumps(
                {
                    "success": False,
                    "error": f"Operation '{operation}' is not allowed. Only these read operations are permitted: {allowed_ops}",
                    "operation": operation,
                    "allowed_operations": sorted(MongoConnector.READ_OPERATIONS),
                    "connection_id": connection_id,
                },
                indent=2,
            )

        # Extract parsed components
        collection_name = parsed["collection"]
        args = parsed.get("args", [])
        modifiers = parsed.get("modifiers") or []

        # Block queries against redacted collections/columns
        redaction_rules = ctx.context.get("redaction_rules", {})
        conn_rules = redaction_rules.get(connection_id, {})
        if conn_rules:
            redacted_tables = set(conn_rules.get("tables", []))
            if collection_name in redacted_tables:
                return json.dumps(
                    {
                        "success": False,
                        "error": "Access denied: this collection is restricted and cannot be queried",
                        "connection_id": connection_id,
                        "collection": collection_name,
                    },
                    indent=2,
                )
            if operation == "distinct" and args:
                redacted_cols = conn_rules.get("columns", {})
                redacted_col_names = set(redacted_cols.get(collection_name, []))
                field_name = args[0] if isinstance(args[0], str) else str(args[0])
                if field_name in redacted_col_names:
                    return json.dumps(
                        {
                            "success": False,
                            "error": f"Access denied: field '{field_name}' is restricted and cannot be queried",
                            "connection_id": connection_id,
                            "collection": collection_name,
                        },
                        indent=2,
                    )

        # Use async connector for execution
        async_connector = await AsyncDatabaseService.get_or_create_mongo_connector(connection_id, connection_obj)

        # Execute query with limit and timeout
        result = await async_connector.execute_query(
            collection_name,
            operation,
            args,
            limit=limit,
            modifiers=modifiers,
            timeout=timeout,
        )

        if result.get("success"):
            documents = result.get("result", [])

            redaction_rules = ctx.context.get("redaction_rules", {})
            conn_rules = redaction_rules.get(connection_id, {})
            if conn_rules:
                from server.services.redaction_service import RedactionService

                redacted_cols = {t: set(cols) for t, cols in conn_rules.get("columns", {}).items()}
                redacted_tbls = set(conn_rules.get("tables", []))
                if redacted_cols or redacted_tbls:
                    documents = RedactionService.redact_result_rows(
                        documents, redacted_cols, redacted_tbls, table_name=collection_name
                    )

            doc_count = len(documents) if isinstance(documents, list) else 1
            print(f"[LOG: ✅ MongoDB query executed successfully, returned {doc_count} documents]")

            # Infer schema from returned documents for better AI understanding
            inferred_schema = _infer_result_schema(documents if isinstance(documents, list) else [])

            # Return both data and schema with success flag
            response = {
                "success": True,
                "data": documents,
                "schema": inferred_schema,
                "count": doc_count,
                "connection_id": connection_id,
                "collection": collection_name,
                "operation": operation,
            }
            return json.dumps(response, indent=2)
        else:
            return json.dumps(
                {
                    "success": False,
                    "error": f"Error executing MongoDB query: {result.get('error', 'Unknown error')}",
                    "connection_id": connection_id,
                    "collection": collection_name,
                    "operation": operation,
                },
                indent=2,
            )

    except Exception as e:
        logger.error(
            f"MongoDB query execution error: {str(e)}",
            exc_info=True,
            posthog_context={
                "function": "execute_mongo_query",
                "query_preview": query[:100] if query else None,
                "limit": limit,
                "connection_id": connection_id,
            },
        )
        return json.dumps(
            {
                "success": False,
                "error": f"Error executing MongoDB query: {str(e)}",
                "query": query[:100] + "..." if len(query) > 100 else query,
                "limit": limit,
                "connection_id": connection_id,
            },
            indent=2,
        )


def get_mongo_tools():
    """Get MongoDB tools for agents with improved parameter handling."""
    return [execute_mongo_query]
