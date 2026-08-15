"""add filters_config to notebooks

Revision ID: k4i8j2f9g1b2
Revises: 55dbc70ae325
Create Date: 2025-01-24 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'k4i8j2f9g1b2'
down_revision = '55dbc70ae325'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('notebooks')]

    if 'filters_config' not in columns:
        op.add_column('notebooks', sa.Column('filters_config', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('notebooks', 'filters_config')
