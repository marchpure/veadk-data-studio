"""Add agent sessions tables for OpenAI Agents SDK PostgreSQL support

Revision ID: add_agent_sessions_tables
Revises: ef023df73ec3
Create Date: 2026-02-02

"""

import sqlalchemy as sa
from alembic import op

revision = "add_agent_sessions_tables"
down_revision = "ef023df73ec3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_sessions",
        sa.Column("session_id", sa.String(255), primary_key=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )

    op.create_table(
        "agent_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column(
            "session_id",
            sa.String(255),
            sa.ForeignKey("agent_sessions.session_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("message_data", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_agent_messages_session_created",
        "agent_messages",
        ["session_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_messages_session_created", table_name="agent_messages")
    op.drop_table("agent_messages")
    op.drop_table("agent_sessions")
