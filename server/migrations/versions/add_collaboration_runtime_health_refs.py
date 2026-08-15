"""add collaboration runtime health refs

Revision ID: add_collaboration_runtime_health_refs
Revises: add_collaboration_integration_tables
Create Date: 2026-08-15

Adds nullable/runtime-safe fields introduced after the first collaboration
tables migration. This migration is intentionally separate because existing
Team databases may already have applied add_collaboration_integration_tables.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from fastapi_users_db_sqlalchemy.generics import GUID

revision = "add_collaboration_runtime_health_refs"
down_revision = "add_collaboration_integration_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("collaboration_installations") as batch_op:
        batch_op.add_column(sa.Column("reconnect_count", sa.Integer(), nullable=False, server_default="0"))

    with op.batch_alter_table("collaboration_event_logs") as batch_op:
        batch_op.add_column(sa.Column("conversation_id", GUID(), nullable=True))
        batch_op.add_column(sa.Column("notebook_id", GUID(), nullable=True))
        batch_op.add_column(sa.Column("run_id", sa.String(128), nullable=True))
        batch_op.create_foreign_key(
            "fk_collab_event_logs_conversation_id",
            "collaboration_conversations",
            ["conversation_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_collab_event_logs_notebook_id",
            "notebooks",
            ["notebook_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_collaboration_event_logs_conversation_id", ["conversation_id"])
        batch_op.create_index("ix_collaboration_event_logs_run_id", ["run_id"])


def downgrade() -> None:
    with op.batch_alter_table("collaboration_event_logs") as batch_op:
        batch_op.drop_index("ix_collaboration_event_logs_run_id")
        batch_op.drop_index("ix_collaboration_event_logs_conversation_id")
        batch_op.drop_constraint(
            "fk_collab_event_logs_notebook_id",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_collab_event_logs_conversation_id",
            type_="foreignkey",
        )
        batch_op.drop_column("run_id")
        batch_op.drop_column("notebook_id")
        batch_op.drop_column("conversation_id")

    with op.batch_alter_table("collaboration_installations") as batch_op:
        batch_op.drop_column("reconnect_count")
