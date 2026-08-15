from __future__ import annotations

from sqlalchemy import select

from server.models.tenant_member import TenantMember
from server.repositories.base import AsyncCRUDRepository


class TenantMemberRepository(AsyncCRUDRepository[TenantMember]):
    def __init__(self, session):
        super().__init__(session, TenantMember)

    async def list_by_user(self, user_id: str) -> list[TenantMember]:
        result = await self._session.execute(select(self._model).where(self._model.user_id == user_id))
        return list(result.scalars().all())

    async def list_by_tenant(self, tenant_id: str) -> list[TenantMember]:
        result = await self._session.execute(select(self._model).where(self._model.tenant_id == tenant_id))
        return list(result.scalars().all())

    async def get_membership(self, user_id: str, tenant_id: str) -> TenantMember | None:
        result = await self._session.execute(
            select(self._model).where(self._model.user_id == user_id, self._model.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()
