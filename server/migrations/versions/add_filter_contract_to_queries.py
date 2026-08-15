"""Add filter_contract column to queries table

Revision ID: add_filter_contract_to_queries
Revises: add_instruction_to_schedules
Create Date: 2026-02-07

"""

import sqlalchemy as sa
from alembic import op

revision = "add_filter_contract_to_queries"
down_revision = "add_instruction_to_schedules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col["name"] for col in inspector.get_columns("queries")]
    if "filter_contract" not in columns:
        op.add_column("queries", sa.Column("filter_contract", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("queries", "filter_contract")
