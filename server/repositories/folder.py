from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from server.models.folder import Folder
from server.models.folder_member import FolderMember
from server.models.folder_notebook import FolderNotebook
from server.repositories.base import AsyncCRUDRepository


class FolderRepository(AsyncCRUDRepository[Folder]):
    def __init__(self, session):
        super().__init__(session, Folder)

    async def list_by_tenant(self, tenant_id: UUID) -> list[Folder]:
        """List all folders in a tenant."""
        result = await self._session.execute(
            select(self._model)
            .where(self._model.tenant_id == tenant_id)
            .options(selectinload(Folder.creator))
            .order_by(self._model.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_by_user_membership(self, user_id: UUID, tenant_id: UUID) -> list[Folder]:
        """List folders where user is a member (includes folders they created)."""
        result = await self._session.execute(
            select(self._model)
            .join(FolderMember, FolderMember.folder_id == self._model.id)
            .where(self._model.tenant_id == tenant_id, FolderMember.user_id == user_id)
            .options(selectinload(Folder.creator))
            .order_by(self._model.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_by_user_membership_or_public(self, user_id: UUID, tenant_id: UUID) -> list[Folder]:
        """List folders where user is a member OR folder is public."""
        result = await self._session.execute(
            select(self._model)
            .outerjoin(FolderMember, FolderMember.folder_id == self._model.id)
            .where(
                self._model.tenant_id == tenant_id,
                or_(
                    FolderMember.user_id == user_id,
                    self._model.is_public == True,  # noqa: E712
                ),
            )
            .distinct()
            .options(selectinload(Folder.creator))
            .order_by(self._model.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_name(self, name: str, tenant_id: UUID) -> Folder | None:
        """Get a folder by name within a tenant."""
        result = await self._session.execute(
            select(self._model).where(
                self._model.tenant_id == tenant_id,
                self._model.name == name,
            )
        )
        return result.scalar_one_or_none()

    async def get_with_counts(self, folder_id: UUID) -> dict | None:
        """Get folder with member and notebook counts."""
        folder = await self.get(folder_id)
        if not folder:
            return None

        # Count members
        member_count_result = await self._session.execute(
            select(func.count(FolderMember.id)).where(FolderMember.folder_id == folder_id)
        )
        member_count = member_count_result.scalar() or 0

        # Count notebooks
        notebook_count_result = await self._session.execute(
            select(func.count(FolderNotebook.id)).where(FolderNotebook.folder_id == folder_id)
        )
        notebook_count = notebook_count_result.scalar() or 0

        return {
            "folder": folder,
            "member_count": member_count,
            "notebook_count": notebook_count,
        }

    async def get_with_creator(self, folder_id: UUID) -> Folder | None:
        """Get a folder with creator loaded."""
        result = await self._session.execute(
            select(self._model).where(self._model.id == folder_id).options(selectinload(Folder.creator))
        )
        return result.scalar_one_or_none()
