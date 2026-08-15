"""add semantic model immutable versions

Revision ID: add_semantic_model_versions
Revises: add_source_connections_arch
Create Date: 2026-08-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from fastapi_users_db_sqlalchemy.generics import GUID

revision = "add_semantic_model_versions"
down_revision = "add_source_connections_arch"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table_name: str) -> set[str]:
    if table_name not in _tables():
        return set()
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def upgrade() -> None:
    if "semantic_models" in _tables() and "revision" not in _columns("semantic_models"):
        op.add_column("semantic_models", sa.Column("revision", sa.Integer(), nullable=False, server_default=sa.text("1")))
        if op.get_bind().dialect.name == "postgresql":
            op.execute(sa.text("ALTER TABLE semantic_models ALTER COLUMN revision DROP DEFAULT"))

    if "semantic_model_versions" not in _tables():
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


def downgrade() -> None:
    if "semantic_model_versions" in _tables():
        op.drop_index(op.f("ix_semantic_model_versions_published_by"), table_name="semantic_model_versions")
        op.drop_index(op.f("ix_semantic_model_versions_model_id"), table_name="semantic_model_versions")
        op.drop_index(op.f("ix_semantic_model_versions_tenant_id"), table_name="semantic_model_versions")
        op.drop_table("semantic_model_versions")
    if "semantic_models" in _tables() and "revision" in _columns("semantic_models"):
        op.drop_column("semantic_models", "revision")
