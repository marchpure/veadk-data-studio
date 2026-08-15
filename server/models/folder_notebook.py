from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import TIMESTAMP, Boolean, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.db.base import GUID, Base

if TYPE_CHECKING:
    from server.models.folder import Folder
    from server.models.notebooks import Notebook
    from server.models.user import User


def generate_uuid() -> UUID:
    return uuid4()


class FolderNotebook(Base):
    __tablename__ = "folder_notebooks"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    folder_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("folders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    notebook_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    shared_by: Mapped[UUID | None] = mapped_column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.current_timestamp())

    # Snapshot columns
    is_snapshot: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    snapshot_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    snapshot_updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=False), nullable=True)

    folder: Mapped[Folder] = relationship("Folder", back_populates="folder_notebooks")
    notebook: Mapped[Notebook] = relationship("Notebook")
    shared_by_user: Mapped[User | None] = relationship("User", foreign_keys=[shared_by])

    __table_args__ = (UniqueConstraint("folder_id", "notebook_id", name="uq_folder_notebooks_folder_notebook"),)
