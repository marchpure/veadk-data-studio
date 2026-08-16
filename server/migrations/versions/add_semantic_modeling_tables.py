"""compatibility marker for legacy semantic modeling tables

Revision ID: add_semantic_modeling_tables
Revises: add_oracle_connection_type
Create Date: 2026-08-14

Older self-hosted images shipped this revision with the first Semantic Model
tables. The current consolidated connector migration owns the final schema, but
existing installations can still have this revision recorded in alembic_version.
Keep the revision node so Alembic can advance those databases safely.
"""

revision = "add_semantic_modeling_tables"
down_revision = "add_oracle_connection_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
