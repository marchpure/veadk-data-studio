from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import TIMESTAMP, CheckConstraint, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.db.base import GUID, Base

if TYPE_CHECKING:
    from server.models.tenant import Tenant
    from server.models.user import User
    from server.models.verification_token import VerificationToken


def generate_uuid() -> UUID:
    return uuid4()


class InvitationRole(str, Enum):
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class InvitationStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    REVOKED = "revoked"


INVITATION_ROLES = ("admin", "member", "viewer")
INVITATION_STATUSES = ("pending", "accepted", "expired", "revoked")


class TenantInvitation(Base):
    __tablename__ = "tenant_invitations"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[UUID] = mapped_column(GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), default=InvitationRole.MEMBER.value, nullable=False)
    invited_by_id: Mapped[UUID] = mapped_column(GUID(), ForeignKey("users.id"), nullable=False)
    token_id: Mapped[UUID] = mapped_column(GUID(), ForeignKey("verification_tokens.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=InvitationStatus.PENDING.value, nullable=False)
    plain_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.current_timestamp())

    tenant: Mapped[Tenant] = relationship("Tenant", foreign_keys=[tenant_id])
    invited_by: Mapped[User] = relationship("User", foreign_keys=[invited_by_id])
    token: Mapped[VerificationToken] = relationship("VerificationToken", foreign_keys=[token_id])

    __table_args__ = (
        CheckConstraint(f"role IN {INVITATION_ROLES}", name="ck_tenant_invitations_role"),
        CheckConstraint(f"status IN {INVITATION_STATUSES}", name="ck_tenant_invitations_status"),
    )
