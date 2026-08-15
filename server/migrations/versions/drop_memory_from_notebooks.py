"""drop memory from notebooks

Revision ID: drop_memory_from_notebooks
Revises: add_memory_to_notebooks
Create Date: 2026-02-23

"""

import sqlalchemy as sa
from alembic import op

revision = "drop_memory_from_notebooks"
down_revision = "add_memory_to_notebooks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col["name"] for col in inspector.get_columns("notebooks")]

    if "memory" in columns:
        op.drop_column("notebooks", "memory")


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col["name"] for col in inspector.get_columns("notebooks")]

    if "memory" not in columns:
        op.add_column("notebooks", sa.Column("memory", sa.Text(), nullable=True))
