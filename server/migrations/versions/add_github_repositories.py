"""Add github_repositories and repository_skills tables

Revision ID: add_github_repositories
Revises: add_mcp_api_keys
Create Date: 2026-03-06

"""

import sqlalchemy as sa
from alembic import op
from fastapi_users_db_sqlalchemy.generics import GUID

revision = "add_github_repositories"
down_revision = "add_mcp_api_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "github_repositories",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("user_id", GUID(), nullable=False),
        sa.Column("repo_full_name", sa.String(255), nullable=False),
        sa.Column("default_branch", sa.String(100), nullable=False, server_default="main"),
        sa.Column("last_analyzed_sha", sa.String(40), nullable=True),
        sa.Column("analysis_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("analysis_error", sa.Text(), nullable=True),
        sa.Column("language_breakdown", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_github_repositories_tenant_id_tenants"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_github_repositories_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_github_repositories")),
        sa.UniqueConstraint("tenant_id", "repo_full_name", name="uq_github_repositories_tenant_repo"),
    )
    op.create_index(op.f("ix_github_repositories_tenant_id"), "github_repositories", ["tenant_id"])
    op.create_index(op.f("ix_github_repositories_user_id"), "github_repositories", ["user_id"])

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


def downgrade() -> None:
    op.drop_index(op.f("ix_repository_skills_skill_type"), table_name="repository_skills")
    op.drop_index(op.f("ix_repository_skills_repo_id"), table_name="repository_skills")
    op.drop_table("repository_skills")

    op.drop_index(op.f("ix_github_repositories_user_id"), table_name="github_repositories")
    op.drop_index(op.f("ix_github_repositories_tenant_id"), table_name="github_repositories")
    op.drop_table("github_repositories")
