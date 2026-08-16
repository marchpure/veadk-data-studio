"""Add semantic modeling persistence tables

Revision ID: add_semantic_modeling_tables
Revises: add_oracle_connection_type
Create Date: 2026-08-14
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "add_semantic_modeling_tables"
down_revision = "add_data_skill_agent_runs"
branch_labels = None
depends_on = None


def uuid_type():
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        return postgresql.UUID(as_uuid=True)
    return sa.String(36)


def ts():
    return sa.TIMESTAMP(timezone=False)


def upgrade() -> None:
    guid = uuid_type()

    op.create_table(
        "semantic_models",
        sa.Column("id", guid, nullable=False),
        sa.Column("tenant_id", guid, nullable=False),
        sa.Column("created_by", guid, nullable=True),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("owner", sa.String(length=255), nullable=False),
        sa.Column("datasource_id", sa.String(length=120), nullable=False),
        sa.Column("datasource_name", sa.String(length=255), nullable=False),
        sa.Column("datasource_kind", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="Draft"),
        sa.Column("draft_revision", sa.String(length=64), nullable=False, server_default="draft-1"),
        sa.Column("published_version", sa.String(length=64), nullable=False, server_default="v0"),
        sa.Column("readiness", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("readiness_level", sa.String(length=32), nullable=False, server_default="blocked"),
        sa.Column("drift_alerts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consumers_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("explore_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("review_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("mcp_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("validation_log_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", ts(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", ts(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_semantic_models_tenant_slug"),
    )
    op.create_index("ix_semantic_models_tenant_id", "semantic_models", ["tenant_id"])
    op.create_index("ix_semantic_models_created_by", "semantic_models", ["created_by"])
    op.create_index("ix_semantic_models_datasource_id", "semantic_models", ["datasource_id"])

    op.create_table(
        "semantic_model_entities",
        sa.Column("id", guid, nullable=False),
        sa.Column("model_id", guid, nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("business_name", sa.String(length=255), nullable=False),
        sa.Column("table_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("primary_key", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("entity_type", sa.String(length=32), nullable=False, server_default="dimension"),
        sa.Column("validation_status", sa.String(length=32), nullable=False, server_default="valid"),
        sa.Column("profile_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("lineage_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("permission_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["model_id"], ["semantic_models.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_id", "slug", name="uq_semantic_model_entities_model_slug"),
    )
    op.create_index("ix_semantic_model_entities_model_id", "semantic_model_entities", ["model_id"])

    op.create_table(
        "semantic_model_fields",
        sa.Column("id", guid, nullable=False),
        sa.Column("entity_id", guid, nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("source_field", sa.String(length=255), nullable=False),
        sa.Column("data_type", sa.String(length=120), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False, server_default="attribute"),
        sa.Column("nullable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("profile_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["entity_id"], ["semantic_model_entities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_semantic_model_fields_entity_id", "semantic_model_fields", ["entity_id"])

    op.create_table(
        "semantic_model_relationships",
        sa.Column("id", guid, nullable=False),
        sa.Column("model_id", guid, nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("from_entity", sa.String(length=120), nullable=False),
        sa.Column("to_entity", sa.String(length=120), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("join_fields_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("cardinality", sa.String(length=64), nullable=False),
        sa.Column("fk_evidence", sa.Text(), nullable=False, server_default=""),
        sa.Column("unique_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("orphan_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("fanout_risk", sa.String(length=32), nullable=False, server_default="low"),
        sa.Column("validation_status", sa.String(length=32), nullable=False, server_default="valid"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="confirmed"),
        sa.Column("validation_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("evidence_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["model_id"], ["semantic_models.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_id", "slug", name="uq_semantic_model_relationships_model_slug"),
    )
    op.create_index("ix_semantic_model_relationships_model_id", "semantic_model_relationships", ["model_id"])

    op.create_table(
        "semantic_model_metrics",
        sa.Column("id", guid, nullable=False),
        sa.Column("model_id", guid, nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("business_name", sa.String(length=255), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False, server_default=""),
        sa.Column("kind", sa.String(length=64), nullable=False, server_default="measure"),
        sa.Column("formula", sa.Text(), nullable=False),
        sa.Column("filter_expr", sa.Text(), nullable=False, server_default=""),
        sa.Column("time_field", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("default_grain", sa.String(length=32), nullable=False, server_default="month"),
        sa.Column("dimensions_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("unit", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("owner", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("certification", sa.String(length=64), nullable=False, server_default="draft"),
        sa.Column("lineage_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("preview_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("compiled_sql", sa.Text(), nullable=False, server_default=""),
        sa.Column("validation_status", sa.String(length=32), nullable=False, server_default="valid"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["model_id"], ["semantic_models.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_id", "slug", name="uq_semantic_model_metrics_model_slug"),
    )
    op.create_index("ix_semantic_model_metrics_model_id", "semantic_model_metrics", ["model_id"])

    op.create_table(
        "semantic_model_dimensions",
        sa.Column("id", guid, nullable=False),
        sa.Column("model_id", guid, nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("entity_slug", sa.String(length=120), nullable=False),
        sa.Column("field", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["model_id"], ["semantic_models.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_id", "slug", name="uq_semantic_model_dimensions_model_slug"),
    )
    op.create_index("ix_semantic_model_dimensions_model_id", "semantic_model_dimensions", ["model_id"])

    op.create_table(
        "semantic_model_calculated_fields",
        sa.Column("id", guid, nullable=False),
        sa.Column("model_id", guid, nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("entity_slug", sa.String(length=120), nullable=False),
        sa.Column("expression", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["model_id"], ["semantic_models.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_id", "slug", name="uq_semantic_model_calculated_fields_model_slug"),
    )
    op.create_index("ix_semantic_model_calculated_fields_model_id", "semantic_model_calculated_fields", ["model_id"])

    op.create_table(
        "semantic_model_suggestions",
        sa.Column("id", guid, nullable=False),
        sa.Column("model_id", guid, nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("suggestion_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("evidence_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("validation", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("edited_note", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["model_id"], ["semantic_models.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_id", "slug", name="uq_semantic_model_suggestions_model_slug"),
    )
    op.create_index("ix_semantic_model_suggestions_model_id", "semantic_model_suggestions", ["model_id"])

    op.create_table(
        "semantic_model_validation_results",
        sa.Column("id", guid, nullable=False),
        sa.Column("model_id", guid, nullable=False),
        sa.Column("result_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", ts(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["model_id"], ["semantic_models.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_semantic_model_validation_results_model_id", "semantic_model_validation_results", ["model_id"])

    op.create_table(
        "semantic_model_versions",
        sa.Column("id", guid, nullable=False),
        sa.Column("model_id", guid, nullable=False),
        sa.Column("version_label", sa.String(length=64), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("publish_notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", guid, nullable=True),
        sa.Column("created_at", ts(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("immutable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["model_id"], ["semantic_models.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_id", "version_label", name="uq_semantic_model_versions_model_label"),
    )
    op.create_index("ix_semantic_model_versions_model_id", "semantic_model_versions", ["model_id"])

    op.create_table(
        "semantic_model_publications",
        sa.Column("id", guid, nullable=False),
        sa.Column("model_id", guid, nullable=False),
        sa.Column("version_id", guid, nullable=False),
        sa.Column("version_label", sa.String(length=64), nullable=False),
        sa.Column("created_by", guid, nullable=True),
        sa.Column("published_at", ts(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["model_id"], ["semantic_models.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["version_id"], ["semantic_model_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "semantic_model_generation_jobs",
        sa.Column("id", guid, nullable=False),
        sa.Column("tenant_id", guid, nullable=False),
        sa.Column("created_by", guid, nullable=True),
        sa.Column("datasource_id", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("phase", sa.String(length=32), nullable=False, server_default="profile"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("steps_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("request_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("result_model_id", guid, nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", ts(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", ts(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["result_model_id"], ["semantic_models.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_semantic_model_generation_jobs_tenant_id", "semantic_model_generation_jobs", ["tenant_id"])
    op.create_index("ix_semantic_model_generation_jobs_created_by", "semantic_model_generation_jobs", ["created_by"])

    op.create_table(
        "semantic_model_consumers",
        sa.Column("id", guid, nullable=False),
        sa.Column("model_id", guid, nullable=False),
        sa.Column("version_label", sa.String(length=64), nullable=False),
        sa.Column("consumer_type", sa.String(length=64), nullable=False),
        sa.Column("reference_name", sa.String(length=255), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_by", guid, nullable=True),
        sa.Column("created_at", ts(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["model_id"], ["semantic_models.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_semantic_model_consumers_model_id", "semantic_model_consumers", ["model_id"])

    op.create_table(
        "semantic_model_audit_events",
        sa.Column("id", guid, nullable=False),
        sa.Column("tenant_id", guid, nullable=False),
        sa.Column("model_id", guid, nullable=True),
        sa.Column("user_id", guid, nullable=True),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", ts(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["model_id"], ["semantic_models.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_semantic_model_audit_events_tenant_id", "semantic_model_audit_events", ["tenant_id"])
    op.create_index("ix_semantic_model_audit_events_model_id", "semantic_model_audit_events", ["model_id"])


def downgrade() -> None:
    op.drop_index("ix_semantic_model_audit_events_model_id", table_name="semantic_model_audit_events")
    op.drop_index("ix_semantic_model_audit_events_tenant_id", table_name="semantic_model_audit_events")
    op.drop_table("semantic_model_audit_events")
    op.drop_index("ix_semantic_model_consumers_model_id", table_name="semantic_model_consumers")
    op.drop_table("semantic_model_consumers")
    op.drop_index("ix_semantic_model_generation_jobs_created_by", table_name="semantic_model_generation_jobs")
    op.drop_index("ix_semantic_model_generation_jobs_tenant_id", table_name="semantic_model_generation_jobs")
    op.drop_table("semantic_model_generation_jobs")
    op.drop_table("semantic_model_publications")
    op.drop_index("ix_semantic_model_versions_model_id", table_name="semantic_model_versions")
    op.drop_table("semantic_model_versions")
    op.drop_index("ix_semantic_model_validation_results_model_id", table_name="semantic_model_validation_results")
    op.drop_table("semantic_model_validation_results")
    op.drop_index("ix_semantic_model_suggestions_model_id", table_name="semantic_model_suggestions")
    op.drop_table("semantic_model_suggestions")
    op.drop_index("ix_semantic_model_calculated_fields_model_id", table_name="semantic_model_calculated_fields")
    op.drop_table("semantic_model_calculated_fields")
    op.drop_index("ix_semantic_model_dimensions_model_id", table_name="semantic_model_dimensions")
    op.drop_table("semantic_model_dimensions")
    op.drop_index("ix_semantic_model_metrics_model_id", table_name="semantic_model_metrics")
    op.drop_table("semantic_model_metrics")
    op.drop_index("ix_semantic_model_relationships_model_id", table_name="semantic_model_relationships")
    op.drop_table("semantic_model_relationships")
    op.drop_index("ix_semantic_model_fields_entity_id", table_name="semantic_model_fields")
    op.drop_table("semantic_model_fields")
    op.drop_index("ix_semantic_model_entities_model_id", table_name="semantic_model_entities")
    op.drop_table("semantic_model_entities")
    op.drop_index("ix_semantic_models_datasource_id", table_name="semantic_models")
    op.drop_index("ix_semantic_models_created_by", table_name="semantic_models")
    op.drop_index("ix_semantic_models_tenant_id", table_name="semantic_models")
    op.drop_table("semantic_models")
