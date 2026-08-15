"""add model selection columns to notebooks

Revision ID: i2g6h0d5e7f9
Revises: h1f5g9c4d6e8
Create Date: 2025-11-26 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'i2g6h0d5e7f9'
down_revision = 'h1f5g9c4d6e8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if columns exist before adding them (handles case where they were manually added)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('notebooks')]

    if 'last_used_provider' not in columns:
        op.add_column('notebooks', sa.Column('last_used_provider', sa.String(50), nullable=True))

    if 'last_used_model' not in columns:
        op.add_column('notebooks', sa.Column('last_used_model', sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column('notebooks', 'last_used_model')
    op.drop_column('notebooks', 'last_used_provider')
