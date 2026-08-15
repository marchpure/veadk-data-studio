"""
MCP Session Manager

Manages MCP client sessions using database persistence.
"""

from uuid import UUID

from server.db.session import AsyncSessionFactory
from server.repositories.mcp_session import MCPSessionRepository
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)


class MCPSessionManager:
    def __init__(self):
        pass

    async def create_session(
        self,
        session_id: str,
        tenant_id: UUID,
        user_id: UUID,
        mcp_api_key_id: UUID | None = None,
    ) -> dict:
        async with AsyncSessionFactory() as db_session:
            repo = MCPSessionRepository(db_session)
            mcp_session = await repo.create(
                session_id=session_id,
                tenant_id=tenant_id,
                user_id=user_id,
                mcp_api_key_id=mcp_api_key_id,
            )

            logger.info(
                f"Created MCP session {session_id} for tenant {tenant_id}",
                extra={"posthog_context": {"tenant_id": str(tenant_id), "user_id": str(user_id)}},
            )

            return {
                "session_id": mcp_session.session_id,
                "tenant_id": mcp_session.tenant_id,
                "user_id": mcp_session.user_id,
                "mcp_api_key_id": mcp_session.mcp_api_key_id,
                "notebook_id": mcp_session.notebook_id,
            }

    async def get_session(self, session_id: str) -> dict | None:
        async with AsyncSessionFactory() as db_session:
            repo = MCPSessionRepository(db_session)
            mcp_session = await repo.get_by_session_id(session_id)

            if not mcp_session:
                return None

            return {
                "session_id": mcp_session.session_id,
                "tenant_id": mcp_session.tenant_id,
                "user_id": mcp_session.user_id,
                "mcp_api_key_id": mcp_session.mcp_api_key_id,
                "notebook_id": mcp_session.notebook_id,
            }

    async def update_activity(self, session_id: str) -> None:
        async with AsyncSessionFactory() as db_session:
            repo = MCPSessionRepository(db_session)
            await repo.update_activity(session_id)

    async def update_notebook(self, session_id: str, notebook_id: UUID) -> None:
        async with AsyncSessionFactory() as db_session:
            repo = MCPSessionRepository(db_session)
            await repo.update_notebook(session_id, notebook_id)

            logger.info(
                f"Associated MCP session {session_id} with notebook {notebook_id}",
            )
