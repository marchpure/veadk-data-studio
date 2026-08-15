"""add custom_skills table

Revision ID: add_custom_skills
Revises: add_scope_to_skill_credentials
Create Date: 2026-01-30

"""

import sqlalchemy as sa
from alembic import op
from fastapi_users_db_sqlalchemy.generics import GUID

revision = "add_custom_skills"
down_revision = "add_scope_to_skill_credentials"
branch_labels = None
depends_on = None

TABLE_NAME = "custom_skills"


def upgrade() -> None:
    op.create_table(
        TABLE_NAME,
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("created_by", GUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("scope", sa.String(length=10), nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_custom_skills_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_custom_skills_created_by_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_custom_skills")),
    )

    op.create_index(
        "ix_custom_skills_tenant_id", TABLE_NAME, ["tenant_id"], unique=False
    )
    op.create_index(
        "ix_custom_skills_created_by", TABLE_NAME, ["created_by"], unique=False
    )
    op.create_index(
        "ix_custom_skills_tenant_scope",
        TABLE_NAME,
        ["tenant_id", "scope"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_custom_skills_tenant_scope", table_name=TABLE_NAME)
    op.drop_index("ix_custom_skills_created_by", table_name=TABLE_NAME)
    op.drop_index("ix_custom_skills_tenant_id", table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)
