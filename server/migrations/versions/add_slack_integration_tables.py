"""add slack integration tables

Revision ID: add_slack_integration_tables
Revises: add_skill_type_to_custom_skills
Create Date: 2026-02-01

"""

import sqlalchemy as sa
from alembic import op
from fastapi_users_db_sqlalchemy.generics import GUID

revision = "add_slack_integration_tables"
down_revision = "add_skill_type_to_custom_skills"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # slack_workspaces table
    op.create_table(
        "slack_workspaces",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("slack_team_id", sa.String(50), nullable=False),
        sa.Column("slack_team_name", sa.String(255), nullable=True),
        sa.Column("bot_token_encrypted", sa.Text(), nullable=False),
        sa.Column("bot_user_id", sa.String(50), nullable=True),
        sa.Column("signing_secret_encrypted", sa.Text(), nullable=False),
        sa.Column("default_llm_connection_id", GUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("installed_by", GUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_slack_workspaces_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["default_llm_connection_id"],
            ["llm_connections.id"],
            name=op.f("fk_slack_workspaces_default_llm_connection_id"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["installed_by"],
            ["users.id"],
            name=op.f("fk_slack_workspaces_installed_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_slack_workspaces")),
        sa.UniqueConstraint("slack_team_id", name=op.f("uq_slack_workspaces_slack_team_id")),
    )
    op.create_index("ix_slack_workspaces_tenant_id", "slack_workspaces", ["tenant_id"], unique=False)
    op.create_index("ix_slack_workspaces_slack_team_id", "slack_workspaces", ["slack_team_id"], unique=False)

    # slack_conversations table
    op.create_table(
        "slack_conversations",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("slack_workspace_id", GUID(), nullable=False),
        sa.Column("slack_channel_id", sa.String(50), nullable=False),
        sa.Column("slack_thread_ts", sa.String(50), nullable=True),
        sa.Column("notebook_id", GUID(), nullable=True),
        sa.Column("slack_user_id", sa.String(50), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "last_activity_at",
            sa.TIMESTAMP(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["slack_workspace_id"],
            ["slack_workspaces.id"],
            name=op.f("fk_slack_conversations_workspace_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["notebook_id"],
            ["notebooks.id"],
            name=op.f("fk_slack_conversations_notebook_id"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_slack_conversations")),
        sa.UniqueConstraint(
            "slack_workspace_id", "slack_channel_id", "slack_thread_ts",
            name="uq_slack_conversation_workspace_channel_thread"
        ),
    )
    op.create_index("ix_slack_conversations_workspace_id", "slack_conversations", ["slack_workspace_id"], unique=False)
    op.create_index("ix_slack_conversations_channel_id", "slack_conversations", ["slack_channel_id"], unique=False)

    # slack_event_logs table
    op.create_table(
        "slack_event_logs",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("slack_workspace_id", GUID(), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("event_id", sa.String(50), nullable=False),
        sa.Column("slack_channel_id", sa.String(50), nullable=True),
        sa.Column("slack_user_id", sa.String(50), nullable=True),
        sa.Column("processing_status", sa.String(20), nullable=False, server_default="received"),
        sa.Column("redaction_applied", sa.Boolean(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_slack_event_logs")),
        sa.UniqueConstraint("event_id", name=op.f("uq_slack_event_logs_event_id")),
    )
    op.create_index("ix_slack_event_logs_workspace_id", "slack_event_logs", ["slack_workspace_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_slack_event_logs_workspace_id", table_name="slack_event_logs")
    op.drop_table("slack_event_logs")
    op.drop_index("ix_slack_conversations_channel_id", table_name="slack_conversations")
    op.drop_index("ix_slack_conversations_workspace_id", table_name="slack_conversations")
    op.drop_table("slack_conversations")
    op.drop_index("ix_slack_workspaces_slack_team_id", table_name="slack_workspaces")
    op.drop_index("ix_slack_workspaces_tenant_id", table_name="slack_workspaces")
    op.drop_table("slack_workspaces")
