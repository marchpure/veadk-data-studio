"""SQL tool for agents - supports both sync and async operations."""

import json
from typing import Any

import sqlglot
from agents import function_tool
from agents.run_context import RunContextWrapper
from sqlglot import exp

from server.auth.tenant_context import set_tenant_id
from server.db.session import get_async_session
from server.repositories.connections import ConnectionRepository
from server.services.database_operations import AsyncDatabaseService
from server.tools.plan_tools import check_plan_gate
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)

# Disallowed SQL operations - only read operations are permitted
DISALLOWED_NODES = (
    exp.Delete,
    exp.Insert,
    exp.Update,
    exp.Create,
    exp.Alter,
    exp.Drop,
    exp.TruncateTable,
    exp.Grant,
    exp.Command,
)

# Dialect mapping for sqlglot
DIALECT_MAP = {
    "pg": "postgres",
    "mysql": "mysql",
    "sqlite": None,  # SQLite uses standard SQL, no specific dialect needed
    "mssql": "tsql",  # SQL Server / T-SQL
    "oracle": "oracle",
}


def validate_sql_query(query: str, dialect: str = None) -> str:
    """
    Validate SQL query to ensure it's safe (read-only).

    Args:
        query: SQL query to validate
        dialect: SQL dialect (postgres, mysql, sqlite, tsql)

    Returns:
        Validated and processed query

    Raises:
        ValueError: If query contains disallowed operations
    """
    try:
        # Preprocess the query to handle escaped characters and formatting
        processed_query = query.replace("\\n", "\n").replace("\\t", "\t").strip()

        # Remove trailing semicolon if present
        if processed_query.endswith(";"):
            processed_query = processed_query[:-1].strip()

        if not processed_query:
            raise ValueError("Query is empty")

        # Parse with the appropriate dialect for accurate validation
        expressions = sqlglot.parse(processed_query, dialect=dialect)

        for tree in expressions:
            for disallowed in DISALLOWED_NODES:
                if isinstance(tree, disallowed) or tree.find(disallowed):
                    raise ValueError(
                        f"🚨 Unsafe query detected: {disallowed.__name__.upper()} is not allowed. "
                        f"Only read-only queries (SELECT) are permitted."
                    )
            if not isinstance(tree, (exp.Select, exp.Union, exp.With)):
                raise ValueError("🚨 Unsafe query detected: only read-only SELECT queries are permitted.")

        return processed_query

    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"❌ SQL parsing failed: {str(e)}")


@function_tool
async def execute_sql_query(
    ctx: RunContextWrapper[Any], connection_id: str, query: str, limit: int = 5, timeout: int = 30
) -> str:
    """
    Execute a SQL query with automatic limit for testing (supports PostgreSQL, MySQL, SQLite, MSSQL)

    Args:
        ctx: Run context wrapper
        connection_id: Database connection ID to use for query execution
        query: SQL query to execute (without LIMIT clause for testing)
        limit: Maximum number of rows to return for testing (max 50, default 5)
        timeout: Query execution timeout in seconds (default 30)

    Returns:
        JSON string containing:
        - success: Boolean indicating if query executed successfully
        - result: Array of rows returned (on success)
        - columns: Column names (on success)
        - row_count: Number of rows returned (on success)
        - limited: Boolean indicating if limit was applied (on success)
        - timeout: Boolean indicating if query timed out (on timeout)
        - timeout_seconds: Configured timeout value (on timeout)
        - execution_time_seconds: Actual execution time before timeout (on timeout)
        - error: Error message (on failure)
        - connection_id: Connection identifier used
        - db_type: Database type (pg, mysql, sqlite, mssql)
        - Additional context fields based on the operation
    """
    if gate_error := check_plan_gate(ctx):
        return gate_error

    # Enforce maximum limit to prevent context overflow
    if limit > 50:
        limit = 50

    logger.info(
        f"Executing SQL with connection_id={connection_id}, limit={limit}, timeout={timeout}s: {query[:100]}..."
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

            # Get database type from connection
            db_type = connection.type.lower()

            # Get decrypted connection object
            connection_obj = await connection.get_decrypted_connection_obj(session)

            if not connection_obj:
                return json.dumps(
                    {
                        "success": False,
                        "error": "Failed to decrypt connection credentials",
                        "connection_id": connection_id,
                        "db_type": db_type,
                    },
                    indent=2,
                )
        finally:
            await session.close()

        # Continue with query execution outside session
        break

    try:
        # Get the correct SQL dialect for validation
        dialect = DIALECT_MAP.get(db_type)

        # Validate query using sqlglot to ensure it's read-only
        try:
            validated_query = validate_sql_query(query, dialect=dialect)
        except ValueError as e:
            return json.dumps(
                {
                    "success": False,
                    "error": str(e),
                    "query": query[:100] + "..." if len(query) > 100 else query,
                    "connection_id": connection_id,
                    "db_type": db_type,
                },
                indent=2,
            )

        # Block queries against redacted tables and columns
        redaction_rules = ctx.context.get("redaction_rules", {})
        conn_rules = redaction_rules.get(connection_id, {})
        queried_tables: set[str] = set()
        if conn_rules:
            redacted_tables = set(conn_rules.get("tables", []))
            redacted_col_map = conn_rules.get("columns", {})
            try:
                parsed_expressions = sqlglot.parse(validated_query, dialect=dialect)
                for tree in parsed_expressions:
                    for tbl in tree.find_all(exp.Table):
                        queried_tables.add(tbl.name)
            except Exception:
                pass

            for tbl_name in queried_tables:
                if tbl_name in redacted_tables:
                    return json.dumps(
                        {
                            "success": False,
                            "error": f"Access denied: table '{tbl_name}' is restricted and cannot be queried",
                            "connection_id": connection_id,
                            "db_type": db_type,
                        },
                        indent=2,
                    )

            if queried_tables and redacted_col_map:
                blocked_cols = set()
                for tbl_name in queried_tables:
                    blocked_cols.update(redacted_col_map.get(tbl_name, []))
                if blocked_cols:
                    try:
                        for tree in sqlglot.parse(validated_query, dialect=dialect):
                            for col in tree.find_all(exp.Column):
                                if col.name in blocked_cols:
                                    return json.dumps(
                                        {
                                            "success": False,
                                            "error": f"Access denied: column '{col.name}' is restricted and cannot be queried",
                                            "connection_id": connection_id,
                                            "db_type": db_type,
                                        },
                                        indent=2,
                                    )
                    except Exception:
                        pass

        # Use unified async SQL connector (supports PostgreSQL, MySQL, SQLite, MSSQL)
        # The connector will automatically apply the correct limit syntax (TOP for MSSQL, LIMIT for others)
        async_connector = await AsyncDatabaseService.get_or_create_sql_connector(
            connection_id, connection_obj, db_type=db_type
        )

        # Pass limit and timeout to connector - it will apply TOP for MSSQL or LIMIT for others dynamically
        result = await async_connector.execute_query(validated_query, limit=limit, timeout=timeout)

        if result.get("success"):
            if conn_rules:
                from server.services.redaction_service import RedactionService

                redacted_cols = {t: set(cols) for t, cols in conn_rules.get("columns", {}).items()}
                redacted_tbls = set(conn_rules.get("tables", []))
                # Only mask_all for tables actually in the query (avoids over-masking unrelated tables)
                relevant_redacted_tbls = redacted_tbls & queried_tables if queried_tables else redacted_tbls
                if redacted_cols or relevant_redacted_tbls:
                    RedactionService.redact_result_rows(result.get("result", []), redacted_cols, relevant_redacted_tbls)

            row_count = len(result.get("result", []))
            limit_applied = result.get("limited", False)
            if limit_applied:
                print(
                    f"[LOG: ✅ SQL query executed successfully with {db_type.upper()} limit syntax, returned {row_count} rows]"
                )
            else:
                print(f"[LOG: ✅ SQL query executed successfully, returned {row_count} rows]")

            # Keep the success field and add additional context
            result["success"] = True
            result["connection_id"] = connection_id
            result["db_type"] = db_type
            result["row_count"] = row_count
            return json.dumps(result, indent=2)
        else:
            return json.dumps(
                {
                    "success": False,
                    "error": f"Error executing query: {result.get('error', 'Unknown error')}",
                    "query": validated_query[:100] + "..." if len(validated_query) > 100 else validated_query,
                    "connection_id": connection_id,
                    "db_type": db_type,
                },
                indent=2,
            )
    except Exception as e:
        logger.error(
            f"SQL query execution error: {str(e)}",
            exc_info=True,
            posthog_context={
                "function": "execute_sql_query",
                "query_preview": query[:100] if query else None,
                "limit": limit,
                "connection_id": connection_id,
                "db_type": db_type,
            },
        )
        return json.dumps(
            {
                "success": False,
                "error": f"Error executing query: {str(e)}",
                "query": query[:100] + "..." if len(query) > 100 else query,
                "limit": limit,
                "connection_id": connection_id,
                "db_type": db_type,
            },
            indent=2,
        )


def get_sql_tools():
    """Get SQL tools for agents with improved limit handling."""
    return [execute_sql_query]
