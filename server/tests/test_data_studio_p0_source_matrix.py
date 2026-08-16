from __future__ import annotations

from pathlib import Path

from server.scripts.generate_data_studio_p0_source_matrix import (
    OUTPUT_PATH,
    beta_to_ready_requirements,
    build_matrix_rows,
    matrix_summary,
    render_markdown,
)
from server.services.connector_catalog import CONNECTOR_CATALOG


def test_data_studio_p0_source_matrix_is_generated_from_current_code() -> None:
    rendered = render_markdown()
    existing = Path(OUTPUT_PATH).read_text(encoding="utf-8")

    assert existing == rendered


def test_data_studio_p0_source_matrix_covers_connector_catalog_and_statuses() -> None:
    rows = build_matrix_rows()
    row_by_source = {row.source_type: row for row in rows}
    connector_ids = {connector.id for connector in CONNECTOR_CATALOG}

    assert len(row_by_source) == len(rows)
    assert {"local_files", "web", "feishu", "sql_databases", "volcengine_tos", "databricks"}.issubset(connector_ids)
    for connector in CONNECTOR_CATALOG:
        if connector.availability == "planned":
            assert connector.id in row_by_source
            assert row_by_source[connector.id].final_status == "planned"

    for required_source in {
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
    }:
        assert required_source in row_by_source

    summary = matrix_summary(rows)
    assert summary["beta"] >= 1
    assert summary["planned"] >= 1
    assert summary["blocked"] == 0
    assert set(summary) == {"ready", "beta", "planned", "blocked"}
    assert row_by_source["mongo"].final_status == "beta"
    assert row_by_source["mongo"].modeling_mode == "document_projection"
    assert row_by_source["dynamodb"].final_status == "beta"
    assert row_by_source["dynamodb"].modeling_mode == "document_projection"


def test_data_studio_p0_source_matrix_readiness_is_partial_until_rows_are_ready() -> None:
    rows = build_matrix_rows()
    summary = matrix_summary(rows)
    rendered = render_markdown()
    requirement_sources = {source_type for source_type, _requirement in beta_to_ready_requirements()}
    beta_sources = {row.source_type for row in rows if row.final_status == "beta"}

    assert summary == {"ready": 0, "beta": 14, "planned": 26, "blocked": 0}
    assert requirement_sources == beta_sources
    assert "Final acceptance status: `PARTIAL`" in rendered
    assert "8080 deployment status: `8080_PARTIAL`" in rendered
    assert "Runtime adapter status: `UNVERIFIED`" in rendered
