from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import JSON, TIMESTAMP, CheckConstraint, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.db.base import GUID, Base

if TYPE_CHECKING:
    from server.models.source_resources import SourceResource
    from server.models.source_snapshots import SourceSnapshot


def generate_uuid() -> UUID:
    return uuid4()


KNOWLEDGE_PARSE_STATUSES = ("pending", "parsed", "failed")
KNOWLEDGE_INDEX_STATUSES = ("pending", "indexed", "failed")
EVIDENCE_FRAGMENT_TYPES = (
    "page",
    "block",
    "paragraph",
    "table_region",
    "sheet_range",
    "url_section",
    "document_section",
    "tos_object",
    "tos_prefix_entry",
    "csv_rows",
    "json_records",
    "parquet_rows",
    "excel_range",
    "html_section",
    "docx_paragraph",
    "raw_text",
    "database_catalog",
    "database_schema",
    "database_table",
    "database_column",
    "database_sample",
    "database_constraint",
)


class KnowledgeResource(Base):
    __tablename__ = "knowledge_resources"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resource_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("source_resources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    snapshot_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("source_snapshots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_resource_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    parse_status: Mapped[str] = mapped_column(String(30), nullable=False, default="parsed")
    index_status: Mapped[str] = mapped_column(String(30), nullable=False, default="indexed")
    completeness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.current_timestamp())

    resource: Mapped[SourceResource] = relationship("SourceResource")
    snapshot: Mapped[SourceSnapshot] = relationship("SourceSnapshot")
    evidence_fragments: Mapped[list[EvidenceFragment]] = relationship(
        "EvidenceFragment", back_populates="knowledge_resource", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(f"parse_status IN {KNOWLEDGE_PARSE_STATUSES}", name="ck_knowledge_resources_parse_status"),
        CheckConstraint(f"index_status IN {KNOWLEDGE_INDEX_STATUSES}", name="ck_knowledge_resources_index_status"),
    )


class EvidenceFragment(Base):
    __tablename__ = "evidence_fragments"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    knowledge_resource_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("knowledge_resources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    snapshot_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("source_snapshots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fragment_type: Mapped[str] = mapped_column(String(30), nullable=False)
    title_path: Mapped[list | None] = mapped_column(JSON, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    locator_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    confidence: Mapped[str | None] = mapped_column(String(30), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.current_timestamp())

    knowledge_resource: Mapped[KnowledgeResource] = relationship(
        "KnowledgeResource", back_populates="evidence_fragments"
    )
    snapshot: Mapped[SourceSnapshot] = relationship("SourceSnapshot")

    __table_args__ = (
        CheckConstraint(f"fragment_type IN {EVIDENCE_FRAGMENT_TYPES}", name="ck_evidence_fragments_fragment_type"),
    )
