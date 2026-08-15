"""Add slack_channel_id to schedules table

Revision ID: add_slack_channel_to_schedules
Revises: add_schedules_tables
Create Date: 2026-02-01

"""

from alembic import op
import sqlalchemy as sa


revision = "add_slack_channel_to_schedules"
down_revision = "add_schedules_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("schedules", sa.Column("slack_channel_id", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("schedules", "slack_channel_id")
