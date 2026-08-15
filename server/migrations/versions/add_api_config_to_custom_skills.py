"""Add API config columns to custom_skills table

Revision ID: add_api_config_to_custom_skills
Revises: repair_datasets_missing_columns
Create Date: 2026-02-27

"""

import sqlalchemy as sa
from alembic import op

revision = "add_api_config_to_custom_skills"
down_revision = "repair_datasets_missing_columns"
branch_labels = None
depends_on = None

COLUMNS = [
    ("api_base_url", sa.String(500), True, None),
    ("api_type", sa.String(20), True, "rest"),
    ("api_auth_type", sa.String(20), True, "bearer"),
    ("api_domain", sa.String(200), True, None),
    ("api_credentials_encrypted", sa.Text(), True, None),
    ("domain_active", sa.Boolean(), False, True),
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = [c["name"] for c in inspector.get_columns("custom_skills")]

    for col_name, col_type, nullable, default in COLUMNS:
        if col_name not in existing:
            kwargs = {"nullable": nullable}
            if default is not None:
                kwargs["server_default"] = str(default).lower() if isinstance(default, bool) else str(default)
            op.add_column("custom_skills", sa.Column(col_name, col_type, **kwargs))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = [c["name"] for c in inspector.get_columns("custom_skills")]

    for col_name, _, _, _ in reversed(COLUMNS):
        if col_name in existing:
            op.drop_column("custom_skills", col_name)
