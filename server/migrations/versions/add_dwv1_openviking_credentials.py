"""add OpenViking credential mode and validation timestamp

Revision ID: add_dwv1_openviking_credentials
Revises: add_dwv1_openviking_profile_store
Create Date: 2026-09-07
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "add_dwv1_openviking_credentials"
down_revision = "add_dwv1_openviking_profile_store"
branch_labels = None
depends_on = None


def upgrade() -> None:
    policy = os.getenv("OPENVIKING_CREDENTIAL_POLICY", "").strip().casefold()
    managed_runtime = (
        os.getenv("DWV1_EXTERNAL_OIDC_ENABLED", "").strip().casefold() in {"1", "true", "yes"}
        or bool(os.getenv("OPENVIKING_MANAGED_BASE_URL", "").strip())
    )
    legacy_mode = "byok" if policy == "byok" or (not policy and not managed_runtime) else "managed"
    with op.batch_alter_table("openviking_profiles", recreate="always") as batch_op:
        batch_op.add_column(
            sa.Column("credential_mode", sa.String(16), nullable=False, server_default="managed"),
        )
        batch_op.create_check_constraint(
            "ck_openviking_profile_credential_mode",
            "credential_mode IN ('managed', 'byok')",
        )
        batch_op.add_column(
            sa.Column("last_validated_at", sa.Float(), nullable=True),
        )
    if legacy_mode == "byok":
        op.execute("UPDATE openviking_profiles SET credential_mode = 'byok'")
    op.create_table(
        "openviking_access_grants",
        sa.Column("grant_id", sa.String(80), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("profile_id", sa.String(64), nullable=False),
        sa.Column("subject_type", sa.String(16), nullable=False),
        sa.Column("subject", sa.String(256), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("effect", sa.String(16), nullable=False),
        sa.Column("actions", sa.Text(), nullable=False),
        sa.Column("conditions", sa.Text(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False, server_default=""),
        sa.Column("policy_version", sa.String(32), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
        sa.Column("revoked_at", sa.Float(), nullable=True),
    )
    op.create_index("ix_ov_access_grants_scope", "openviking_access_grants", ["tenant_id", "profile_id", "revoked_at"])
    op.create_table(
        "openviking_access_audit",
        sa.Column("audit_id", sa.String(80), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("profile_id", sa.String(64), nullable=False),
        sa.Column("actor", sa.String(256), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("subject_type", sa.String(16), nullable=True),
        sa.Column("subject", sa.String(256), nullable=True),
        sa.Column("details", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.Float(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("openviking_access_audit")
    op.drop_index("ix_ov_access_grants_scope", table_name="openviking_access_grants")
    op.drop_table("openviking_access_grants")
    with op.batch_alter_table("openviking_profiles", recreate="always") as batch_op:
        batch_op.drop_column("last_validated_at")
        batch_op.drop_constraint(
            "ck_openviking_profile_credential_mode",
            type_="check",
        )
        batch_op.drop_column("credential_mode")
