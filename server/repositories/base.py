from __future__ import annotations

from typing import Any, Generic, TypeVar

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.tenant_context import get_tenant_id

ModelT = TypeVar("ModelT")


class AsyncCRUDRepository(Generic[ModelT]):
    def __init__(self, session: AsyncSession, model: type[ModelT]):
        self._session = session
        self._model = model
        # Read tenant_id from context automatically
        self._tenant_id = get_tenant_id()

    def _apply_tenant_filter(self, query):
        """Auto-inject tenant_id filter if model has tenant_id column and tenant_id is set."""
        if self._tenant_id is not None and hasattr(self._model, "tenant_id"):
            query = query.where(self._model.tenant_id == self._tenant_id)
        return query

    async def create(self, data: dict[str, Any]) -> ModelT:
        # Auto-inject tenant_id if model has it and tenant_id is set
        if self._tenant_id is not None and hasattr(self._model, "tenant_id") and "tenant_id" not in data:
            data["tenant_id"] = self._tenant_id

        instance = self._model(**data)
        self._session.add(instance)
        await self._session.commit()
        await self._session.refresh(instance)
        return instance

    async def get(self, id: Any) -> ModelT | None:
        query = select(self._model).where(self._model.id == id)
        query = self._apply_tenant_filter(query)
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        filters: dict[str, Any] | None = None,
    ) -> list[ModelT]:
        query = select(self._model)

        # Apply tenant filter first
        query = self._apply_tenant_filter(query)

        # Then apply additional filters
        if filters:
            for key, value in filters.items():
                attr = getattr(self._model, key, None)
                if attr is not None:
                    query = query.where(attr == value)

        query = query.offset(offset).limit(limit)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def update(self, id: Any, data: dict[str, Any]) -> ModelT | None:
        instance = await self.get(id)  # get() already applies tenant filter
        if instance is None:
            return None
        data = {k: v for k, v in data.items() if k != "id"}
        for key, value in data.items():
            if hasattr(instance, key):
                setattr(instance, key, value)
        await self._session.commit()
        await self._session.refresh(instance)
        return instance

    async def delete(self, id: Any) -> bool:
        query = delete(self._model).where(self._model.id == id)

        # Apply tenant filter to delete as well
        if self._tenant_id is not None and hasattr(self._model, "tenant_id"):
            query = query.where(self._model.tenant_id == self._tenant_id)

        result = await self._session.execute(query)
        await self._session.commit()
        affected = getattr(result, "rowcount", None) or 0
        return affected > 0
