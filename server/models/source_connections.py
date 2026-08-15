from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import JSON, TIMESTAMP, CheckConstraint, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.db.base import GUID, Base

if TYPE_CHECKING:
    from server.models.source_resources import SourceResource
    from server.models.user import User


def generate_uuid() -> UUID:
    return uuid4()


SOURCE_CONNECTION_PROVIDERS = (
    "feishu",
    "volcengine_tos",
)
SOURCE_CONNECTION_AUTH_MODES = (
    "oauth",
    "access_key",
    "sts",
    "none",
)
SOURCE_CONNECTION_STATUSES = (
    "connected",
    "pending",
    "reauthorization_required",
    "authorization_required",
    "failed",
    "disconnected",
)


class SourceConnection(Base):
    __tablename__ = "source_connections"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    auth_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    encrypted_credentials: Mapped[str] = mapped_column(Text, nullable=False)
    external_account_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="connected", index=True)
    capabilities_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    token_expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=False), nullable=True, index=True)
    created_by: Mapped[UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    creator: Mapped[User | None] = relationship("User", foreign_keys=[created_by])
    resources: Mapped[list[SourceResource]] = relationship("SourceResource", back_populates="source_connection")

    __table_args__ = (
        CheckConstraint(f"provider IN {SOURCE_CONNECTION_PROVIDERS}", name="ck_source_connections_provider"),
        CheckConstraint(f"auth_mode IN {SOURCE_CONNECTION_AUTH_MODES}", name="ck_source_connections_auth_mode"),
        CheckConstraint(f"status IN {SOURCE_CONNECTION_STATUSES}", name="ck_source_connections_status"),
        UniqueConstraint(
            "tenant_id",
            "provider",
            "created_by",
            "external_account_id",
            name="uq_source_connections_account",
        ),
    )


class FeishuOAuthFlow(Base):
    __tablename__ = "feishu_oauth_flows"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    state_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    purpose: Mapped[str] = mapped_column(String(60), nullable=False, default="source_authorization")
    provider: Mapped[str] = mapped_column(String(30), nullable=False, default="feishu")
    redirect_uri: Mapped[str] = mapped_column(Text, nullable=False)
    redirect_origin: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(60), nullable=False, default="authorizing", index=True)
    connection_id: Mapped[UUID | None] = mapped_column(
        GUID(), ForeignKey("source_connections.id", ondelete="SET NULL"), nullable=True, index=True
    )
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), nullable=False, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=False), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    __table_args__ = (
        CheckConstraint("provider IN ('feishu')", name="ck_feishu_oauth_flows_provider"),
        CheckConstraint(
            "status IN ('authorizing', 'connected', 'state_expired', 'authorization_declined', 'scope_missing', "
            "'admin_approval_required', 'oauth_error', 'callback_unreachable')",
            name="ck_feishu_oauth_flows_status",
        ),
    )
