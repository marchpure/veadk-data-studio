from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import TIMESTAMP, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.db.base import GUID, Base

if TYPE_CHECKING:
    from server.models.folder import Folder
    from server.models.user import User


def generate_uuid() -> UUID:
    return uuid4()


class FolderMember(Base):
    __tablename__ = "folder_members"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    folder_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("folders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    added_by: Mapped[UUID | None] = mapped_column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.current_timestamp())

    folder: Mapped[Folder] = relationship("Folder", back_populates="members")
    user: Mapped[User] = relationship("User", foreign_keys=[user_id])
    added_by_user: Mapped[User | None] = relationship("User", foreign_keys=[added_by])

    __table_args__ = (UniqueConstraint("folder_id", "user_id", name="uq_folder_members_folder_user"),)
