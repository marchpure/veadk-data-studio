"""add knowledge provider metadata

Revision ID: add_knowledge_provider_metadata
Revises: add_feishu_oauth_flows
Create Date: 2026-08-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "add_knowledge_provider_metadata"
down_revision = "add_feishu_oauth_flows"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table_name: str) -> set[str]:
    if table_name not in _tables():
        return set()
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def upgrade() -> None:
    if "knowledge_resources" not in _tables():
        return
    columns = _columns("knowledge_resources")
    additions = [
        ("context_uri", sa.Column("context_uri", sa.Text(), nullable=True)),
        ("provider_status", sa.Column("provider_status", sa.String(length=60), nullable=True)),
        ("last_indexed_at", sa.Column("last_indexed_at", sa.TIMESTAMP(), nullable=True)),
        ("provider_error", sa.Column("provider_error", sa.JSON(), nullable=True)),
        ("retrieval_debug_uri", sa.Column("retrieval_debug_uri", sa.Text(), nullable=True)),
        ("provider_metadata_json", sa.Column("provider_metadata_json", sa.JSON(), nullable=True)),
    ]
    with op.batch_alter_table("knowledge_resources") as batch_op:
        for name, column in additions:
            if name not in columns:
                batch_op.add_column(column)


def downgrade() -> None:
    if "knowledge_resources" not in _tables():
        return
    columns = _columns("knowledge_resources")
    removals = [
        "provider_metadata_json",
        "retrieval_debug_uri",
        "provider_error",
        "last_indexed_at",
        "provider_status",
        "context_uri",
    ]
    with op.batch_alter_table("knowledge_resources") as batch_op:
        for name in removals:
            if name in columns:
                batch_op.drop_column(name)
