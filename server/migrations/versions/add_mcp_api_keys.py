"""Add MCP API keys and sessions tables

Revision ID: add_mcp_api_keys
Revises: merge_memory_and_api_skills
Create Date: 2026-02-26

"""

import sqlalchemy as sa
from alembic import op
from fastapi_users_db_sqlalchemy.generics import GUID

revision = "add_mcp_api_keys"
down_revision = "merge_memory_and_api_skills"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_api_keys",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("user_id", GUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("key_prefix", sa.String(length=20), nullable=False),
        sa.Column("default_llm_connection_id", GUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_used_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column(
            "updated_at", sa.TIMESTAMP(), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mcp_api_keys")),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_mcp_api_keys_tenant_id_tenants"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_mcp_api_keys_user_id_users"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["default_llm_connection_id"],
            ["llm_connections.id"],
            name=op.f("fk_mcp_api_keys_default_llm_connection_id_llm_connections"),
            ondelete="SET NULL",
        ),
    )
    op.create_index(op.f("ix_mcp_api_keys_tenant_id"), "mcp_api_keys", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_mcp_api_keys_user_id"), "mcp_api_keys", ["user_id"], unique=False)
    op.create_index(op.f("ix_mcp_api_keys_key_hash"), "mcp_api_keys", ["key_hash"], unique=True)

    op.create_table(
        "mcp_sessions",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("session_id", sa.String(length=100), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("user_id", GUID(), nullable=False),
        sa.Column("mcp_api_key_id", GUID(), nullable=True),
        sa.Column("notebook_id", GUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_activity_at", sa.TIMESTAMP(), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mcp_sessions")),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_mcp_sessions_tenant_id_tenants"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_mcp_sessions_user_id_users"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["mcp_api_key_id"],
            ["mcp_api_keys.id"],
            name=op.f("fk_mcp_sessions_mcp_api_key_id_mcp_api_keys"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["notebook_id"], ["notebooks.id"], name=op.f("fk_mcp_sessions_notebook_id_notebooks"), ondelete="SET NULL"
        ),
    )
    op.create_index(op.f("ix_mcp_sessions_session_id"), "mcp_sessions", ["session_id"], unique=True)
    op.create_index(op.f("ix_mcp_sessions_tenant_id"), "mcp_sessions", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_mcp_sessions_user_id"), "mcp_sessions", ["user_id"], unique=False)
    op.create_index(op.f("ix_mcp_sessions_mcp_api_key_id"), "mcp_sessions", ["mcp_api_key_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_mcp_sessions_mcp_api_key_id"), table_name="mcp_sessions")
    op.drop_index(op.f("ix_mcp_sessions_user_id"), table_name="mcp_sessions")
    op.drop_index(op.f("ix_mcp_sessions_tenant_id"), table_name="mcp_sessions")
    op.drop_index(op.f("ix_mcp_sessions_session_id"), table_name="mcp_sessions")
    op.drop_table("mcp_sessions")

    op.drop_index(op.f("ix_mcp_api_keys_key_hash"), table_name="mcp_api_keys")
    op.drop_index(op.f("ix_mcp_api_keys_user_id"), table_name="mcp_api_keys")
    op.drop_index(op.f("ix_mcp_api_keys_tenant_id"), table_name="mcp_api_keys")
    op.drop_table("mcp_api_keys")
