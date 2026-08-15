"""add message attachments

Revision ID: h1f5g9c4d6e8
Revises: g9e4f8b2c3d5
Create Date: 2025-11-20 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'h1f5g9c4d6e8'
down_revision = 'g9e4f8b2c3d5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'message_attachments',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('message_id', sa.String(length=36), nullable=False),
        sa.Column('file_name', sa.String(length=255), nullable=False),
        sa.Column('mime_type', sa.String(length=50), nullable=False),
        sa.Column('file_data', sa.Text(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint("mime_type IN ('image/png', 'image/jpeg', 'image/webp')", name=op.f('ck_message_attachments_mime_type')),
        sa.ForeignKeyConstraint(['message_id'], ['messages.id'], name=op.f('fk_message_attachments_message_id_messages'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_message_attachments'))
    )


def downgrade() -> None:
    op.drop_table('message_attachments')
