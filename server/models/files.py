from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import TIMESTAMP, ForeignKey, Integer, LargeBinary, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.db.base import GUID, Base

if TYPE_CHECKING:
    from server.models.datasets import Dataset


def generate_uuid() -> UUID:
    return uuid4()


class File(Base):
    __tablename__ = "files"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)  # Legacy inline storage for small files
    type: Mapped[str] = mapped_column(Text, nullable=False)
    size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dataset_id: Mapped[UUID] = mapped_column(GUID(), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)  # Absolute path to on-disk file
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)  # Optional integrity hash (e.g., SHA256)
    optimized_storage_path: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # Path to materialized columnar copy
    optimized_format: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )  # Format of optimized copy (e.g., parquet)
    optimized_checksum: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )  # Integrity hash for optimized copy
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Cached row count after materialization
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)  # Original source URL if downloaded from URL
    uploaded_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.current_timestamp())

    dataset: Mapped[Dataset] = relationship(back_populates="files")
