from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    CheckConstraint,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.db.base import GUID, Base

if TYPE_CHECKING:
    from server.models.connections import Connection
    from server.models.files import File
    from server.models.notebooks import NotebookDataset


def generate_uuid() -> UUID:
    return uuid4()


DATASET_TYPES = ("connection", "file", "skill_api")


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by: Mapped[UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    connection_id: Mapped[UUID | None] = mapped_column(
        GUID(), ForeignKey("connections.id", ondelete="CASCADE"), nullable=True
    )
    storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)  # Root directory for dataset assets
    duckdb_path: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # Path to dedicated DuckDB catalog (if materialized)
    skill_name: Mapped[str | None] = mapped_column(String(50), nullable=True)  # For skill_api type
    skill_scope: Mapped[str | None] = mapped_column(String(10), nullable=True)  # "user" or "org" for skill_api type
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.current_timestamp())
    schema_cache: Mapped[str | None] = mapped_column(Text, nullable=True)  # Cached schema JSON for file datasets
    schema_updated_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=False), nullable=True
    )  # Last schema update time
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    # Relationships
    connection: Mapped[Connection | None] = relationship("Connection", foreign_keys=[connection_id])
    files: Mapped[list[File]] = relationship(back_populates="dataset", cascade="all, delete-orphan")
    notebook_datasets: Mapped[list[NotebookDataset]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(f"type IN {DATASET_TYPES}", name="ck_datasets_type"),
        CheckConstraint(
            "(type='connection' AND connection_id IS NOT NULL) OR "
            "(type='file') OR "
            "(type='skill_api' AND skill_name IS NOT NULL)",
            name="ck_datasets_type_refs",
        ),
    )
