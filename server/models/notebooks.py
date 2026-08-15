from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import JSON, TIMESTAMP, CheckConstraint, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.db.base import GUID, Base

if TYPE_CHECKING:
    from server.models.dashboard import Dashboard
    from server.models.datasets import Dataset
    from server.models.queries import Query
    from server.models.threads import Thread
    from server.models.user import User


def generate_uuid() -> UUID:
    return uuid4()


class NotebookDataset(Base):
    __tablename__ = "notebook_datasets"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    notebook_id: Mapped[UUID] = mapped_column(GUID(), ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False)
    dataset_id: Mapped[UUID] = mapped_column(GUID(), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.current_timestamp())

    notebook: Mapped[Notebook] = relationship("Notebook", back_populates="notebook_datasets")
    dataset: Mapped[Dataset] = relationship("Dataset", back_populates="notebook_datasets")


NOTEBOOK_ASSET_TYPES = ("dataset", "semantic_model", "knowledge_resource")


class NotebookAsset(Base):
    __tablename__ = "notebook_assets"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    notebook_id: Mapped[UUID] = mapped_column(GUID(), ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(30), nullable=False)
    asset_id: Mapped[UUID] = mapped_column(GUID(), nullable=False, index=True)
    added_by: Mapped[UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    added_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.current_timestamp())
    usage_policy_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    notebook: Mapped[Notebook] = relationship("Notebook", back_populates="notebook_assets")

    __table_args__ = (
        CheckConstraint(f"asset_type IN {NOTEBOOK_ASSET_TYPES}", name="ck_notebook_assets_asset_type"),
    )


class Notebook(Base):
    __tablename__ = "notebooks"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by: Mapped[UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    notebook_name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_used_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_used_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    claude_session_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # For Claude Agent SDK conversation continuity
    filters_config: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # JSON storage for dashboard filter definitions
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    threads: Mapped[list[Thread]] = relationship(back_populates="notebook", cascade="all, delete-orphan")
    notebook_datasets: Mapped[list[NotebookDataset]] = relationship(
        back_populates="notebook", cascade="all, delete-orphan"
    )
    notebook_assets: Mapped[list[NotebookAsset]] = relationship(
        back_populates="notebook", cascade="all, delete-orphan"
    )
    dashboards: Mapped[list[Dashboard]] = relationship(back_populates="notebook", cascade="all, delete-orphan")
    queries: Mapped[list[Query]] = relationship(back_populates="notebook", cascade="all, delete-orphan")
    creator: Mapped[User | None] = relationship("User", foreign_keys=[created_by])
