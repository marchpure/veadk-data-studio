from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import TIMESTAMP, Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.db.base import GUID, Base

if TYPE_CHECKING:
    from server.models.user import User


def generate_uuid() -> UUID:
    return uuid4()


class SemanticModel(Base):
    __tablename__ = "semantic_models"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by: Mapped[UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    datasource_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    datasource_name: Mapped[str] = mapped_column(String(255), nullable=False)
    datasource_kind: Mapped[str] = mapped_column(String(64), nullable=False, default="oracle")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Draft")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    draft_revision: Mapped[str] = mapped_column(String(64), nullable=False, default="draft-1")
    published_version: Mapped[str] = mapped_column(String(64), nullable=False, default="v0")
    readiness: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    readiness_level: Mapped[str] = mapped_column(String(32), nullable=False, default="blocked")
    drift_alerts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consumers_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    explore_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    review_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    mcp_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    validation_log_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    entities: Mapped[list[SemanticModelEntity]] = relationship(
        back_populates="model", cascade="all, delete-orphan", order_by="SemanticModelEntity.sort_order"
    )
    relationships: Mapped[list[SemanticModelRelationship]] = relationship(
        back_populates="model", cascade="all, delete-orphan", order_by="SemanticModelRelationship.sort_order"
    )
    metrics: Mapped[list[SemanticModelMetric]] = relationship(
        back_populates="model", cascade="all, delete-orphan", order_by="SemanticModelMetric.sort_order"
    )
    dimensions: Mapped[list[SemanticModelDimension]] = relationship(
        back_populates="model", cascade="all, delete-orphan", order_by="SemanticModelDimension.sort_order"
    )
    versions: Mapped[list[SemanticModelVersion]] = relationship(
        back_populates="model", cascade="all, delete-orphan", order_by="SemanticModelVersion.created_at"
    )

    __table_args__ = (UniqueConstraint("tenant_id", "slug", name="uq_semantic_models_tenant_slug"),)


class SemanticModelEntity(Base):
    __tablename__ = "semantic_model_entities"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    model_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("semantic_models.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    business_name: Mapped[str] = mapped_column(String(255), nullable=False)
    table_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    primary_key: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, default="dimension")
    validation_status: Mapped[str] = mapped_column(String(32), nullable=False, default="valid")
    profile_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    lineage_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    permission_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    model: Mapped[SemanticModel] = relationship(back_populates="entities")
    fields: Mapped[list[SemanticModelField]] = relationship(
        back_populates="entity", cascade="all, delete-orphan", order_by="SemanticModelField.sort_order"
    )

    __table_args__ = (UniqueConstraint("model_id", "slug", name="uq_semantic_model_entities_model_slug"),)


class SemanticModelField(Base):
    __tablename__ = "semantic_model_fields"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    entity_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("semantic_model_entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    source_field: Mapped[str] = mapped_column(String(255), nullable=False)
    data_type: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False, default="attribute")
    nullable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    profile_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    entity: Mapped[SemanticModelEntity] = relationship(back_populates="fields")


class SemanticModelRelationship(Base):
    __tablename__ = "semantic_model_relationships"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    model_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("semantic_models.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    from_entity: Mapped[str] = mapped_column(String(120), nullable=False)
    to_entity: Mapped[str] = mapped_column(String(120), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    join_fields_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    cardinality: Mapped[str] = mapped_column(String(64), nullable=False)
    fk_evidence: Mapped[str] = mapped_column(Text, nullable=False, default="")
    unique_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    orphan_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    fanout_risk: Mapped[str] = mapped_column(String(32), nullable=False, default="low")
    validation_status: Mapped[str] = mapped_column(String(32), nullable=False, default="valid")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="confirmed")
    validation_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    model: Mapped[SemanticModel] = relationship(back_populates="relationships")

    __table_args__ = (UniqueConstraint("model_id", "slug", name="uq_semantic_model_relationships_model_slug"),)


class SemanticModelMetric(Base):
    __tablename__ = "semantic_model_metrics"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    model_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("semantic_models.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    business_name: Mapped[str] = mapped_column(String(255), nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False, default="")
    kind: Mapped[str] = mapped_column(String(64), nullable=False, default="measure")
    formula: Mapped[str] = mapped_column(Text, nullable=False)
    filter_expr: Mapped[str] = mapped_column(Text, nullable=False, default="")
    time_field: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    default_grain: Mapped[str] = mapped_column(String(32), nullable=False, default="month")
    dimensions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    unit: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    owner: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    certification: Mapped[str] = mapped_column(String(64), nullable=False, default="draft")
    lineage_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    preview_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    compiled_sql: Mapped[str] = mapped_column(Text, nullable=False, default="")
    validation_status: Mapped[str] = mapped_column(String(32), nullable=False, default="valid")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    model: Mapped[SemanticModel] = relationship(back_populates="metrics")

    __table_args__ = (UniqueConstraint("model_id", "slug", name="uq_semantic_model_metrics_model_slug"),)


class SemanticModelDimension(Base):
    __tablename__ = "semantic_model_dimensions"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    model_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("semantic_models.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_slug: Mapped[str] = mapped_column(String(120), nullable=False)
    field: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    model: Mapped[SemanticModel] = relationship(back_populates="dimensions")

    __table_args__ = (UniqueConstraint("model_id", "slug", name="uq_semantic_model_dimensions_model_slug"),)


class SemanticModelAuditEvent(Base):
    __tablename__ = "semantic_model_audit_events"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("semantic_models.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[UUID | None] = mapped_column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    details_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.current_timestamp())

    user: Mapped[User | None] = relationship("User")


class SemanticModelVersion(Base):
    __tablename__ = "semantic_model_versions"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("semantic_models.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_label: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    source_snapshot_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    physical_schema_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    review_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    published_by: Mapped[UUID | None] = mapped_column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.current_timestamp())

    model: Mapped[SemanticModel] = relationship(back_populates="versions")
    publisher: Mapped[User | None] = relationship("User")

    __table_args__ = (UniqueConstraint("model_id", "version_label", name="uq_semantic_model_versions_model_label"),)
