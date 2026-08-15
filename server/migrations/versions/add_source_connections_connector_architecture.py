"""add source connections connector architecture

Revision ID: add_source_connections_arch
Revises: add_multi_source_assets
Create Date: 2026-08-14
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op
from fastapi_users_db_sqlalchemy.generics import GUID

revision = "add_source_connections_arch"
down_revision = "add_multi_source_assets"
branch_labels = None
depends_on = None

MARKER_TABLE = "_source_connector_migration_state"

SOURCE_RESOURCE_TYPES_OLD = (
    "pdf",
    "web",
    "feishu_doc",
    "feishu_wiki",
    "feishu_sheet",
    "extracted_table",
    "database_catalog",
    "database_schema",
    "database_table",
)
SOURCE_RESOURCE_TYPES_NEW = (
    "pdf",
    "web",
    "feishu_doc",
    "feishu_wiki",
    "feishu_sheet",
    "feishu_base",
    "tos_bucket",
    "tos_prefix",
    "tos_object",
    "extracted_table",
    "database_catalog",
    "database_schema",
    "database_table",
)
SOURCE_RESOURCE_STATUSES_OLD = ("pending", "syncing", "understanding", "needs_confirmation", "ready", "failed")
SOURCE_RESOURCE_STATUSES_NEW = (
    "pending",
    "syncing",
    "understanding",
    "authorization_required",
    "reauthorization_required",
    "source_unavailable",
    "permission_lost",
    "needs_confirmation",
    "ready",
    "failed",
)
EVIDENCE_FRAGMENT_TYPES_OLD = (
    "page",
    "block",
    "paragraph",
    "table_region",
    "sheet_range",
    "url_section",
    "document_section",
    "raw_text",
    "database_catalog",
    "database_schema",
    "database_table",
    "database_column",
    "database_sample",
    "database_constraint",
)
EVIDENCE_FRAGMENT_TYPES_NEW = (
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


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table_name: str) -> set[str]:
    if table_name not in _tables():
        return set()
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _check_names(table_name: str) -> set[str]:
    if table_name not in _tables():
        return set()
    return {item["name"] for item in sa.inspect(op.get_bind()).get_check_constraints(table_name) if item.get("name")}


def _unique_names(table_name: str) -> set[str]:
    if table_name not in _tables():
        return set()
    return {item["name"] for item in sa.inspect(op.get_bind()).get_unique_constraints(table_name) if item.get("name")}


def _ensure_marker_table() -> None:
    if MARKER_TABLE not in _tables():
        op.create_table(
            MARKER_TABLE,
            sa.Column("key", sa.String(length=120), nullable=False),
            sa.Column("value", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("key"),
        )


def _mark_created_tables(table_names: list[str]) -> None:
    _ensure_marker_table()
    op.execute(
        sa.text(f"INSERT INTO {MARKER_TABLE} (key, value) VALUES (:key, :value)").bindparams(
            key="created_tables",
            value=json.dumps(table_names),
        )
    )


def _created_tables_from_marker() -> set[str]:
    if MARKER_TABLE not in _tables():
        return set()
    result = op.get_bind().execute(sa.text(f"SELECT value FROM {MARKER_TABLE} WHERE key = :key"), {"key": "created_tables"})
    row = result.fetchone()
    if not row:
        return set()
    try:
        return set(json.loads(row[0]))
    except Exception:
        return set()


def upgrade() -> None:
    created: list[str] = []
    existing = _tables()
    if "source_connections" not in existing:
        _create_source_connections()
        created.append("source_connections")
    if "source_resources" not in existing:
        _create_source_resources()
        created.append("source_resources")
    else:
        _alter_existing_source_resources()
    if "source_snapshots" not in existing:
        _create_source_snapshots()
        created.append("source_snapshots")
    if "knowledge_resources" not in existing:
        _create_knowledge_resources()
        created.append("knowledge_resources")
    if "evidence_fragments" not in existing:
        _create_evidence_fragments()
        created.append("evidence_fragments")
    else:
        _alter_existing_evidence_fragments()
    if "source_understanding_runs" not in existing:
        _create_source_understanding_runs()
        created.append("source_understanding_runs")
    if "source_skill_candidates" not in existing:
        _create_source_skill_candidates()
        created.append("source_skill_candidates")
    if "semantic_models" not in existing:
        _create_semantic_model_tables(created)
    else:
        _alter_existing_semantic_model_tables()
    if "notebook_assets" not in existing:
        _create_notebook_assets()
        created.append("notebook_assets")
    else:
        _alter_existing_notebook_assets()
    if "analysis_artifacts" not in existing:
        _create_analysis_artifacts()
        created.append("analysis_artifacts")
    else:
        _alter_existing_analysis_artifacts()
    _mark_created_tables(created)


def downgrade() -> None:
    created = _created_tables_from_marker()
    if "evidence_fragments" not in created and "evidence_fragments" in _tables():
        _revert_existing_evidence_fragments()
    if "source_resources" not in created and "source_resources" in _tables():
        _revert_existing_source_resources()

    for table_name in (
        "analysis_artifacts",
        "notebook_assets",
        "semantic_model_audit_events",
        "semantic_model_versions",
        "semantic_model_dimensions",
        "semantic_model_metrics",
        "semantic_model_relationships",
        "semantic_model_fields",
        "semantic_model_entities",
        "semantic_models",
        "source_skill_candidates",
        "source_understanding_runs",
        "evidence_fragments",
        "knowledge_resources",
        "source_snapshots",
        "source_resources",
        "source_connections",
    ):
        if table_name in created and table_name in _tables():
            op.drop_table(table_name)
    if MARKER_TABLE in _tables():
        op.drop_table(MARKER_TABLE)


def _create_source_connections() -> None:
    op.create_table(
        "source_connections",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("provider", sa.String(length=60), nullable=False),
        sa.Column("auth_mode", sa.String(length=30), nullable=False),
        sa.Column("encrypted_credentials", sa.Text(), nullable=False),
        sa.Column("external_account_id", sa.Text(), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("capabilities_json", sa.JSON(), nullable=False),
        sa.Column("token_expires_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("created_by", GUID(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("provider IN ('feishu', 'volcengine_tos')", name=op.f("ck_source_connections_provider")),
        sa.CheckConstraint("auth_mode IN ('oauth', 'access_key', 'sts', 'none')", name=op.f("ck_source_connections_auth_mode")),
        sa.CheckConstraint(
            "status IN ('connected', 'pending', 'reauthorization_required', 'authorization_required', 'failed', 'disconnected')",
            name=op.f("ck_source_connections_status"),
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_source_connections_created_by_users"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_source_connections_tenant_id_tenants"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_connections")),
        sa.UniqueConstraint("tenant_id", "provider", "created_by", "external_account_id", name="uq_source_connections_account"),
    )
    op.create_index(op.f("ix_source_connections_tenant_id"), "source_connections", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_source_connections_provider"), "source_connections", ["provider"], unique=False)
    op.create_index(op.f("ix_source_connections_status"), "source_connections", ["status"], unique=False)
    op.create_index(op.f("ix_source_connections_created_by"), "source_connections", ["created_by"], unique=False)
    op.create_index(op.f("ix_source_connections_token_expires_at"), "source_connections", ["token_expires_at"], unique=False)


def _create_source_resources() -> None:
    op.create_table(
        "source_resources",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("connection_id", GUID(), nullable=True),
        sa.Column("source_connection_id", GUID(), nullable=True),
        sa.Column("resource_type", sa.String(length=30), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("parent_external_id", sa.Text(), nullable=True),
        sa.Column("selection_config_json", sa.JSON(), nullable=True),
        sa.Column("owner_id", GUID(), nullable=True),
        sa.Column("visibility", sa.String(length=30), nullable=False),
        sa.Column("sync_mode", sa.String(length=20), nullable=False),
        sa.Column("sync_config_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("latest_snapshot_id", GUID(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint(f"resource_type IN {SOURCE_RESOURCE_TYPES_NEW}", name=op.f("ck_source_resources_resource_type")),
        sa.CheckConstraint("sync_mode IN ('manual', 'scheduled')", name=op.f("ck_source_resources_sync_mode")),
        sa.CheckConstraint(f"status IN {SOURCE_RESOURCE_STATUSES_NEW}", name=op.f("ck_source_resources_status")),
        sa.ForeignKeyConstraint(["connection_id"], ["connections.id"], name=op.f("fk_source_resources_connection_id_connections"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_connection_id"], ["source_connections.id"], name=op.f("fk_source_resources_source_connection_id_source_connections"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name=op.f("fk_source_resources_owner_id_users"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_source_resources_tenant_id_tenants"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_resources")),
    )
    for column in ("tenant_id", "connection_id", "source_connection_id", "owner_id", "status", "latest_snapshot_id"):
        op.create_index(op.f(f"ix_source_resources_{column}"), "source_resources", [column], unique=False)


def _alter_existing_source_resources() -> None:
    columns = _columns("source_resources")
    checks = _check_names("source_resources")
    if op.get_bind().dialect.name == "postgresql":
        if "source_connection_id" not in columns:
            op.add_column("source_resources", sa.Column("source_connection_id", GUID(), nullable=True))
            op.create_foreign_key(
                "fk_source_resources_source_connection_id_source_connections",
                "source_resources",
                "source_connections",
                ["source_connection_id"],
                ["id"],
                ondelete="SET NULL",
            )
            op.create_index("ix_source_resources_source_connection_id", "source_resources", ["source_connection_id"])
        if "parent_external_id" not in columns:
            op.add_column("source_resources", sa.Column("parent_external_id", sa.Text(), nullable=True))
        if "selection_config_json" not in columns:
            op.add_column("source_resources", sa.Column("selection_config_json", sa.JSON(), nullable=True))
        op.execute(sa.text("ALTER TABLE source_resources DROP CONSTRAINT IF EXISTS ck_source_resources_resource_type"))
        op.execute(sa.text("ALTER TABLE source_resources DROP CONSTRAINT IF EXISTS ck_source_resources_ck_source_resources_resource_type"))
        op.execute(
            sa.text(
                f"""
                ALTER TABLE source_resources
                ADD CONSTRAINT ck_source_resources_resource_type
                CHECK (resource_type IN {SOURCE_RESOURCE_TYPES_NEW})
                """
            )
        )
        op.execute(sa.text("ALTER TABLE source_resources DROP CONSTRAINT IF EXISTS ck_source_resources_status"))
        op.execute(sa.text("ALTER TABLE source_resources DROP CONSTRAINT IF EXISTS ck_source_resources_ck_source_resources_status"))
        op.execute(
            sa.text(
                f"""
                ALTER TABLE source_resources
                ADD CONSTRAINT ck_source_resources_status
                CHECK (status IN {SOURCE_RESOURCE_STATUSES_NEW})
                """
            )
        )
        return

    with op.batch_alter_table("source_resources") as batch_op:
        if "source_connection_id" not in columns:
            batch_op.add_column(sa.Column("source_connection_id", GUID(), nullable=True))
            batch_op.create_foreign_key(
                "fk_source_resources_source_connection_id_source_connections",
                "source_connections",
                ["source_connection_id"],
                ["id"],
                ondelete="SET NULL",
            )
            batch_op.create_index("ix_source_resources_source_connection_id", ["source_connection_id"])
        if "parent_external_id" not in columns:
            batch_op.add_column(sa.Column("parent_external_id", sa.Text(), nullable=True))
        if "selection_config_json" not in columns:
            batch_op.add_column(sa.Column("selection_config_json", sa.JSON(), nullable=True))
        if "ck_source_resources_resource_type" in checks:
            batch_op.drop_constraint("ck_source_resources_resource_type", type_="check")
        batch_op.create_check_constraint("ck_source_resources_resource_type", f"resource_type IN {SOURCE_RESOURCE_TYPES_NEW}")
        if "ck_source_resources_status" in checks:
            batch_op.drop_constraint("ck_source_resources_status", type_="check")
        batch_op.create_check_constraint("ck_source_resources_status", f"status IN {SOURCE_RESOURCE_STATUSES_NEW}")


def _revert_existing_source_resources() -> None:
    columns = _columns("source_resources")
    checks = _check_names("source_resources")
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("ALTER TABLE source_resources DROP CONSTRAINT IF EXISTS ck_source_resources_resource_type"))
        op.execute(sa.text("ALTER TABLE source_resources DROP CONSTRAINT IF EXISTS ck_source_resources_ck_source_resources_resource_type"))
        op.execute(
            sa.text(
                f"""
                ALTER TABLE source_resources
                ADD CONSTRAINT ck_source_resources_resource_type
                CHECK (resource_type IN {SOURCE_RESOURCE_TYPES_OLD})
                """
            )
        )
        op.execute(sa.text("ALTER TABLE source_resources DROP CONSTRAINT IF EXISTS ck_source_resources_status"))
        op.execute(sa.text("ALTER TABLE source_resources DROP CONSTRAINT IF EXISTS ck_source_resources_ck_source_resources_status"))
        op.execute(
            sa.text(
                f"""
                ALTER TABLE source_resources
                ADD CONSTRAINT ck_source_resources_status
                CHECK (status IN {SOURCE_RESOURCE_STATUSES_OLD})
                """
            )
        )
        if "source_connection_id" in columns:
            op.drop_index("ix_source_resources_source_connection_id", table_name="source_resources")
            op.drop_constraint("fk_source_resources_source_connection_id_source_connections", "source_resources", type_="foreignkey")
            op.drop_column("source_resources", "source_connection_id")
        if "selection_config_json" in columns:
            op.drop_column("source_resources", "selection_config_json")
        if "parent_external_id" in columns:
            op.drop_column("source_resources", "parent_external_id")
        return

    with op.batch_alter_table("source_resources") as batch_op:
        if "ck_source_resources_resource_type" in checks:
            batch_op.drop_constraint("ck_source_resources_resource_type", type_="check")
        batch_op.create_check_constraint("ck_source_resources_resource_type", f"resource_type IN {SOURCE_RESOURCE_TYPES_OLD}")
        if "ck_source_resources_status" in checks:
            batch_op.drop_constraint("ck_source_resources_status", type_="check")
        batch_op.create_check_constraint("ck_source_resources_status", f"status IN {SOURCE_RESOURCE_STATUSES_OLD}")
        if "source_connection_id" in columns:
            batch_op.drop_index("ix_source_resources_source_connection_id")
            batch_op.drop_constraint("fk_source_resources_source_connection_id_source_connections", type_="foreignkey")
            batch_op.drop_column("source_connection_id")
        if "selection_config_json" in columns:
            batch_op.drop_column("selection_config_json")
        if "parent_external_id" in columns:
            batch_op.drop_column("parent_external_id")


def _create_source_snapshots() -> None:
    op.create_table(
        "source_snapshots",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("resource_id", GUID(), nullable=False),
        sa.Column("external_revision", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("raw_storage_uri", sa.Text(), nullable=False),
        sa.Column("captured_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("parser_version", sa.String(length=100), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("error_json", sa.JSON(), nullable=True),
        sa.CheckConstraint("status IN ('pending', 'captured', 'parsed', 'indexed', 'failed')", name=op.f("ck_source_snapshots_status")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_source_snapshots_tenant_id_tenants"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resource_id"], ["source_resources.id"], name=op.f("fk_source_snapshots_resource_id_source_resources"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_snapshots")),
    )
    for column in ("tenant_id", "resource_id", "content_hash", "status"):
        op.create_index(op.f(f"ix_source_snapshots_{column}"), "source_snapshots", [column], unique=False)


def _create_knowledge_resources() -> None:
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
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("parse_status IN ('pending', 'parsed', 'failed')", name=op.f("ck_knowledge_resources_parse_status")),
        sa.CheckConstraint("index_status IN ('pending', 'indexed', 'failed')", name=op.f("ck_knowledge_resources_index_status")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_knowledge_resources_tenant_id_tenants"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resource_id"], ["source_resources.id"], name=op.f("fk_knowledge_resources_resource_id_source_resources"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["source_snapshots.id"], name=op.f("fk_knowledge_resources_snapshot_id_source_snapshots"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_resources")),
    )
    for column in ("tenant_id", "resource_id", "snapshot_id"):
        op.create_index(op.f(f"ix_knowledge_resources_{column}"), "knowledge_resources", [column], unique=False)


def _create_evidence_fragments() -> None:
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
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint(f"fragment_type IN {EVIDENCE_FRAGMENT_TYPES_NEW}", name=op.f("ck_evidence_fragments_fragment_type")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_evidence_fragments_tenant_id_tenants"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["knowledge_resource_id"], ["knowledge_resources.id"], name=op.f("fk_evidence_fragments_knowledge_resource_id_knowledge_resources"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["source_snapshots.id"], name=op.f("fk_evidence_fragments_snapshot_id_source_snapshots"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence_fragments")),
    )
    for column in ("tenant_id", "knowledge_resource_id", "snapshot_id"):
        op.create_index(op.f(f"ix_evidence_fragments_{column}"), "evidence_fragments", [column], unique=False)


def _alter_existing_evidence_fragments() -> None:
    checks = _check_names("evidence_fragments")
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("ALTER TABLE evidence_fragments DROP CONSTRAINT IF EXISTS ck_evidence_fragments_fragment_type"))
        op.execute(
            sa.text(
                "ALTER TABLE evidence_fragments DROP CONSTRAINT IF EXISTS "
                "ck_evidence_fragments_ck_evidence_fragments_fragment_type"
            )
        )
        op.execute(
            sa.text(
                f"""
                ALTER TABLE evidence_fragments
                ADD CONSTRAINT ck_evidence_fragments_fragment_type
                CHECK (fragment_type IN {EVIDENCE_FRAGMENT_TYPES_NEW})
                """
            )
        )
        return

    with op.batch_alter_table("evidence_fragments") as batch_op:
        if "ck_evidence_fragments_fragment_type" in checks:
            batch_op.drop_constraint("ck_evidence_fragments_fragment_type", type_="check")
        batch_op.create_check_constraint("ck_evidence_fragments_fragment_type", f"fragment_type IN {EVIDENCE_FRAGMENT_TYPES_NEW}")


def _revert_existing_evidence_fragments() -> None:
    checks = _check_names("evidence_fragments")
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("ALTER TABLE evidence_fragments DROP CONSTRAINT IF EXISTS ck_evidence_fragments_fragment_type"))
        op.execute(
            sa.text(
                "ALTER TABLE evidence_fragments DROP CONSTRAINT IF EXISTS "
                "ck_evidence_fragments_ck_evidence_fragments_fragment_type"
            )
        )
        op.execute(
            sa.text(
                f"""
                ALTER TABLE evidence_fragments
                ADD CONSTRAINT ck_evidence_fragments_fragment_type
                CHECK (fragment_type IN {EVIDENCE_FRAGMENT_TYPES_OLD})
                """
            )
        )
        return

    with op.batch_alter_table("evidence_fragments") as batch_op:
        if "ck_evidence_fragments_fragment_type" in checks:
            batch_op.drop_constraint("ck_evidence_fragments_fragment_type", type_="check")
        batch_op.create_check_constraint("ck_evidence_fragments_fragment_type", f"fragment_type IN {EVIDENCE_FRAGMENT_TYPES_OLD}")


def _create_source_understanding_runs() -> None:
    op.create_table(
        "source_understanding_runs",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("connection_id", GUID(), nullable=True),
        sa.Column("datasource_id", sa.String(length=120), nullable=False),
        sa.Column("provider", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("analyzer_version", sa.String(length=100), nullable=False),
        sa.Column("source_snapshot_ids_json", sa.JSON(), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("drift_json", sa.JSON(), nullable=False),
        sa.Column("error_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("completed_at", sa.TIMESTAMP(), nullable=True),
        sa.CheckConstraint("provider IN ('database')", name=op.f("ck_source_understanding_runs_provider")),
        sa.CheckConstraint("status IN ('running', 'completed', 'failed')", name=op.f("ck_source_understanding_runs_status")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_source_understanding_runs_tenant_id_tenants"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["connection_id"], ["connections.id"], name=op.f("fk_source_understanding_runs_connection_id_connections"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_understanding_runs")),
    )
    for column in ("tenant_id", "connection_id", "datasource_id", "status"):
        op.create_index(op.f(f"ix_source_understanding_runs_{column}"), "source_understanding_runs", [column], unique=False)


def _create_source_skill_candidates() -> None:
    op.create_table(
        "source_skill_candidates",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("run_id", GUID(), nullable=False),
        sa.Column("resource_id", GUID(), nullable=False),
        sa.Column("snapshot_id", GUID(), nullable=False),
        sa.Column("source_id", sa.String(length=120), nullable=False),
        sa.Column("candidate_type", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("structured_payload_json", sa.JSON(), nullable=False),
        sa.Column("evidence_ids_json", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("validation_status", sa.String(length=30), nullable=False),
        sa.Column("validation_json", sa.JSON(), nullable=False),
        sa.Column("review_status", sa.String(length=30), nullable=False),
        sa.Column("generator", sa.String(length=120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("reviewed_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("candidate_type IN ('schema_map', 'data_profile', 'relationship', 'data_truth', 'quality_gotcha')", name=op.f("ck_source_skill_candidates_type")),
        sa.CheckConstraint("validation_status IN ('not_run', 'passed', 'warning', 'failed')", name=op.f("ck_source_skill_candidates_validation_status")),
        sa.CheckConstraint("review_status IN ('suggested', 'verified', 'rejected', 'stale')", name=op.f("ck_source_skill_candidates_review_status")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_source_skill_candidates_tenant_id_tenants"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["source_understanding_runs.id"], name=op.f("fk_source_skill_candidates_run_id_source_understanding_runs"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resource_id"], ["source_resources.id"], name=op.f("fk_source_skill_candidates_resource_id_source_resources"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["source_snapshots.id"], name=op.f("fk_source_skill_candidates_snapshot_id_source_snapshots"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_skill_candidates")),
    )
    for column in ("tenant_id", "run_id", "resource_id", "snapshot_id", "source_id", "candidate_type", "validation_status", "review_status"):
        op.create_index(op.f(f"ix_source_skill_candidates_{column}"), "source_skill_candidates", [column], unique=False)


def _create_semantic_model_tables(created: list[str]) -> None:
    op.create_table(
        "semantic_models",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("created_by", GUID(), nullable=True),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("owner", sa.String(length=255), nullable=False),
        sa.Column("datasource_id", sa.String(length=120), nullable=False),
        sa.Column("datasource_name", sa.String(length=255), nullable=False),
        sa.Column("datasource_kind", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("draft_revision", sa.String(length=64), nullable=False),
        sa.Column("published_version", sa.String(length=64), nullable=False),
        sa.Column("readiness", sa.Integer(), nullable=False),
        sa.Column("readiness_level", sa.String(length=32), nullable=False),
        sa.Column("drift_alerts", sa.Integer(), nullable=False),
        sa.Column("consumers_json", sa.Text(), nullable=False),
        sa.Column("explore_json", sa.Text(), nullable=False),
        sa.Column("review_json", sa.Text(), nullable=False),
        sa.Column("mcp_json", sa.Text(), nullable=False),
        sa.Column("validation_log_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_semantic_models_tenant_id_tenants"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_semantic_models_created_by_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_semantic_models")),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_semantic_models_tenant_slug"),
    )
    op.create_index(op.f("ix_semantic_models_tenant_id"), "semantic_models", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_semantic_models_created_by"), "semantic_models", ["created_by"], unique=False)
    op.create_index(op.f("ix_semantic_models_datasource_id"), "semantic_models", ["datasource_id"], unique=False)
    created.append("semantic_models")

    _create_semantic_child_table(
        "semantic_model_entities",
        [
            sa.Column("slug", sa.String(length=120), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("business_name", sa.String(length=255), nullable=False),
            sa.Column("table_name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("primary_key", sa.String(length=255), nullable=False),
            sa.Column("entity_type", sa.String(length=32), nullable=False),
            sa.Column("validation_status", sa.String(length=32), nullable=False),
            sa.Column("profile_json", sa.Text(), nullable=False),
            sa.Column("lineage_json", sa.Text(), nullable=False),
            sa.Column("permission_json", sa.Text(), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False),
            sa.UniqueConstraint("model_id", "slug", name="uq_semantic_model_entities_model_slug"),
        ],
    )
    created.append("semantic_model_entities")
    _create_semantic_child_table(
        "semantic_model_fields",
        [
            sa.Column("entity_id", GUID(), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("source_field", sa.String(length=255), nullable=False),
            sa.Column("data_type", sa.String(length=120), nullable=False),
            sa.Column("role", sa.String(length=64), nullable=False),
            sa.Column("nullable", sa.Boolean(), nullable=False),
            sa.Column("profile_json", sa.Text(), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["entity_id"], ["semantic_model_entities.id"], name=op.f("fk_semantic_model_fields_entity_id_semantic_model_entities"), ondelete="CASCADE"),
        ],
        include_model_id=False,
    )
    created.append("semantic_model_fields")
    _create_semantic_child_table(
        "semantic_model_relationships",
        [
            sa.Column("slug", sa.String(length=120), nullable=False),
            sa.Column("from_entity", sa.String(length=120), nullable=False),
            sa.Column("to_entity", sa.String(length=120), nullable=False),
            sa.Column("label", sa.String(length=255), nullable=False),
            sa.Column("join_fields_json", sa.Text(), nullable=False),
            sa.Column("cardinality", sa.String(length=64), nullable=False),
            sa.Column("fk_evidence", sa.Text(), nullable=False),
            sa.Column("unique_rate", sa.Float(), nullable=False),
            sa.Column("orphan_rate", sa.Float(), nullable=False),
            sa.Column("fanout_risk", sa.String(length=32), nullable=False),
            sa.Column("validation_status", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("validation_message", sa.Text(), nullable=False),
            sa.Column("evidence_json", sa.Text(), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False),
            sa.UniqueConstraint("model_id", "slug", name="uq_semantic_model_relationships_model_slug"),
        ],
    )
    created.append("semantic_model_relationships")
    _create_semantic_child_table(
        "semantic_model_metrics",
        [
            sa.Column("slug", sa.String(length=120), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("business_name", sa.String(length=255), nullable=False),
            sa.Column("definition", sa.Text(), nullable=False),
            sa.Column("kind", sa.String(length=64), nullable=False),
            sa.Column("formula", sa.Text(), nullable=False),
            sa.Column("filter_expr", sa.Text(), nullable=False),
            sa.Column("time_field", sa.String(length=255), nullable=False),
            sa.Column("default_grain", sa.String(length=32), nullable=False),
            sa.Column("dimensions_json", sa.Text(), nullable=False),
            sa.Column("unit", sa.String(length=64), nullable=False),
            sa.Column("owner", sa.String(length=255), nullable=False),
            sa.Column("certification", sa.String(length=64), nullable=False),
            sa.Column("lineage_json", sa.Text(), nullable=False),
            sa.Column("preview_json", sa.Text(), nullable=False),
            sa.Column("compiled_sql", sa.Text(), nullable=False),
            sa.Column("validation_status", sa.String(length=32), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False),
            sa.UniqueConstraint("model_id", "slug", name="uq_semantic_model_metrics_model_slug"),
        ],
    )
    created.append("semantic_model_metrics")
    _create_semantic_child_table(
        "semantic_model_dimensions",
        [
            sa.Column("slug", sa.String(length=120), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("entity_slug", sa.String(length=120), nullable=False),
            sa.Column("field", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False),
            sa.UniqueConstraint("model_id", "slug", name="uq_semantic_model_dimensions_model_slug"),
        ],
    )
    created.append("semantic_model_dimensions")
    op.create_table(
        "semantic_model_audit_events",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("model_id", GUID(), nullable=False),
        sa.Column("user_id", GUID(), nullable=True),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_semantic_model_audit_events_tenant_id_tenants"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["model_id"], ["semantic_models.id"], name=op.f("fk_semantic_model_audit_events_model_id_semantic_models"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_semantic_model_audit_events_user_id_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_semantic_model_audit_events")),
    )
    for column in ("tenant_id", "model_id"):
        op.create_index(op.f(f"ix_semantic_model_audit_events_{column}"), "semantic_model_audit_events", [column], unique=False)
    created.append("semantic_model_audit_events")

    _create_semantic_model_versions()
    created.append("semantic_model_versions")


def _alter_existing_semantic_model_tables() -> None:
    columns = _columns("semantic_models")
    if "revision" not in columns:
        op.add_column("semantic_models", sa.Column("revision", sa.Integer(), nullable=False, server_default=sa.text("1")))
        if op.get_bind().dialect.name == "postgresql":
            op.execute(sa.text("ALTER TABLE semantic_models ALTER COLUMN revision DROP DEFAULT"))
    if "semantic_model_versions" not in _tables():
        _create_semantic_model_versions()


def _create_semantic_model_versions() -> None:
    op.create_table(
        "semantic_model_versions",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("model_id", GUID(), nullable=False),
        sa.Column("version_label", sa.String(length=64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("source_snapshot_ids_json", sa.Text(), nullable=False),
        sa.Column("physical_schema_json", sa.Text(), nullable=False),
        sa.Column("review_json", sa.Text(), nullable=False),
        sa.Column("published_by", GUID(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_semantic_model_versions_tenant_id_tenants"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["model_id"], ["semantic_models.id"], name=op.f("fk_semantic_model_versions_model_id_semantic_models"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["published_by"], ["users.id"], name=op.f("fk_semantic_model_versions_published_by_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_semantic_model_versions")),
        sa.UniqueConstraint("model_id", "version_label", name="uq_semantic_model_versions_model_label"),
    )
    for column in ("tenant_id", "model_id", "published_by"):
        op.create_index(op.f(f"ix_semantic_model_versions_{column}"), "semantic_model_versions", [column], unique=False)


def _create_semantic_child_table(table_name: str, columns: list[sa.Column], *, include_model_id: bool = True) -> None:
    base_columns = [sa.Column("id", GUID(), nullable=False)]
    constraints: list[sa.Constraint] = []
    if include_model_id:
        base_columns.append(sa.Column("model_id", GUID(), nullable=False))
        constraints.append(sa.ForeignKeyConstraint(["model_id"], ["semantic_models.id"], name=op.f(f"fk_{table_name}_model_id_semantic_models"), ondelete="CASCADE"))
    for item in columns:
        if isinstance(item, sa.Constraint):
            constraints.append(item)
        else:
            base_columns.append(item)
    op.create_table(table_name, *base_columns, *constraints, sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table_name}")))
    if include_model_id:
        op.create_index(op.f(f"ix_{table_name}_model_id"), table_name, ["model_id"], unique=False)
    elif table_name == "semantic_model_fields":
        op.create_index(op.f("ix_semantic_model_fields_entity_id"), table_name, ["entity_id"], unique=False)


def _create_notebook_assets() -> None:
    op.create_table(
        "notebook_assets",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("notebook_id", GUID(), nullable=False),
        sa.Column("asset_type", sa.String(length=40), nullable=False),
        sa.Column("asset_id", sa.String(length=120), nullable=False),
        sa.Column("added_by", GUID(), nullable=True),
        sa.Column("usage_policy_json", sa.JSON(), nullable=False),
        sa.Column("added_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("asset_type IN ('dataset', 'semantic_model', 'knowledge_resource')", name=op.f("ck_notebook_assets_type")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_notebook_assets_tenant_id_tenants"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["notebook_id"], ["notebooks.id"], name=op.f("fk_notebook_assets_notebook_id_notebooks"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["added_by"], ["users.id"], name=op.f("fk_notebook_assets_added_by_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notebook_assets")),
        sa.UniqueConstraint("tenant_id", "notebook_id", "asset_type", "asset_id", name="uq_notebook_assets_asset"),
    )
    for column in ("tenant_id", "notebook_id", "asset_type", "asset_id", "added_by"):
        op.create_index(op.f(f"ix_notebook_assets_{column}"), "notebook_assets", [column], unique=False)


def _alter_existing_notebook_assets() -> None:
    columns = _columns("notebook_assets")
    checks = _check_names("notebook_assets")
    unique_names = _unique_names("notebook_assets")
    bind = op.get_bind()
    dialect = bind.dialect.name
    is_postgresql = dialect == "postgresql"
    if "tenant_id" not in columns:
        op.add_column("notebook_assets", sa.Column("tenant_id", GUID(), nullable=True))
        op.execute(
            sa.text(
                """
                UPDATE notebook_assets AS na
                SET tenant_id = n.tenant_id
                FROM notebooks AS n
                WHERE na.notebook_id = n.id AND na.tenant_id IS NULL
                """
            )
        )
        null_tenant_count = bind.execute(
            sa.text("SELECT COUNT(*) FROM notebook_assets WHERE tenant_id IS NULL")
        ).scalar_one()
        if is_postgresql and not null_tenant_count:
            op.execute(sa.text("ALTER TABLE notebook_assets ALTER COLUMN tenant_id SET NOT NULL"))
        op.create_foreign_key(
            op.f("fk_notebook_assets_tenant_id_tenants"),
            "notebook_assets",
            "tenants",
            ["tenant_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_index(op.f("ix_notebook_assets_tenant_id"), "notebook_assets", ["tenant_id"], unique=False)
    if "usage_policy_json" in columns:
        op.execute(sa.text("UPDATE notebook_assets SET usage_policy_json = '{}' WHERE usage_policy_json IS NULL"))
        if is_postgresql:
            op.execute(sa.text("ALTER TABLE notebook_assets ALTER COLUMN usage_policy_json SET NOT NULL"))
    if is_postgresql:
        op.execute(sa.text("ALTER TABLE notebook_assets ALTER COLUMN asset_id TYPE VARCHAR(120) USING asset_id::text"))
        op.execute(sa.text("ALTER TABLE notebook_assets DROP CONSTRAINT IF EXISTS ck_notebook_assets_asset_type"))
        op.execute(sa.text("ALTER TABLE notebook_assets DROP CONSTRAINT IF EXISTS ck_notebook_assets_ck_notebook_assets_asset_type"))
        op.execute(sa.text("ALTER TABLE notebook_assets DROP CONSTRAINT IF EXISTS ck_notebook_assets_type"))
        op.execute(
            sa.text(
                """
                ALTER TABLE notebook_assets
                ADD CONSTRAINT ck_notebook_assets_type
                CHECK (asset_type IN ('dataset', 'semantic_model', 'knowledge_resource'))
                """
            )
        )
    else:
        if "ck_notebook_assets_asset_type" in checks:
            op.drop_constraint("ck_notebook_assets_asset_type", "notebook_assets", type_="check")
        if "ck_notebook_assets_type" not in checks:
            op.create_check_constraint(
                op.f("ck_notebook_assets_type"),
                "notebook_assets",
                "asset_type IN ('dataset', 'semantic_model', 'knowledge_resource')",
            )
    if "uq_notebook_assets_asset" not in unique_names and {"tenant_id", "notebook_id", "asset_type", "asset_id"}.issubset(
        _columns("notebook_assets")
    ):
        duplicate_count = bind.execute(
            sa.text(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT tenant_id, notebook_id, asset_type, asset_id
                    FROM notebook_assets
                    GROUP BY tenant_id, notebook_id, asset_type, asset_id
                    HAVING COUNT(*) > 1
                ) AS duplicate_assets
                """
            )
        ).scalar_one()
        if not duplicate_count:
            if is_postgresql:
                op.execute(
                    sa.text(
                        """
                        ALTER TABLE notebook_assets
                        ADD CONSTRAINT uq_notebook_assets_asset
                        UNIQUE (tenant_id, notebook_id, asset_type, asset_id)
                        """
                    )
                )
            else:
                op.create_unique_constraint(
                    "uq_notebook_assets_asset",
                    "notebook_assets",
                    ["tenant_id", "notebook_id", "asset_type", "asset_id"],
                )


def _create_analysis_artifacts() -> None:
    op.create_table(
        "analysis_artifacts",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("notebook_id", GUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("definition_json", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("latest_result_snapshot_id", sa.String(length=120), nullable=True),
        sa.Column("created_by", GUID(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("status IN ('draft', 'review', 'published', 'archived')", name=op.f("ck_analysis_artifacts_status")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_analysis_artifacts_tenant_id_tenants"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["notebook_id"], ["notebooks.id"], name=op.f("fk_analysis_artifacts_notebook_id_notebooks"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_analysis_artifacts_created_by_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analysis_artifacts")),
        sa.UniqueConstraint("tenant_id", "notebook_id", "name", "version", name="uq_analysis_artifacts_version"),
    )
    for column in ("tenant_id", "notebook_id", "status", "created_by"):
        op.create_index(op.f(f"ix_analysis_artifacts_{column}"), "analysis_artifacts", [column], unique=False)


def _alter_existing_analysis_artifacts() -> None:
    columns = _columns("analysis_artifacts")
    unique_names = _unique_names("analysis_artifacts")
    bind = op.get_bind()
    dialect = bind.dialect.name
    is_postgresql = dialect == "postgresql"
    if "objective" in columns:
        op.execute(sa.text("UPDATE analysis_artifacts SET objective = '' WHERE objective IS NULL"))
        if is_postgresql:
            op.execute(sa.text("ALTER TABLE analysis_artifacts ALTER COLUMN objective SET NOT NULL"))
    if is_postgresql and "latest_result_snapshot_id" in columns:
        op.execute(
            sa.text(
                "ALTER TABLE analysis_artifacts ALTER COLUMN latest_result_snapshot_id TYPE VARCHAR(120) USING latest_result_snapshot_id::text"
            )
        )
    if "uq_analysis_artifacts_version" not in unique_names and {"tenant_id", "notebook_id", "name", "version"}.issubset(columns):
        duplicate_count = bind.execute(
            sa.text(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT tenant_id, notebook_id, name, version
                    FROM analysis_artifacts
                    GROUP BY tenant_id, notebook_id, name, version
                    HAVING COUNT(*) > 1
                ) AS duplicate_artifacts
                """
            )
        ).scalar_one()
        if not duplicate_count:
            if is_postgresql:
                op.execute(
                    sa.text(
                        """
                        ALTER TABLE analysis_artifacts
                        ADD CONSTRAINT uq_analysis_artifacts_version
                        UNIQUE (tenant_id, notebook_id, name, version)
                        """
                    )
                )
            else:
                op.create_unique_constraint(
                    "uq_analysis_artifacts_version",
                    "analysis_artifacts",
                    ["tenant_id", "notebook_id", "name", "version"],
                )
