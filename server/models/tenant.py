from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import TIMESTAMP, Boolean, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.db.base import GUID, Base

if TYPE_CHECKING:
    from server.models.tenant_member import TenantMember
    from server.models.user import User


def generate_uuid() -> UUID:
    return uuid4()


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    owner_id: Mapped[UUID] = mapped_column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    is_personal: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    owner: Mapped[User] = relationship("User", foreign_keys=[owner_id])
    members: Mapped[list[TenantMember]] = relationship(back_populates="tenant", cascade="all, delete-orphan")
