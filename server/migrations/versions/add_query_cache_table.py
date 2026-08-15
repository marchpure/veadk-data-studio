"""Add query_cache table for PostgreSQL-backed caching

Revision ID: add_query_cache
Revises: k4i8j2f9g1b2
Create Date: 2025-01-26

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = "add_query_cache"
down_revision = "k4i8j2f9g1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    if conn.dialect.name == "postgresql":
        result_data_type = JSONB()
    else:
        result_data_type = sa.JSON()

    op.create_table(
        "query_cache",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("cache_key", sa.Text(), nullable=False, unique=True, index=True),
        sa.Column("query_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("result_data", result_data_type, nullable=False),
        sa.Column("ttl_seconds", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.current_timestamp()),
        sa.Column("expires_at", sa.TIMESTAMP(), nullable=False, index=True),
        sa.Column("has_filters", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    op.create_index(
        "ix_query_cache_query_expires",
        "query_cache",
        ["query_id", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_query_cache_query_expires", table_name="query_cache")
    op.drop_table("query_cache")
