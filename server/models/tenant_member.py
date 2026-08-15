from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import TIMESTAMP, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.db.base import GUID, Base

if TYPE_CHECKING:
    from server.models.tenant import Tenant
    from server.models.user import User


def generate_uuid() -> UUID:
    return uuid4()


class TenantRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class TenantMember(Base):
    __tablename__ = "tenant_members"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    user_id: Mapped[UUID] = mapped_column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default=TenantRole.MEMBER.value)
    invited_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=False), nullable=True)
    joined_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.current_timestamp())

    user: Mapped[User] = relationship(back_populates="tenant_memberships")
    tenant: Mapped[Tenant] = relationship(back_populates="members")
