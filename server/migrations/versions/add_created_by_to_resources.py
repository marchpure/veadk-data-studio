"""Add created_by column to resources for ownership tracking

Revision ID: a1c2e4f6g8h0
Revises: 5793cc98ac53
Create Date: 2025-12-29

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "a1c2e4f6g8h0"
down_revision = "5793cc98ac53"
branch_labels = None
depends_on = None


def get_uuid_type():
    """Return appropriate UUID type based on database dialect."""
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        return postgresql.UUID(as_uuid=True)
    else:
        return sa.String(36)


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    uuid_type = get_uuid_type()

    # Add created_by to connections
    columns = [col["name"] for col in inspector.get_columns("connections")]
    if "created_by" not in columns:
        with op.batch_alter_table("connections") as batch_op:
            batch_op.add_column(sa.Column("created_by", uuid_type, nullable=True))
            batch_op.create_index("ix_connections_created_by", ["created_by"])
            batch_op.create_foreign_key(
                "fk_connections_created_by_users",
                "users",
                ["created_by"],
                ["id"],
                ondelete="SET NULL",
            )

    # Add created_by to datasets
    columns = [col["name"] for col in inspector.get_columns("datasets")]
    if "created_by" not in columns:
        with op.batch_alter_table("datasets") as batch_op:
            batch_op.add_column(sa.Column("created_by", uuid_type, nullable=True))
            batch_op.create_index("ix_datasets_created_by", ["created_by"])
            batch_op.create_foreign_key(
                "fk_datasets_created_by_users",
                "users",
                ["created_by"],
                ["id"],
                ondelete="SET NULL",
            )

    # Add created_by to queries
    columns = [col["name"] for col in inspector.get_columns("queries")]
    if "created_by" not in columns:
        with op.batch_alter_table("queries") as batch_op:
            batch_op.add_column(sa.Column("created_by", uuid_type, nullable=True))
            batch_op.create_index("ix_queries_created_by", ["created_by"])
            batch_op.create_foreign_key(
                "fk_queries_created_by_users",
                "users",
                ["created_by"],
                ["id"],
                ondelete="SET NULL",
            )

    # Add created_by to llm_connections
    columns = [col["name"] for col in inspector.get_columns("llm_connections")]
    if "created_by" not in columns:
        with op.batch_alter_table("llm_connections") as batch_op:
            batch_op.add_column(sa.Column("created_by", uuid_type, nullable=True))
            batch_op.create_index("ix_llm_connections_created_by", ["created_by"])
            batch_op.create_foreign_key(
                "fk_llm_connections_created_by_users",
                "users",
                ["created_by"],
                ["id"],
                ondelete="SET NULL",
            )


def downgrade() -> None:
    with op.batch_alter_table("llm_connections") as batch_op:
        batch_op.drop_constraint("fk_llm_connections_created_by_users", type_="foreignkey")
        batch_op.drop_index("ix_llm_connections_created_by")
        batch_op.drop_column("created_by")

    with op.batch_alter_table("queries") as batch_op:
        batch_op.drop_constraint("fk_queries_created_by_users", type_="foreignkey")
        batch_op.drop_index("ix_queries_created_by")
        batch_op.drop_column("created_by")

    with op.batch_alter_table("datasets") as batch_op:
        batch_op.drop_constraint("fk_datasets_created_by_users", type_="foreignkey")
        batch_op.drop_index("ix_datasets_created_by")
        batch_op.drop_column("created_by")

    with op.batch_alter_table("connections") as batch_op:
        batch_op.drop_constraint("fk_connections_created_by_users", type_="foreignkey")
        batch_op.drop_index("ix_connections_created_by")
        batch_op.drop_column("created_by")
