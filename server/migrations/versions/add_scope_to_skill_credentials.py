"""add scope and created_by to skill_credentials

Revision ID: add_scope_to_skill_credentials
Revises: add_skill_credentials
Create Date: 2026-01-29

"""

import sqlalchemy as sa
from alembic import op

revision = "add_scope_to_skill_credentials"
down_revision = "add_skill_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    inspector = sa.inspect(bind)

    if dialect == "sqlite":
        uuid_type = sa.String(36)
    else:
        from sqlalchemy.dialects.postgresql import UUID

        uuid_type = UUID(as_uuid=True)

    existing_columns = [col["name"] for col in inspector.get_columns("skill_credentials")]

    # Step 1: Add scope column if not exists
    if "scope" not in existing_columns:
        with op.batch_alter_table("skill_credentials") as batch_op:
            batch_op.add_column(sa.Column("scope", sa.String(length=10), nullable=False, server_default="user"))

    # Step 2: Add created_by column if not exists
    if "created_by" not in existing_columns:
        with op.batch_alter_table("skill_credentials") as batch_op:
            batch_op.add_column(sa.Column("created_by", uuid_type, nullable=True))

    # Step 3: Make user_id nullable and update constraints
    with op.batch_alter_table("skill_credentials", recreate="always") as batch_op:
        batch_op.alter_column("user_id", existing_type=uuid_type, nullable=True)
        batch_op.drop_constraint("uq_skill_credentials_tenant_user_skill", type_="unique")
        batch_op.create_unique_constraint(
            "uq_skill_credentials_tenant_user_skill_scope",
            ["tenant_id", "user_id", "skill_name", "scope"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        uuid_type = sa.String(36)
    else:
        from sqlalchemy.dialects.postgresql import UUID

        uuid_type = UUID(as_uuid=True)

    # Step 1: Restore constraints and make user_id non-nullable
    with op.batch_alter_table("skill_credentials", recreate="always") as batch_op:
        batch_op.drop_constraint("uq_skill_credentials_tenant_user_skill_scope", type_="unique")
        batch_op.alter_column("user_id", existing_type=uuid_type, nullable=False)
        batch_op.create_unique_constraint(
            "uq_skill_credentials_tenant_user_skill",
            ["tenant_id", "user_id", "skill_name"],
        )

    # Step 2: Drop created_by column
    with op.batch_alter_table("skill_credentials") as batch_op:
        batch_op.drop_column("created_by")

    # Step 3: Drop scope column
    with op.batch_alter_table("skill_credentials") as batch_op:
        batch_op.drop_column("scope")
