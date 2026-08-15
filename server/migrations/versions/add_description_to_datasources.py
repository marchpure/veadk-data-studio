"""Add description to datasets and connections

Revision ID: add_description_to_datasources
Revises: add_is_public_to_datasources
Create Date: 2026-01-31

"""

import sqlalchemy as sa
from alembic import op

revision = "add_description_to_datasources"
down_revision = "add_is_public_to_datasources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("datasets", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("connections", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("datasets", "description")
    op.drop_column("connections", "description")
