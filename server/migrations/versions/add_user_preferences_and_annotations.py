"""add user preferences and datasource annotations tables

Revision ID: f8d3e7a1b2c4
Revises: 9d41f3cdb2ab
Create Date: 2025-11-05 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f8d3e7a1b2c4'
down_revision = '9d41f3cdb2ab'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create user_preferences table
    op.create_table('user_preferences',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('preference_type', sa.String(length=50), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('(CURRENT_TIMESTAMP)'), onupdate=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_preferences')),
    sa.UniqueConstraint('preference_type', name=op.f('uq_user_preferences_preference_type'))
    )

    # Create datasource_annotations table
    op.create_table('datasource_annotations',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('datasource_id', sa.String(length=36), nullable=False),
    sa.Column('table_name', sa.String(length=255), nullable=False),
    sa.Column('column_name', sa.String(length=255), nullable=True),
    sa.Column('annotation_type', sa.String(length=50), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('(CURRENT_TIMESTAMP)'), onupdate=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_datasource_annotations')),
    sa.UniqueConstraint('datasource_id', 'table_name', 'column_name', 'annotation_type',
                       name=op.f('uq_datasource_annotations_unique_annotation'))
    )

    # Create index for faster lookups by datasource_id
    op.create_index(
        op.f('ix_datasource_annotations_datasource_id'),
        'datasource_annotations',
        ['datasource_id'],
        unique=False
    )


def downgrade() -> None:
    # Drop datasource_annotations table and index
    op.drop_index(op.f('ix_datasource_annotations_datasource_id'), table_name='datasource_annotations')
    op.drop_table('datasource_annotations')

    # Drop user_preferences table
    op.drop_table('user_preferences')
