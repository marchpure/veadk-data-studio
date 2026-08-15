"""Add schedules and schedule_runs tables for cron scheduling

Revision ID: add_schedules_tables
Revises: e9a8c462cd41
Create Date: 2026-02-01

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "add_schedules_tables"
down_revision = "e9a8c462cd41"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    is_postgres = conn.dialect.name == "postgresql"

    if is_postgres:
        id_type = UUID(as_uuid=True)
    else:
        id_type = sa.CHAR(36)

    op.create_table(
        "schedules",
        sa.Column("id", id_type, primary_key=True),
        sa.Column("tenant_id", id_type, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("notebook_id", id_type, sa.ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("created_by", id_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("cron_expression", sa.String(100), nullable=False),
        sa.Column("timezone", sa.String(50), nullable=False, server_default="UTC"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("webhook_url", sa.Text(), nullable=True),
        sa.Column("next_run_at", sa.TIMESTAMP(), nullable=True, index=True),
        sa.Column("is_running", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.current_timestamp()),
    )

    op.create_index(
        "ix_schedules_due",
        "schedules",
        ["next_run_at", "is_enabled", "is_running"],
    )

    op.create_table(
        "schedule_runs",
        sa.Column("id", id_type, primary_key=True),
        sa.Column("schedule_id", id_type, sa.ForeignKey("schedules.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(), server_default=sa.func.current_timestamp()),
        sa.Column("completed_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("queries_total", sa.Integer(), nullable=True),
        sa.Column("queries_succeeded", sa.Integer(), nullable=True),
        sa.Column("queries_failed", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("message_id", id_type, nullable=True),
    )

    op.create_index(
        "ix_schedule_runs_lookup",
        "schedule_runs",
        ["schedule_id", "started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_schedule_runs_lookup", table_name="schedule_runs")
    op.drop_table("schedule_runs")
    op.drop_index("ix_schedules_due", table_name="schedules")
    op.drop_table("schedules")
