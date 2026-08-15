"""Add API query support to queries table

Revision ID: add_api_query_support
Revises: add_custom_skills
Create Date: 2026-01-30

"""

import sqlalchemy as sa
from alembic import op

revision = "add_api_query_support"
down_revision = "add_custom_skills"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = [col["name"] for col in inspector.get_columns("queries")]

    with op.batch_alter_table("queries") as batch_op:
        if "query_type" not in existing_columns:
            batch_op.add_column(sa.Column("query_type", sa.String(length=10), nullable=False, server_default="sql"))

        if "skill_name" not in existing_columns:
            batch_op.add_column(sa.Column("skill_name", sa.String(length=50), nullable=True))

        if "skill_scope" not in existing_columns:
            batch_op.add_column(sa.Column("skill_scope", sa.String(length=10), nullable=True))

        if "api_config" not in existing_columns:
            batch_op.add_column(sa.Column("api_config", sa.Text(), nullable=True))

    with op.batch_alter_table("queries", recreate="always") as batch_op:
        batch_op.alter_column("dataset_id", existing_nullable=False, nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("queries") as batch_op:
        batch_op.drop_column("api_config")
        batch_op.drop_column("skill_scope")
        batch_op.drop_column("skill_name")
        batch_op.drop_column("query_type")

    with op.batch_alter_table("queries", recreate="always") as batch_op:
        batch_op.alter_column("dataset_id", existing_nullable=True, nullable=False)
