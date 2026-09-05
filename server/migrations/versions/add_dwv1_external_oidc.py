"""add Data Studio external OIDC sessions

Revision ID: add_dwv1_external_oidc
Revises: add_dw_skill_workbench
Create Date: 2026-09-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from server.db.base import GUID

revision = "add_dwv1_external_oidc"
down_revision = "add_dw_skill_workbench"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dwv1_external_oidc_logins",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("state_hash", sa.String(64), nullable=False),
        sa.Column("encrypted_code_verifier", sa.Text(), nullable=False),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_hash"),
    )
    op.create_index("ix_dwv1_external_oidc_logins_state_hash", "dwv1_external_oidc_logins", ["state_hash"])
    op.create_index("ix_dwv1_external_oidc_logins_expires_at", "dwv1_external_oidc_logins", ["expires_at"])

    op.create_table(
        "dwv1_external_oidc_sessions",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("session_hash", sa.String(64), nullable=False),
        sa.Column("user_id", GUID(), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("groups", sa.Text(), nullable=False),
        sa.Column("encrypted_tokens", sa.Text(), nullable=False),
        sa.Column("issuer", sa.Text(), nullable=False),
        sa.Column("audience", sa.String(255), nullable=False),
        sa.Column("user_pool", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_hash"),
    )
    op.create_index("ix_dwv1_external_oidc_sessions_session_hash", "dwv1_external_oidc_sessions", ["session_hash"])
    op.create_index("ix_dwv1_external_oidc_sessions_user_id", "dwv1_external_oidc_sessions", ["user_id"])
    op.create_index("ix_dwv1_external_oidc_sessions_expires_at", "dwv1_external_oidc_sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_dwv1_external_oidc_sessions_expires_at", table_name="dwv1_external_oidc_sessions")
    op.drop_index("ix_dwv1_external_oidc_sessions_user_id", table_name="dwv1_external_oidc_sessions")
    op.drop_index("ix_dwv1_external_oidc_sessions_session_hash", table_name="dwv1_external_oidc_sessions")
    op.drop_table("dwv1_external_oidc_sessions")
    op.drop_index("ix_dwv1_external_oidc_logins_expires_at", table_name="dwv1_external_oidc_logins")
    op.drop_index("ix_dwv1_external_oidc_logins_state_hash", table_name="dwv1_external_oidc_logins")
    op.drop_table("dwv1_external_oidc_logins")
