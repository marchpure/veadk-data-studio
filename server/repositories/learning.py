from __future__ import annotations

import re

from sqlalchemy import or_, select

from server.models.learning import Learning
from server.repositories.base import AsyncCRUDRepository


class LearningRepository(AsyncCRUDRepository[Learning]):
    def __init__(self, session):
        super().__init__(session, Learning)

    async def search_by_title(self, query: str, dataset_id: str = "", limit: int = 50) -> list[Learning]:
        words = re.findall(r"\w+", query.lower())
        if not words and not dataset_id:
            return await self.list_by_tenant(limit=limit)

        filters = []
        if words:
            filters.extend([self._model.title.ilike(f"%{w}%") for w in words])
        if dataset_id:
            filters.append(self._model.dataset_id == dataset_id)

        q = select(self._model).where(or_(*filters))
        q = self._apply_tenant_filter(q)
        q = q.order_by(self._model.updated_at.desc()).limit(limit)
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def search_by_dataset_id(self, dataset_id: str, limit: int = 50) -> list[Learning]:
        q = select(self._model).where(self._model.dataset_id == dataset_id)
        q = self._apply_tenant_filter(q)
        q = q.order_by(self._model.updated_at.desc()).limit(limit)
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def list_by_tenant(self, limit: int = 100) -> list[Learning]:
        q = select(self._model)
        q = self._apply_tenant_filter(q)
        q = q.order_by(self._model.updated_at.desc()).limit(limit)
        result = await self._session.execute(q)
        return list(result.scalars().all())
