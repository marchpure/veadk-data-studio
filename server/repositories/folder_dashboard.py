from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from server.models.dashboard import Dashboard
from server.models.folder_dashboard import FolderDashboard
from server.repositories.base import AsyncCRUDRepository


class FolderDashboardRepository(AsyncCRUDRepository[FolderDashboard]):
    def __init__(self, session):
        super().__init__(session, FolderDashboard)

    async def get_by_folder_and_dashboard(self, folder_id: UUID, dashboard_id: UUID) -> FolderDashboard | None:
        """Get a specific folder-dashboard association."""
        result = await self._session.execute(
            select(self._model).where(self._model.folder_id == folder_id, self._model.dashboard_id == dashboard_id)
        )
        return result.scalar_one_or_none()

    async def list_by_folder(self, folder_id: UUID) -> list[FolderDashboard]:
        """List all dashboards shared to a folder."""
        result = await self._session.execute(
            select(self._model)
            .where(self._model.folder_id == folder_id)
            .options(
                selectinload(FolderDashboard.dashboard).selectinload(Dashboard.notebook),
                selectinload(FolderDashboard.shared_by_user),
            )
            .order_by(self._model.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_by_dashboard(self, dashboard_id: UUID) -> list[FolderDashboard]:
        """List all folders a dashboard is shared to."""
        result = await self._session.execute(
            select(self._model)
            .where(self._model.dashboard_id == dashboard_id)
            .options(selectinload(FolderDashboard.folder), selectinload(FolderDashboard.shared_by_user))
            .order_by(self._model.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_by_notebook_id(self, notebook_id: UUID) -> list[FolderDashboard]:
        """List all folders where any dashboard version of a notebook is shared."""
        result = await self._session.execute(
            select(self._model)
            .join(Dashboard, self._model.dashboard_id == Dashboard.id)
            .where(Dashboard.notebook_id == notebook_id)
            .options(
                selectinload(FolderDashboard.folder),
                selectinload(FolderDashboard.shared_by_user),
                selectinload(FolderDashboard.dashboard),
            )
            .order_by(self._model.created_at.desc())
        )
        return list(result.scalars().all())

    async def is_dashboard_shared_to_folder(self, folder_id: UUID, dashboard_id: UUID) -> bool:
        """Check if a dashboard is shared to a folder."""
        association = await self.get_by_folder_and_dashboard(folder_id, dashboard_id)
        return association is not None

    async def get_by_folder_and_notebook(self, folder_id: UUID, notebook_id: UUID) -> FolderDashboard | None:
        """Get any folder-dashboard association for a notebook in a folder (any version)."""
        result = await self._session.execute(
            select(self._model)
            .join(Dashboard, self._model.dashboard_id == Dashboard.id)
            .where(self._model.folder_id == folder_id, Dashboard.notebook_id == notebook_id)
            .options(selectinload(FolderDashboard.dashboard))
        )
        return result.scalar_one_or_none()

    async def get_all_shared(self) -> list[FolderDashboard]:
        """Get all dashboards that are shared to any folder (for scheduled cache refresh)."""
        result = await self._session.execute(
            select(self._model)
            .options(
                selectinload(FolderDashboard.dashboard).selectinload(Dashboard.notebook),
            )
            .order_by(self._model.created_at.desc())
        )
        return list(result.scalars().all())
