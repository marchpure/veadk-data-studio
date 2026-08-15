"""DuckDB SQL tool for agents - executes read-only queries over uploaded files."""

import json
import logging
from typing import Any

import sqlglot
from agents import function_tool
from agents.run_context import RunContextWrapper
from sqlglot import exp

from server.auth.tenant_context import set_tenant_id
from server.db.session import get_async_session
from server.repositories.datasets import DatasetRepository
from server.services.file_operations import DataFrameFileService
from server.tools.plan_tools import check_plan_gate

logger = logging.getLogger(__name__)


@function_tool
async def execute_duckdb_query(
    ctx: RunContextWrapper[Any],
    dataset_id: str,
    query: str,
    limit: int = 5,
    timeout: int = 30,
) -> str:
    """
    Execute a DuckDB SQL query against file datasets (CSV/Parquet/JSON).

    Args:
        ctx: Run context wrapper
        dataset_id: Dataset ID to use for query execution
        query: DuckDB-compatible SQL SELECT statement
        limit: Maximum number of rows to return (applies only during testing)
        timeout: Query execution timeout in seconds (default 30)

    Returns:
        JSON string containing:
        - success: Boolean indicating if query executed successfully
        - result: Array of rows returned (on success)
        - columns: Column names (on success)
        - returned_count: Number of rows returned (on success)
        - limited: Boolean indicating if limit was applied (on success)
        - timeout: Boolean indicating if query timed out (on timeout)
        - timeout_seconds: Configured timeout value (on timeout)
        - execution_time_seconds: Actual execution time before timeout (on timeout)
        - error: Error message (on failure)
        - query: Query that was attempted (on failure)
        - dataset_id: Dataset identifier used
        - Additional context fields based on the operation
    """
    if gate_error := check_plan_gate(ctx):
        return gate_error

    if limit > 50:
        limit = 50

    logger.info(
        f"Executing DuckDB query with dataset_id={dataset_id}, limit={limit}, timeout={timeout}s: {query[:100]}..."
    )

    # Fetch dataset using repository (auto-applies tenant filtering)
    async for session in get_async_session():
        try:
            tenant_id = ctx.context.get("tenant_id")
            set_tenant_id(tenant_id)
            dataset_repo = DatasetRepository(session)
            dataset = await dataset_repo.get(dataset_id)

            if not dataset:
                return json.dumps(
                    {
                        "success": False,
                        "error": f"Dataset with ID '{dataset_id}' not found",
                        "dataset_id": dataset_id,
                    },
                    indent=2,
                )
        finally:
            await session.close()

        # Continue with query execution outside session
        break

    # Build connection_obj from dataset_id
    connection_obj = {"dataset_id": dataset_id}

    # Block queries against redacted tables and columns
    redaction_rules = ctx.context.get("redaction_rules", {})
    ds_rules = redaction_rules.get(dataset_id, {})
    queried_tables: set[str] = set()
    if ds_rules:
        redacted_tables = set(ds_rules.get("tables", []))
        redacted_col_map = ds_rules.get("columns", {})
        try:
            parsed_expressions = sqlglot.parse(query)
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
                        "dataset_id": dataset_id,
                    },
                    indent=2,
                )

        if queried_tables and redacted_col_map:
            blocked_cols = set()
            for tbl_name in queried_tables:
                blocked_cols.update(redacted_col_map.get(tbl_name, []))
            if blocked_cols:
                try:
                    for tree in sqlglot.parse(query):
                        for col in tree.find_all(exp.Column):
                            if col.name in blocked_cols:
                                return json.dumps(
                                    {
                                        "success": False,
                                        "error": f"Access denied: column '{col.name}' is restricted and cannot be queried",
                                        "dataset_id": dataset_id,
                                    },
                                    indent=2,
                                )
                except Exception:
                    pass

    try:
        result = await DataFrameFileService.execute_duckdb_query(
            connection_obj=connection_obj,
            query=query,
            limit=limit,
            timeout=timeout,
        )

        if result.get("success"):
            result_payload = dict(result)

            if ds_rules:
                from server.services.redaction_service import RedactionService

                redacted_cols = {t: set(cols) for t, cols in ds_rules.get("columns", {}).items()}
                redacted_tbls = set(ds_rules.get("tables", []))
                relevant_redacted_tbls = redacted_tbls & queried_tables if queried_tables else redacted_tbls
                if redacted_cols or relevant_redacted_tbls:
                    RedactionService.redact_result_rows(
                        result_payload.get("result", []), redacted_cols, relevant_redacted_tbls
                    )

            # Keep the success field
            result_payload["success"] = True
            result_payload["dataset_id"] = dataset_id
            row_count = result_payload.get("returned_count", 0)
            limited = result_payload.get("limited", False)

            if limited:
                print(f"[LOG: ✅ DuckDB query executed successfully, returned {row_count} rows (limited)]")
            else:
                print(f"[LOG: ✅ DuckDB query executed successfully, returned {row_count} rows]")

            return json.dumps(result_payload, indent=2)

        return json.dumps(
            {
                "success": False,
                "error": f"Error executing DuckDB query: {result.get('error', 'Unknown error')}",
                "query": query[:100] + "..." if len(query) > 100 else query,
                "dataset_id": dataset_id,
            },
            indent=2,
        )
    except Exception as exc:
        logger.error(f"Error in execute_duckdb_query: {exc}")
        return json.dumps(
            {
                "success": False,
                "error": f"Error executing DuckDB query: {exc}",
                "query": query[:100] + "..." if len(query) > 100 else query,
                "dataset_id": dataset_id,
                "limit": limit,
            },
            indent=2,
        )


def get_duckdb_tools():
    """Get DuckDB SQL tools for agents."""
    return [execute_duckdb_query]


def get_dataframe_tools():
    """Backward-compatible alias for legacy imports."""
    return get_duckdb_tools()
