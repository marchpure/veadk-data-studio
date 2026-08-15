"""Drop default_llm_connection_id from mcp_api_keys

Revision ID: drop_mcp_default_llm_connection
Revises: add_local_repo_support
Create Date: 2026-04-09

"""

import sqlalchemy as sa
from alembic import op
from fastapi_users_db_sqlalchemy.generics import GUID

revision = "drop_mcp_default_llm_connection"
down_revision = "add_local_repo_support"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("mcp_api_keys") as batch_op:
        batch_op.drop_constraint("fk_mcp_api_keys_default_llm_connection_id_llm_connections", type_="foreignkey")
        batch_op.drop_column("default_llm_connection_id")


def downgrade() -> None:
    with op.batch_alter_table("mcp_api_keys") as batch_op:
        batch_op.add_column(sa.Column("default_llm_connection_id", GUID(), nullable=True))
        batch_op.create_foreign_key(
            "fk_mcp_api_keys_default_llm_connection_id_llm_connections",
            "llm_connections",
            ["default_llm_connection_id"],
            ["id"],
            ondelete="SET NULL",
        )
