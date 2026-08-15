"""add filesystem storage columns for datasets and files

Revision ID: 6f2dc9b1f0a6
Revises: a1b2c3d4e5f6
Create Date: 2025-02-09 22:17:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


def _get_inspector():
    bind = op.get_bind()
    return sa.inspect(bind)


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = _get_inspector()
    columns = {col["name"] for col in inspector.get_columns(table_name)}
    return column_name in columns


def _is_column_nullable(table_name: str, column_name: str) -> bool:
    inspector = _get_inspector()
    for column in inspector.get_columns(table_name):
        if column["name"] == column_name:
            return bool(column.get("nullable", True))
    raise ValueError(f"Column {table_name}.{column_name} not found")


# revision identifiers, used by Alembic.
revision = "6f2dc9b1f0a6"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not _has_column("datasets", "storage_path"):
        op.add_column("datasets", sa.Column("storage_path", sa.Text(), nullable=True))
    if not _has_column("datasets", "duckdb_path"):
        op.add_column("datasets", sa.Column("duckdb_path", sa.Text(), nullable=True))

    if not _has_column("files", "storage_path"):
        op.add_column("files", sa.Column("storage_path", sa.Text(), nullable=True))
    if not _has_column("files", "checksum"):
        op.add_column("files", sa.Column("checksum", sa.String(length=128), nullable=True))
    if _has_column("files", "content") and not _is_column_nullable("files", "content"):
        with op.batch_alter_table("files") as batch_op:
            batch_op.alter_column("content", existing_type=sa.LargeBinary(), nullable=True)


def downgrade() -> None:
    if _has_column("files", "content") and _is_column_nullable("files", "content"):
        with op.batch_alter_table("files") as batch_op:
            batch_op.alter_column("content", existing_type=sa.LargeBinary(), nullable=False)
    if _has_column("files", "checksum"):
        op.drop_column("files", "checksum")
    if _has_column("files", "storage_path"):
        op.drop_column("files", "storage_path")

    if _has_column("datasets", "duckdb_path"):
        op.drop_column("datasets", "duckdb_path")
    if _has_column("datasets", "storage_path"):
        op.drop_column("datasets", "storage_path")
