"""Add snapshot columns to folder_notebooks table

Revision ID: add_snapshot_columns
Revises: add_folder_sharing
Create Date: 2025-01-05

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "add_snapshot_columns"
down_revision = "add_folder_sharing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add snapshot columns to folder_notebooks table
    op.add_column(
        "folder_notebooks",
        sa.Column("is_snapshot", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "folder_notebooks",
        sa.Column("snapshot_data", sa.Text(), nullable=True),
    )
    op.add_column(
        "folder_notebooks",
        sa.Column("snapshot_updated_at", sa.TIMESTAMP(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("folder_notebooks", "snapshot_updated_at")
    op.drop_column("folder_notebooks", "snapshot_data")
    op.drop_column("folder_notebooks", "is_snapshot")
