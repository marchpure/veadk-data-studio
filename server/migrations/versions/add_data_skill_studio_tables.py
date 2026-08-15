"""compatibility marker for archived Data Skill Studio tables

Revision ID: add_data_skill_studio_tables
Revises: add_skill_loop_lease
Create Date: 2026-08-14

Earlier integration images exposed Data Skill Studio as a first-class feature
and recorded this Alembic revision. The implementation has since been archived
out of mainline, while current self-hosted databases may still have one of the
Data Skill revisions stamped in alembic_version. Keep the historical graph node
so those installations can advance to the active Semantic Model / Source
Connector migrations without resurrecting Data Skill production tables.
"""

revision = "add_data_skill_studio_tables"
down_revision = "add_skill_loop_lease"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
