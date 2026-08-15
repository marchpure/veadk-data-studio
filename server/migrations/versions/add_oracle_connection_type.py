"""add oracle connection type

Revision ID: add_oracle_connection_type
Revises: add_skill_loop_lease
Create Date: 2026-08-14
"""

from alembic import op

revision = "add_oracle_connection_type"
down_revision = "add_skill_loop_lease"
branch_labels = None
depends_on = None

OLD_TYPES = ("pg", "mysql", "mongo", "sqlite", "mssql", "dynamodb", "databricks")
NEW_TYPES = ("pg", "mysql", "mongo", "sqlite", "mssql", "oracle", "dynamodb", "databricks")


def upgrade() -> None:
    with op.batch_alter_table("connections") as batch_op:
        batch_op.drop_constraint("ck_connections_type_allowed", type_="check")
        batch_op.create_check_constraint("ck_connections_type_allowed", f"type IN {NEW_TYPES}")


def downgrade() -> None:
    with op.batch_alter_table("connections") as batch_op:
        batch_op.drop_constraint("ck_connections_type_allowed", type_="check")
        batch_op.create_check_constraint("ck_connections_type_allowed", f"type IN {OLD_TYPES}")
