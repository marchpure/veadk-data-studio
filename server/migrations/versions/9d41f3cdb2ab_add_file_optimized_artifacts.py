"""add optimized artifact columns for files

Revision ID: 9d41f3cdb2ab
Revises: 6f2dc9b1f0a6
Create Date: 2025-02-10 14:22:00.000000
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


# revision identifiers, used by Alembic.
revision = "9d41f3cdb2ab"
down_revision = "6f2dc9b1f0a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not _has_column("files", "optimized_storage_path"):
        op.add_column("files", sa.Column("optimized_storage_path", sa.Text(), nullable=True))
    if not _has_column("files", "optimized_format"):
        op.add_column("files", sa.Column("optimized_format", sa.String(length=32), nullable=True))
    if not _has_column("files", "optimized_checksum"):
        op.add_column("files", sa.Column("optimized_checksum", sa.String(length=128), nullable=True))
    if not _has_column("files", "row_count"):
        op.add_column("files", sa.Column("row_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    if _has_column("files", "row_count"):
        op.drop_column("files", "row_count")
    if _has_column("files", "optimized_checksum"):
        op.drop_column("files", "optimized_checksum")
    if _has_column("files", "optimized_format"):
        op.drop_column("files", "optimized_format")
    if _has_column("files", "optimized_storage_path"):
        op.drop_column("files", "optimized_storage_path")
