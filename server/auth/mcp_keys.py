from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.tenant_context import set_tenant_id
from server.db.session import get_async_session
from server.repositories.mcp_api_key import MCPAPIKeyRepository


@dataclass(frozen=True)
class MCPKeyContext:
    key_id: UUID
    tenant_id: UUID
    user_id: UUID


def hash_mcp_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


async def require_mcp_key(
    authorization: str | None = Header(None, alias="Authorization"),
    session: AsyncSession = Depends(get_async_session),
) -> MCPKeyContext:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="MCP API key is required")
    api_key = authorization.removeprefix("Bearer ").strip()
    if not api_key.startswith("byaan_"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid MCP API key")

    repo = MCPAPIKeyRepository(session)
    key_hash = hash_mcp_api_key(api_key)
    db_key = await repo.get_by_hash(key_hash)
    if not db_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid MCP API key")

    await repo.update_last_used(db_key.id)
    set_tenant_id(db_key.tenant_id)
    return MCPKeyContext(key_id=db_key.id, tenant_id=db_key.tenant_id, user_id=db_key.user_id)
