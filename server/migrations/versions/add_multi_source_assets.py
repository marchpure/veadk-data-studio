"""compatibility marker for legacy multi-source asset tables

Revision ID: add_multi_source_assets
Revises: add_semantic_modeling_tables
Create Date: 2026-08-14

Older self-hosted images shipped this revision with early Source Resource,
Knowledge Resource, Notebook Asset, and Analysis Artifact tables. The current
consolidated connector migration is idempotent and upgrades those tables to the
active schema, so this file only preserves the historical Alembic graph node.
"""

revision = "add_multi_source_assets"
down_revision = "add_semantic_modeling_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
