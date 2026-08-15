from __future__ import annotations

from sqlalchemy import select

from server.models.tenant import Tenant
from server.repositories.base import AsyncCRUDRepository


class TenantRepository(AsyncCRUDRepository[Tenant]):
    def __init__(self, session):
        super().__init__(session, Tenant)

    async def get_by_slug(self, slug: str) -> Tenant | None:
        result = await self._session.execute(select(self._model).where(self._model.slug == slug))
        return result.scalar_one_or_none()

    async def list_by_owner(self, owner_id: str) -> list[Tenant]:
        result = await self._session.execute(select(self._model).where(self._model.owner_id == owner_id))
        return list(result.scalars().all())
