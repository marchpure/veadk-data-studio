"""add Data Workshop Skill workbench persistence

Revision ID: add_dw_skill_workbench
Revises: add_feishu_oauth_flows
Create Date: 2026-09-04
"""

import sqlalchemy as sa
from alembic import op

from server.db.base import GUID

revision = "add_dw_skill_workbench"
down_revision = "add_feishu_oauth_flows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_workshop_skills",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("owner_id", GUID(), nullable=False),
        sa.Column("target_skill", sa.String(160), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(40), nullable=False, server_default="draft"),
        sa.Column("context_refs_json", sa.JSON(), nullable=False),
        sa.Column("active_revision", sa.String(160), nullable=True),
        sa.Column("artifact_metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "owner_id", "target_skill", name="uq_dw_skill_owner_target"),
    )
    op.create_index(
        "ix_dw_skills_tenant_owner_updated", "data_workshop_skills", ["tenant_id", "owner_id", "updated_at"]
    )
    op.create_index("ix_data_workshop_skills_status", "data_workshop_skills", ["status"])

    op.create_table(
        "data_workshop_skill_sessions",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("owner_id", GUID(), nullable=False),
        sa.Column("skill_id", GUID(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False, server_default="新会话"),
        sa.Column("status", sa.String(40), nullable=False, server_default="idle"),
        sa.Column("context_refs_json", sa.JSON(), nullable=False),
        sa.Column("messages_json", sa.JSON(), nullable=False),
        sa.Column("events_json", sa.JSON(), nullable=False),
        sa.Column("last_invocation_json", sa.JSON(), nullable=True),
        sa.Column("current_invocation_id", sa.String(160), nullable=True),
        sa.Column("active_revision", sa.String(160), nullable=True),
        sa.Column("artifact_metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["data_workshop_skills.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_dw_skill_sessions_scope_updated",
        "data_workshop_skill_sessions",
        ["tenant_id", "owner_id", "skill_id", "updated_at"],
    )
    op.create_index("ix_data_workshop_skill_sessions_status", "data_workshop_skill_sessions", ["status"])

    op.create_table(
        "data_workshop_skill_revisions",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("owner_id", GUID(), nullable=False),
        sa.Column("skill_id", GUID(), nullable=False),
        sa.Column("session_id", GUID(), nullable=False),
        sa.Column("revision", sa.String(160), nullable=False),
        sa.Column("artifact_metadata_json", sa.JSON(), nullable=False),
        sa.Column("upstream_artifact_url", sa.Text(), nullable=True),
        sa.Column("validation_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["data_workshop_skills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["data_workshop_skill_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("skill_id", "revision", name="uq_dw_skill_revision"),
    )
    op.create_index(
        "ix_dw_skill_revisions_scope",
        "data_workshop_skill_revisions",
        ["tenant_id", "owner_id", "skill_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_dw_skill_revisions_scope", table_name="data_workshop_skill_revisions")
    op.drop_table("data_workshop_skill_revisions")
    op.drop_index("ix_data_workshop_skill_sessions_status", table_name="data_workshop_skill_sessions")
    op.drop_index("ix_dw_skill_sessions_scope_updated", table_name="data_workshop_skill_sessions")
    op.drop_table("data_workshop_skill_sessions")
    op.drop_index("ix_data_workshop_skills_status", table_name="data_workshop_skills")
    op.drop_index("ix_dw_skills_tenant_owner_updated", table_name="data_workshop_skills")
    op.drop_table("data_workshop_skills")
