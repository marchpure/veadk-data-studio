"""add file source resource type

Revision ID: add_file_source_resource_type
Revises: add_knowledge_provider_metadata
Create Date: 2026-08-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "add_file_source_resource_type"
down_revision = "add_knowledge_provider_metadata"
branch_labels = None
depends_on = None

SOURCE_RESOURCE_TYPES_WITH_FILE = (
    "file",
    "pdf",
    "web",
    "feishu_doc",
    "feishu_wiki",
    "feishu_sheet",
    "feishu_base",
    "tos_bucket",
    "tos_prefix",
    "tos_object",
    "extracted_table",
    "database_catalog",
    "database_schema",
    "database_table",
)

SOURCE_RESOURCE_TYPES_WITHOUT_FILE = tuple(
    resource_type for resource_type in SOURCE_RESOURCE_TYPES_WITH_FILE if resource_type != "file"
)


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _check_names(table_name: str) -> set[str]:
    if table_name not in _tables():
        return set()
    return {item["name"] for item in sa.inspect(op.get_bind()).get_check_constraints(table_name) if item.get("name")}


def upgrade() -> None:
    if "source_resources" not in _tables():
        return
    _replace_resource_type_constraint(SOURCE_RESOURCE_TYPES_WITH_FILE)


def downgrade() -> None:
    if "source_resources" not in _tables():
        return
    bind = op.get_bind()
    existing_file_rows = bind.execute(
        sa.text("SELECT 1 FROM source_resources WHERE resource_type = 'file' LIMIT 1")
    ).fetchone()
    if existing_file_rows:
        return
    _replace_resource_type_constraint(SOURCE_RESOURCE_TYPES_WITHOUT_FILE)


def _replace_resource_type_constraint(resource_types: tuple[str, ...]) -> None:
    constraint_sql = f"resource_type IN {resource_types}"
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("ALTER TABLE source_resources DROP CONSTRAINT IF EXISTS ck_source_resources_resource_type"))
        op.execute(sa.text("ALTER TABLE source_resources DROP CONSTRAINT IF EXISTS ck_source_resources_ck_source_resources_resource_type"))
        op.execute(
            sa.text(
                f"""
                ALTER TABLE source_resources
                ADD CONSTRAINT ck_source_resources_resource_type
                CHECK ({constraint_sql})
                """
            )
        )
        return

    checks = _check_names("source_resources")
    with op.batch_alter_table("source_resources") as batch_op:
        for name in ("ck_source_resources_resource_type", "ck_source_resources_ck_source_resources_resource_type"):
            if name in checks:
                batch_op.drop_constraint(name, type_="check")
        batch_op.create_check_constraint("ck_source_resources_resource_type", constraint_sql)
