import hashlib
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from server.repositories.mcp_api_key import MCPAPIKeyRepository
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)


class MCPAuthError(Exception):
    pass


async def validate_api_key(api_key: str, session: AsyncSession) -> tuple[UUID, UUID]:
    if not api_key or not api_key.startswith("byaan_"):
        raise MCPAuthError("Invalid API key format")

    key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    repo = MCPAPIKeyRepository(session)
    db_key = await repo.get_by_hash(key_hash)

    if not db_key:
        raise MCPAuthError("Invalid API key")

    if not db_key.is_active:
        raise MCPAuthError("API key has been revoked")

    await repo.update_last_used(db_key.id)

    logger.info(
        f"MCP API key validated for tenant {db_key.tenant_id}",
        extra={"posthog_context": {"tenant_id": str(db_key.tenant_id), "user_id": str(db_key.user_id)}},
    )

    return db_key.tenant_id, db_key.user_id
