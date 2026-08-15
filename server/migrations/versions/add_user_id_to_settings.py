"""Add user_id column to settings table for user-specific settings

Revision ID: add_user_id_to_settings
Revises: add_folder_dashboards
Create Date: 2025-01-06

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "add_user_id_to_settings"
down_revision = "add_folder_dashboards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Detect dialect for appropriate column type
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        user_id_type = sa.String(36)
    else:
        # PostgreSQL and others use UUID
        from sqlalchemy.dialects.postgresql import UUID

        user_id_type = UUID(as_uuid=True)

    # Use batch mode for SQLite compatibility
    with op.batch_alter_table("settings", recreate="always") as batch_op:
        # Add user_id column (nullable - NULL means global/tenant setting)
        batch_op.add_column(sa.Column("user_id", user_id_type, nullable=True))

        # Drop old unique constraint
        batch_op.drop_constraint("uq_settings_tenant_key", type_="unique")

        # Create new unique constraint that includes user_id
        batch_op.create_unique_constraint(
            "uq_settings_tenant_user_key",
            ["tenant_id", "user_id", "setting_key"],
        )

        # Create index on user_id
        batch_op.create_index("ix_settings_user_id", ["user_id"])


def downgrade() -> None:
    with op.batch_alter_table("settings", recreate="always") as batch_op:
        # Drop index
        batch_op.drop_index("ix_settings_user_id")

        # Drop new unique constraint
        batch_op.drop_constraint("uq_settings_tenant_user_key", type_="unique")

        # Restore old unique constraint
        batch_op.create_unique_constraint(
            "uq_settings_tenant_key",
            ["tenant_id", "setting_key"],
        )

        # Remove user_id column
        batch_op.drop_column("user_id")
