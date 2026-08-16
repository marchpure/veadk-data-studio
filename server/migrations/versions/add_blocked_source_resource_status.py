"""add blocked source resource status

Revision ID: add_blocked_source_resource_status
Revises: add_file_source_resource_type
Create Date: 2026-08-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "add_blocked_source_resource_status"
down_revision = "add_file_source_resource_type"
branch_labels = None
depends_on = None

STATUSES_WITH_BLOCKED = (
    "pending",
    "syncing",
    "understanding",
    "authorization_required",
    "reauthorization_required",
    "blocked",
    "source_unavailable",
    "permission_lost",
    "needs_confirmation",
    "ready",
    "failed",
)

STATUSES_WITHOUT_BLOCKED = tuple(status for status in STATUSES_WITH_BLOCKED if status != "blocked")


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _check_sqltexts(table_name: str) -> dict[str, str]:
    if table_name not in _tables():
        return {}
    return {
        item["name"]: item.get("sqltext") or ""
        for item in sa.inspect(op.get_bind()).get_check_constraints(table_name)
        if item.get("name")
    }


def upgrade() -> None:
    if "source_resources" not in _tables():
        return
    _replace_status_constraint(STATUSES_WITH_BLOCKED)


def downgrade() -> None:
    if "source_resources" not in _tables():
        return
    existing_blocked_rows = op.get_bind().execute(
        sa.text("SELECT 1 FROM source_resources WHERE status = 'blocked' LIMIT 1")
    ).fetchone()
    if existing_blocked_rows:
        return
    _replace_status_constraint(STATUSES_WITHOUT_BLOCKED)


def _replace_status_constraint(statuses: tuple[str, ...]) -> None:
    constraint_sql = f"status IN {statuses}"
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("ALTER TABLE source_resources DROP CONSTRAINT IF EXISTS ck_source_resources_status"))
        op.execute(
            sa.text("ALTER TABLE source_resources DROP CONSTRAINT IF EXISTS ck_source_resources_ck_source_resources_status")
        )
        op.execute(
            sa.text(
                f"""
                ALTER TABLE source_resources
                ADD CONSTRAINT ck_source_resources_status
                CHECK ({constraint_sql})
                """
            )
        )
        return

    checks = _check_sqltexts("source_resources")
    if checks.get("ck_source_resources_status") == constraint_sql:
        return

    with op.batch_alter_table("source_resources") as batch_op:
        for name in ("ck_source_resources_status", "ck_source_resources_ck_source_resources_status"):
            if name in checks:
                batch_op.drop_constraint(op.f(name), type_="check")
        batch_op.create_check_constraint(op.f("ck_source_resources_status"), constraint_sql)
