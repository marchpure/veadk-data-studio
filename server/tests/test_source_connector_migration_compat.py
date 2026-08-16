from __future__ import annotations

import inspect

from server.migrations.versions import add_source_connections_connector_architecture as migration


def test_source_connector_migration_uses_formatted_constraint_names() -> None:
    source = inspect.getsource(migration)

    assert 'drop_constraint("ck_source_resources_resource_type"' not in source
    assert 'drop_constraint("ck_source_resources_status"' not in source
    assert 'drop_constraint("ck_evidence_fragments_fragment_type"' not in source
    assert 'drop_constraint("ck_notebook_assets_asset_type"' not in source
    assert 'create_check_constraint("ck_source_resources_resource_type"' not in source
    assert 'create_check_constraint("ck_source_resources_status"' not in source
    assert 'create_check_constraint("ck_evidence_fragments_fragment_type"' not in source
    assert "ck_notebook_assets_ck_notebook_assets_asset_type" in source
    assert "DROP CONSTRAINT IF EXISTS ck_notebook_assets_asset_type" in source
    assert "DROP CONSTRAINT IF EXISTS ck_notebook_assets_type" in source


def test_formatted_constraint_name_helper_delegates_to_alembic_op_f(monkeypatch) -> None:
    class FakeOp:
        @staticmethod
        def f(name: str) -> str:
            return f"formatted:{name}"

    monkeypatch.setattr(migration, "op", FakeOp())

    assert migration._n("ck_source_resources_resource_type") == "formatted:ck_source_resources_resource_type"
