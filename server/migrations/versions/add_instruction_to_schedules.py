"""Add instruction column to schedules table

Revision ID: add_instruction_to_schedules
Revises: merge_heads
Create Date: 2026-02-01

"""

from alembic import op
import sqlalchemy as sa


revision = "add_instruction_to_schedules"
down_revision = "merge_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("schedules", sa.Column("instruction", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("schedules", "instruction")
