"""Add learnings table for structured agent self-learning

Revision ID: add_learnings_table
Revises: drop_mcp_default_llm_connection
Create Date: 2026-04-10

"""

from alembic import op
import sqlalchemy as sa
from fastapi_users_db_sqlalchemy.generics import GUID

revision = "add_learnings_table"
down_revision = "drop_mcp_default_llm_connection"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learnings",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("learning", sa.Text(), nullable=False),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("tags", sa.Text(), nullable=True),
        sa.Column("datasource_id", GUID(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_learnings")),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_learnings_tenant_id_tenants"), ondelete="CASCADE"
        ),
    )
    op.create_index(op.f("ix_learnings_tenant_id"), "learnings", ["tenant_id"])
    op.create_index(op.f("ix_learnings_datasource_id"), "learnings", ["datasource_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_learnings_datasource_id"), table_name="learnings")
    op.drop_index(op.f("ix_learnings_tenant_id"), table_name="learnings")
    op.drop_table("learnings")
