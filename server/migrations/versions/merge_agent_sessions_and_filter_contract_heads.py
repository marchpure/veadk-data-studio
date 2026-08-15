"""Merge agent sessions and filter contract heads.

Revision ID: merge_agent_filter_heads
Revises: add_agent_sessions_tables, add_filter_contract_to_queries
Create Date: 2026-02-07
"""

revision = "merge_agent_filter_heads"
down_revision = ("add_agent_sessions_tables", "add_filter_contract_to_queries")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
