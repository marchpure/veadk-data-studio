"""Add multi-tenancy and auth schema updates

Revision ID: 5793cc98ac53
Revises: j3h7i1e8f0a1
Create Date: 2025-12-23 18:48:03.218657

"""

from alembic import op
import sqlalchemy as sa
from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy.dialects import sqlite


# revision identifiers, used by Alembic.
revision = '5793cc98ac53'
down_revision = 'j3h7i1e8f0a1'
branch_labels = None
depends_on = None


# Default tenant ID for existing data (will be created first)
DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    # ### Create new tables ###

    # Create users table first (no dependencies)
    op.create_table('users',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=1024), nullable=False, server_default=''),
        sa.Column('full_name', sa.String(length=255), nullable=True),
        sa.Column('google_id', sa.String(length=255), nullable=True),
        sa.Column('avatar_url', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('is_verified', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('is_superuser', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
        sa.UniqueConstraint('google_id', name=op.f('uq_users_google_id'))
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    # Create refresh_tokens table
    op.create_table('refresh_tokens',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('user_id', GUID(), nullable=False),
        sa.Column('token_hash', sa.String(length=255), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('expires_at', sa.TIMESTAMP(), nullable=False),
        sa.Column('revoked_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_refresh_tokens_user_id_users'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_refresh_tokens')),
        sa.UniqueConstraint('token_hash', name=op.f('uq_refresh_tokens_token_hash'))
    )
    op.create_index(op.f('ix_refresh_tokens_user_id'), 'refresh_tokens', ['user_id'], unique=False)

    # Create tenants table (depends on users for owner_id)
    op.create_table('tenants',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=255), nullable=False),
        sa.Column('owner_id', GUID(), nullable=False),
        sa.Column('is_personal', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_tenants_owner_id_users'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_tenants'))
    )
    op.create_index(op.f('ix_tenants_slug'), 'tenants', ['slug'], unique=True)

    # Create verification_tokens table
    op.create_table('verification_tokens',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('user_id', GUID(), nullable=False),
        sa.Column('token_hash', sa.String(length=255), nullable=False),
        sa.Column('expires_at', sa.TIMESTAMP(), nullable=False),
        sa.Column('verified_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_verification_tokens_user_id_users'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_verification_tokens')),
        sa.UniqueConstraint('token_hash', name=op.f('uq_verification_tokens_token_hash'))
    )

    # Create tenant_invitations table
    op.create_table('tenant_invitations',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('tenant_id', GUID(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('invited_by_id', GUID(), nullable=False),
        sa.Column('token_id', GUID(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('expires_at', sa.TIMESTAMP(), nullable=False),
        sa.Column('accepted_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint("role IN ('admin', 'member')", name=op.f('ck_tenant_invitations_ck_tenant_invitations_role')),
        sa.CheckConstraint("status IN ('pending', 'accepted', 'expired', 'revoked')", name=op.f('ck_tenant_invitations_ck_tenant_invitations_status')),
        sa.ForeignKeyConstraint(['invited_by_id'], ['users.id'], name=op.f('fk_tenant_invitations_invited_by_id_users')),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_tenant_invitations_tenant_id_tenants'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['token_id'], ['verification_tokens.id'], name=op.f('fk_tenant_invitations_token_id_verification_tokens')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_tenant_invitations'))
    )
    op.create_index(op.f('ix_tenant_invitations_email'), 'tenant_invitations', ['email'], unique=False)

    # Create tenant_members table
    op.create_table('tenant_members',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('user_id', GUID(), nullable=False),
        sa.Column('tenant_id', GUID(), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('invited_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('joined_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_tenant_members_tenant_id_tenants'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_tenant_members_user_id_users'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_tenant_members'))
    )

    # Drop old tables that are no longer needed
    op.drop_table('notebook_state')
    op.drop_table('message_attachments')

    # Insert a default user and tenant for existing data
    op.execute(f"""
        INSERT INTO users (id, email, hashed_password, is_active, is_verified, is_superuser)
        VALUES ('{DEFAULT_USER_ID}', 'system@local', '', true, true, true)
    """)
    op.execute(f"""
        INSERT INTO tenants (id, name, slug, owner_id, is_personal)
        VALUES ('{DEFAULT_TENANT_ID}', 'Default Workspace', 'default', '{DEFAULT_USER_ID}', false)
    """)

    # ### Add tenant_id columns to existing tables using batch operations for SQLite ###

    # For each table, we:
    # 1. Add nullable column with default
    # 2. Update existing rows
    # 3. In a fresh migration context, the column will be created with proper constraints

    # connections table
    with op.batch_alter_table('connections', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tenant_id', GUID(), nullable=True))
    op.execute(f"UPDATE connections SET tenant_id = '{DEFAULT_TENANT_ID}' WHERE tenant_id IS NULL")
    with op.batch_alter_table('connections', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', nullable=False)
        batch_op.create_index(op.f('ix_connections_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_foreign_key(op.f('fk_connections_tenant_id_tenants'), 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')

    # dashboards table
    with op.batch_alter_table('dashboards', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tenant_id', GUID(), nullable=True))
    op.execute(f"UPDATE dashboards SET tenant_id = '{DEFAULT_TENANT_ID}' WHERE tenant_id IS NULL")
    with op.batch_alter_table('dashboards', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', nullable=False)
        batch_op.create_index(op.f('ix_dashboards_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_foreign_key(op.f('fk_dashboards_tenant_id_tenants'), 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')

    # datasets table
    with op.batch_alter_table('datasets', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tenant_id', GUID(), nullable=True))
    op.execute(f"UPDATE datasets SET tenant_id = '{DEFAULT_TENANT_ID}' WHERE tenant_id IS NULL")
    with op.batch_alter_table('datasets', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', nullable=False)
        batch_op.create_index(op.f('ix_datasets_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_foreign_key(op.f('fk_datasets_tenant_id_tenants'), 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')

    # datasource_annotations table
    with op.batch_alter_table('datasource_annotations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tenant_id', GUID(), nullable=True))
        batch_op.drop_constraint('uq_datasource_annotations_unique_annotation', type_='unique')
    op.execute(f"UPDATE datasource_annotations SET tenant_id = '{DEFAULT_TENANT_ID}' WHERE tenant_id IS NULL")
    with op.batch_alter_table('datasource_annotations', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', nullable=False)
        batch_op.create_index(op.f('ix_datasource_annotations_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_foreign_key(op.f('fk_datasource_annotations_tenant_id_tenants'), 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')

    # files table
    with op.batch_alter_table('files', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tenant_id', GUID(), nullable=True))
    op.execute(f"UPDATE files SET tenant_id = '{DEFAULT_TENANT_ID}' WHERE tenant_id IS NULL")
    with op.batch_alter_table('files', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', nullable=False)
        batch_op.create_index(op.f('ix_files_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_foreign_key(op.f('fk_files_tenant_id_tenants'), 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')

    # llm_connections table
    with op.batch_alter_table('llm_connections', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tenant_id', GUID(), nullable=True))
    op.execute(f"UPDATE llm_connections SET tenant_id = '{DEFAULT_TENANT_ID}' WHERE tenant_id IS NULL")
    with op.batch_alter_table('llm_connections', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', nullable=False)
        batch_op.create_index(op.f('ix_llm_connections_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_foreign_key(op.f('fk_llm_connections_tenant_id_tenants'), 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')

    # notebooks table
    with op.batch_alter_table('notebooks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tenant_id', GUID(), nullable=True))
        batch_op.add_column(sa.Column('created_by', GUID(), nullable=True))
    op.execute(f"UPDATE notebooks SET tenant_id = '{DEFAULT_TENANT_ID}' WHERE tenant_id IS NULL")
    with op.batch_alter_table('notebooks', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', nullable=False)
        batch_op.create_index(op.f('ix_notebooks_created_by'), ['created_by'], unique=False)
        batch_op.create_index(op.f('ix_notebooks_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_foreign_key(op.f('fk_notebooks_created_by_users'), 'users', ['created_by'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key(op.f('fk_notebooks_tenant_id_tenants'), 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')

    # queries table
    with op.batch_alter_table('queries', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tenant_id', GUID(), nullable=True))
    op.execute(f"UPDATE queries SET tenant_id = '{DEFAULT_TENANT_ID}' WHERE tenant_id IS NULL")
    with op.batch_alter_table('queries', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', nullable=False)
        batch_op.create_index(op.f('ix_queries_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_foreign_key(op.f('fk_queries_tenant_id_tenants'), 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')

    # settings table
    with op.batch_alter_table('settings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tenant_id', GUID(), nullable=True))
        batch_op.drop_constraint('uq_settings_setting_key', type_='unique')
    op.execute(f"UPDATE settings SET tenant_id = '{DEFAULT_TENANT_ID}' WHERE tenant_id IS NULL")
    with op.batch_alter_table('settings', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', nullable=False)
        batch_op.create_index(op.f('ix_settings_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_unique_constraint('uq_settings_tenant_key', ['tenant_id', 'setting_key'])
        batch_op.create_foreign_key(op.f('fk_settings_tenant_id_tenants'), 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')

    # user_preferences table
    with op.batch_alter_table('user_preferences', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id', GUID(), nullable=True))
        batch_op.drop_constraint('uq_user_preferences_preference_type', type_='unique')
    op.execute(f"UPDATE user_preferences SET user_id = '{DEFAULT_USER_ID}' WHERE user_id IS NULL")
    with op.batch_alter_table('user_preferences', schema=None) as batch_op:
        batch_op.alter_column('user_id', nullable=False)
        batch_op.create_index(op.f('ix_user_preferences_user_id'), ['user_id'], unique=False)
        batch_op.create_unique_constraint('uq_user_preferences_user_type', ['user_id', 'preference_type'])
        batch_op.create_foreign_key(op.f('fk_user_preferences_user_id_users'), 'users', ['user_id'], ['id'], ondelete='CASCADE')


def downgrade() -> None:
    # ### Reverse changes to existing tables ###
    with op.batch_alter_table('user_preferences', schema=None) as batch_op:
        batch_op.drop_constraint(op.f('fk_user_preferences_user_id_users'), type_='foreignkey')
        batch_op.drop_constraint('uq_user_preferences_user_type', type_='unique')
        batch_op.drop_index(op.f('ix_user_preferences_user_id'))
        batch_op.create_unique_constraint('uq_user_preferences_preference_type', ['preference_type'])
        batch_op.drop_column('user_id')

    with op.batch_alter_table('settings', schema=None) as batch_op:
        batch_op.drop_constraint(op.f('fk_settings_tenant_id_tenants'), type_='foreignkey')
        batch_op.drop_constraint('uq_settings_tenant_key', type_='unique')
        batch_op.drop_index(op.f('ix_settings_tenant_id'))
        batch_op.create_unique_constraint('uq_settings_setting_key', ['setting_key'])
        batch_op.drop_column('tenant_id')

    with op.batch_alter_table('queries', schema=None) as batch_op:
        batch_op.drop_constraint(op.f('fk_queries_tenant_id_tenants'), type_='foreignkey')
        batch_op.drop_index(op.f('ix_queries_tenant_id'))
        batch_op.drop_column('tenant_id')

    with op.batch_alter_table('notebooks', schema=None) as batch_op:
        batch_op.drop_constraint(op.f('fk_notebooks_tenant_id_tenants'), type_='foreignkey')
        batch_op.drop_constraint(op.f('fk_notebooks_created_by_users'), type_='foreignkey')
        batch_op.drop_index(op.f('ix_notebooks_tenant_id'))
        batch_op.drop_index(op.f('ix_notebooks_created_by'))
        batch_op.drop_column('created_by')
        batch_op.drop_column('tenant_id')

    with op.batch_alter_table('llm_connections', schema=None) as batch_op:
        batch_op.drop_constraint(op.f('fk_llm_connections_tenant_id_tenants'), type_='foreignkey')
        batch_op.drop_index(op.f('ix_llm_connections_tenant_id'))
        batch_op.drop_column('tenant_id')

    with op.batch_alter_table('files', schema=None) as batch_op:
        batch_op.drop_constraint(op.f('fk_files_tenant_id_tenants'), type_='foreignkey')
        batch_op.drop_index(op.f('ix_files_tenant_id'))
        batch_op.drop_column('tenant_id')

    with op.batch_alter_table('datasource_annotations', schema=None) as batch_op:
        batch_op.drop_constraint(op.f('fk_datasource_annotations_tenant_id_tenants'), type_='foreignkey')
        batch_op.drop_index(op.f('ix_datasource_annotations_tenant_id'))
        batch_op.create_unique_constraint('uq_datasource_annotations_unique_annotation', ['datasource_id', 'table_name', 'column_name', 'annotation_type'])
        batch_op.drop_column('tenant_id')

    with op.batch_alter_table('datasets', schema=None) as batch_op:
        batch_op.drop_constraint(op.f('fk_datasets_tenant_id_tenants'), type_='foreignkey')
        batch_op.drop_index(op.f('ix_datasets_tenant_id'))
        batch_op.drop_column('tenant_id')

    with op.batch_alter_table('dashboards', schema=None) as batch_op:
        batch_op.drop_constraint(op.f('fk_dashboards_tenant_id_tenants'), type_='foreignkey')
        batch_op.drop_index(op.f('ix_dashboards_tenant_id'))
        batch_op.drop_column('tenant_id')

    with op.batch_alter_table('connections', schema=None) as batch_op:
        batch_op.drop_constraint(op.f('fk_connections_tenant_id_tenants'), type_='foreignkey')
        batch_op.drop_index(op.f('ix_connections_tenant_id'))
        batch_op.drop_column('tenant_id')

    # Delete default user and tenant
    op.execute(f"DELETE FROM tenants WHERE id = '{DEFAULT_TENANT_ID}'")
    op.execute(f"DELETE FROM users WHERE id = '{DEFAULT_USER_ID}'")

    # Recreate old tables
    op.create_table('message_attachments',
        sa.Column('id', sa.VARCHAR(length=36), nullable=False),
        sa.Column('message_id', sa.VARCHAR(length=36), nullable=False),
        sa.Column('file_name', sa.VARCHAR(length=255), nullable=False),
        sa.Column('mime_type', sa.VARCHAR(length=50), nullable=False),
        sa.Column('file_data', sa.TEXT(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint("mime_type IN ('image/png', 'image/jpeg', 'image/webp')", name=op.f('ck_message_attachments_mime_type')),
        sa.ForeignKeyConstraint(['message_id'], ['messages.id'], name=op.f('fk_message_attachments_message_id_messages'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_message_attachments'))
    )
    op.create_table('notebook_state',
        sa.Column('id', sa.VARCHAR(length=36), nullable=False),
        sa.Column('notebook_id', sa.VARCHAR(length=36), nullable=False),
        sa.Column('version_number', sa.INTEGER(), nullable=False),
        sa.Column('state', sqlite.JSON(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['notebook_id'], ['notebooks.id'], name=op.f('fk_notebook_state_notebook_id_notebooks'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_notebook_state')),
        sa.UniqueConstraint('notebook_id', 'version_number', name=op.f('uq_notebook_state_version'))
    )

    # Drop new tables
    op.drop_table('tenant_members')
    op.drop_index(op.f('ix_tenant_invitations_email'), table_name='tenant_invitations')
    op.drop_table('tenant_invitations')
    op.drop_table('verification_tokens')
    op.drop_index(op.f('ix_tenants_slug'), table_name='tenants')
    op.drop_table('tenants')
    op.drop_index(op.f('ix_refresh_tokens_user_id'), table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
