from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import JSON, TIMESTAMP, CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.db.base import GUID, Base

if TYPE_CHECKING:
    from server.models.notebooks import Notebook
    from server.models.user import User


def generate_uuid() -> UUID:
    return uuid4()


ANALYSIS_ARTIFACT_STATUSES = ("draft", "review", "published", "archived")
ANALYSIS_ARTIFACT_BLOCK_TYPES = (
    "narrative",
    "metric",
    "chart",
    "table",
    "evidence",
    "finding",
    "recommendation",
)


class AnalysisArtifact(Base):
    __tablename__ = "analysis_artifacts"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    notebook_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False, default="")
    definition_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft", index=True)
    latest_result_snapshot_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    notebook: Mapped[Notebook] = relationship("Notebook")
    creator: Mapped[User | None] = relationship("User")

    __table_args__ = (
        CheckConstraint(f"status IN {ANALYSIS_ARTIFACT_STATUSES}", name="ck_analysis_artifacts_status"),
        UniqueConstraint("tenant_id", "notebook_id", "name", "version", name="uq_analysis_artifacts_version"),
    )
