"""add claude_session_id to notebooks

Revision ID: j3h7i1e8f0a1
Revises: i2g6h0d5e7f9
Create Date: 2025-12-17 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'j3h7i1e8f0a1'
down_revision = 'i2g6h0d5e7f9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if column exists before adding it (handles case where it was manually added)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('notebooks')]

    if 'claude_session_id' not in columns:
        op.add_column('notebooks', sa.Column('claude_session_id', sa.String(length=255), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    op.drop_column('notebooks', 'claude_session_id')