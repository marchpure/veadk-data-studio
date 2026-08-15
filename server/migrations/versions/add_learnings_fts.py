"""Add full-text search support to learnings table (PostgreSQL only)

Revision ID: add_learnings_fts
Revises: add_learnings_table
Create Date: 2026-04-13

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TSVECTOR

revision = "add_learnings_fts"
down_revision = "add_learnings_table"
branch_labels = None
depends_on = None


TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION learnings_search_vector_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('english', coalesce(NEW.title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(NEW.learning, '')), 'B') ||
        setweight(to_tsvector('english', coalesce(NEW.tags, '')), 'C');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

TRIGGER = """
CREATE TRIGGER learnings_search_vector_trigger
    BEFORE INSERT OR UPDATE OF title, learning, tags
    ON learnings
    FOR EACH ROW
    EXECUTE FUNCTION learnings_search_vector_update();
"""

BACKFILL = """
UPDATE learnings SET search_vector =
    setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(learning, '')), 'B') ||
    setweight(to_tsvector('english', coalesce(tags, '')), 'C');
"""


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    op.add_column("learnings", sa.Column("search_vector", TSVECTOR(), nullable=True))
    op.execute(TRIGGER_FUNCTION)
    op.execute(TRIGGER)
    op.execute(BACKFILL)
    op.create_index("ix_learnings_search_vector", "learnings", ["search_vector"], postgresql_using="gin")


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    op.drop_index("ix_learnings_search_vector", table_name="learnings")
    op.execute("DROP TRIGGER IF EXISTS learnings_search_vector_trigger ON learnings")
    op.execute("DROP FUNCTION IF EXISTS learnings_search_vector_update()")
    op.drop_column("learnings", "search_vector")
