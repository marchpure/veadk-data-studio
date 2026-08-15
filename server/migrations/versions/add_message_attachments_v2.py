"""add message_attachments table

Revision ID: add_message_attachments_v2
Revises: 17788cce911a
Create Date: 2026-01-05

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "add_message_attachments_v2"
down_revision = "17788cce911a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from sqlalchemy.dialects.postgresql import UUID

    op.create_table(
        "message_attachments",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", UUID(as_uuid=True), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=50), nullable=False),
        sa.Column("file_data", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("mime_type IN ('image/png', 'image/jpeg', 'image/webp')", name="ck_message_attachments_mime_type"),
    )


def downgrade() -> None:
    op.drop_table("message_attachments")
