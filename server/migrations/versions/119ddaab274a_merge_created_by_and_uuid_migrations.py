"""merge created_by and uuid migrations

Revision ID: 119ddaab274a
Revises: a1c2e4f6g8h0, convert_varchar_to_uuid
Create Date: 2025-12-29 21:36:49.562586

"""

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision = '119ddaab274a'
down_revision = ('a1c2e4f6g8h0', 'convert_varchar_to_uuid')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

