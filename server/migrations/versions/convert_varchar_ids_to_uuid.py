"""Convert VARCHAR(36) id columns to UUID for PostgreSQL

Revision ID: convert_varchar_to_uuid
Revises: 5793cc98ac53
Create Date: 2025-12-26

This migration converts all VARCHAR(36) id columns to native UUID type
to fix type mismatch errors with models using GUID().
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "convert_varchar_to_uuid"
down_revision = "5793cc98ac53"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if we're on PostgreSQL
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite doesn't have native UUID type, skip
        return

    # Phase 1: Drop ALL Foreign Keys that reference VARCHAR id columns
    # Notebooks FKs
    op.drop_constraint("fk_dashboards_notebook_id_notebooks", "dashboards", type_="foreignkey")
    op.drop_constraint("fk_notebook_datasets_notebook_id", "notebook_datasets", type_="foreignkey")
    op.drop_constraint("fk_queries_notebook_id_notebooks", "queries", type_="foreignkey")
    op.drop_constraint("fk_threads_notebook_id_notebooks", "threads", type_="foreignkey")

    # Connections FK
    op.drop_constraint("fk_datasets_connection_id_connections", "datasets", type_="foreignkey")

    # Datasets FKs
    op.drop_constraint("fk_files_dataset_id", "files", type_="foreignkey")
    op.drop_constraint("fk_notebook_datasets_dataset_id", "notebook_datasets", type_="foreignkey")
    op.drop_constraint("fk_queries_dataset_id", "queries", type_="foreignkey")

    # Threads FK
    op.drop_constraint("fk_messages_thread_id_threads", "messages", type_="foreignkey")

    # Phase 2: Convert Primary Key columns (id) to UUID
    tables_to_convert = [
        "connections",
        "datasets",
        "notebooks",
        "threads",
        "messages",
        "files",
        "dashboards",
        "queries",
        "notebook_datasets",
        "settings",
        "datasource_annotations",
        "llm_connections",
        "user_preferences",
        "projects",
    ]

    for table in tables_to_convert:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN id TYPE UUID USING id::uuid")

    # Phase 3: Convert Foreign Key columns to UUID
    # FK columns referencing notebooks.id
    op.execute("ALTER TABLE dashboards ALTER COLUMN notebook_id TYPE UUID USING notebook_id::uuid")
    op.execute("ALTER TABLE notebook_datasets ALTER COLUMN notebook_id TYPE UUID USING notebook_id::uuid")
    op.execute("ALTER TABLE queries ALTER COLUMN notebook_id TYPE UUID USING notebook_id::uuid")
    op.execute("ALTER TABLE threads ALTER COLUMN notebook_id TYPE UUID USING notebook_id::uuid")

    # FK columns referencing connections.id
    op.execute("ALTER TABLE datasets ALTER COLUMN connection_id TYPE UUID USING connection_id::uuid")

    # FK columns referencing datasets.id
    op.execute("ALTER TABLE files ALTER COLUMN dataset_id TYPE UUID USING dataset_id::uuid")
    op.execute("ALTER TABLE notebook_datasets ALTER COLUMN dataset_id TYPE UUID USING dataset_id::uuid")
    op.execute("ALTER TABLE queries ALTER COLUMN dataset_id TYPE UUID USING dataset_id::uuid")

    # FK columns referencing threads.id
    op.execute("ALTER TABLE messages ALTER COLUMN thread_id TYPE UUID USING thread_id::uuid")

    # datasource_id in datasource_annotations (references datasets.id)
    op.execute("ALTER TABLE datasource_annotations ALTER COLUMN datasource_id TYPE UUID USING datasource_id::uuid")

    # Phase 4: Recreate Foreign Key Constraints
    # Notebooks FKs
    op.create_foreign_key(
        "fk_dashboards_notebook_id_notebooks",
        "dashboards",
        "notebooks",
        ["notebook_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_notebook_datasets_notebook_id",
        "notebook_datasets",
        "notebooks",
        ["notebook_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_queries_notebook_id_notebooks",
        "queries",
        "notebooks",
        ["notebook_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_threads_notebook_id_notebooks",
        "threads",
        "notebooks",
        ["notebook_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # Connections FK
    op.create_foreign_key(
        "fk_datasets_connection_id_connections",
        "datasets",
        "connections",
        ["connection_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # Datasets FKs
    op.create_foreign_key(
        "fk_files_dataset_id",
        "files",
        "datasets",
        ["dataset_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_notebook_datasets_dataset_id",
        "notebook_datasets",
        "datasets",
        ["dataset_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_queries_dataset_id",
        "queries",
        "datasets",
        ["dataset_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Threads FK
    op.create_foreign_key(
        "fk_messages_thread_id_threads",
        "messages",
        "threads",
        ["thread_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    # Check if we're on PostgreSQL
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # Reverse: Convert UUID back to VARCHAR(36)
    # Phase 1: Drop FKs
    op.drop_constraint("fk_dashboards_notebook_id_notebooks", "dashboards", type_="foreignkey")
    op.drop_constraint("fk_notebook_datasets_notebook_id", "notebook_datasets", type_="foreignkey")
    op.drop_constraint("fk_queries_notebook_id_notebooks", "queries", type_="foreignkey")
    op.drop_constraint("fk_threads_notebook_id_notebooks", "threads", type_="foreignkey")
    op.drop_constraint("fk_datasets_connection_id_connections", "datasets", type_="foreignkey")
    op.drop_constraint("fk_files_dataset_id", "files", type_="foreignkey")
    op.drop_constraint("fk_notebook_datasets_dataset_id", "notebook_datasets", type_="foreignkey")
    op.drop_constraint("fk_queries_dataset_id", "queries", type_="foreignkey")
    op.drop_constraint("fk_messages_thread_id_threads", "messages", type_="foreignkey")

    # Phase 2: Convert back to VARCHAR
    tables_to_convert = [
        "connections",
        "datasets",
        "notebooks",
        "threads",
        "messages",
        "files",
        "dashboards",
        "queries",
        "notebook_datasets",
        "settings",
        "datasource_annotations",
        "llm_connections",
        "user_preferences",
        "projects",
    ]
    for table in tables_to_convert:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN id TYPE VARCHAR(36) USING id::text")

    # Phase 3: Convert FK columns back
    op.execute("ALTER TABLE dashboards ALTER COLUMN notebook_id TYPE VARCHAR(36) USING notebook_id::text")
    op.execute("ALTER TABLE notebook_datasets ALTER COLUMN notebook_id TYPE VARCHAR(36) USING notebook_id::text")
    op.execute("ALTER TABLE queries ALTER COLUMN notebook_id TYPE VARCHAR(36) USING notebook_id::text")
    op.execute("ALTER TABLE threads ALTER COLUMN notebook_id TYPE VARCHAR(36) USING notebook_id::text")
    op.execute("ALTER TABLE datasets ALTER COLUMN connection_id TYPE VARCHAR(36) USING connection_id::text")
    op.execute("ALTER TABLE files ALTER COLUMN dataset_id TYPE VARCHAR(36) USING dataset_id::text")
    op.execute("ALTER TABLE notebook_datasets ALTER COLUMN dataset_id TYPE VARCHAR(36) USING dataset_id::text")
    op.execute("ALTER TABLE queries ALTER COLUMN dataset_id TYPE VARCHAR(36) USING dataset_id::text")
    op.execute("ALTER TABLE messages ALTER COLUMN thread_id TYPE VARCHAR(36) USING thread_id::text")
    op.execute("ALTER TABLE datasource_annotations ALTER COLUMN datasource_id TYPE VARCHAR(36) USING datasource_id::text")

    # Phase 4: Recreate FKs (same as upgrade)
    op.create_foreign_key(
        "fk_dashboards_notebook_id_notebooks", "dashboards", "notebooks", ["notebook_id"], ["id"], ondelete="CASCADE"
    )
    op.create_foreign_key(
        "fk_notebook_datasets_notebook_id",
        "notebook_datasets",
        "notebooks",
        ["notebook_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_queries_notebook_id_notebooks", "queries", "notebooks", ["notebook_id"], ["id"], ondelete="CASCADE"
    )
    op.create_foreign_key(
        "fk_threads_notebook_id_notebooks", "threads", "notebooks", ["notebook_id"], ["id"], ondelete="CASCADE"
    )
    op.create_foreign_key(
        "fk_datasets_connection_id_connections",
        "datasets",
        "connections",
        ["connection_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key("fk_files_dataset_id", "files", "datasets", ["dataset_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key(
        "fk_notebook_datasets_dataset_id", "notebook_datasets", "datasets", ["dataset_id"], ["id"], ondelete="CASCADE"
    )
    op.create_foreign_key("fk_queries_dataset_id", "queries", "datasets", ["dataset_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key(
        "fk_messages_thread_id_threads", "messages", "threads", ["thread_id"], ["id"], ondelete="CASCADE"
    )
