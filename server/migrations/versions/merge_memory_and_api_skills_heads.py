"""Merge memory and api-skills migration branches

Revision ID: merge_memory_and_api_skills
Revises: drop_memory_from_notebooks, add_api_config_to_custom_skills
Create Date: 2026-03-02
"""

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401

revision = "merge_memory_and_api_skills"
down_revision = ("drop_memory_from_notebooks", "add_api_config_to_custom_skills")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
