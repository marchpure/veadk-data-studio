"""merge migration branches

Revision ID: ef023df73ec3
Revises: add_instruction_to_schedules, add_skill_api_dataset_type
Create Date: 2026-02-02 17:19:43.700597

"""

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision = 'ef023df73ec3'
down_revision = ('add_instruction_to_schedules', 'add_skill_api_dataset_type')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

