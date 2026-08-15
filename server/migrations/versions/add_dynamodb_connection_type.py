"""Add dynamodb to allowed connection types

Revision ID: add_dynamodb_connection_type
Revises: add_dataset_id_to_learnings
Create Date: 2026-04-15

"""

from alembic import op

revision = "add_dynamodb_connection_type"
down_revision = "add_dataset_id_to_learnings"
branch_labels = None
depends_on = None

OLD_TYPES = ("pg", "mysql", "mongo", "sqlite", "mssql")
NEW_TYPES = ("pg", "mysql", "mongo", "sqlite", "mssql", "dynamodb")


def upgrade() -> None:
    with op.batch_alter_table("connections") as batch_op:
        batch_op.drop_constraint("ck_connections_type_allowed", type_="check")
        batch_op.create_check_constraint("ck_connections_type_allowed", f"type IN {NEW_TYPES}")


def downgrade() -> None:
    with op.batch_alter_table("connections") as batch_op:
        batch_op.drop_constraint("ck_connections_type_allowed", type_="check")
        batch_op.create_check_constraint("ck_connections_type_allowed", f"type IN {OLD_TYPES}")
