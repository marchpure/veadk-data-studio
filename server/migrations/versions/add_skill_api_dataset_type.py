"""add skill_api dataset type with skill_name and skill_scope columns

Revision ID: add_skill_api_dataset_type
Revises: add_custom_skills
Create Date: 2026-01-30

"""

import sqlalchemy as sa
from alembic import op

revision = "add_skill_api_dataset_type"
down_revision = "add_custom_skills"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = [col["name"] for col in inspector.get_columns("datasets")]

    if "skill_name" not in existing_columns:
        op.add_column("datasets", sa.Column("skill_name", sa.String(length=50), nullable=True))

    if "skill_scope" not in existing_columns:
        op.add_column("datasets", sa.Column("skill_scope", sa.String(length=10), nullable=True))

    dialect = bind.dialect.name
    if dialect == "sqlite":
        op.execute(
            """
            CREATE TABLE datasets_new (
                id VARCHAR(36) NOT NULL,
                type TEXT NOT NULL,
                name VARCHAR(255),
                connection_id VARCHAR(36),
                created_at TIMESTAMP DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
                storage_path TEXT,
                duckdb_path TEXT,
                schema_cache TEXT,
                schema_updated_at TIMESTAMP,
                tenant_id VARCHAR(36) NOT NULL,
                created_by VARCHAR(36),
                skill_name VARCHAR(50),
                skill_scope VARCHAR(10),
                is_public BOOLEAN NOT NULL DEFAULT 0,
                description TEXT,
                CONSTRAINT pk_datasets PRIMARY KEY (id),
                CONSTRAINT fk_datasets_connection_id_connections FOREIGN KEY(connection_id) REFERENCES connections (id) ON DELETE CASCADE,
                CONSTRAINT fk_datasets_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE,
                CONSTRAINT fk_datasets_created_by_users FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL,
                CONSTRAINT ck_datasets_type CHECK (type IN ('connection', 'file', 'skill_api')),
                CONSTRAINT ck_datasets_type_refs CHECK (
                    (type='connection' AND connection_id IS NOT NULL) OR
                    (type='file') OR
                    (type='skill_api' AND skill_name IS NOT NULL)
                )
            )
            """
        )
        op.execute(
            """
            INSERT INTO datasets_new (id, type, name, connection_id, created_at, storage_path, duckdb_path,
                schema_cache, schema_updated_at, tenant_id, created_by, skill_name, skill_scope,
                is_public, description)
            SELECT id, type, name, connection_id, created_at, storage_path, duckdb_path,
                schema_cache, schema_updated_at, tenant_id, created_by, skill_name, skill_scope,
                COALESCE(is_public, 0), description
            FROM datasets
            """
        )
        op.execute("DROP TABLE datasets")
        op.execute("ALTER TABLE datasets_new RENAME TO datasets")
        op.execute("CREATE INDEX ix_datasets_tenant_id ON datasets (tenant_id)")
        op.execute("CREATE INDEX ix_datasets_created_by ON datasets (created_by)")


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        op.execute(
            """
            CREATE TABLE datasets_new (
                id VARCHAR(36) NOT NULL,
                type TEXT NOT NULL,
                name VARCHAR(255),
                connection_id VARCHAR(36),
                created_at TIMESTAMP DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
                storage_path TEXT,
                duckdb_path TEXT,
                schema_cache TEXT,
                schema_updated_at TIMESTAMP,
                tenant_id VARCHAR(36) NOT NULL,
                created_by VARCHAR(36),
                is_public BOOLEAN NOT NULL DEFAULT 0,
                description TEXT,
                CONSTRAINT pk_datasets PRIMARY KEY (id),
                CONSTRAINT fk_datasets_connection_id_connections FOREIGN KEY(connection_id) REFERENCES connections (id) ON DELETE CASCADE,
                CONSTRAINT fk_datasets_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE,
                CONSTRAINT fk_datasets_created_by_users FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL,
                CONSTRAINT ck_datasets_type CHECK (type IN ('connection', 'file')),
                CONSTRAINT ck_datasets_type_refs CHECK (
                    (type='connection' AND connection_id IS NOT NULL) OR (type='file')
                )
            )
            """
        )
        op.execute(
            """
            INSERT INTO datasets_new (id, type, name, connection_id, created_at, storage_path, duckdb_path,
                schema_cache, schema_updated_at, tenant_id, created_by, is_public, description)
            SELECT id, type, name, connection_id, created_at, storage_path, duckdb_path,
                schema_cache, schema_updated_at, tenant_id, created_by,
                COALESCE(is_public, 0), description
            FROM datasets
            WHERE type IN ('connection', 'file')
            """
        )
        op.execute("DROP TABLE datasets")
        op.execute("ALTER TABLE datasets_new RENAME TO datasets")
        op.execute("CREATE INDEX ix_datasets_tenant_id ON datasets (tenant_id)")
        op.execute("CREATE INDEX ix_datasets_created_by ON datasets (created_by)")
    else:
        op.drop_column("datasets", "skill_scope")
        op.drop_column("datasets", "skill_name")
