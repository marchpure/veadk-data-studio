from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = ROOT / "scripts" / "commercial_p0_matrix.json"
REPORT_PATH = ROOT / "docs" / "product" / "data-studio-commercial-p0-verification-report.md"
SCRIPT_PATH = ROOT / "scripts" / "commercial_p0_verification.mjs"
RUNNER_PATH = ROOT / "scripts" / "commercial_p0_verification.sh"


def _matrix() -> dict:
    return json.loads(MATRIX_PATH.read_text())


def test_required_verification_artifacts_exist() -> None:
    for path in [MATRIX_PATH, REPORT_PATH, SCRIPT_PATH, RUNNER_PATH]:
        assert path.exists(), path


def test_branch_base_ports_and_routes_are_fixed_to_coordinator_contract() -> None:
    matrix = _matrix()

    assert matrix["base_sha"] == "e9358ea56554cc0ecdf93b723359eee711cb13b1"
    assert matrix["branch"] == "verification/data-studio-commercial-p0"
    assert matrix["ports"] == {"backend": 18123, "frontend": 15179, "do_not_touch": 8080}

    required_routes = {route["path"] for route in matrix["ui_routes"]}
    assert {
        "/login",
        "/dashboard-assets",
        "/dashboard-assets/commercial-verification-asset",
        "/evaluation",
        "/data-modeling",
        "/data-models",
        "/databases",
        "/sources",
    } <= required_routes

    assert {(viewport["width"], viewport["height"]) for viewport in matrix["viewports"]} == {
        (1440, 900),
        (390, 844),
    }


def test_connector_matrix_covers_required_commercial_families_and_fields() -> None:
    matrix = _matrix()
    connector_ids = {connector["id"] for connector in matrix["connectors"]}

    assert connector_ids == {
        "files",
        "web",
        "feishu_lark",
        "tos",
        "postgres",
        "mysql",
        "sqlite",
        "mssql",
        "oracle",
        "databricks",
        "mongo",
        "dynamodb",
    }

    required_fields = set(matrix["connector_required_fields"])
    for connector in matrix["connectors"]:
        assert required_fields <= set(connector), connector["id"]
        assert connector["status"] in {"ready", "beta", "planned", "blocked"}


def test_verification_edits_stay_out_of_forbidden_product_paths() -> None:
    matrix = _matrix()
    base_sha = matrix["base_sha"]
    changed = subprocess.run(
        ["git", "-C", str(ROOT), "diff", "--name-only", f"{base_sha}...HEAD"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.splitlines()

    allowed = tuple(matrix["allowed_verification_paths"])
    forbidden = tuple(matrix["forbidden_paths"])
    for path in changed:
        assert path.startswith(allowed), path
        assert not path.startswith(forbidden), path


def test_runner_documents_isolated_runtime_without_touching_8080() -> None:
    runner = RUNNER_PATH.read_text()

    assert "e9358ea56554cc0ecdf93b723359eee711cb13b1" in runner
    assert "BACKEND_PORT=\"${BACKEND_PORT:-18123}\"" in runner
    assert "FRONTEND_PORT=\"${FRONTEND_PORT:-15179}\"" in runner
    assert "byaan-commercial-p0-postgres-data" in runner
    assert "SQLITE_DB=\"${SQLITE_DB:-$APP_DATA_DIR/sqlite/app.db}\"" in runner
    assert "sqlite+aiosqlite:///$SQLITE_DB" in runner
    assert "iTCP:8080" not in runner
    assert "kill 8080" not in runner


def test_verifier_supports_self_hosted_auth_probe() -> None:
    verifier = SCRIPT_PATH.read_text()

    assert "/api/auth/login" in verifier
    assert "/api/scopes/all" in verifier
    assert "MASTER_USER_EMAIL" in verifier
    assert "MASTER_USER_PASSWORD" in verifier
    assert "Bearer ${authState.accessToken}" in verifier
    assert "X-Tenant-ID" in verifier


def test_verifier_probes_current_commercial_api_surfaces() -> None:
    probe_ids = {probe["id"] for probe in _matrix()["api_probes"]}

    assert {
        "dashboard_assets",
        "evaluation_suites",
        "connector_definitions",
        "sources_overview",
        "datasources",
        "data_models",
        "semantic_models",
        "folders",
        "mcp_stdio_config",
    } <= probe_ids


def test_report_contains_all_required_evidence_sections() -> None:
    report = REPORT_PATH.read_text()
    required_sections = [
        "Branch / Build Provenance",
        "Migration Evidence",
        "Connector Evidence Matrix",
        "Modeling Evidence",
        "Dashboard Evidence",
        "Evaluation Evidence",
        "Sharing Evidence",
        "Playwright Route Evidence",
        "Current Verdict",
    ]
    for section in required_sections:
        assert section in report
