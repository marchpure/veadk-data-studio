"""Add local repository support columns

Revision ID: add_local_repo_support
Revises: migrate_repo_to_custom_skills
Create Date: 2026-03-12

"""

import sqlalchemy as sa
from alembic import op

revision = "add_local_repo_support"
down_revision = "migrate_repo_to_custom_skills"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("github_repositories", schema=None) as batch_op:
        batch_op.add_column(sa.Column("source", sa.String(20), nullable=False, server_default="github"))
        batch_op.add_column(sa.Column("local_path", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("github_repositories", schema=None) as batch_op:
        batch_op.drop_column("local_path")
        batch_op.drop_column("source")
