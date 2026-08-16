from __future__ import annotations

import ast
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[2]
SERVER_DIR = ROOT / "server"


def _script_directory() -> ScriptDirectory:
    config = Config(str(SERVER_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(SERVER_DIR / "migrations"))
    return ScriptDirectory.from_config(config)


def test_semantic_versions_revision_alias_preserves_legacy_and_short_ids() -> None:
    script = _script_directory()

    legacy = script.get_revision("harden_semantic_model_versions_compat")
    alias = script.get_revision("harden_semantic_versions")

    assert legacy.revision == "harden_semantic_model_versions_compat"
    assert legacy.down_revision == "add_semantic_model_versions"
    assert alias.revision == "harden_semantic_versions"
    assert alias.down_revision == "harden_semantic_model_versions_compat"
    assert script.get_heads() == ["backfill_legacy_dashboard_assets"]

    collaboration = script.get_revision("add_collaboration_integration_tables")
    assert collaboration.down_revision == "harden_semantic_versions"

    file_source = script.get_revision("add_file_source_resource_type")
    assert file_source.down_revision == "add_knowledge_provider_metadata"

    dashboard = script.get_revision("add_governed_dashboard_assets")
    assert dashboard.down_revision == "add_file_source_resource_type"
    dashboard_backfill = script.get_revision("backfill_legacy_dashboard_assets")
    assert dashboard_backfill.down_revision == "add_governed_dashboard_assets"


def test_self_hosted_entrypoint_serializes_migrations_and_blocks_bad_startup() -> None:
    candidates = [
        ROOT / "docker" / "self-hosted" / "start-backend.sh",
        ROOT / "start-backend.sh",
        Path("/app/start-backend.sh"),
    ]
    script_path = next(path for path in candidates if path.exists())
    script = script_path.read_text()

    assert 'MIGRATION_LOCK_FILE="${MIGRATION_LOCK_FILE:-/data/logs/.migration.lock}"' in script
    assert 'flock "$MIGRATION_LOCK_FILE" uv run --frozen --no-sync alembic upgrade head' in script
    assert 'flock "$MIGRATION_LOCK_FILE" uv run --frozen --no-sync alembic downgrade "$CURRENT_REV"' in script
    assert "exit 1" in script[script.index("if [ $MIGRATION_EXIT_CODE -eq 0 ]") : script.index("# Skip startup migrations")]
    assert "exec uv run --frozen --no-sync uvicorn" in script


def test_alembic_cli_preflights_postgres_version_column_width() -> None:
    env_script = (SERVER_DIR / "migrations" / "env.py").read_text()

    assert "async def _ensure_wide_alembic_version_column" in env_script
    assert "CREATE TABLE IF NOT EXISTS alembic_version" in env_script
    assert "version_num VARCHAR(255) NOT NULL" in env_script
    assert "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)" in env_script
    assert env_script.index("await _ensure_wide_alembic_version_column") < env_script.index(
        "await connection.run_sync(do_run_migrations)"
    )


def test_collaboration_migration_names_fit_postgres_identifier_limit() -> None:
    migration_path = SERVER_DIR / "migrations" / "versions" / "add_collaboration_integration_tables.py"
    module = ast.parse(migration_path.read_text())
    names: list[str] = []

    for node in ast.walk(module):
        if not isinstance(node, ast.Call):
            continue
        function_name = getattr(node.func, "attr", "")
        if function_name not in {"create_foreign_key", "drop_constraint", "create_index", "drop_index"}:
            continue
        if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            names.append(node.args[0].value)

    assert names
    assert all(len(name) <= 63 for name in names)
