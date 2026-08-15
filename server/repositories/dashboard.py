from __future__ import annotations

from uuid import UUID

from sqlalchemy import desc, func, select, update

from server.models.dashboard import Dashboard
from server.repositories.base import AsyncCRUDRepository


class DashboardRepository(AsyncCRUDRepository[Dashboard]):
    def __init__(self, session):
        super().__init__(session, Dashboard)

    async def get_by_notebook_id(self, notebook_id: str, limit: int = 100) -> list[Dashboard]:
        """Get all dashboard versions for a notebook, ordered by version_num descending"""
        query = (
            select(Dashboard)
            .where(Dashboard.notebook_id == notebook_id)
            .order_by(desc(Dashboard.version_num))
            .limit(limit)
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_latest_version(self, notebook_id: str) -> Dashboard | None:
        """Get the latest dashboard version for a notebook"""
        query = (
            select(Dashboard).where(Dashboard.notebook_id == notebook_id).order_by(desc(Dashboard.version_num)).limit(1)
        )
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def get_next_version_num(self, notebook_id: str) -> int:
        """Get the next version number for a notebook"""
        query = select(func.max(Dashboard.version_num)).where(Dashboard.notebook_id == notebook_id)
        result = await self._session.execute(query)
        max_version = result.scalar_one_or_none()
        return (max_version or 0) + 1

    async def create_with_version(
        self, notebook_id: str, html_content: str, tenant_id: str | UUID | None = None
    ) -> Dashboard:
        """Create a new dashboard version with auto-incremented version number"""
        version_num = await self.get_next_version_num(notebook_id)
        data = {
            "notebook_id": notebook_id,
            "version_num": version_num,
            "html_content": html_content,
            "tenant_id": tenant_id or self._tenant_id,
        }
        return await self.create(data)

    async def get_version(self, notebook_id: str, version_num: int) -> Dashboard | None:
        """Get a specific version of a dashboard for a notebook"""
        query = select(Dashboard).where(Dashboard.notebook_id == notebook_id, Dashboard.version_num == version_num)
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def update_version_content(self, notebook_id: str, version_num: int, html_content: str) -> Dashboard:
        """Update the HTML content of an existing dashboard version (for session-based edits)"""
        query = (
            update(Dashboard)
            .where(Dashboard.notebook_id == notebook_id, Dashboard.version_num == version_num)
            .values(html_content=html_content)
            .returning(Dashboard)
        )
        result = await self._session.execute(query)
        await self._session.commit()
        return result.scalar_one()
