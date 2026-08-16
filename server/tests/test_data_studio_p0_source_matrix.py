from __future__ import annotations

from pathlib import Path

from server.scripts.generate_data_studio_p0_source_matrix import (
    OUTPUT_PATH,
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
        "legacy_dataset_parquet_json",
        "web_url",
        "feishu_doc_wiki",
        "feishu_sheet_base",
        "volcengine_tos_bucket_prefix",
        "volcengine_tos_object_tabular",
        "volcengine_tos_object_context",
        "sql_pg_mysql_sqlite_oracle",
        "sqlserver_mssql",
        "mongo",
        "dynamodb",
        "databricks",
    }:
        assert required_source in row_by_source

    summary = matrix_summary(rows)
    assert summary["beta"] >= 1
    assert summary["planned"] >= 1
    assert summary["blocked"] >= 1
    assert set(summary) == {"ready", "beta", "planned", "blocked"}
