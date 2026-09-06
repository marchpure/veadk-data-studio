"""add Data Studio OpenViking profile store

Revision ID: add_dwv1_openviking_profile_store
Revises: add_dwv1_external_oidc
Create Date: 2026-09-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "add_dwv1_openviking_profile_store"
down_revision = "add_dwv1_external_oidc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "openviking_profiles",
        sa.Column("profile_id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("workspace_id", sa.String(255), nullable=False),
        sa.Column("principal_id", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("encrypted_base_url", sa.LargeBinary(), nullable=False),
        sa.Column("encrypted_api_key", sa.LargeBinary(), nullable=False),
        sa.Column("workspace_uri", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("profile_id"),
    )
    op.create_index(
        "ix_openviking_profile_scope",
        "openviking_profiles",
        ["tenant_id", "workspace_id", "principal_id"],
    )

    op.create_table(
        "openviking_task_history",
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("workspace_id", sa.String(255), nullable=False),
        sa.Column("profile_id", sa.String(64), nullable=False),
        sa.Column("task_id", sa.String(255), nullable=False),
        sa.Column("task_json", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "workspace_id", "profile_id", "task_id"),
    )

    op.create_table(
        "openviking_idempotency",
        sa.Column("scope_key", sa.String(128), nullable=False),
        sa.Column("response_json", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("scope_key"),
    )

    op.create_table(
        "openviking_resource_refs",
        sa.Column("ref_id", sa.String(64), nullable=False),
        sa.Column("profile_id", sa.String(64), nullable=False),
        sa.Column("encrypted_uri", sa.LargeBinary(), nullable=False),
        sa.Column("uri_digest", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("ref_id"),
    )
    op.create_index("ix_openviking_resource_ref_profile", "openviking_resource_refs", ["profile_id"])
    op.create_index(
        "ix_openviking_resource_ref_unique",
        "openviking_resource_refs",
        ["profile_id", "uri_digest"],
        unique=True,
        postgresql_where=sa.text("uri_digest <> ''"),
    )


def downgrade() -> None:
    op.drop_index("ix_openviking_resource_ref_unique", table_name="openviking_resource_refs")
    op.drop_index("ix_openviking_resource_ref_profile", table_name="openviking_resource_refs")
    op.drop_table("openviking_resource_refs")
    op.drop_table("openviking_idempotency")
    op.drop_table("openviking_task_history")
    op.drop_index("ix_openviking_profile_scope", table_name="openviking_profiles")
    op.drop_table("openviking_profiles")
