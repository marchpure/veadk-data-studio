"""merge_snapshot_and_auth_branches

Revision ID: 17788cce911a
Revises: 119ddaab274a, add_snapshot_columns
Create Date: 2026-01-05 17:31:08.366552

"""

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision = '17788cce911a'
down_revision = ('119ddaab274a', 'add_snapshot_columns')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

