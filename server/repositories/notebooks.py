from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from server.models.mcp_session import MCPSession
from server.models.notebooks import Notebook
from server.repositories.base import AsyncCRUDRepository


class NotebookRepository(AsyncCRUDRepository[Notebook]):
    def __init__(self, session):
        super().__init__(session, Notebook)

    async def list_all(self) -> list[Notebook]:
        query = select(self._model).where(
            self._model.id.notin_(select(MCPSession.notebook_id).where(MCPSession.notebook_id.isnot(None)))
        )
        query = self._apply_tenant_filter(query)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def list_by_user(self, user_id: UUID) -> list[Notebook]:
        """List notebooks created by a specific user within the current tenant."""
        query = select(self._model).where(
            self._model.created_by == user_id,
            self._model.id.notin_(select(MCPSession.notebook_id).where(MCPSession.notebook_id.isnot(None))),
        )
        query = self._apply_tenant_filter(query)
        result = await self._session.execute(query)
        return list(result.scalars().all())
