"""Compatibility marker for archived Data Skill revisions.

Revision ID: add_data_skill_agent_runs
Revises: add_oracle_connection_type
Create Date: 2026-08-14
"""

revision = "add_data_skill_agent_runs"
down_revision = "add_oracle_connection_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Historical self-hosted volumes may already be stamped with this archived
    # Data Skill revision. The Data Skill tables are not required by main.
    pass


def downgrade() -> None:
    pass
