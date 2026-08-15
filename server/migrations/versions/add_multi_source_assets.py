"""add multi-source asset contract tables

Revision ID: add_multi_source_assets
Revises: add_semantic_modeling_tables
Create Date: 2026-08-14

Phase 0 foundations for Source Resource/Snapshot, Knowledge Resource,
Evidence Fragment, Notebook Asset, and Analysis Artifact contracts.
"""

import sqlalchemy as sa
from alembic import op
from fastapi_users_db_sqlalchemy.generics import GUID

revision = "add_multi_source_assets"
down_revision = "add_semantic_modeling_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_resources",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("connection_id", GUID(), nullable=True),
        sa.Column("resource_type", sa.String(length=30), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("owner_id", GUID(), nullable=True),
        sa.Column("visibility", sa.String(length=30), nullable=False),
        sa.Column("sync_mode", sa.String(length=20), nullable=False),
        sa.Column("sync_config_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("latest_snapshot_id", GUID(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.CheckConstraint(
            "resource_type IN ('pdf', 'web', 'feishu_doc', 'feishu_sheet')",
            name=op.f("ck_source_resources_resource_type"),
        ),
        sa.CheckConstraint("sync_mode IN ('manual', 'scheduled')", name=op.f("ck_source_resources_sync_mode")),
        sa.CheckConstraint(
            "status IN ('pending', 'syncing', 'understanding', 'needs_confirmation', 'ready', 'failed')",
            name=op.f("ck_source_resources_status"),
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["connections.id"],
            name=op.f("fk_source_resources_connection_id_connections"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_source_resources_owner_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_source_resources_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_resources")),
    )
    op.create_index(op.f("ix_source_resources_tenant_id"), "source_resources", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_source_resources_connection_id"), "source_resources", ["connection_id"], unique=False)
    op.create_index(op.f("ix_source_resources_owner_id"), "source_resources", ["owner_id"], unique=False)
    op.create_index(op.f("ix_source_resources_status"), "source_resources", ["status"], unique=False)
    op.create_index(
        op.f("ix_source_resources_latest_snapshot_id"), "source_resources", ["latest_snapshot_id"], unique=False
    )

    op.create_table(
        "source_snapshots",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("resource_id", GUID(), nullable=False),
        sa.Column("external_revision", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("raw_storage_uri", sa.Text(), nullable=False),
        sa.Column("captured_at", sa.TIMESTAMP(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("parser_version", sa.String(length=100), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("error_json", sa.JSON(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'captured', 'parsed', 'indexed', 'failed')",
            name=op.f("ck_source_snapshots_status"),
        ),
        sa.ForeignKeyConstraint(
            ["resource_id"],
            ["source_resources.id"],
            name=op.f("fk_source_snapshots_resource_id_source_resources"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_source_snapshots_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_snapshots")),
    )
    op.create_index(op.f("ix_source_snapshots_tenant_id"), "source_snapshots", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_source_snapshots_resource_id"), "source_snapshots", ["resource_id"], unique=False)
    op.create_index(op.f("ix_source_snapshots_content_hash"), "source_snapshots", ["content_hash"], unique=False)
    op.create_index(op.f("ix_source_snapshots_status"), "source_snapshots", ["status"], unique=False)

    op.create_table(
        "knowledge_resources",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("resource_id", GUID(), nullable=False),
        sa.Column("snapshot_id", GUID(), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("provider_resource_id", sa.Text(), nullable=True),
        sa.Column("parse_status", sa.String(length=30), nullable=False),
        sa.Column("index_status", sa.String(length=30), nullable=False),
        sa.Column("completeness_score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.CheckConstraint(
            "parse_status IN ('pending', 'parsed', 'failed')",
            name=op.f("ck_knowledge_resources_parse_status"),
        ),
        sa.CheckConstraint(
            "index_status IN ('pending', 'indexed', 'failed')",
            name=op.f("ck_knowledge_resources_index_status"),
        ),
        sa.ForeignKeyConstraint(
            ["resource_id"],
            ["source_resources.id"],
            name=op.f("fk_knowledge_resources_resource_id_source_resources"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["source_snapshots.id"],
            name=op.f("fk_knowledge_resources_snapshot_id_source_snapshots"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_knowledge_resources_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_resources")),
    )
    op.create_index(op.f("ix_knowledge_resources_tenant_id"), "knowledge_resources", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_knowledge_resources_resource_id"), "knowledge_resources", ["resource_id"], unique=False)
    op.create_index(op.f("ix_knowledge_resources_snapshot_id"), "knowledge_resources", ["snapshot_id"], unique=False)

    op.create_table(
        "evidence_fragments",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("knowledge_resource_id", GUID(), nullable=False),
        sa.Column("snapshot_id", GUID(), nullable=False),
        sa.Column("fragment_type", sa.String(length=30), nullable=False),
        sa.Column("title_path", sa.JSON(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("locator_json", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.String(length=30), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.CheckConstraint(
            "fragment_type IN ('page', 'block', 'paragraph', 'table_region', 'sheet_range', 'url_section')",
            name=op.f("ck_evidence_fragments_fragment_type"),
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_resource_id"],
            ["knowledge_resources.id"],
            name=op.f("fk_evidence_fragments_knowledge_resource_id_knowledge_resources"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["source_snapshots.id"],
            name=op.f("fk_evidence_fragments_snapshot_id_source_snapshots"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_evidence_fragments_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence_fragments")),
    )
    op.create_index(op.f("ix_evidence_fragments_tenant_id"), "evidence_fragments", ["tenant_id"], unique=False)
    op.create_index(
        op.f("ix_evidence_fragments_knowledge_resource_id"),
        "evidence_fragments",
        ["knowledge_resource_id"],
        unique=False,
    )
    op.create_index(op.f("ix_evidence_fragments_snapshot_id"), "evidence_fragments", ["snapshot_id"], unique=False)

    op.create_table(
        "notebook_assets",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("notebook_id", GUID(), nullable=False),
        sa.Column("asset_type", sa.String(length=30), nullable=False),
        sa.Column("asset_id", GUID(), nullable=False),
        sa.Column("added_by", GUID(), nullable=True),
        sa.Column("added_at", sa.TIMESTAMP(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("usage_policy_json", sa.JSON(), nullable=True),
        sa.CheckConstraint(
            "asset_type IN ('dataset', 'semantic_model', 'knowledge_resource')",
            name=op.f("ck_notebook_assets_asset_type"),
        ),
        sa.ForeignKeyConstraint(
            ["added_by"],
            ["users.id"],
            name=op.f("fk_notebook_assets_added_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["notebook_id"],
            ["notebooks.id"],
            name=op.f("fk_notebook_assets_notebook_id_notebooks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notebook_assets")),
    )
    op.create_index(op.f("ix_notebook_assets_asset_id"), "notebook_assets", ["asset_id"], unique=False)

    op.create_table(
        "analysis_artifacts",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("notebook_id", GUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("objective", sa.Text(), nullable=True),
        sa.Column("definition_json", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("latest_result_snapshot_id", GUID(), nullable=True),
        sa.Column("created_by", GUID(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'review', 'published', 'archived')",
            name=op.f("ck_analysis_artifacts_status"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_analysis_artifacts_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["notebook_id"],
            ["notebooks.id"],
            name=op.f("fk_analysis_artifacts_notebook_id_notebooks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_analysis_artifacts_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analysis_artifacts")),
    )
    op.create_index(op.f("ix_analysis_artifacts_tenant_id"), "analysis_artifacts", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_analysis_artifacts_status"), "analysis_artifacts", ["status"], unique=False)
    op.create_index(op.f("ix_analysis_artifacts_created_by"), "analysis_artifacts", ["created_by"], unique=False)
    op.create_index(
        op.f("ix_analysis_artifacts_latest_result_snapshot_id"),
        "analysis_artifacts",
        ["latest_result_snapshot_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_analysis_artifacts_latest_result_snapshot_id"), table_name="analysis_artifacts")
    op.drop_index(op.f("ix_analysis_artifacts_created_by"), table_name="analysis_artifacts")
    op.drop_index(op.f("ix_analysis_artifacts_status"), table_name="analysis_artifacts")
    op.drop_index(op.f("ix_analysis_artifacts_tenant_id"), table_name="analysis_artifacts")
    op.drop_table("analysis_artifacts")

    op.drop_index(op.f("ix_notebook_assets_asset_id"), table_name="notebook_assets")
    op.drop_table("notebook_assets")

    op.drop_index(op.f("ix_evidence_fragments_snapshot_id"), table_name="evidence_fragments")
    op.drop_index(op.f("ix_evidence_fragments_knowledge_resource_id"), table_name="evidence_fragments")
    op.drop_index(op.f("ix_evidence_fragments_tenant_id"), table_name="evidence_fragments")
    op.drop_table("evidence_fragments")

    op.drop_index(op.f("ix_knowledge_resources_snapshot_id"), table_name="knowledge_resources")
    op.drop_index(op.f("ix_knowledge_resources_resource_id"), table_name="knowledge_resources")
    op.drop_index(op.f("ix_knowledge_resources_tenant_id"), table_name="knowledge_resources")
    op.drop_table("knowledge_resources")

    op.drop_index(op.f("ix_source_snapshots_status"), table_name="source_snapshots")
    op.drop_index(op.f("ix_source_snapshots_content_hash"), table_name="source_snapshots")
    op.drop_index(op.f("ix_source_snapshots_resource_id"), table_name="source_snapshots")
    op.drop_index(op.f("ix_source_snapshots_tenant_id"), table_name="source_snapshots")
    op.drop_table("source_snapshots")

    op.drop_index(op.f("ix_source_resources_latest_snapshot_id"), table_name="source_resources")
    op.drop_index(op.f("ix_source_resources_status"), table_name="source_resources")
    op.drop_index(op.f("ix_source_resources_owner_id"), table_name="source_resources")
    op.drop_index(op.f("ix_source_resources_connection_id"), table_name="source_resources")
    op.drop_index(op.f("ix_source_resources_tenant_id"), table_name="source_resources")
    op.drop_table("source_resources")
