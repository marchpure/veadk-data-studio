from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from server.utils.custom_logger import get_logger

logger = get_logger(__name__)


async def extract_datasource_info(
    connection_id: str | UUID | None,
    dataset_id: str | UUID | None,
    database_schemas: list[dict[str, Any]] | None = None,
    session: AsyncSession | None = None,
) -> tuple[str, str, str]:
    """
    Extract datasource ID, name, and type from context or database.

    Priority:
    1. Try context database_schemas first (fast, pre-built)
    2. Fall back to DB query if context not available

    Args:
        connection_id: Connection ID from tool input
        dataset_id: Dataset ID from tool input
        database_schemas: Pre-built context schemas (Claude MCP path)
        session: Database session for fallback lookup (OpenAI path)

    Returns:
        Tuple of (datasource_id, datasource_name, datasource_type)
        Returns ("", "Unnamed", "unknown") if not found
    """
    datasource_id = str(connection_id or dataset_id or "")
    datasource_name = "Unnamed"
    datasource_type = "unknown"

    if not datasource_id:
        return ("", datasource_name, datasource_type)

    if database_schemas:
        for db_schema in database_schemas:
            schema_conn_id = db_schema.get("connection_id")
            schema_dataset_id = db_schema.get("dataset_id")

            if (connection_id and str(schema_conn_id) == str(connection_id)) or (
                dataset_id and str(schema_dataset_id) == str(dataset_id)
            ):
                datasource_name = db_schema.get("connection_name") or db_schema.get("dataset_name", "Unnamed")
                datasource_type = db_schema.get("db_type", "unknown")
                return (datasource_id, datasource_name, datasource_type)

    if session:
        try:
            from server.repositories.connections import ConnectionRepository
            from server.repositories.datasets import DatasetRepository

            if connection_id:
                conn_repo = ConnectionRepository(session)
                connection = await conn_repo.get(connection_id)
                if connection:
                    datasource_name = connection.name or "Unnamed"
                    datasource_type = connection.type or "unknown"
                    return (datasource_id, datasource_name, datasource_type)

            if dataset_id:
                ds_repo = DatasetRepository(session)
                dataset = await ds_repo.get(dataset_id)
                if dataset:
                    datasource_name = dataset.name or "Unnamed"
                    datasource_type = dataset.type or "file"
                    return (datasource_id, datasource_name, datasource_type)

        except Exception as e:
            logger.warning(f"Could not fetch datasource info for {datasource_id}: {e}")

    if not database_schemas and not session:
        logger.warning(f"Could not extract datasource info for {datasource_id}: no context or session available")

    return (datasource_id, datasource_name, datasource_type)
