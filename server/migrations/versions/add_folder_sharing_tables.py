"""Add folder sharing tables

Revision ID: add_folder_sharing
Revises: 5793cc98ac53
Create Date: 2025-01-05

"""

from alembic import op
import sqlalchemy as sa
from fastapi_users_db_sqlalchemy.generics import GUID


# revision identifiers, used by Alembic.
revision = "add_folder_sharing"
down_revision = "5793cc98ac53"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create folders table
    op.create_table(
        "folders",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("created_by", GUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_folders_tenant_id_tenants"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_folders_created_by_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_folders")),
    )
    op.create_index(op.f("ix_folders_tenant_id"), "folders", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_folders_created_by"), "folders", ["created_by"], unique=False)

    # Create folder_members table
    op.create_table(
        "folder_members",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("folder_id", GUID(), nullable=False),
        sa.Column("user_id", GUID(), nullable=False),
        sa.Column("added_by", GUID(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(
            ["folder_id"], ["folders.id"], name=op.f("fk_folder_members_folder_id_folders"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_folder_members_user_id_users"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["added_by"], ["users.id"], name=op.f("fk_folder_members_added_by_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_folder_members")),
        sa.UniqueConstraint("folder_id", "user_id", name="uq_folder_members_folder_user"),
    )
    op.create_index(op.f("ix_folder_members_folder_id"), "folder_members", ["folder_id"], unique=False)
    op.create_index(op.f("ix_folder_members_user_id"), "folder_members", ["user_id"], unique=False)

    # Create folder_notebooks table
    op.create_table(
        "folder_notebooks",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("folder_id", GUID(), nullable=False),
        sa.Column("notebook_id", GUID(), nullable=False),
        sa.Column("shared_by", GUID(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(
            ["folder_id"], ["folders.id"], name=op.f("fk_folder_notebooks_folder_id_folders"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["notebook_id"], ["notebooks.id"], name=op.f("fk_folder_notebooks_notebook_id_notebooks"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["shared_by"], ["users.id"], name=op.f("fk_folder_notebooks_shared_by_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_folder_notebooks")),
        sa.UniqueConstraint("folder_id", "notebook_id", name="uq_folder_notebooks_folder_notebook"),
    )
    op.create_index(op.f("ix_folder_notebooks_folder_id"), "folder_notebooks", ["folder_id"], unique=False)
    op.create_index(op.f("ix_folder_notebooks_notebook_id"), "folder_notebooks", ["notebook_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_folder_notebooks_notebook_id"), table_name="folder_notebooks")
    op.drop_index(op.f("ix_folder_notebooks_folder_id"), table_name="folder_notebooks")
    op.drop_table("folder_notebooks")

    op.drop_index(op.f("ix_folder_members_user_id"), table_name="folder_members")
    op.drop_index(op.f("ix_folder_members_folder_id"), table_name="folder_members")
    op.drop_table("folder_members")

    op.drop_index(op.f("ix_folders_created_by"), table_name="folders")
    op.drop_index(op.f("ix_folders_tenant_id"), table_name="folders")
    op.drop_table("folders")
