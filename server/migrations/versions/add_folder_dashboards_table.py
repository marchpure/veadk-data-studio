"""Add folder_dashboards table for sharing dashboards to folders

Revision ID: add_folder_dashboards
Revises: add_message_attachments_v2
Create Date: 2025-01-05

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = "add_folder_dashboards"
down_revision = "add_message_attachments_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create folder_dashboards table with unique constraint inline (SQLite compatible)
    op.create_table(
        "folder_dashboards",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("folder_id", UUID(as_uuid=True), sa.ForeignKey("folders.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column(
            "dashboard_id", UUID(as_uuid=True), sa.ForeignKey("dashboards.id", ondelete="CASCADE"), nullable=False, index=True
        ),
        sa.Column("shared_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("is_snapshot", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("snapshot_data", sa.Text(), nullable=True),
        sa.Column("snapshot_updated_at", sa.TIMESTAMP(), nullable=True),
        sa.UniqueConstraint("folder_id", "dashboard_id", name="uq_folder_dashboards_folder_dashboard"),
    )


def downgrade() -> None:
    op.drop_table("folder_dashboards")
