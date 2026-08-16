"""add collaboration integration tables

Revision ID: add_collaboration_integration_tables
Revises: add_multi_source_assets
Create Date: 2026-08-14

Adds platform-neutral collaboration tables for Slack compatibility and Feishu
Phase 1. Existing Slack tables, APIs, and columns are intentionally retained.
Rollback drops only the new generic tables/nullable references.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from fastapi_users_db_sqlalchemy.generics import GUID

revision = "add_collaboration_integration_tables"
down_revision = "add_multi_source_assets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collaboration_installations",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("platform", sa.String(30), nullable=False),
        sa.Column("external_tenant_id", sa.String(128), nullable=False),
        sa.Column("external_tenant_name", sa.String(255), nullable=True),
        sa.Column("app_id", sa.String(128), nullable=True),
        sa.Column("credentials_encrypted", sa.Text(), nullable=False),
        sa.Column("connection_mode", sa.String(30), nullable=False, server_default="websocket"),
        sa.Column("default_llm_connection_id", GUID(), nullable=True),
        sa.Column("bot_external_id", sa.String(128), nullable=True),
        sa.Column("public_id", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("health_status", sa.String(30), nullable=False, server_default="disconnected"),
        sa.Column("health_error", sa.Text(), nullable=True),
        sa.Column("last_connected_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("last_event_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("reconnect_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("config_json", sa.JSON(), nullable=True),
        sa.Column("installed_by", GUID(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["default_llm_connection_id"], ["llm_connections.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["installed_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collaboration_installations")),
        sa.UniqueConstraint("public_id", name=op.f("uq_collaboration_installations_public_id")),
        sa.UniqueConstraint(
            "platform",
            "external_tenant_id",
            name="uq_collab_installations_platform_external_tenant",
        ),
    )
    op.create_index("ix_collaboration_installations_tenant_id", "collaboration_installations", ["tenant_id"])
    op.create_index("ix_collaboration_installations_platform", "collaboration_installations", ["platform"])
    op.create_index(
        "ix_collaboration_installations_external_tenant_id",
        "collaboration_installations",
        ["external_tenant_id"],
    )

    op.create_table(
        "collaboration_conversations",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("installation_id", GUID(), nullable=False),
        sa.Column("external_chat_id", sa.String(128), nullable=False),
        sa.Column("external_root_id", sa.String(128), nullable=True),
        sa.Column("normalized_root_id", sa.String(128), nullable=False, server_default="__root__"),
        sa.Column("external_user_id", sa.String(128), nullable=True),
        sa.Column("chat_type", sa.String(30), nullable=False),
        sa.Column("notebook_id", GUID(), nullable=True),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("bot_owned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("auto_follow_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_activity_at", sa.TIMESTAMP(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["installation_id"], ["collaboration_installations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["notebook_id"], ["notebooks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collaboration_conversations")),
        sa.UniqueConstraint(
            "installation_id",
            "external_chat_id",
            "normalized_root_id",
            name="uq_collab_conversation_install_chat_root",
        ),
    )
    op.create_index("ix_collaboration_conversations_installation_id", "collaboration_conversations", ["installation_id"])
    op.create_index("ix_collaboration_conversations_external_chat_id", "collaboration_conversations", ["external_chat_id"])

    op.create_table(
        "collaboration_event_logs",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("installation_id", GUID(), nullable=False),
        sa.Column("platform", sa.String(30), nullable=False),
        sa.Column("external_event_id", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("external_chat_id", sa.String(128), nullable=True),
        sa.Column("external_user_id", sa.String(128), nullable=True),
        sa.Column("processing_status", sa.String(30), nullable=False, server_default="received"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("redaction_applied", sa.Boolean(), nullable=True),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["installation_id"], ["collaboration_installations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collaboration_event_logs")),
        sa.UniqueConstraint("installation_id", "external_event_id", name="uq_collab_event_install_external_event"),
    )
    op.create_index("ix_collaboration_event_logs_installation_id", "collaboration_event_logs", ["installation_id"])
    op.create_index("ix_collaboration_event_logs_platform", "collaboration_event_logs", ["platform"])

    op.create_table(
        "collaboration_delivery_targets",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("installation_id", GUID(), nullable=False),
        sa.Column("target_type", sa.String(30), nullable=False),
        sa.Column("external_target_id", sa.String(128), nullable=False),
        sa.Column("external_root_id", sa.String(128), nullable=True),
        sa.Column("normalized_root_id", sa.String(128), nullable=False, server_default="__root__"),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("config_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["installation_id"], ["collaboration_installations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collaboration_delivery_targets")),
        sa.UniqueConstraint(
            "installation_id",
            "target_type",
            "external_target_id",
            "normalized_root_id",
            name="uq_collab_delivery_target",
        ),
    )
    op.create_index(
        "ix_collaboration_delivery_targets_installation_id",
        "collaboration_delivery_targets",
        ["installation_id"],
    )

    op.create_table(
        "external_identities",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("platform", sa.String(30), nullable=False),
        sa.Column("installation_id", GUID(), nullable=False),
        sa.Column("external_user_id", sa.String(128), nullable=False),
        sa.Column("union_id", sa.String(128), nullable=True),
        sa.Column("user_id", GUID(), nullable=True),
        sa.Column("byaan_user_id", GUID(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="seen"),
        sa.Column("last_seen_at", sa.TIMESTAMP(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["installation_id"], ["collaboration_installations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["byaan_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_identities")),
        sa.UniqueConstraint("installation_id", "external_user_id", name="uq_external_identity_install_external_user"),
    )
    op.create_index("ix_external_identities_tenant_id", "external_identities", ["tenant_id"])
    op.create_index("ix_external_identities_platform", "external_identities", ["platform"])
    op.create_index("ix_external_identities_installation_id", "external_identities", ["installation_id"])

    op.create_table(
        "collaboration_response_refs",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("run_id", sa.String(128), nullable=False),
        sa.Column("conversation_id", GUID(), nullable=False),
        sa.Column("platform_message_id", sa.String(128), nullable=False),
        sa.Column("platform_card_id", sa.String(128), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(30), nullable=False, server_default="running"),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["collaboration_conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collaboration_response_refs")),
    )
    op.create_index("ix_collaboration_response_refs_run_id", "collaboration_response_refs", ["run_id"])
    op.create_index(
        "ix_collaboration_response_refs_conversation_id",
        "collaboration_response_refs",
        ["conversation_id"],
    )

    op.create_table(
        "collaboration_leases",
        sa.Column("installation_id", GUID(), nullable=False),
        sa.Column("owner_id", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(), nullable=False),
        sa.Column("heartbeat_at", sa.TIMESTAMP(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["installation_id"], ["collaboration_installations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("installation_id", name=op.f("pk_collaboration_leases")),
    )
    op.create_index("ix_collaboration_leases_expires_at", "collaboration_leases", ["expires_at"])

    with op.batch_alter_table("schedules") as batch_op:
        batch_op.add_column(sa.Column("delivery_target_id", GUID(), nullable=True))
        batch_op.create_foreign_key(
            "fk_schedules_delivery_target_id_collaboration_delivery_targets",
            "collaboration_delivery_targets",
            ["delivery_target_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_schedules_delivery_target_id", "schedules", ["delivery_target_id"])

    with op.batch_alter_table("skill_suggestions") as batch_op:
        batch_op.add_column(sa.Column("reviewer_external_identity_id", GUID(), nullable=True))
        batch_op.add_column(sa.Column("channel_delivery_target_id", GUID(), nullable=True))
        batch_op.add_column(sa.Column("channel_message_id", sa.String(128), nullable=True))
        batch_op.create_foreign_key(
            "fk_skill_suggestions_reviewer_external_identity_id_external_identities",
            "external_identities",
            ["reviewer_external_identity_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_skill_suggestions_channel_delivery_target_id_collaboration_delivery_targets",
            "collaboration_delivery_targets",
            ["channel_delivery_target_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    op.drop_index("ix_schedules_delivery_target_id", table_name="schedules")
    with op.batch_alter_table("skill_suggestions") as batch_op:
        batch_op.drop_constraint(
            "fk_skill_suggestions_channel_delivery_target_id_collaboration_delivery_targets",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_skill_suggestions_reviewer_external_identity_id_external_identities",
            type_="foreignkey",
        )
        batch_op.drop_column("channel_message_id")
        batch_op.drop_column("channel_delivery_target_id")
        batch_op.drop_column("reviewer_external_identity_id")

    with op.batch_alter_table("schedules") as batch_op:
        batch_op.drop_constraint("fk_schedules_delivery_target_id_collaboration_delivery_targets", type_="foreignkey")
        batch_op.drop_column("delivery_target_id")

    op.drop_index("ix_collaboration_leases_expires_at", table_name="collaboration_leases")
    op.drop_table("collaboration_leases")
    op.drop_index("ix_collaboration_response_refs_conversation_id", table_name="collaboration_response_refs")
    op.drop_index("ix_collaboration_response_refs_run_id", table_name="collaboration_response_refs")
    op.drop_table("collaboration_response_refs")
    op.drop_index("ix_external_identities_installation_id", table_name="external_identities")
    op.drop_index("ix_external_identities_platform", table_name="external_identities")
    op.drop_index("ix_external_identities_tenant_id", table_name="external_identities")
    op.drop_table("external_identities")
    op.drop_index("ix_collaboration_delivery_targets_installation_id", table_name="collaboration_delivery_targets")
    op.drop_table("collaboration_delivery_targets")
    op.drop_index("ix_collaboration_event_logs_platform", table_name="collaboration_event_logs")
    op.drop_index("ix_collaboration_event_logs_installation_id", table_name="collaboration_event_logs")
    op.drop_table("collaboration_event_logs")
    op.drop_index("ix_collaboration_conversations_external_chat_id", table_name="collaboration_conversations")
    op.drop_index("ix_collaboration_conversations_installation_id", table_name="collaboration_conversations")
    op.drop_table("collaboration_conversations")
    op.drop_index("ix_collaboration_installations_external_tenant_id", table_name="collaboration_installations")
    op.drop_index("ix_collaboration_installations_platform", table_name="collaboration_installations")
    op.drop_index("ix_collaboration_installations_tenant_id", table_name="collaboration_installations")
    op.drop_table("collaboration_installations")
