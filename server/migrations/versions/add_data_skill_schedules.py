"""compatibility marker for archived Data Skill schedules

Revision ID: add_data_skill_schedules
Revises: add_data_skill_studio_tables
Create Date: 2026-08-14

See add_data_skill_studio_tables.py for why these legacy Data Skill revisions
remain in the Alembic graph as no-op compatibility markers.
"""

revision = "add_data_skill_schedules"
down_revision = "add_data_skill_studio_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
