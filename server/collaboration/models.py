from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, TIMESTAMP, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.db.base import GUID, Base

if TYPE_CHECKING:
    from server.models.llm_connections import LLMConnection
    from server.models.notebooks import Notebook
    from server.models.tenant import Tenant
    from server.models.user import User


def generate_uuid() -> UUID:
    return uuid4()


NORMALIZED_ROOT_NONE = "__root__"


class CollaborationInstallation(Base):
    __tablename__ = "collaboration_installations"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    platform: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    external_tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    external_tenant_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    app_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    credentials_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    connection_mode: Mapped[str] = mapped_column(String(30), nullable=False, default="websocket")
    default_llm_connection_id: Mapped[UUID | None] = mapped_column(
        GUID(), ForeignKey("llm_connections.id", ondelete="SET NULL"), nullable=True
    )
    bot_external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    public_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, default=lambda: uuid4().hex)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    health_status: Mapped[str] = mapped_column(String(30), nullable=False, default="disconnected")
    health_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_connected_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=False), nullable=True)
    last_event_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=False), nullable=True)
    reconnect_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    config_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    installed_by: Mapped[UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), default=datetime.now, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), default=datetime.now, server_default=func.current_timestamp(), onupdate=datetime.now
    )

    tenant: Mapped[Tenant] = relationship("Tenant", foreign_keys=[tenant_id])
    default_llm_connection: Mapped[LLMConnection | None] = relationship(
        "LLMConnection", foreign_keys=[default_llm_connection_id]
    )
    installed_by_user: Mapped[User | None] = relationship("User", foreign_keys=[installed_by])

    __table_args__ = (
        UniqueConstraint("platform", "external_tenant_id", name="uq_collab_installations_platform_external_tenant"),
    )


class CollaborationConversation(Base):
    __tablename__ = "collaboration_conversations"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    installation_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("collaboration_installations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_chat_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    external_root_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    normalized_root_id: Mapped[str] = mapped_column(String(128), nullable=False, default=NORMALIZED_ROOT_NONE)
    external_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    chat_type: Mapped[str] = mapped_column(String(30), nullable=False)
    notebook_id: Mapped[UUID | None] = mapped_column(
        GUID(), ForeignKey("notebooks.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    bot_owned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    auto_follow_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    last_activity_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), default=datetime.now, server_default=func.current_timestamp()
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), default=datetime.now, server_default=func.current_timestamp()
    )

    installation: Mapped[CollaborationInstallation] = relationship(
        "CollaborationInstallation", foreign_keys=[installation_id]
    )
    notebook: Mapped[Notebook | None] = relationship("Notebook", foreign_keys=[notebook_id])

    __table_args__ = (
        UniqueConstraint(
            "installation_id",
            "external_chat_id",
            "normalized_root_id",
            name="uq_collab_conversation_install_chat_root",
        ),
    )


class CollaborationEventLog(Base):
    __tablename__ = "collaboration_event_logs"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    installation_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("collaboration_installations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    platform: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    external_event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    external_chat_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    external_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    conversation_id: Mapped[UUID | None] = mapped_column(
        GUID(), ForeignKey("collaboration_conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    notebook_id: Mapped[UUID | None] = mapped_column(
        GUID(), ForeignKey("notebooks.id", ondelete="SET NULL"), nullable=True
    )
    run_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(30), nullable=False, default="received")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    next_attempt_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=False), nullable=True)
    redaction_applied: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), default=datetime.now, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), default=datetime.now, server_default=func.current_timestamp(), onupdate=datetime.now
    )

    installation: Mapped[CollaborationInstallation] = relationship(
        "CollaborationInstallation", foreign_keys=[installation_id]
    )
    conversation: Mapped[CollaborationConversation | None] = relationship(
        "CollaborationConversation", foreign_keys=[conversation_id]
    )
    notebook: Mapped[Notebook | None] = relationship("Notebook", foreign_keys=[notebook_id])

    __table_args__ = (
        UniqueConstraint("installation_id", "external_event_id", name="uq_collab_event_install_external_event"),
    )


class CollaborationDeliveryTarget(Base):
    __tablename__ = "collaboration_delivery_targets"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    installation_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("collaboration_installations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_type: Mapped[str] = mapped_column(String(30), nullable=False)
    external_target_id: Mapped[str] = mapped_column(String(128), nullable=False)
    external_root_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    normalized_root_id: Mapped[str] = mapped_column(String(128), nullable=False, default=NORMALIZED_ROOT_NONE)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    config_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), default=datetime.now, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), default=datetime.now, server_default=func.current_timestamp(), onupdate=datetime.now
    )

    installation: Mapped[CollaborationInstallation] = relationship(
        "CollaborationInstallation", foreign_keys=[installation_id]
    )

    __table_args__ = (
        UniqueConstraint(
            "installation_id",
            "target_type",
            "external_target_id",
            "normalized_root_id",
            name="uq_collab_delivery_target",
        ),
    )


class ExternalIdentity(Base):
    __tablename__ = "external_identities"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    platform: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    installation_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("collaboration_installations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    union_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    user_id: Mapped[UUID | None] = mapped_column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    byaan_user_id: Mapped[UUID | None] = mapped_column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="seen")
    last_seen_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), default=datetime.now, server_default=func.current_timestamp()
    )

    tenant: Mapped[Tenant] = relationship("Tenant", foreign_keys=[tenant_id])
    installation: Mapped[CollaborationInstallation] = relationship(
        "CollaborationInstallation", foreign_keys=[installation_id]
    )

    __table_args__ = (
        UniqueConstraint(
            "installation_id", "external_user_id", name="uq_external_identity_install_external_user"
        ),
    )


class CollaborationResponseRef(Base):
    __tablename__ = "collaboration_response_refs"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    conversation_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("collaboration_conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    platform_message_id: Mapped[str] = mapped_column(String(128), nullable=False)
    platform_card_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="running")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), default=datetime.now, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), default=datetime.now, server_default=func.current_timestamp(), onupdate=datetime.now
    )

    conversation: Mapped[CollaborationConversation] = relationship(
        "CollaborationConversation", foreign_keys=[conversation_id]
    )


class CollaborationLease(Base):
    __tablename__ = "collaboration_leases"

    installation_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("collaboration_installations.id", ondelete="CASCADE"), primary_key=True
    )
    owner_id: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), nullable=False, index=True)
    heartbeat_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), default=datetime.now, server_default=func.current_timestamp()
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), default=datetime.now, server_default=func.current_timestamp()
    )

    installation: Mapped[CollaborationInstallation] = relationship(
        "CollaborationInstallation", foreign_keys=[installation_id]
    )
