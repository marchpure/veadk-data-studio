"""Simplify learnings table — drop and recreate with only title + learning columns

Revision ID: simplify_learnings_table
Revises: add_learnings_fts
Create Date: 2026-04-14

"""

import sqlalchemy as sa
from alembic import op
from fastapi_users_db_sqlalchemy.generics import GUID

revision = "simplify_learnings_table"
down_revision = "add_learnings_fts"
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


def upgrade() -> None:
    conn = op.get_bind()

    if conn.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS learnings_search_vector_trigger ON learnings")
        op.execute("DROP FUNCTION IF EXISTS learnings_search_vector_update()")

    op.drop_table("learnings")

    op.create_table(
        "learnings",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("learning", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_learnings")),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_learnings_tenant_id_tenants"), ondelete="CASCADE"
        ),
    )
    op.create_index(op.f("ix_learnings_tenant_id"), "learnings", ["tenant_id"])


def downgrade() -> None:
    from sqlalchemy.dialects.postgresql import TSVECTOR

    op.drop_index(op.f("ix_learnings_tenant_id"), table_name="learnings")
    op.drop_table("learnings")

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

    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.add_column("learnings", sa.Column("search_vector", TSVECTOR(), nullable=True))
        op.execute(TRIGGER_FUNCTION)
        op.execute(TRIGGER)
        op.create_index("ix_learnings_search_vector", "learnings", ["search_vector"], postgresql_using="gin")
