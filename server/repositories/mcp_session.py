from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.mcp_session import MCPSession


class MCPSessionRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_session_id(self, session_id: str) -> MCPSession | None:
        query = select(MCPSession).where(MCPSession.session_id == session_id, MCPSession.is_active.is_(True))
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def create(
        self,
        session_id: str,
        tenant_id: UUID,
        user_id: UUID,
        mcp_api_key_id: UUID | None = None,
    ) -> MCPSession:
        mcp_session = MCPSession(
            session_id=session_id,
            tenant_id=tenant_id,
            user_id=user_id,
            mcp_api_key_id=mcp_api_key_id,
        )
        self._session.add(mcp_session)
        await self._session.commit()
        await self._session.refresh(mcp_session)
        return mcp_session

    async def update_activity(self, session_id: str) -> None:
        query = select(MCPSession).where(MCPSession.session_id == session_id)
        result = await self._session.execute(query)
        mcp_session = result.scalar_one_or_none()

        if mcp_session:
            mcp_session.last_activity_at = datetime.now()
            await self._session.commit()

    async def update_notebook(self, session_id: str, notebook_id: UUID) -> None:
        query = select(MCPSession).where(MCPSession.session_id == session_id)
        result = await self._session.execute(query)
        mcp_session = result.scalar_one_or_none()

        if mcp_session:
            mcp_session.notebook_id = notebook_id
            mcp_session.last_activity_at = datetime.now()
            await self._session.commit()

    async def deactivate(self, session_id: str) -> bool:
        query = select(MCPSession).where(MCPSession.session_id == session_id)
        result = await self._session.execute(query)
        mcp_session = result.scalar_one_or_none()

        if not mcp_session:
            return False

        mcp_session.is_active = False
        await self._session.commit()
        return True
