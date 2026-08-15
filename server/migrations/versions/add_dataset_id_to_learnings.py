"""Add dataset_id column to learnings table

Revision ID: add_dataset_id_to_learnings
Revises: simplify_learnings_table
Create Date: 2026-04-14

"""

import sqlalchemy as sa
from alembic import op
from fastapi_users_db_sqlalchemy.generics import GUID

revision = "add_dataset_id_to_learnings"
down_revision = "simplify_learnings_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("learnings") as batch_op:
        batch_op.add_column(sa.Column("dataset_id", GUID(), nullable=True))
        batch_op.create_foreign_key(
            op.f("fk_learnings_dataset_id_datasets"),
            "datasets",
            ["dataset_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(op.f("ix_learnings_dataset_id"), "learnings", ["dataset_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_learnings_dataset_id"), table_name="learnings")
    with op.batch_alter_table("learnings") as batch_op:
        batch_op.drop_constraint(op.f("fk_learnings_dataset_id_datasets"), type_="foreignkey")
        batch_op.drop_column("dataset_id")
