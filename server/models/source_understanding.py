from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import JSON, TIMESTAMP, CheckConstraint, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.db.base import GUID, Base

if TYPE_CHECKING:
    from server.models.connections import Connection
    from server.models.source_resources import SourceResource
    from server.models.source_snapshots import SourceSnapshot


def generate_uuid() -> UUID:
    return uuid4()


SOURCE_ANALYZER_PROVIDERS = ("database",)
SOURCE_UNDERSTANDING_RUN_STATUSES = ("running", "completed", "failed")
SOURCE_SKILL_CANDIDATE_TYPES = (
    "schema_map",
    "data_profile",
    "relationship",
    "data_truth",
    "quality_gotcha",
)
SOURCE_SKILL_REVIEW_STATUSES = ("suggested", "verified", "rejected", "stale")
SOURCE_SKILL_VALIDATION_STATUSES = ("not_run", "passed", "warning", "failed")


class SourceUnderstandingRun(Base):
    __tablename__ = "source_understanding_runs"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connection_id: Mapped[UUID | None] = mapped_column(
        GUID(), ForeignKey("connections.id", ondelete="SET NULL"), nullable=True, index=True
    )
    datasource_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="running", index=True)
    analyzer_version: Mapped[str] = mapped_column(String(100), nullable=False)
    source_snapshot_ids_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    summary_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    drift_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.current_timestamp())
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=False), nullable=True)

    connection: Mapped[Connection | None] = relationship("Connection", foreign_keys=[connection_id])
    candidates: Mapped[list[SourceSkillCandidate]] = relationship(
        "SourceSkillCandidate", back_populates="run", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("provider IN ('database')", name="ck_source_understanding_runs_provider"),
        CheckConstraint(
            f"status IN {SOURCE_UNDERSTANDING_RUN_STATUSES}", name="ck_source_understanding_runs_status"
        ),
    )


class SourceSkillCandidate(Base):
    __tablename__ = "source_skill_candidates"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("source_understanding_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resource_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("source_resources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    snapshot_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("source_snapshots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    candidate_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    structured_payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    evidence_ids_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    validation_status: Mapped[str] = mapped_column(String(30), nullable=False, default="not_run", index=True)
    validation_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    review_status: Mapped[str] = mapped_column(String(30), nullable=False, default="suggested", index=True)
    generator: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    reviewed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=False), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    run: Mapped[SourceUnderstandingRun] = relationship("SourceUnderstandingRun", back_populates="candidates")
    resource: Mapped[SourceResource] = relationship("SourceResource")
    snapshot: Mapped[SourceSnapshot] = relationship("SourceSnapshot")

    __table_args__ = (
        CheckConstraint(f"candidate_type IN {SOURCE_SKILL_CANDIDATE_TYPES}", name="ck_source_skill_candidates_type"),
        CheckConstraint(
            f"validation_status IN {SOURCE_SKILL_VALIDATION_STATUSES}",
            name="ck_source_skill_candidates_validation_status",
        ),
        CheckConstraint(f"review_status IN {SOURCE_SKILL_REVIEW_STATUSES}", name="ck_source_skill_candidates_review_status"),
    )
