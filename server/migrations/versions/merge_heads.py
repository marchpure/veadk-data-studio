"""Merge multiple heads

Revision ID: merge_heads
Revises: add_slack_channel_to_schedules, add_slack_integration_tables, add_description_to_datasources
Create Date: 2026-02-01

"""

from alembic import op
import sqlalchemy as sa


revision = "merge_heads"
down_revision = ("add_slack_channel_to_schedules", "add_slack_integration_tables", "add_description_to_datasources")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
