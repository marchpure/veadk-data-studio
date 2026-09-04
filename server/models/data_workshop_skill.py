from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, TIMESTAMP, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.db.base import GUID, Base


class DataWorkshopSkill(Base):
    __tablename__ = "data_workshop_skills"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_skill: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft", index=True)
    context_refs_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    active_revision: Mapped[str | None] = mapped_column(String(160), nullable=True)
    artifact_metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False),
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        index=True,
    )

    sessions: Mapped[list[DataWorkshopSkillSession]] = relationship(
        "DataWorkshopSkillSession", back_populates="skill", cascade="all, delete-orphan"
    )
    revisions: Mapped[list[DataWorkshopSkillRevision]] = relationship(
        "DataWorkshopSkillRevision", back_populates="skill", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("tenant_id", "owner_id", "target_skill", name="uq_dw_skill_owner_target"),)


class DataWorkshopSkillSession(Base):
    __tablename__ = "data_workshop_skill_sessions"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("data_workshop_skills.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="新会话")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="idle", index=True)
    context_refs_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    messages_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    events_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    last_invocation_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    current_invocation_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    active_revision: Mapped[str | None] = mapped_column(String(160), nullable=True)
    artifact_metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False),
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        index=True,
    )

    skill: Mapped[DataWorkshopSkill] = relationship("DataWorkshopSkill", back_populates="sessions")
    revisions: Mapped[list[DataWorkshopSkillRevision]] = relationship(
        "DataWorkshopSkillRevision", back_populates="session", cascade="all, delete-orphan"
    )


class DataWorkshopSkillRevision(Base):
    __tablename__ = "data_workshop_skill_revisions"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("data_workshop_skills.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("data_workshop_skill_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision: Mapped[str] = mapped_column(String(160), nullable=False)
    artifact_metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    upstream_artifact_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    skill: Mapped[DataWorkshopSkill] = relationship("DataWorkshopSkill", back_populates="revisions")
    session: Mapped[DataWorkshopSkillSession] = relationship("DataWorkshopSkillSession", back_populates="revisions")

    __table_args__ = (UniqueConstraint("skill_id", "revision", name="uq_dw_skill_revision"),)
