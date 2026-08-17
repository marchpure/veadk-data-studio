"""Generate the Connector/Modeling commercial P0 acceptance report.

The report is intentionally derived from the source-matrix generator so the
acceptance branch records evidence without hand-promoting beta/planned rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from server.scripts.generate_data_studio_p0_source_matrix import MatrixRow, build_matrix_rows, matrix_summary

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = REPO_ROOT / "docs" / "product" / "data-studio-commercial-p0-connector-modeling-acceptance.md"
ORIGINAL_BASE_SHA = "290679967d4e823077861fbd9875c860d698b4b9"
ORIGINAL_BASE_SHORT_SHA = "2906799"
PARALLEL_BASE_SHA = "13ed502b79d0e5f3b936af54316b2ab571e735a7"
PARALLEL_BASE_SHORT_SHA = "13ed502"
FINAL_SYNC_STAGING_SHA = "13ed502b79d0e5f3b936af54316b2ab571e735a7"
D_HEAD = "reported-after-final-push"
WORKTREE = "/Users/bytedance/worktrees/byaan-connector-modeling-acceptance-p0"
BRANCH = "acceptance/connector-modeling-commercial-p0"


ACCEPTANCE_SOURCES = [
    "local_file_csv",
    "local_file_xlsx_xlsm",
    "local_file_pdf_docx_pptx",
    "local_file_parquet_json_jsonl",
    "web_url",
    "feishu_doc_wiki",
    "feishu_sheet_base",
    "volcengine_tos_bucket_prefix",
    "volcengine_tos_object_tabular",
    "volcengine_tos_object_context",
    "sql_pg_mysql_sqlite_oracle_mssql",
    "mongo",
    "dynamodb",
    "databricks",
]


PROOF_COMMANDS = [
    (
        "matrix contract",
        "cd server && PYTHONPATH=..:tests uv run pytest tests/test_data_studio_p0_source_matrix.py "
        "tests/test_connector_modeling_commercial_acceptance.py -q",
    ),
    (
        "connector contracts",
        "cd server && PYTHONPATH=..:tests uv run pytest "
        "tests/test_source_connectors_api.py::test_connector_catalog_marks_only_real_connectors_available "
        "tests/test_source_connectors_api.py::test_picker_import_sync_and_idempotency_use_source_connection_not_placeholder "
        "tests/test_source_connectors_api.py::test_feishu_picker_import_syncs_real_resource_types_without_placeholder_state "
        "tests/test_source_connectors_api.py::test_local_json_jsonl_source_upload_creates_governed_snapshot_evidence_and_projection "
        "tests/test_source_connectors_api.py::test_local_parquet_source_upload_creates_governed_snapshot_evidence_and_projection "
        "tests/test_source_connectors_api.py::test_projection_review_api_records_current_review_and_lineage "
        "tests/test_source_connectors_api.py::test_tos_parser_contracts_cover_supported_formats_and_actionable_errors "
        "tests/test_source_connectors_api.py::test_tos_object_sync_maps_large_missing_and_permission_errors "
        "tests/test_source_connectors_api.py::test_feishu_refresh_failure_marks_connection_reauthorization_required "
        "tests/test_source_connectors_api.py::test_source_connection_browse_requires_authorization_without_fake_empty_success "
        "tests/test_source_connectors_api.py::test_tos_resource_listing_persists_picker_permission_failure -q",
    ),
    (
        "modeling contracts",
        "cd server && PYTHONPATH=..:tests uv run pytest "
        "tests/test_source_understanding_api.py::test_database_source_understanding_generates_profile_relationship_evidence_and_review "
        "tests/test_source_understanding_api.py::test_verified_source_candidates_create_semantic_model_draft_with_lineage "
        "tests/test_source_understanding_api.py::test_sqlite_source_understanding_creates_semantic_model_draft "
        "tests/test_source_understanding_api.py::test_mssql_source_understanding_creates_snapshots_evidence_and_semantic_model_draft "
        "tests/test_source_understanding_api.py::test_mongo_source_understanding_creates_profile_snapshots_without_semantic_candidates "
        "tests/test_source_understanding_api.py::test_dynamodb_source_understanding_creates_profile_snapshots_without_semantic_candidates "
        "tests/test_source_understanding_api.py::test_projected_dataset_source_understanding_creates_semantic_draft_with_projection_lineage "
        "tests/test_semantic_modeling_api.py::test_data_models_validate_publish_and_query_metric_use_persisted_model "
        "tests/test_semantic_modeling_api.py::test_publish_creates_immutable_version_and_query_uses_published_snapshot "
        "tests/test_semantic_modeling_api.py::test_projected_dataset_semantic_model_publish_and_mcp_query -q",
    ),
    (
        "warehouse and NoSQL parser contracts",
        "cd server && PYTHONPATH=..:tests uv run pytest tests/test_databricks_connector.py tests/test_mongo_connector.py -q",
    ),
    (
        "acceptance generator",
        "cd server && PYTHONPATH=..:tests uv run python scripts/generate_connector_modeling_acceptance.py --check",
    ),
    ("diff check", "git diff --check"),
    ("branch status", "git status --short --branch"),
]


REAL_E2E_COMMANDS = [
    (
        "projected source browser/API journey",
        "API_URL=http://127.0.0.1:<backend-port> BASE_URL=http://127.0.0.1:<client-port> "
        "SCREEN_DIR=/Users/bytedance/.codex/data-studio-p0-evidence/<run-id> "
        "node client/scripts/data-studio-p0-projected-source-e2e.mjs",
    ),
    (
        "external Postgres modeling journey",
        "BASE_URL=http://127.0.0.1:<client-port> PG_HOST=<host> PG_PORT=<port> PG_USER=<user> "
        "PG_PASSWORD=<password> PG_DATABASE=<database> PG_SCHEMA=<schema> "
        "EVIDENCE_DIR=/Users/bytedance/.codex/data-studio-p0-evidence/<run-id> "
        "node client/scripts/data-modeling-api-journey.mjs",
    ),
    (
        "real TOS object E2E",
        "cd server && BYAAN_REAL_TOS_ENDPOINT=<endpoint> BYAAN_REAL_TOS_REGION=<region> "
        "BYAAN_REAL_TOS_ACCESS_KEY_ID=<access-key> BYAAN_REAL_TOS_SECRET_ACCESS_KEY=<secret> "
        "BYAAN_REAL_TOS_BUCKET=<bucket> BYAAN_REAL_TOS_OBJECT_KEY=<csv-json-xlsx-jsonl-parquet-key> "
        "PYTHONPATH=..:tests uv run pytest tests/test_real_source_connector_e2e.py::test_real_tos_object_source_snapshot_evidence_dataset_e2e -q",
    ),
    (
        "real Feishu Sheet E2E",
        "cd server && BYAAN_REAL_FEISHU_ACCESS_TOKEN=<token> BYAAN_REAL_FEISHU_SPREADSHEET_TOKEN=<sheet-token> "
        "BYAAN_REAL_FEISHU_SHEET_ID=<sheet-id> BYAAN_REAL_FEISHU_RANGE=<range> "
        "PYTHONPATH=..:tests uv run pytest tests/test_real_source_connector_e2e.py::test_real_feishu_sheet_source_snapshot_evidence_dataset_e2e -q",
    ),
]


@dataclass(frozen=True)
class AcceptanceStatus:
    source_type: str
    final_status: str
    evidence_class: str
    connector_verdict: str
    modeling_verdict: str
    credential_state: str


def acceptance_rows() -> list[MatrixRow]:
    row_by_source = {row.source_type: row for row in build_matrix_rows()}
    return [row_by_source[source] for source in ACCEPTANCE_SOURCES]


def status_for_row(row: MatrixRow) -> AcceptanceStatus:
    if row.source_type in {"mongo", "dynamodb"}:
        return AcceptanceStatus(
            source_type=row.source_type,
            final_status=row.final_status,
            evidence_class="mock contract plus schema-cache profile fixture",
            connector_verdict="profile snapshots and evidence exist; tabular projection is not reviewed",
            modeling_verdict="semantic candidates are intentionally disabled until reviewed tabular projection exists",
            credential_state="real credentials absent; remains beta",
        )
    if row.source_type == "databricks":
        return AcceptanceStatus(
            source_type=row.source_type,
            final_status=row.final_status,
            evidence_class="mock contract plus OAuth/catalog unit coverage",
            connector_verdict="OAuth/schema/profile contract exists; live warehouse drill-down not proven",
            modeling_verdict="structured warehouse modeling path exists but needs live profile freshness proof",
            credential_state="live Databricks OAuth credentials absent; remains beta",
        )
    if row.source_type.startswith("feishu"):
        return AcceptanceStatus(
            source_type=row.source_type,
            final_status=row.final_status,
            evidence_class="mock contract; env-gated real Sheet E2E available",
            connector_verdict="OAuth/picker/import/already-added/reauthorization contracts exist",
            modeling_verdict="Sheets/Base projection handoff exists; Docs/Wiki context extraction provenance is unverified",
            credential_state="live tenant OAuth credentials absent in this branch; remains beta",
        )
    if row.source_type.startswith("volcengine_tos"):
        return AcceptanceStatus(
            source_type=row.source_type,
            final_status=row.final_status,
            evidence_class="mock contract; env-gated real TOS E2E available",
            connector_verdict="bucket/prefix/object browser, parser, retry, and permission contracts exist",
            modeling_verdict="tabular projection handoff exists for objects; context extraction provenance is unverified",
            credential_state="real TOS credentials absent in this branch; remains beta",
        )
    if row.source_type == "sql_pg_mysql_sqlite_oracle_mssql":
        return AcceptanceStatus(
            source_type=row.source_type,
            final_status=row.final_status,
            evidence_class="mock contract plus local SQLite/projected-source E2E harness; live external DB optional",
            connector_verdict="schema/profile/relationship evidence exists for cached SQL dialect fixtures",
            modeling_verdict="review, semantic draft, publish, reload, MCP contracts exist",
            credential_state="live-driver credentials for every dialect absent; remains beta",
        )
    if row.source_type == "web_url":
        return AcceptanceStatus(
            source_type=row.source_type,
            final_status=row.final_status,
            evidence_class="mock contract",
            connector_verdict="public URL capture, parser, retry, and SSRF guard contracts exist",
            modeling_verdict="context evidence exists; semantic-ready tabular extraction is not proven",
            credential_state="no auth required; public-site crawl/freshness evidence incomplete; remains beta",
        )
    return AcceptanceStatus(
        source_type=row.source_type,
        final_status=row.final_status,
        evidence_class=_local_file_evidence_class(row),
        connector_verdict="governed upload, snapshot, parser, projection/context evidence, review, and reindex/delete contracts exist",
        modeling_verdict="tabular files can hand off reviewed projections to semantic draft/publish/MCP; context files need verified extraction provenance",
        credential_state="no auth required; customer-scale fixtures and manual review evidence incomplete; remains beta",
    )


def _local_file_evidence_class(row: MatrixRow) -> str:
    if row.modeling_mode == "context_only":
        return "mock contract; context extraction provenance is not live-verified"
    return "mock contract plus local projected-source E2E harness where tabular"


def render_report() -> str:
    rows = acceptance_rows()
    status_by_source = {status.source_type: status for status in (status_for_row(row) for row in rows)}
    summary = matrix_summary(build_matrix_rows())
    lines = [
        "# Data Studio Commercial P0 Connector/Modeling Acceptance",
        "",
        "> Generated by `server/scripts/generate_connector_modeling_acceptance.py` from the source matrix. Do not hand-promote source rows in this report.",
        "",
        "## Baseline",
        "",
        f"- Branch: `{BRANCH}`",
        f"- Worktree: `{WORKTREE}`",
        f"- ORIGINAL_BASE_SHA: `{ORIGINAL_BASE_SHA}` (`{ORIGINAL_BASE_SHORT_SHA}`)",
        f"- PARALLEL_BASE_SHA: `{PARALLEL_BASE_SHA}` (`{PARALLEL_BASE_SHORT_SHA}`)",
        f"- FINAL_SYNC_STAGING_SHA: `{FINAL_SYNC_STAGING_SHA}`",
        f"- D_HEAD: `{D_HEAD}`",
        "- Current acceptance baseline: `PARALLEL_BASE_SHA`; `ORIGINAL_BASE_SHA` is retained as the historical source of the Session D worktree.",
        "- Scope owner: Connector and Modeling Commercial Acceptance",
        "- Scope limit: fixture, contract tests, E2E harness, source matrix evidence, and documentation only. This branch does not change production connector/modeling code.",
        "- Port rule: use isolated ports for local runs. Do not touch `8080`; final 8080 validation belongs to Coordinator after integration.",
        "- Database rule: use isolated local/test databases only. Do not reuse Coordinator shared backend state.",
        "",
        "## Final Classification",
        "",
        f"- Overall connector/modeling status: `PARTIAL`, not `READY`.",
        f"- Source matrix summary: `{summary['ready']} ready / {summary['beta']} beta / {summary['planned']} planned / {summary['blocked']} blocked / {sum(summary.values())} total`.",
        "- The 14 acceptance source groups below are all `beta`; no row is ready-complete because at least one of real credentials, real customer-scale data, verified runtime provenance, manual review evidence, or live-provider E2E is missing.",
        "- MongoDB and DynamoDB stay in `document_projection`: they must not enter semantic modeling until a tabular projection has been reviewed.",
        "- Semi-structured context rows stay `beta` because OpenHuman-style provenance is documented but not verified as persisted runtime metadata.",
        "- This report intentionally distinguishes mock contract evidence, real E2E harnesses, credential-blocked E2E, and pre-existing failures.",
        "",
        "## Acceptance Source Matrix",
        "",
        "| source | final | evidence class | auth | browse/select/import | already-added | snapshot/profile | raw locator | parser/version/warnings | retry/permission/reauth | delete/reindex | detail | lineage/evidence | fixture | UI/API/MCP result | verdict |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        status = status_by_source[row.source_type]
        lines.append(
            "| "
            + " | ".join(
                _cell(value)
                for value in (
                    row.source_type,
                    row.final_status,
                    status.evidence_class,
                    row.auth_config_contract,
                    row.browse_select_import_contract,
                    _already_added(row),
                    row.snapshot_raw_artifact,
                    _raw_locator(row),
                    _parser_warnings(row),
                    row.retry_revoke,
                    _delete_reindex(row),
                    row.blocker_reason,
                    row.lineage_evidence,
                    row.fixture,
                    _ui_api_mcp(row, status),
                    f"{status.connector_verdict}; {status.modeling_verdict}; {status.credential_state}",
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Modeling Acceptance Coverage",
            "",
            "| stage | current proof | status |",
            "|---|---|---|",
            "| source understanding | `/api/datasources/{id}/understanding/analyze` contract tests create runs, resources, snapshots, evidence, and candidates for SQL/projected sources. | beta evidence |",
            "| schema/profile | SQL, projected datasets, MongoDB, DynamoDB, and Databricks contracts expose cached schema/profile facts; live-provider profile freshness remains missing. | beta evidence |",
            "| candidate | SQL/projected data create schema, profile, relationship, data-truth, and quality candidates. | beta evidence |",
            "| relationship review | Candidate review accepts, edits, rejects, and persists lineage/review notes in focused tests. | beta evidence |",
            "| projection review | File/Feishu/TOS projection review stores `verified`, `needs_changes`, and `rejected` states with source locators. | beta evidence |",
            "| semantic draft | Verified candidates can create semantic model drafts with source-understanding lineage. | beta evidence |",
            "| publish | Published semantic models create immutable versions and reject publish when readiness blockers remain. | beta evidence |",
            "| reload | Reloaded semantic models retain published version, calculated fields, and MCP last-result state. | beta evidence |",
            "| MCP | Published models respond through `/api/data-models/{id}/mcp/query_metric`; draft-only models are rejected. | beta evidence |",
            "| lineage/evidence | SourceUnderstandingRun, SourceResource, SourceSnapshot, EvidenceFragment, projection_manifest, projection_review, and SemanticModel review lineage are asserted in tests. | beta evidence |",
            "| readiness detail | Validation returns blockers and readiness detail; no broad row is promoted to ready. | beta evidence |",
            "| Mongo/Dynamo guard | NoSQL profile tests assert no semantic candidates before reviewed tabular projection. | required guard present |",
            "",
            "## OpenHuman Provenance Gate",
            "",
            "- Reference chain to preserve for semi-structured sources: reader -> canonicalize -> archive/raw document -> chunk -> extract -> entity-relation -> tree/summary.",
            "- Runtime fields required before ready: `algorithm_name`, `algorithm_version`, `config_digest`, `source_revision`, `confidence`, `evidence_locator`, `provenance`, and `warnings`.",
            "- Current state: `UNVERIFIED`. Native KnowledgeProvider evidence exists, but this branch does not prove verified OpenHuman-compatible runtime persistence, so context rows remain beta.",
            "",
            "## Reproducible Commands",
            "",
            "Run these scoped commands from the acceptance worktree. They avoid port `8080` unless a caller explicitly passes an isolated `BASE_URL`/`API_URL`.",
            "",
        ]
    )
    lines.extend(_render_commands("Scoped Contract Gates", PROOF_COMMANDS))
    lines.extend(_render_commands("Optional Real E2E Gates With Credentials", REAL_E2E_COMMANDS))
    lines.extend(
        [
            "## Evidence Boundaries",
            "",
            "- Real E2E: only the optional credential-gated commands, or the projected-source/local API journeys when run against an actual isolated backend/client pair, count as real E2E.",
            "- Mock contract: focused pytest coverage with fake Feishu/TOS/Databricks/Mongo/Dynamo adapters proves contracts only.",
            "- Credential blocked: Feishu/Lark, TOS, Databricks, external PG/MySQL/MSSQL/Oracle, MongoDB, and DynamoDB live-provider readiness remains blocked by missing credentials/data in this branch.",
            "- Pre-existing failure: broader full-suite failures must be recorded separately and must not be hidden by this acceptance report.",
            "- Catalog tiles: planned rows in `docs/product/data-studio-p0-source-matrix.md` are roadmap catalog tiles, not adapters.",
            "",
        ]
    )
    return "\n".join(lines)


def _already_added(row: MatrixRow) -> str:
    if "already-added" in row.browse_select_import_contract or "already_added" in row.browse_select_import_contract:
        return "covered by picker contract"
    if row.source_type in {"feishu_doc_wiki", "feishu_sheet_base", "volcengine_tos_bucket_prefix"}:
        return "covered by SourceConnection picker idempotency tests"
    if row.source_type.startswith("local_file") or row.source_type == "web_url":
        return "resource identity/dedup is not picker-based"
    return "not picker-based"


def _raw_locator(row: MatrixRow) -> str:
    text = row.snapshot_raw_artifact
    for marker in ("file://", "web://", "feishu://", "tos://", "db://"):
        if marker in text:
            return text[text.find(marker) :]
    if row.source_type == "databricks":
        return "external warehouse; profile locator is Connection schema_cache"
    return text


def _parser_warnings(row: MatrixRow) -> str:
    if row.source_type.startswith("volcengine_tos"):
        return f"{row.parser_profile_contract}; parser failures map to actionable warnings/errors"
    if row.source_type.startswith("feishu"):
        return f"{row.parser_profile_contract}; OpenAPI/provider warnings not live-verified"
    if "OpenHuman" in row.blocker_reason:
        return f"{row.parser_profile_contract}; verified provenance warnings missing"
    return row.parser_profile_contract


def _delete_reindex(row: MatrixRow) -> str:
    retry = row.retry_revoke.lower()
    if "delete" in retry or "sync" in retry or "refresh" in retry:
        return row.retry_revoke
    return "delete/reindex not proven beyond listed contract"


def _ui_api_mcp(row: MatrixRow, status: AcceptanceStatus) -> str:
    if row.source_type in {"mongo", "dynamodb"}:
        return "API profile only; UI handoff says projection needed; MCP intentionally unavailable before reviewed projection"
    if row.modeling_mode in {"tabular_projection", "structured_data_modeler", "structured_warehouse_modeler"}:
        return f"API/UI journey listed; MCP only after published semantic model. {status.evidence_class}"
    return f"API/UI context journey listed; MCP semantic metric not applicable before verified tabular/semantic model. {status.evidence_class}"


def _render_commands(title: str, commands: Iterable[tuple[str, str]]) -> list[str]:
    lines = [f"### {title}", ""]
    for name, command in commands:
        lines.extend([f"- {name}:", "", "```bash", command, "```", ""])
    return lines


def _cell(value: object) -> str:
    return str(value).replace("\n", "<br>").replace("|", "\\|")


def write_report(path: Path = OUTPUT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(), encoding="utf-8")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Fail if the generated report is stale.")
    args = parser.parse_args()

    rendered = render_report()
    if args.check:
        existing = OUTPUT_PATH.read_text(encoding="utf-8")
        if existing != rendered:
            raise SystemExit(f"{OUTPUT_PATH} is stale; run server/scripts/generate_connector_modeling_acceptance.py")
        return
    write_report()


if __name__ == "__main__":
    main()
