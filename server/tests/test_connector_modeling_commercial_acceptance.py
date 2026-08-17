from __future__ import annotations

from pathlib import Path

from server.scripts.generate_connector_modeling_acceptance import (
    ACCEPTANCE_SOURCES,
    FINAL_SYNC_STAGING_SHA,
    ORIGINAL_BASE_SHA,
    OUTPUT_PATH,
    PARALLEL_BASE_SHA,
    PROOF_COMMANDS,
    REAL_E2E_COMMANDS,
    acceptance_rows,
    render_report,
)


REQUIRED_COLUMNS = {
    "auth",
    "browse/select/import",
    "already-added",
    "snapshot/profile",
    "raw locator",
    "parser/version/warnings",
    "retry/permission/reauth",
    "delete/reindex",
    "detail",
    "lineage/evidence",
    "fixture",
    "UI/API/MCP result",
    "verdict",
}


def test_connector_modeling_acceptance_report_is_generated() -> None:
    assert Path(OUTPUT_PATH).read_text(encoding="utf-8") == render_report()


def test_connector_modeling_acceptance_covers_required_source_groups_without_ready_claims() -> None:
    rows = acceptance_rows()
    row_by_source = {row.source_type: row for row in rows}

    assert list(row_by_source) == ACCEPTANCE_SOURCES
    assert set(row_by_source) == {
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
    }
    assert {row.final_status for row in rows} == {"beta"}


def test_connector_modeling_acceptance_report_keeps_guardrails_explicit() -> None:
    report = render_report()

    assert "Overall connector/modeling status: `PARTIAL`, not `READY`." in report
    assert f"ORIGINAL_BASE_SHA: `{ORIGINAL_BASE_SHA}`" in report
    assert f"PARALLEL_BASE_SHA: `{PARALLEL_BASE_SHA}`" in report
    assert f"FINAL_SYNC_STAGING_SHA: `{FINAL_SYNC_STAGING_SHA}`" in report
    assert "Do not touch `8080`" in report
    assert "Catalog tiles: planned rows" in report
    assert "MongoDB and DynamoDB stay in `document_projection`" in report
    assert "Runtime fields required before ready" in report
    assert "`algorithm_name`" in report
    assert "`config_digest`" in report
    assert "`source_revision`" in report
    assert "`confidence`" in report
    assert "`evidence_locator`" in report
    assert "`provenance`" in report
    assert "`warnings`" in report


def test_connector_modeling_acceptance_report_has_required_evidence_columns() -> None:
    report = render_report()
    header = next(line for line in report.splitlines() if line.startswith("| source | final | evidence class |"))

    for column in REQUIRED_COLUMNS:
        assert column in header


def test_connector_modeling_acceptance_commands_are_scoped_and_reproducible() -> None:
    command_text = "\n".join(command for _name, command in [*PROOF_COMMANDS, *REAL_E2E_COMMANDS])

    assert "tests/test_connector_modeling_commercial_acceptance.py" in command_text
    assert "git diff --check" in command_text
    assert "git status --short --branch" in command_text
    assert "client/scripts/data-studio-p0-projected-source-e2e.mjs" in command_text
    assert "client/scripts/data-modeling-api-journey.mjs" in command_text
    assert "tests/test_real_source_connector_e2e.py::test_real_tos_object_source_snapshot_evidence_dataset_e2e" in command_text
    assert "tests/test_real_source_connector_e2e.py::test_real_feishu_sheet_source_snapshot_evidence_dataset_e2e" in command_text
    assert "localhost:8080" not in command_text
    assert "127.0.0.1:8080" not in command_text
