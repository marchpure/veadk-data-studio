"""add memory to notebooks

Revision ID: add_memory_to_notebooks
Revises: repair_datasets_missing_columns
Create Date: 2026-02-17

"""

import sqlalchemy as sa
from alembic import op

revision = "add_memory_to_notebooks"
down_revision = "repair_datasets_missing_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col["name"] for col in inspector.get_columns("notebooks")]

    if "memory" not in columns:
        op.add_column("notebooks", sa.Column("memory", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("notebooks", "memory")
