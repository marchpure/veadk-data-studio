"""add persistent Feishu OAuth flows

Revision ID: add_feishu_oauth_flows
Revises: add_collaboration_integration_tables
Create Date: 2026-08-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from fastapi_users_db_sqlalchemy.generics import GUID

revision = "add_feishu_oauth_flows"
down_revision = "add_collaboration_integration_tables"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "feishu_oauth_flows" in _tables():
        return
    op.create_table(
        "feishu_oauth_flows",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("user_id", GUID(), nullable=False),
        sa.Column("state_hash", sa.String(128), nullable=False),
        sa.Column("purpose", sa.String(60), nullable=False, server_default="source_authorization"),
        sa.Column("provider", sa.String(30), nullable=False, server_default="feishu"),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("redirect_origin", sa.Text(), nullable=True),
        sa.Column("status", sa.String(60), nullable=False, server_default="authorizing"),
        sa.Column("connection_id", GUID(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("error_json", sa.JSON(), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(), nullable=False),
        sa.Column("consumed_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.CheckConstraint("provider IN ('feishu')", name="ck_feishu_oauth_flows_provider"),
        sa.CheckConstraint(
            "status IN ('authorizing', 'connected', 'state_expired', 'authorization_declined', 'scope_missing', "
            "'admin_approval_required', 'oauth_error', 'callback_unreachable')",
            name="ck_feishu_oauth_flows_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["connection_id"], ["source_connections.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_feishu_oauth_flows")),
        sa.UniqueConstraint("state_hash", name=op.f("uq_feishu_oauth_flows_state_hash")),
    )
    op.create_index("ix_feishu_oauth_flows_tenant_id", "feishu_oauth_flows", ["tenant_id"])
    op.create_index("ix_feishu_oauth_flows_user_id", "feishu_oauth_flows", ["user_id"])
    op.create_index("ix_feishu_oauth_flows_state_hash", "feishu_oauth_flows", ["state_hash"])
    op.create_index("ix_feishu_oauth_flows_status", "feishu_oauth_flows", ["status"])
    op.create_index("ix_feishu_oauth_flows_connection_id", "feishu_oauth_flows", ["connection_id"])
    op.create_index("ix_feishu_oauth_flows_expires_at", "feishu_oauth_flows", ["expires_at"])
    op.create_index("ix_feishu_oauth_flows_consumed_at", "feishu_oauth_flows", ["consumed_at"])


def downgrade() -> None:
    if "feishu_oauth_flows" not in _tables():
        return
    op.drop_index("ix_feishu_oauth_flows_consumed_at", table_name="feishu_oauth_flows")
    op.drop_index("ix_feishu_oauth_flows_expires_at", table_name="feishu_oauth_flows")
    op.drop_index("ix_feishu_oauth_flows_connection_id", table_name="feishu_oauth_flows")
    op.drop_index("ix_feishu_oauth_flows_status", table_name="feishu_oauth_flows")
    op.drop_index("ix_feishu_oauth_flows_state_hash", table_name="feishu_oauth_flows")
    op.drop_index("ix_feishu_oauth_flows_user_id", table_name="feishu_oauth_flows")
    op.drop_index("ix_feishu_oauth_flows_tenant_id", table_name="feishu_oauth_flows")
    op.drop_table("feishu_oauth_flows")
