"""add skill_credentials table

Revision ID: add_skill_credentials
Revises: add_message_attachments_v2
Create Date: 2026-01-28

"""

import sqlalchemy as sa
from alembic import op
from fastapi_users_db_sqlalchemy.generics import GUID

revision = "add_skill_credentials"
down_revision = "add_query_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "skill_credentials",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("user_id", GUID(), nullable=False),
        sa.Column("skill_name", sa.String(length=50), nullable=False),
        sa.Column("credentials_encrypted", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_skill_credentials_tenant_id_tenants"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_skill_credentials_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_skill_credentials")),
        sa.UniqueConstraint("tenant_id", "user_id", "skill_name", name="uq_skill_credentials_tenant_user_skill"),
    )
    op.create_index(op.f("ix_skill_credentials_tenant_id"), "skill_credentials", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_skill_credentials_user_id"), "skill_credentials", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_skill_credentials_user_id"), table_name="skill_credentials")
    op.drop_index(op.f("ix_skill_credentials_tenant_id"), table_name="skill_credentials")
    op.drop_table("skill_credentials")
