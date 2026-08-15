from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.mcp_api_key import MCPAPIKey


class MCPAPIKeyRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_hash(self, key_hash: str) -> MCPAPIKey | None:
        query = select(MCPAPIKey).where(MCPAPIKey.key_hash == key_hash, MCPAPIKey.is_active.is_(True))
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_id(self, key_id: UUID) -> MCPAPIKey | None:
        query = select(MCPAPIKey).where(MCPAPIKey.id == key_id)
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def list_by_tenant(self, tenant_id: UUID) -> list[MCPAPIKey]:
        query = select(MCPAPIKey).where(MCPAPIKey.tenant_id == tenant_id).order_by(MCPAPIKey.created_at.desc())
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def list_by_user(self, user_id: UUID) -> list[MCPAPIKey]:
        query = select(MCPAPIKey).where(MCPAPIKey.user_id == user_id).order_by(MCPAPIKey.created_at.desc())
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def create(
        self,
        tenant_id: UUID,
        user_id: UUID,
        name: str,
        key_hash: str,
        key_prefix: str,
    ) -> MCPAPIKey:
        api_key = MCPAPIKey(
            tenant_id=tenant_id,
            user_id=user_id,
            name=name,
            key_hash=key_hash,
            key_prefix=key_prefix,
        )
        self._session.add(api_key)
        await self._session.commit()
        await self._session.refresh(api_key)
        return api_key

    async def update_last_used(self, key_id: UUID) -> None:
        query = select(MCPAPIKey).where(MCPAPIKey.id == key_id)
        result = await self._session.execute(query)
        api_key = result.scalar_one_or_none()

        if api_key:
            api_key.last_used_at = datetime.now()
            await self._session.commit()

    async def revoke(self, key_id: UUID, tenant_id: UUID) -> bool:
        query = select(MCPAPIKey).where(MCPAPIKey.id == key_id, MCPAPIKey.tenant_id == tenant_id)
        result = await self._session.execute(query)
        api_key = result.scalar_one_or_none()

        if not api_key:
            return False

        api_key.is_active = False
        await self._session.commit()
        return True

    async def delete(self, key_id: UUID, tenant_id: UUID) -> bool:
        query = select(MCPAPIKey).where(MCPAPIKey.id == key_id, MCPAPIKey.tenant_id == tenant_id)
        result = await self._session.execute(query)
        api_key = result.scalar_one_or_none()

        if not api_key:
            return False

        await self._session.delete(api_key)
        await self._session.commit()
        return True
