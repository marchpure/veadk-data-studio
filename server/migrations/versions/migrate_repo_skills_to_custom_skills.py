"""Migrate repository_skills to custom_skills table

Revision ID: migrate_repo_to_custom_skills
Revises: add_github_repositories
Create Date: 2026-03-09

"""

import sqlalchemy as sa
from alembic import op
from fastapi_users_db_sqlalchemy.generics import GUID

revision = "migrate_repo_to_custom_skills"
down_revision = "add_github_repositories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("custom_skills", schema=None) as batch_op:
        batch_op.add_column(sa.Column("github_repo_id", GUID(), nullable=True))
        batch_op.add_column(sa.Column("github_analysis_type", sa.String(30), nullable=True))
        batch_op.create_foreign_key(
            op.f("fk_custom_skills_github_repo_id_github_repositories"),
            "github_repositories",
            ["github_repo_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(op.f("ix_custom_skills_github_repo_id"), ["github_repo_id"])
        batch_op.create_index(op.f("ix_custom_skills_github_analysis_type"), ["github_analysis_type"])

    op.drop_index(op.f("ix_repository_skills_skill_type"), table_name="repository_skills")
    op.drop_index(op.f("ix_repository_skills_repo_id"), table_name="repository_skills")
    op.drop_table("repository_skills")


def downgrade() -> None:
    op.create_table(
        "repository_skills",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("repo_id", GUID(), nullable=False),
        sa.Column("skill_type", sa.String(30), nullable=False),
        sa.Column("skill_name", sa.String(100), nullable=False),
        sa.Column("skill_content", sa.Text(), nullable=False),
        sa.Column("prompt_template", sa.Text(), nullable=True),
        sa.Column("parameters", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("analyzed_sha", sa.String(40), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.ForeignKeyConstraint(
            ["repo_id"],
            ["github_repositories.id"],
            name=op.f("fk_repository_skills_repo_id_github_repositories"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_repository_skills")),
    )
    op.create_index(op.f("ix_repository_skills_repo_id"), "repository_skills", ["repo_id"])
    op.create_index(op.f("ix_repository_skills_skill_type"), "repository_skills", ["skill_type"])

    with op.batch_alter_table("custom_skills", schema=None) as batch_op:
        batch_op.drop_index(op.f("ix_custom_skills_github_analysis_type"))
        batch_op.drop_index(op.f("ix_custom_skills_github_repo_id"))
        batch_op.drop_constraint(op.f("fk_custom_skills_github_repo_id_github_repositories"), type_="foreignkey")
        batch_op.drop_column("github_analysis_type")
        batch_op.drop_column("github_repo_id")
