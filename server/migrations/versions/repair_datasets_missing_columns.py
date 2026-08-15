"""Repair datasets table missing is_public and description columns on SQLite

The add_skill_api_dataset_type migration recreated the datasets table for SQLite
with a hardcoded CREATE TABLE that omitted is_public and description columns added
by sibling migration branches. This migration re-adds them if missing.

Revision ID: repair_datasets_missing_columns
Revises: add_plain_token_to_invitations
Create Date: 2026-02-16

"""

import sqlalchemy as sa
from alembic import op

revision = "repair_datasets_missing_columns"
down_revision = "add_plain_token_to_invitations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = [c["name"] for c in inspector.get_columns("datasets")]

    if "description" not in existing:
        op.add_column("datasets", sa.Column("description", sa.Text(), nullable=True))
    if "is_public" not in existing:
        op.add_column("datasets", sa.Column("is_public", sa.Boolean(), server_default="false", nullable=False))


def downgrade() -> None:
    pass
