from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import TIMESTAMP, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from server.db.base import GUID, Base


def generate_uuid() -> UUID:
    return uuid4()


class DatasourceAnnotation(Base):
    """
    Model for storing user annotations on datasource schemas.

    Supports two types of annotations:
    - table_description: Semantic description of what a table represents
    - column_annotation: Annotation/note about what a specific column contains
    """

    __tablename__ = "datasource_annotations"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    datasource_id: Mapped[UUID] = mapped_column(GUID(), nullable=False, index=True)
    table_name: Mapped[str] = mapped_column(String(255), nullable=False)
    column_name: Mapped[str | None] = mapped_column(String(255), nullable=True)  # NULL for table-level annotations
    annotation_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'table_description' or 'column_annotation'
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )
