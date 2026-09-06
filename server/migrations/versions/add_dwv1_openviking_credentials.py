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


def downgrade() -> None:
    with op.batch_alter_table("openviking_profiles", recreate="always") as batch_op:
        batch_op.drop_column("last_validated_at")
        batch_op.drop_constraint(
            "ck_openviking_profile_credential_mode",
            type_="check",
        )
        batch_op.drop_column("credential_mode")
