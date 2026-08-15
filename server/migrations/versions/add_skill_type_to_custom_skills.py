"""add skill_type to custom_skills

Revision ID: add_skill_type_to_custom_skills
Revises: add_custom_skills
Create Date: 2026-02-01

"""

import sqlalchemy as sa
from alembic import op

revision = "add_skill_type_to_custom_skills"
down_revision = "add_custom_skills"
branch_labels = None
depends_on = None

TABLE_NAME = "custom_skills"


def upgrade() -> None:
    op.add_column(
        TABLE_NAME,
        sa.Column("skill_type", sa.String(length=30), nullable=False, server_default="general"),
    )
    op.create_index(
        "ix_custom_skills_skill_type",
        TABLE_NAME,
        ["skill_type"],
        unique=False,
    )
    op.create_index(
        "ix_custom_skills_tenant_skill_type",
        TABLE_NAME,
        ["tenant_id", "skill_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_custom_skills_tenant_skill_type", table_name=TABLE_NAME)
    op.drop_index("ix_custom_skills_skill_type", table_name=TABLE_NAME)
    op.drop_column(TABLE_NAME, "skill_type")
