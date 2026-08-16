from __future__ import annotations

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table, Text, create_engine, inspect

from server.db.base import Base
from server.migrations.versions import add_governed_dashboard_assets
from server.models.dashboard import Dashboard, DashboardAsset, DashboardAuditEvent, DashboardRun


def _create_minimal_dashboard_legacy_schema(engine) -> None:
    metadata = MetaData()
    Table(
        "users",
        metadata,
        Column("id", String(36), primary_key=True),
    )
    Table(
        "tenants",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("owner_id", String(36), ForeignKey("users.id"), nullable=False),
    )
    Table(
        "notebooks",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("tenant_id", String(36), ForeignKey("tenants.id"), nullable=False),
    )
    Table(
        "dashboards",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("tenant_id", String(36), ForeignKey("tenants.id"), nullable=False),
        Column("notebook_id", String(36), ForeignKey("notebooks.id"), nullable=False),
        Column("version_num", Integer, nullable=False),
        Column("html_content", Text, nullable=False),
    )
    metadata.create_all(engine)


def test_dashboard_persistence_models_are_registered() -> None:
    assert DashboardAsset.__tablename__ in Base.metadata.tables
    assert DashboardRun.__tablename__ in Base.metadata.tables
    assert DashboardAuditEvent.__tablename__ in Base.metadata.tables

    dashboard_columns = {column.name for column in Dashboard.__table__.columns}
    assert {
        "asset_id",
        "manifest_schema_version",
        "manifest_json",
        "content_hash",
        "status",
        "pinned_model_versions_json",
        "pinned_source_snapshots_json",
        "validation_result_json",
        "migration_state",
        "is_published_immutable",
    }.issubset(dashboard_columns)


def test_governed_dashboard_migration_upgrade_and_downgrade_sqlite() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_minimal_dashboard_legacy_schema(engine)

    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        operations = Operations(context)
        original_op = add_governed_dashboard_assets.op
        add_governed_dashboard_assets.op = operations
        try:
            add_governed_dashboard_assets.upgrade()
            inspector = inspect(connection)
            assert "dashboard_assets" in inspector.get_table_names()
            assert "dashboard_runs" in inspector.get_table_names()
            assert "dashboard_audit_events" in inspector.get_table_names()

            dashboard_columns = {column["name"] for column in inspector.get_columns("dashboards")}
            assert {
                "asset_id",
                "manifest_json",
                "status",
                "migration_state",
                "is_published_immutable",
            }.issubset(dashboard_columns)

            add_governed_dashboard_assets.downgrade()
            inspector = inspect(connection)
            assert "dashboard_assets" not in inspector.get_table_names()
            assert "dashboard_runs" not in inspector.get_table_names()
            assert "dashboard_audit_events" not in inspector.get_table_names()
            dashboard_columns = {column["name"] for column in inspector.get_columns("dashboards")}
            assert "asset_id" not in dashboard_columns
            assert "html_content" in dashboard_columns
        finally:
            add_governed_dashboard_assets.op = original_op
