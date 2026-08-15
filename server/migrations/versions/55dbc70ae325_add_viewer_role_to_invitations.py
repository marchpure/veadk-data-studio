"""add_viewer_role_to_invitations

Revision ID: 55dbc70ae325
Revises: e9a8c462cd41
Create Date: 2026-01-09 00:02:48.745126

"""

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision = '55dbc70ae325'
down_revision = 'e9a8c462cd41'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the old check constraint and add a new one with 'viewer' role
    # For SQLite, we need to use batch operations to modify constraints
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("tenant_invitations", recreate="always") as batch_op:
            batch_op.drop_constraint("ck_tenant_invitations_role", type_="check")
            batch_op.create_check_constraint(
                "ck_tenant_invitations_role",
                "role IN ('admin', 'member', 'viewer')"
            )
    else:
        op.drop_constraint("ck_tenant_invitations_role", "tenant_invitations", type_="check")
        op.create_check_constraint(
            "ck_tenant_invitations_role",
            "tenant_invitations",
            "role IN ('admin', 'member', 'viewer')"
        )


def downgrade() -> None:
    # Revert to original constraint without 'viewer' role
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("tenant_invitations", recreate="always") as batch_op:
            batch_op.drop_constraint("ck_tenant_invitations_role", type_="check")
            batch_op.create_check_constraint(
                "ck_tenant_invitations_role",
                "role IN ('admin', 'member')"
            )
    else:
        op.drop_constraint("ck_tenant_invitations_role", "tenant_invitations", type_="check")
        op.create_check_constraint(
            "ck_tenant_invitations_role",
            "tenant_invitations",
            "role IN ('admin', 'member')"
        )

