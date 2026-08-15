from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from server.models.folder_member import FolderMember
from server.repositories.base import AsyncCRUDRepository


class FolderMemberRepository(AsyncCRUDRepository[FolderMember]):
    def __init__(self, session):
        super().__init__(session, FolderMember)

    async def get_membership(self, folder_id: UUID, user_id: UUID) -> FolderMember | None:
        """Check if a user is a member of a folder."""
        result = await self._session.execute(
            select(self._model).where(self._model.folder_id == folder_id, self._model.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def list_by_folder(self, folder_id: UUID) -> list[FolderMember]:
        """List all members of a folder."""
        result = await self._session.execute(
            select(self._model)
            .where(self._model.folder_id == folder_id)
            .options(selectinload(FolderMember.user), selectinload(FolderMember.added_by_user))
            .order_by(self._model.created_at)
        )
        return list(result.scalars().all())

    async def list_by_user(self, user_id: UUID) -> list[FolderMember]:
        """List all folder memberships for a user."""
        result = await self._session.execute(
            select(self._model).where(self._model.user_id == user_id).options(selectinload(FolderMember.folder))
        )
        return list(result.scalars().all())

    async def is_member(self, folder_id: UUID, user_id: UUID) -> bool:
        """Check if user is a member of the folder."""
        membership = await self.get_membership(folder_id, user_id)
        return membership is not None
