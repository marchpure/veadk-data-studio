from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import TIMESTAMP, Boolean, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.db.base import GUID, Base

if TYPE_CHECKING:
    from server.models.folder_dashboard import FolderDashboard
    from server.models.folder_member import FolderMember
    from server.models.folder_notebook import FolderNotebook
    from server.models.tenant import Tenant
    from server.models.user import User


def generate_uuid() -> UUID:
    return uuid4()


class Folder(Base):
    __tablename__ = "folders"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    creator: Mapped[User] = relationship("User", foreign_keys=[created_by])
    tenant: Mapped[Tenant] = relationship("Tenant")
    members: Mapped[list[FolderMember]] = relationship(back_populates="folder", cascade="all, delete-orphan")
    folder_notebooks: Mapped[list[FolderNotebook]] = relationship(back_populates="folder", cascade="all, delete-orphan")
    folder_dashboards: Mapped[list[FolderDashboard]] = relationship(
        back_populates="folder", cascade="all, delete-orphan"
    )
