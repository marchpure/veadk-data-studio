from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from server.models.folder_notebook import FolderNotebook
from server.repositories.base import AsyncCRUDRepository


class FolderNotebookRepository(AsyncCRUDRepository[FolderNotebook]):
    def __init__(self, session):
        super().__init__(session, FolderNotebook)

    async def get_by_folder_and_notebook(self, folder_id: UUID, notebook_id: UUID) -> FolderNotebook | None:
        """Get a specific folder-notebook association."""
        result = await self._session.execute(
            select(self._model).where(self._model.folder_id == folder_id, self._model.notebook_id == notebook_id)
        )
        return result.scalar_one_or_none()

    async def list_by_folder(self, folder_id: UUID) -> list[FolderNotebook]:
        """List all notebooks shared to a folder."""
        result = await self._session.execute(
            select(self._model)
            .where(self._model.folder_id == folder_id)
            .options(selectinload(FolderNotebook.notebook), selectinload(FolderNotebook.shared_by_user))
            .order_by(self._model.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_by_notebook(self, notebook_id: UUID) -> list[FolderNotebook]:
        """List all folders a notebook is shared to."""
        result = await self._session.execute(
            select(self._model)
            .where(self._model.notebook_id == notebook_id)
            .options(selectinload(FolderNotebook.folder), selectinload(FolderNotebook.shared_by_user))
            .order_by(self._model.created_at.desc())
        )
        return list(result.scalars().all())

    async def is_notebook_shared_to_folder(self, folder_id: UUID, notebook_id: UUID) -> bool:
        """Check if a notebook is shared to a folder."""
        association = await self.get_by_folder_and_notebook(folder_id, notebook_id)
        return association is not None
