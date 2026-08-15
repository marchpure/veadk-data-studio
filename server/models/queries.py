from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import TIMESTAMP, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.db.base import GUID, Base

QUERY_TYPES = ("sql", "nosql", "api")

if TYPE_CHECKING:
    from server.models.datasets import Dataset
    from server.models.notebooks import Notebook


def generate_uuid() -> UUID:
    return uuid4()


class Query(Base):
    __tablename__ = "queries"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by: Mapped[UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    output_schema: Mapped[str] = mapped_column(Text, nullable=False)

    # Reference datasets (unified abstraction for both connections and files)
    # Nullable for API-type queries which use skills instead of datasets
    dataset_id: Mapped[UUID | None] = mapped_column(
        GUID(), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=True
    )

    notebook_id: Mapped[UUID] = mapped_column(GUID(), ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False)

    # Query type discriminator: "sql" | "nosql" | "api"
    query_type: Mapped[str] = mapped_column(String(10), default="sql", nullable=False)

    # Skill-based query fields (for query_type="api")
    skill_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    skill_scope: Mapped[str | None] = mapped_column(String(10), nullable=True)
    api_config: Mapped[str | None] = mapped_column(Text, nullable=True)
    filter_contract: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    dataset: Mapped[Dataset] = relationship("Dataset")
    notebook: Mapped[Notebook] = relationship("Notebook", back_populates="queries")
