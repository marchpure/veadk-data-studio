"""harden semantic model versions compatibility

Revision ID: harden_semantic_model_versions_compat
Revises: add_semantic_model_versions
Create Date: 2026-08-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from fastapi_users_db_sqlalchemy.generics import GUID

revision = "harden_semantic_model_versions_compat"
down_revision = "add_semantic_model_versions"
branch_labels = None
depends_on = None


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _tables() -> set[str]:
    return set(_inspector().get_table_names())


def _columns(table_name: str) -> set[str]:
    if table_name not in _tables():
        return set()
    return {column["name"] for column in _inspector().get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    if table_name not in _tables():
        return set()
    return {index["name"] for index in _inspector().get_indexes(table_name) if index.get("name")}


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
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["model_id"], ["semantic_models.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["published_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_id", "version_label", name="uq_semantic_model_versions_model_label"),
    )


def _add_column_if_missing(table_name: str, column_name: str, column: sa.Column) -> None:
    if column_name not in _columns(table_name):
        op.add_column(table_name, column)


def _create_index_if_missing(table_name: str, column_name: str) -> None:
    index_name = op.f(f"ix_{table_name}_{column_name}")
    if index_name not in _indexes(table_name):
        op.create_index(index_name, table_name, [column_name], unique=False)


def upgrade() -> None:
    if "semantic_model_versions" not in _tables():
        _create_semantic_model_versions()
    else:
        _add_column_if_missing("semantic_model_versions", "tenant_id", sa.Column("tenant_id", GUID(), nullable=True))
        _add_column_if_missing(
            "semantic_model_versions",
            "revision",
            sa.Column("revision", sa.Integer(), nullable=False, server_default=sa.text("1")),
        )
        _add_column_if_missing(
            "semantic_model_versions",
            "source_snapshot_ids_json",
            sa.Column("source_snapshot_ids_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
        )
        _add_column_if_missing(
            "semantic_model_versions",
            "physical_schema_json",
            sa.Column("physical_schema_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
        )
        _add_column_if_missing(
            "semantic_model_versions",
            "review_json",
            sa.Column("review_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
        )
        _add_column_if_missing("semantic_model_versions", "published_by", sa.Column("published_by", GUID(), nullable=True))

        existing = _columns("semantic_model_versions")
        if "created_by" in existing and "published_by" in existing:
            op.execute(
                sa.text(
                    """
                    UPDATE semantic_model_versions
                    SET published_by = created_by
                    WHERE published_by IS NULL AND created_by IS NOT NULL
                    """
                )
            )
        if "publish_notes" in existing and "review_json" in existing:
            if op.get_bind().dialect.name == "postgresql":
                op.execute(
                    sa.text(
                        """
                        UPDATE semantic_model_versions
                        SET review_json = json_build_object('publish_notes', publish_notes)::text
                        WHERE publish_notes IS NOT NULL
                          AND (review_json IS NULL OR review_json = '{}')
                        """
                    )
                )

        if "tenant_id" in _columns("semantic_model_versions") and "semantic_models" in _tables():
            op.execute(
                sa.text(
                    """
                    UPDATE semantic_model_versions AS version
                    SET tenant_id = model.tenant_id
                    FROM semantic_models AS model
                    WHERE version.model_id = model.id
                      AND version.tenant_id IS NULL
                    """
                )
            )
            if op.get_bind().dialect.name == "postgresql":
                missing = op.get_bind().execute(
                    sa.text("SELECT COUNT(*) FROM semantic_model_versions WHERE tenant_id IS NULL")
                ).scalar()
                if missing == 0:
                    op.alter_column("semantic_model_versions", "tenant_id", nullable=False)

    for column_name in ("tenant_id", "model_id", "published_by"):
        if column_name in _columns("semantic_model_versions"):
            _create_index_if_missing("semantic_model_versions", column_name)


def downgrade() -> None:
    # Compatibility-only migration. Do not drop columns that may now hold
    # immutable publication metadata for upgraded self-hosted installations.
    pass
