"""add_unified_dataset_file_architecture

Revision ID: a1b2c3d4e5f6
Revises: 2fc672af4630
Create Date: 2025-10-28 00:00:00.000000

This migration implements the unified dataset/file architecture:
1. Creates notebook_datasets junction table (many-to-many)
2. Adds name column to datasets table
3. Adds BLOB storage (content column) to files table
4. Adds dataset_id foreign key to files table
5. Updates queries table to reference datasets instead of connections
6. Removes notebook_connections table (replaced by notebook_datasets)

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = 'a1b2c3d4e5f6'
down_revision = '2fc672af4630'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply unified dataset/file architecture changes."""
    import uuid
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()

    # ============================================
    # 0. SAVE OLD DATASETS DATA AND RESTRUCTURE TABLE
    # ============================================
    datasets_columns = [col['name'] for col in inspector.get_columns('datasets')]

    # Storage for preserving notebook relationships during migration
    old_datasets_with_notebooks = []  # (dataset_id, notebook_id, created_at)

    if 'notebook_id' in datasets_columns or 'file_id' in datasets_columns:
        print("⚙️  Migrating datasets table from develop branch schema...")

        # Build query to get ALL columns including notebook_id and file_id
        query_cols = ["id", "type", "connection_id", "created_at"]
        select_parts = ["id", "type", "connection_id", "created_at"]

        if 'file_id' in datasets_columns:
            select_parts.append("file_id")
        else:
            select_parts.append("NULL as file_id")

        if 'notebook_id' in datasets_columns:
            select_parts.append("notebook_id")
        else:
            select_parts.append("NULL as notebook_id")

        query = f"SELECT {', '.join(select_parts)} FROM datasets"
        result = conn.execute(sa.text(query))

        connection_datasets = []  # datasets to restore
        file_datasets_count = 0  # orphaned file datasets to skip

        for row in result:
            dataset_id, dtype, connection_id, created_at, file_id, notebook_id = row[0], row[1], row[2], row[3], row[4], row[5]

            # Only migrate connection-type datasets (file-type are orphaned since files table is empty)
            if dtype == 'connection' and connection_id:
                connection_datasets.append((dataset_id, dtype, connection_id, created_at))

                # Save notebook relationship for migration to notebook_datasets
                if notebook_id:
                    old_datasets_with_notebooks.append((dataset_id, notebook_id, created_at))
            elif dtype == 'file':
                file_datasets_count += 1

        print(f"  Found {len(connection_datasets)} connection-type datasets to migrate")
        print(f"  Found {file_datasets_count} orphaned file-type datasets (will be deleted)")
        print(f"  Found {len(old_datasets_with_notebooks)} datasets with notebook relationships")

        # Drop old table
        op.drop_table('datasets')
        print("✓ Dropped old datasets table")

        # Create new table with correct schema (no notebook_id, no file_id) + name + CHECK constraints
        op.create_table(
            'datasets',
            sa.Column('id', sa.String(length=36), nullable=False),
            sa.Column('type', sa.Text(), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=True),
            sa.Column('connection_id', sa.String(length=36), nullable=True),
            sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['connection_id'], ['connections.id'], ondelete='CASCADE'),
            sa.CheckConstraint("type IN ('connection', 'file')", name='ck_datasets_type'),
            sa.CheckConstraint("(type='connection' AND connection_id IS NOT NULL) OR (type='file')", name='ck_datasets_type_refs')
        )
        print("✓ Created new datasets table with all columns and constraints")

        # Restore only connection-type datasets
        for dataset_id, dtype, connection_id, created_at in connection_datasets:
            conn.execute(sa.text("""
                INSERT INTO datasets (id, type, connection_id, created_at)
                VALUES (:id, :type, :connection_id, :created_at)
            """), {"id": dataset_id, "type": dtype, "connection_id": connection_id, "created_at": created_at})

        print(f"✓ Migrated {len(connection_datasets)} connection datasets")
        if file_datasets_count > 0:
            print(f"✓ Cleaned up {file_datasets_count} orphaned file datasets")

    # Refresh inspector cache and column list after table recreation
    inspector.info_cache.clear()
    datasets_columns = [col['name'] for col in inspector.get_columns('datasets')]

    # ============================================
    # 1. ENSURE ALL CONNECTIONS HAVE DATASETS
    # ============================================
    # Check connections referenced by notebook_connections
    if 'notebook_connections' in tables:
        result = conn.execute(sa.text("""
            SELECT DISTINCT nc.connection_id
            FROM notebook_connections nc
            WHERE NOT EXISTS (
                SELECT 1 FROM datasets d
                WHERE d.connection_id = nc.connection_id AND d.type = 'connection'
            )
        """))
        missing_from_nc = [row[0] for row in result]

        for connection_id in missing_from_nc:
            dataset_id = str(uuid.uuid4())
            conn.execute(sa.text("""
                INSERT INTO datasets (id, type, connection_id, created_at)
                VALUES (:id, 'connection', :connection_id, CURRENT_TIMESTAMP)
            """), {"id": dataset_id, "connection_id": connection_id})
            print(f"✓ Created dataset for connection {connection_id} (from notebook_connections)")

    # Check connections referenced by queries
    queries_columns = [col['name'] for col in inspector.get_columns('queries')]
    if 'connection_id' in queries_columns:
        result = conn.execute(sa.text("""
            SELECT DISTINCT q.connection_id
            FROM queries q
            WHERE q.connection_id IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM datasets d
                WHERE d.connection_id = q.connection_id AND d.type = 'connection'
            )
        """))
        missing_from_queries = [row[0] for row in result]

        for connection_id in missing_from_queries:
            dataset_id = str(uuid.uuid4())
            conn.execute(sa.text("""
                INSERT INTO datasets (id, type, connection_id, created_at)
                VALUES (:id, 'connection', :connection_id, CURRENT_TIMESTAMP)
            """), {"id": dataset_id, "connection_id": connection_id})
            print(f"✓ Created dataset for connection {connection_id} (from queries)")

    # ============================================
    # 2. CREATE notebook_datasets JUNCTION TABLE AND MIGRATE RELATIONSHIPS
    # ============================================
    if 'notebook_datasets' not in tables:
        op.create_table(
            'notebook_datasets',
            sa.Column('id', sa.String(length=36), nullable=False),
            sa.Column('notebook_id', sa.String(length=36), nullable=False),
            sa.Column('dataset_id', sa.String(length=36), nullable=False),
            sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
            sa.ForeignKeyConstraint(['notebook_id'], ['notebooks.id'], name='fk_notebook_datasets_notebook_id', ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['dataset_id'], ['datasets.id'], name='fk_notebook_datasets_dataset_id', ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id', name='pk_notebook_datasets')
        )
        print("✓ Created notebook_datasets junction table")

        # Track migrated relationships to avoid duplicates
        migrated_relationships = set()  # (notebook_id, dataset_id)

        # SOURCE 1: Migrate from old datasets table's notebook_id column
        for dataset_id, notebook_id, created_at in old_datasets_with_notebooks:
            key = (notebook_id, dataset_id)
            if key not in migrated_relationships:
                entry_id = str(uuid.uuid4())
                conn.execute(sa.text("""
                    INSERT INTO notebook_datasets (id, notebook_id, dataset_id, created_at)
                    VALUES (:id, :notebook_id, :dataset_id, :created_at)
                """), {"id": entry_id, "notebook_id": notebook_id, "dataset_id": dataset_id, "created_at": created_at})
                migrated_relationships.add(key)

        if old_datasets_with_notebooks:
            print(f"✓ Migrated {len(old_datasets_with_notebooks)} notebook-dataset relationships from old datasets.notebook_id")

        # SOURCE 2: Migrate from notebook_connections table
        if 'notebook_connections' in tables:
            # Get notebook_connections data and map to datasets
            result = conn.execute(sa.text("""
                SELECT nc.id, nc.notebook_id, d.id as dataset_id, nc.created_at
                FROM notebook_connections nc
                JOIN datasets d ON d.connection_id = nc.connection_id AND d.type = 'connection'
            """))

            nc_migrated_count = 0
            for row in result:
                nc_id, notebook_id, dataset_id, created_at = row[0], row[1], row[2], row[3]
                key = (notebook_id, dataset_id)

                # Only insert if not already migrated from datasets.notebook_id
                if key not in migrated_relationships:
                    conn.execute(sa.text("""
                        INSERT INTO notebook_datasets (id, notebook_id, dataset_id, created_at)
                        VALUES (:id, :notebook_id, :dataset_id, :created_at)
                    """), {"id": nc_id, "notebook_id": notebook_id, "dataset_id": dataset_id, "created_at": created_at})
                    migrated_relationships.add(key)
                    nc_migrated_count += 1

            if nc_migrated_count > 0:
                print(f"✓ Migrated {nc_migrated_count} additional notebook-dataset relationships from notebook_connections")

        print(f"✓ Total notebook-dataset relationships migrated: {len(migrated_relationships)}")

    # ============================================
    # 3. ADD name COLUMN AND CONSTRAINTS TO datasets TABLE (if not already done in Step 0)
    # ============================================
    # Note: If Step 0 ran (migrating from develop), the table was already recreated with
    # name column and constraints. This step only runs if upgrading from a different state.
    if 'name' not in datasets_columns:
        print("⚙️  Adding name column and constraints to existing datasets table...")
        with op.batch_alter_table(
            'datasets',
            schema=None,
            copy_from=None,
            table_args=(
                sa.CheckConstraint("type IN ('connection', 'file')", name='ck_datasets_type'),
                sa.CheckConstraint("(type='connection' AND connection_id IS NOT NULL) OR (type='file')", name='ck_datasets_type_refs'),
            )
        ) as batch_op:
            batch_op.add_column(sa.Column('name', sa.String(length=255), nullable=True))
        print("✓ Added name column and constraints to datasets table")
    else:
        print("✓ Datasets table already has name column and constraints (from Step 0)")

    # ============================================
    # 4. UPDATE files TABLE
    # ============================================
    files_columns = [col['name'] for col in inspector.get_columns('files')]

    # Check if there are any existing files
    result = conn.execute(sa.text("SELECT COUNT(*) FROM files"))
    existing_files_count = result.scalar()

    if existing_files_count > 0:
        print(f"⚠️  Found {existing_files_count} existing file(s) with 'path' storage")
        print("⚠️  Old files cannot be migrated to BLOB storage (file content not in DB)")
        print("⚠️  Deleting old files - please re-upload if needed")
        conn.execute(sa.text("DELETE FROM files"))
        print("✓ Cleared old files from files table")

    with op.batch_alter_table('files', schema=None) as batch_op:
        # Drop deprecated path column first (before adding NOT NULL columns)
        if 'path' in files_columns:
            batch_op.drop_column('path')
            print("✓ Removed path column from files table")

        # Add content column (BLOB storage) - NOT NULL since table is now empty
        if 'content' not in files_columns:
            batch_op.add_column(sa.Column('content', sa.LargeBinary(), nullable=False))
            print("✓ Added content (BLOB) column to files table")

        # Add dataset_id foreign key - NOT NULL since table is now empty
        if 'dataset_id' not in files_columns:
            batch_op.add_column(sa.Column('dataset_id', sa.String(length=36), nullable=False))
            batch_op.create_foreign_key('fk_files_dataset_id', 'datasets', ['dataset_id'], ['id'], ondelete='CASCADE')
            print("✓ Added dataset_id foreign key to files table")

    # ============================================
    # 5. UPDATE queries TABLE: connection_id → dataset_id
    # ============================================
    queries_columns = [col['name'] for col in inspector.get_columns('queries')]

    if 'connection_id' in queries_columns:
        # Add dataset_id column (nullable initially)
        if 'dataset_id' not in queries_columns:
            with op.batch_alter_table('queries', schema=None) as batch_op:
                batch_op.add_column(sa.Column('dataset_id', sa.String(length=36), nullable=True))
            print("✓ Added dataset_id column to queries table")

        # Migrate data: connection_id → dataset_id
        # (datasets for all connections were already ensured in step 1)
        conn.execute(sa.text("""
            UPDATE queries
            SET dataset_id = (
                SELECT d.id
                FROM datasets d
                WHERE d.connection_id = queries.connection_id
                AND d.type = 'connection'
                LIMIT 1
            )
            WHERE connection_id IS NOT NULL
        """))
        print("✓ Migrated queries.connection_id → queries.dataset_id")

        # Drop old connection_id column with its foreign key constraint
        fk_constraints = inspector.get_foreign_keys('queries')
        connection_fk_name = None
        for fk in fk_constraints:
            if 'connection_id' in fk.get('constrained_columns', []):
                connection_fk_name = fk.get('name')
                break

        with op.batch_alter_table('queries', schema=None) as batch_op:
            if connection_fk_name:
                try:
                    batch_op.drop_constraint(connection_fk_name, type_='foreignkey')
                    print(f"✓ Dropped foreign key constraint: {connection_fk_name}")
                except:
                    pass
            batch_op.drop_column('connection_id')
        print("✓ Removed queries.connection_id column")

        # Make dataset_id NOT NULL and add foreign key constraint
        with op.batch_alter_table('queries', schema=None) as batch_op:
            batch_op.alter_column('dataset_id',
                                  existing_type=sa.String(length=36),
                                  nullable=False)
            batch_op.create_foreign_key('fk_queries_dataset_id', 'datasets', ['dataset_id'], ['id'], ondelete='CASCADE')
        print("✓ Made queries.dataset_id NOT NULL with foreign key to datasets")

    # ============================================
    # 6. FIX llm_connections.type COLUMN
    # ============================================
    llm_connections_columns = {col['name']: col for col in inspector.get_columns('llm_connections')}

    # Make type column NOT NULL to match model definition
    if 'type' in llm_connections_columns and llm_connections_columns['type']['nullable']:
        with op.batch_alter_table('llm_connections', schema=None) as batch_op:
            batch_op.alter_column('type',
                                  existing_type=sa.Text(),
                                  nullable=False)
        print("✓ Made llm_connections.type column NOT NULL")

    # ============================================
    # 7. DROP notebook_connections TABLE
    # ============================================
    if 'notebook_connections' in tables:
        op.drop_table('notebook_connections')
        print("✓ Dropped notebook_connections table (replaced by notebook_datasets)")

    print("\n✅ Migration completed: Unified dataset/file architecture is now active!")


def downgrade() -> None:
    """Revert to previous architecture (for rollback only)."""
    conn = op.get_bind()
    inspector = inspect(conn)

    print("⚠️  Rolling back unified dataset/file architecture...")

    # 1. Recreate notebook_connections table
    op.create_table(
        'notebook_connections',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('notebook_id', sa.String(length=36), nullable=False),
        sa.Column('connection_id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['connection_id'], ['connections.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['notebook_id'], ['notebooks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # 2. Revert queries table
    queries_columns = [col['name'] for col in inspector.get_columns('queries')]

    with op.batch_alter_table('queries', schema=None) as batch_op:
        if 'connection_id' not in queries_columns:
            batch_op.add_column(sa.Column('connection_id', sa.String(length=36), nullable=True))
            batch_op.create_foreign_key('fk_queries_connection_id_connections', 'connections', ['connection_id'], ['id'], ondelete='CASCADE')

        if 'dataset_id' in queries_columns:
            batch_op.drop_constraint('fk_queries_dataset_id', type_='foreignkey')
            batch_op.drop_column('dataset_id')

    # 3. Revert files table
    files_columns = [col['name'] for col in inspector.get_columns('files')]

    with op.batch_alter_table('files', schema=None) as batch_op:
        if 'path' not in files_columns:
            batch_op.add_column(sa.Column('path', sa.Text(), nullable=True))

        if 'dataset_id' in files_columns:
            batch_op.drop_constraint('fk_files_dataset_id', type_='foreignkey')
            batch_op.drop_column('dataset_id')

        if 'content' in files_columns:
            batch_op.drop_column('content')

    # 4. Revert datasets table
    datasets_columns = [col['name'] for col in inspector.get_columns('datasets')]

    with op.batch_alter_table('datasets', schema=None, copy_from=None) as batch_op:
        # SQLite batch mode can reflect convention-prefixed check names that
        # are not present in Alembic's internal named constraint map. The
        # checks do not reference the column being removed, so keep them on
        # SQLite and only drop them on databases where the operation is exact.
        if conn.dialect.name != "sqlite":
            for constraint_name in ('ck_datasets_type_refs', 'ck_datasets_type'):
                batch_op.drop_constraint(constraint_name, type_='check')

        if 'name' in datasets_columns:
            batch_op.drop_column('name')

    # 5. Revert llm_connections.type to nullable
    with op.batch_alter_table('llm_connections', schema=None) as batch_op:
        batch_op.alter_column('type',
                              existing_type=sa.Text(),
                              nullable=True)

    # 6. Drop notebook_datasets table
    op.drop_table('notebook_datasets')

    print("✅ Rollback completed")
