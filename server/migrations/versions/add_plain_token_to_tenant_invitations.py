"""Add plain_token column to tenant_invitations

Revision ID: add_plain_token_to_invitations
Revises: merge_agent_filter_heads
Create Date: 2026-02-16

"""

import sqlalchemy as sa
from alembic import op

revision = "add_plain_token_to_invitations"
down_revision = "merge_agent_filter_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col["name"] for col in inspector.get_columns("tenant_invitations")]
    if "plain_token" not in columns:
        op.add_column("tenant_invitations", sa.Column("plain_token", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("tenant_invitations", "plain_token")
