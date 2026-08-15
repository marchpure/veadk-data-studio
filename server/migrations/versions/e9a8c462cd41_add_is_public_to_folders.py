"""add_is_public_to_folders

Revision ID: e9a8c462cd41
Revises: add_user_id_to_settings
Create Date: 2026-01-07 23:12:27.189078

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e9a8c462cd41"
down_revision = "add_user_id_to_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("folders", sa.Column("is_public", sa.Boolean(), server_default="false", nullable=False))


def downgrade() -> None:
    op.drop_column("folders", "is_public")
