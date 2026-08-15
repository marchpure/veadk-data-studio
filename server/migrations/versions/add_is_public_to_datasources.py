"""Add is_public to datasets and connections

Revision ID: add_is_public_to_datasources
Revises: add_api_query_support
Create Date: 2026-01-31

"""

import sqlalchemy as sa
from alembic import op

revision = "add_is_public_to_datasources"
down_revision = "add_api_query_support"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("datasets", sa.Column("is_public", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("connections", sa.Column("is_public", sa.Boolean(), server_default="false", nullable=False))


def downgrade() -> None:
    op.drop_column("datasets", "is_public")
    op.drop_column("connections", "is_public")
