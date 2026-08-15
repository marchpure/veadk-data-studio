from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, TIMESTAMP, Boolean, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from server.db.base import GUID, Base


class QueryCache(Base):
    """PostgreSQL-backed cache for query results."""

    __tablename__ = "query_cache"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    cache_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    query_id: Mapped[UUID] = mapped_column(GUID(), nullable=False, index=True)

    result_data: Mapped[dict] = mapped_column(JSON().with_variant(JSONB(), "postgresql"), nullable=False)

    ttl_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.current_timestamp())
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, index=True)

    has_filters: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (Index("ix_query_cache_query_expires", "query_id", "expires_at"),)
