"""Generate the Unified Data Studio P0 source matrix from current code facts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from server.models.connections import ALLOWED_CONN_TYPES
from server.models.source_resources import SOURCE_RESOURCE_TYPES
from server.services.connector_catalog import CONNECTOR_CATALOG, ConnectorDefinition
from server.services.source_analyzers import (
    DATABASE_ANALYZER_VERSION,
    DATABASE_CONNECTION_TYPES,
    SOURCE_UNDERSTANDING_CONNECTION_TYPES,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = REPO_ROOT / "docs" / "product" / "data-studio-p0-source-matrix.md"


@dataclass(frozen=True)
class MatrixRow:
    source_type: str
    provider_adapter: str
    availability: str
    auth_config_contract: str
    browse_select_import_contract: str
    snapshot_raw_artifact: str
    parser_profile_contract: str
    modeling_mode: str
    fixture: str
    api_journey: str
    ui_journey: str
    lineage_evidence: str
    retry_revoke: str
    final_status: str
    blocker_reason: str


def _connector(provider: str) -> ConnectorDefinition:
    for connector in CONNECTOR_CATALOG:
        if connector.id == provider:
            return connector
    raise AssertionError(f"Missing connector definition: {provider}")


def _planned_connectors() -> list[ConnectorDefinition]:
    return [connector for connector in CONNECTOR_CATALOG if connector.availability == "planned"]


def _row_for_planned_connector(connector: ConnectorDefinition) -> MatrixRow:
    return MatrixRow(
        source_type=connector.id,
        provider_adapter=f"{connector.display_name} / roadmap catalog tile",
        availability=connector.availability,
        auth_config_contract=f"{connector.auth_mode}; config schema is not executable",
        browse_select_import_contract="Roadmap-only tile; no picker, import, or SourceResource contract",
        snapshot_raw_artifact="Missing",
        parser_profile_contract="Missing",
        modeling_mode="none",
        fixture="Not present",
        api_journey="GET /api/connector-definitions returns planned/read-only entry only",
        ui_journey="Databases connector catalog must not open a fake setup flow",
        lineage_evidence="Missing",
        retry_revoke="Missing",
        final_status="planned",
        blocker_reason="No certified adapter, auth, picker, snapshot, parser/profile, fixture, and UI journey",
    )


def build_matrix_rows() -> list[MatrixRow]:
    local_files = _connector("local_files")
    web = _connector("web")
    feishu = _connector("feishu")
    sql = _connector("sql_databases")
    tos = _connector("volcengine_tos")
    databricks = _connector("databricks")
    relational_analyzer_types = sorted({_normalize_database_type(item) for item in DATABASE_CONNECTION_TYPES})
    rows = [
        MatrixRow(
            source_type="local_file_csv",
            provider_adapter=f"{local_files.display_name} / SourceResourceService.create_file_resource_from_upload",
            availability=local_files.availability,
            auth_config_contract="none; tenant/user captured from authenticated upload",
            browse_select_import_contract="POST /api/source-resources/files accepts .csv and creates a governed SourceResource",
            snapshot_raw_artifact="SourceSnapshot with file://source-resources/{id}/raw/{hash}_{filename} and sha256 content hash",
            parser_profile_contract="parse_object_bytes csv -> tos-csv-parser-v1; projected Dataset schema via DataFrameFileService",
            modeling_mode="tabular_projection",
            fixture="server/tests/test_source_connectors_api.py local upload/projection coverage",
            api_journey="upload file -> snapshots -> parsed-assets -> lineage/consumers -> sources overview",
            ui_journey="client/src/pages/Databases.tsx direct source upload accepts .csv",
            lineage_evidence="SourceSnapshot, KnowledgeResource/EvidenceFragment, projected_dataset_id, projection_manifest",
            retry_revoke="POST /api/source-resources/{id}/sync reindexes raw artifact; DELETE tombstones source",
            final_status="beta",
            blocker_reason="Governed upload and projection exist; large-file resumable upload and review-grade projection confirmation remain beta hardening",
        ),
        MatrixRow(
            source_type="local_file_xlsx_xlsm",
            provider_adapter=f"{local_files.display_name} / SourceResourceService.create_file_resource_from_upload",
            availability=local_files.availability,
            auth_config_contract="none; tenant/user captured from authenticated upload",
            browse_select_import_contract="POST /api/source-resources/files accepts .xlsx and .xlsm; legacy .xls is not accepted by SourceResource upload",
            snapshot_raw_artifact="SourceSnapshot with file:// raw artifact and sha256 content hash",
            parser_profile_contract="parse_object_bytes xlsx/xlsm -> tos-excel-parser-v1; projected Dataset schema via DataFrameFileService",
            modeling_mode="tabular_projection",
            fixture="server/tests/test_source_connectors_api.py Excel projection coverage",
            api_journey="upload file -> snapshots -> parsed-assets -> lineage/consumers -> sources overview",
            ui_journey="client/src/pages/Databases.tsx direct source upload accepts .xlsx/.xlsm",
            lineage_evidence="SourceSnapshot, KnowledgeResource/EvidenceFragment, projected_dataset_id, projection_manifest with source locator",
            retry_revoke="POST /api/source-resources/{id}/sync reindexes raw artifact; DELETE tombstones source",
            final_status="beta",
            blocker_reason="Source upload excludes legacy .xls even though legacy dataset upload supports it; projection review remains beta",
        ),
        MatrixRow(
            source_type="local_file_pdf_docx_pptx",
            provider_adapter=f"{local_files.display_name} / SourceResourceService.create_file_resource_from_upload",
            availability=local_files.availability,
            auth_config_contract="none; tenant/user captured from authenticated upload",
            browse_select_import_contract="POST /api/source-resources/files accepts .pdf, .docx, .pptx for context sources",
            snapshot_raw_artifact="SourceSnapshot with file:// raw artifact and sha256 content hash",
            parser_profile_contract="basic PDF fallback, docx zip text, pptx slide text; KnowledgeProvider evidence index",
            modeling_mode="context_only",
            fixture="server/tests/test_source_connectors_api.py parser failure/reindex and source overview context coverage",
            api_journey="upload file -> snapshots -> parsed-assets -> processing -> evidence/search -> lineage/consumers",
            ui_journey="client/src/pages/Databases.tsx direct source upload accepts .pdf/.docx/.pptx",
            lineage_evidence="SourceSnapshot, KnowledgeResource/EvidenceFragment, source locator and raw artifact URI",
            retry_revoke="POST /api/source-resources/{id}/sync reindexes raw artifact; DELETE tombstones source",
            final_status="beta",
            blocker_reason="Context evidence exists; OpenHuman-compatible semi-structured extraction is documented but not verified in code",
        ),
        MatrixRow(
            source_type="local_file_parquet_json_jsonl",
            provider_adapter=f"{local_files.display_name} / SourceResourceService.create_file_resource_from_upload",
            availability=local_files.availability,
            auth_config_contract="none; tenant/user captured from authenticated upload",
            browse_select_import_contract="POST /api/source-resources/files accepts .parquet, .json, and .jsonl as governed SourceResource uploads",
            snapshot_raw_artifact="SourceSnapshot with file://source-resources/{id}/raw/{hash}_{filename} and sha256 content hash",
            parser_profile_contract="parse_object_bytes JSON/JSONL/Parquet parsers; projected Dataset schema via DataFrameFileService and DuckDB readers",
            modeling_mode="tabular_projection",
            fixture="server/tests/test_source_connectors_api.py local JSON/JSONL/Parquet governed upload projection coverage",
            api_journey="upload file -> snapshots -> projected dataset -> parsed-assets -> lineage/consumers -> sources overview",
            ui_journey="client/src/pages/Databases.tsx direct source upload accepts .parquet/.json/.jsonl",
            lineage_evidence="SourceSnapshot, KnowledgeResource/EvidenceFragment, projected_dataset_id, projection_manifest with local file source locator",
            retry_revoke="POST /api/source-resources/{id}/sync reindexes raw artifact; DELETE tombstones source",
            final_status="beta",
            blocker_reason="Governed upload and projection exist; nested/semi-structured JSON flattening policy and projection review remain beta hardening",
        ),
        MatrixRow(
            source_type="web_url",
            provider_adapter=f"{web.display_name} / WebSourceAdapter",
            availability=web.availability,
            auth_config_contract="none; SSRF guard and public http(s) capture policy",
            browse_select_import_contract="POST /api/source-resources with resource_type=web and source_url",
            snapshot_raw_artifact="SourceSnapshot raw_storage_uri web://sha256/{hash}",
            parser_profile_contract="web-html-parser-v1 content extraction; KnowledgeProvider evidence index",
            modeling_mode="context_only",
            fixture="server/tests/test_web_source_adapter.py and test_sources_overview_api.py",
            api_journey="create web source -> sync -> processing -> knowledge/search -> evidence/lineage/consumers",
            ui_journey="client/src/pages/Databases.tsx web source form; SourceDetailPage processing/evidence states",
            lineage_evidence="SourceSnapshot, KnowledgeResource/EvidenceFragment, source overview context status",
            retry_revoke="POST /api/source-resources/{id}/sync recaptures page; DELETE tombstones source",
            final_status="beta",
            blocker_reason="Single-page public capture exists; sitemap/page-group crawl policy and richer table extraction remain beta",
        ),
        MatrixRow(
            source_type="feishu_doc_wiki",
            provider_adapter=f"{feishu.display_name} / FeishuConnectorAdapter",
            availability=feishu.availability,
            auth_config_contract="OAuth admin config, state store, encrypted access/refresh tokens, required scopes",
            browse_select_import_contract="OAuth drive/wiki/search picker with pagination, quick locate, already-added state, multi-select import",
            snapshot_raw_artifact="SourceSnapshot raw_storage_uri feishu://{resource_type}/{token}",
            parser_profile_contract="feishu-openapi-v1 snapshot and KnowledgeProvider evidence index",
            modeling_mode="context_only",
            fixture="server/tests/test_source_connectors_api.py Feishu adapter/resource tests",
            api_journey="admin config/status -> OAuth start/callback/result -> browse/locate -> import -> processing/lineage",
            ui_journey="SourceConnectorImportPanel Feishu OAuth/picker/import plus SourceDetailPage reauth states",
            lineage_evidence="SourceConnection, SourceResource, SourceSnapshot, KnowledgeResource/EvidenceFragment",
            retry_revoke="refresh token and reauthorization states; DELETE connection disconnects resources; resource sync retries",
            final_status="beta",
            blocker_reason="Docs/Wiki context path exists; verified OpenHuman extraction adapter is UNVERIFIED and projection review remains future work",
        ),
        MatrixRow(
            source_type="feishu_sheet_base",
            provider_adapter=f"{feishu.display_name} / FeishuConnectorAdapter",
            availability=feishu.availability,
            auth_config_contract="OAuth admin config, state store, encrypted access/refresh tokens, required scopes",
            browse_select_import_contract="OAuth picker/quick locate and multi-select import for Sheets/Base",
            snapshot_raw_artifact="SourceSnapshot raw_storage_uri feishu://{resource_type}/{token}",
            parser_profile_contract="Feishu sheet/base OpenAPI raw JSON -> CSV projection -> DataFrameFileService schema",
            modeling_mode="tabular_projection",
            fixture="server/tests/test_source_connectors_api.py Feishu Sheet/Base projection tests; real env-gated E2E",
            api_journey="OAuth/browse/import -> snapshots -> projected dataset -> parsed-assets -> lineage/consumers",
            ui_journey="SourceConnectorImportPanel Feishu picker/import; Data Modeling sees needs_projection via /sources/overview",
            lineage_evidence="Projection manifest includes spreadsheet/app/table/range/field/cell locators",
            retry_revoke="refresh token and reauthorization states; source sync retries; DELETE disconnects resources",
            final_status="beta",
            blocker_reason="Projection exists with lineage; production semantic modeling still needs explicit review/confirmation contract",
        ),
        MatrixRow(
            source_type="volcengine_tos_bucket_prefix",
            provider_adapter=f"{tos.display_name} / TosConnectorAdapter",
            availability=tos.availability,
            auth_config_contract="access key credentials encrypted per tenant; endpoint/region/bucket/prefix config",
            browse_select_import_contract="Bucket/prefix/object browser with pagination, multi-select, prefix import manifest",
            snapshot_raw_artifact="SourceSnapshot raw_storage_uri tos://bucket/prefix and object manifest metadata",
            parser_profile_contract="Prefix manifest-first; object parsing only after object import",
            modeling_mode="context_or_projection_manifest",
            fixture="server/tests/test_source_connectors_api.py TOS prefix/object tests",
            api_journey="create connection -> browse -> import prefix/bucket/object -> processing -> lineage",
            ui_journey="SourceConnectorImportPanel TOS credentials/browser/import",
            lineage_evidence="Object manifest and projection_manifest locators for listed objects",
            retry_revoke="Connector error mapping to permission_lost/source_unavailable; source sync retries; DELETE disconnects",
            final_status="beta",
            blocker_reason="Prefix/bucket manifest exists; incremental sync policy and prefix-level parser coverage remain beta",
        ),
        MatrixRow(
            source_type="volcengine_tos_object_tabular",
            provider_adapter=f"{tos.display_name} / TosConnectorAdapter",
            availability=tos.availability,
            auth_config_contract="access key credentials encrypted per tenant",
            browse_select_import_contract="Object browser/import for supported object keys",
            snapshot_raw_artifact="SourceSnapshot raw_storage_uri tos://bucket/key with etag/version/last_modified metadata",
            parser_profile_contract="CSV/XLSX/XLSM/JSON/JSONL/Parquet object parsers; projected Dataset for CSV/Excel/JSON/Parquet object types",
            modeling_mode="tabular_projection",
            fixture="server/tests/test_source_connectors_api.py TOS object projection; server/tests/test_real_source_connector_e2e.py env-gated TOS",
            api_journey="create connection -> browse object -> import -> snapshots -> projected dataset -> parsed-assets/lineage",
            ui_journey="SourceConnectorImportPanel TOS object import; SourceDetailPage projection/processing",
            lineage_evidence="Projection manifest with bucket/key/version/etag locator",
            retry_revoke="permission_lost/source_unavailable/source_sync_failed states; manual retry; DELETE disconnects",
            final_status="beta",
            blocker_reason="Object projection exists; S3-compatible vendor normalization and projection review remain beta",
        ),
        MatrixRow(
            source_type="volcengine_tos_object_context",
            provider_adapter=f"{tos.display_name} / TosConnectorAdapter",
            availability=tos.availability,
            auth_config_contract="access key credentials encrypted per tenant",
            browse_select_import_contract="Object browser/import for supported text/html/pdf/docx/pptx keys",
            snapshot_raw_artifact="SourceSnapshot raw_storage_uri tos://bucket/key with etag/version/last_modified metadata",
            parser_profile_contract="text/html/pdf/docx/pptx parsers feed KnowledgeProvider evidence; no tabular profile unless projected",
            modeling_mode="context_only",
            fixture="server/tests/test_source_connectors_api.py parser/error handling coverage",
            api_journey="create connection -> browse object -> import -> snapshots -> knowledge/search -> lineage",
            ui_journey="SourceConnectorImportPanel TOS object import; SourceDetailPage context/evidence",
            lineage_evidence="SourceSnapshot, KnowledgeResource/EvidenceFragment, bucket/key locator",
            retry_revoke="permission_lost/source_unavailable/source_sync_failed states; manual retry; DELETE disconnects",
            final_status="beta",
            blocker_reason="Context indexing exists; OpenHuman-compatible extraction provenance is not wired into runtime algorithm metadata",
        ),
        MatrixRow(
            source_type="sql_pg_mysql_sqlite_oracle_mssql",
            provider_adapter=f"{sql.display_name} / ConnectionService + SourceAnalyzerService",
            availability=sql.availability,
            auth_config_contract="connection string/fields stored encrypted in Connection; schema refresh via ConnectionService",
            browse_select_import_contract="Database connection form and schema/profile refresh; no SourceConnection picker",
            snapshot_raw_artifact="SourceAnalyzer creates database_catalog/schema/table SourceSnapshot rows with db:// raw_storage_uri",
            parser_profile_contract=f"{DATABASE_ANALYZER_VERSION} produces schema/profile/relationship/metric candidates for {', '.join(relational_analyzer_types)}",
            modeling_mode="structured_data_modeler",
            fixture="server/tests/test_source_understanding_api.py and test_semantic_modeling_api.py",
            api_journey="/connections -> /datasources -> /datasources/{id}/understanding/analyze -> semantic-model-draft -> data-models publish/MCP",
            ui_journey="Databases SQL forms plus Data Modeling Generate from Data/Profile/Review/Publish/Explore",
            lineage_evidence="SourceUnderstandingRun, database_* SourceResources, EvidenceFragment locators, SemanticModel lineage",
            retry_revoke="refresh schema/profile; delete connection; semantic publish/reload through /data-models APIs",
            final_status="beta",
            blocker_reason="Structured model loop exists for PG/MySQL/SQLite/Oracle/MSSQL; live-driver E2E credentials and deeper dialect-specific profiling remain beta",
        ),
        MatrixRow(
            source_type="mongo",
            provider_adapter="Mongo query connector / DatabaseOperationsService.get_mongo_schema_async",
            availability="available",
            auth_config_contract="connection string stored encrypted in Connection",
            browse_select_import_contract="Database connection form and schema refresh",
            snapshot_raw_artifact="SourceAnalyzer creates database_catalog/schema/table SourceSnapshot rows from sampled collection schema_cache",
            parser_profile_contract="Mongo sampled fields/nested schema profile; semantic candidates intentionally disabled until reviewed tabular projection exists",
            modeling_mode="document_projection",
            fixture="server/tests/test_source_understanding_api.py Mongo NoSQL profile coverage plus mongo query/write detection tests",
            api_journey="/connections -> /datasources -> /datasources/{id}/understanding/analyze -> sources overview needs_projection",
            ui_journey="Databases MongoDB connection form and Data Modeling projection-needed handoff",
            lineage_evidence="SourceUnderstandingRun, database_* SourceResources, EvidenceFragment locators with nosql source_family",
            retry_revoke="refresh schema/delete connection",
            final_status="beta",
            blocker_reason="Source profile snapshots/evidence exist; reviewed tabular projection, projection dataset materialization, and semantic draft generation remain beta hardening",
        ),
        MatrixRow(
            source_type="dynamodb",
            provider_adapter="DynamoDB query connector / DatabaseOperationsService.get_dynamodb_schema_async",
            availability="available",
            auth_config_contract="AWS-style credentials stored encrypted in Connection",
            browse_select_import_contract="Database connection form and schema refresh",
            snapshot_raw_artifact="SourceAnalyzer creates database_catalog/schema/table SourceSnapshot rows from key schema, attributes, GSI, and sampled item schema_cache",
            parser_profile_contract="DynamoDB key/attribute/sample profile; semantic candidates intentionally disabled until reviewed tabular projection exists",
            modeling_mode="document_projection",
            fixture="server/tests/test_source_understanding_api.py DynamoDB NoSQL profile coverage plus write detection tests",
            api_journey="/connections -> /datasources -> /datasources/{id}/understanding/analyze -> sources overview needs_projection",
            ui_journey="Databases DynamoDB connection form and Data Modeling projection-needed handoff",
            lineage_evidence="SourceUnderstandingRun, database_* SourceResources, EvidenceFragment locators with nosql source_family",
            retry_revoke="refresh schema/delete connection",
            final_status="beta",
            blocker_reason="Source profile snapshots/evidence exist; reviewed tabular projection, projection dataset materialization, and semantic draft generation remain beta hardening",
        ),
        MatrixRow(
            source_type="databricks",
            provider_adapter=f"{databricks.display_name} / Databricks OAuth + AsyncDatabricksConnector",
            availability=databricks.availability,
            auth_config_contract="Databricks OAuth config/status/start/callback/result, encrypted OAuth block in Connection",
            browse_select_import_contract="Warehouse/catalog/schema picker creates selected Databricks connections",
            snapshot_raw_artifact="Not applicable; warehouse data remains external and profile freshness is schema_cache",
            parser_profile_contract="DatabaseOperationsService.get_databricks_schema_async and SourceOverview profile health",
            modeling_mode="structured_warehouse_modeler",
            fixture="server/tests/test_databricks_*.py and test_sources_overview_api.py",
            api_journey="OAuth -> discover warehouses/catalogs -> create connection -> sources overview -> Data Modeling profile/publish/MCP",
            ui_journey="Databases Databricks OAuth/catalog picker; Data Modeling warehouse mode",
            lineage_evidence="Connection schema_cache, SourceOverview modeling handoff, SemanticModel datasource lineage",
            retry_revoke="OAuth refresh/reauthorization; schema refresh; delete connection",
            final_status="beta",
            blocker_reason="Warehouse profile/modeling path exists; raw snapshot is not applicable and catalog drill-down remains beta hardening",
        ),
    ]
    rows.extend(_row_for_planned_connector(connector) for connector in _planned_connectors())
    return rows


def _normalize_database_type(value: str) -> str:
    if value in {"postgres", "postgresql"}:
        return "pg"
    return value


def matrix_summary(rows: list[MatrixRow]) -> dict[str, int]:
    summary = {"ready": 0, "beta": 0, "planned": 0, "blocked": 0}
    for row in rows:
        summary[row.final_status] += 1
    return summary


def matrix_payload() -> dict[str, Any]:
    rows = build_matrix_rows()
    return {
        "rows": rows,
        "summary": matrix_summary(rows),
        "connector_ids": [connector.id for connector in CONNECTOR_CATALOG],
        "allowed_connection_types": list(ALLOWED_CONN_TYPES),
        "source_resource_types": list(SOURCE_RESOURCE_TYPES),
        "database_analyzer_types": sorted(
            {_normalize_database_type(item) for item in SOURCE_UNDERSTANDING_CONNECTION_TYPES}
        ),
        "relational_analyzer_types": sorted({_normalize_database_type(item) for item in DATABASE_CONNECTION_TYPES}),
    }


def render_markdown() -> str:
    payload = matrix_payload()
    rows: list[MatrixRow] = payload["rows"]
    summary = payload["summary"]
    lines = [
        "# Unified Data Studio P0 Source Matrix",
        "",
        "> Generated by `server/scripts/generate_data_studio_p0_source_matrix.py` from the current connector catalog, connection type allowlist, source resource type allowlist, and database analyzer support. Do not edit this file by hand.",
        "",
        "## Generation Inputs",
        "",
        f"- Connector catalog entries: {len(payload['connector_ids'])} (`{_join(payload['connector_ids'])}`)",
        f"- Allowed connection types: `{_join(payload['allowed_connection_types'])}`",
        f"- SourceResource types: `{_join(payload['source_resource_types'])}`",
        f"- Database analyzer version: `{DATABASE_ANALYZER_VERSION}`",
        f"- Source Understanding analyzer types: `{_join(payload['database_analyzer_types'])}`",
        f"- Relational semantic-candidate analyzer types: `{_join(payload['relational_analyzer_types'])}`",
        "",
        "## Status Summary",
        "",
        "| ready | beta | planned | blocked | total |",
        "|---:|---:|---:|---:|---:|",
        f"| {summary['ready']} | {summary['beta']} | {summary['planned']} | {summary['blocked']} | {len(rows)} |",
        "",
        "## Modeling Mode Coverage",
        "",
        "| mode | current rows | coverage note |",
        "|---|---|---|",
        "| Structured Data Modeler | `sql_pg_mysql_sqlite_oracle_mssql`, `databricks` | Schema/profile, Source Understanding, semantic draft, publish/reload, and MCP metric preview exist for the listed beta rows. |",
        "| Tabular Projection Modeler | local CSV/Excel/Parquet/JSON/JSONL, Feishu Sheets/Base, TOS tabular objects, MongoDB/DynamoDB document profiles | Projection manifests, raw snapshots, field/profile evidence, and projected datasets exist for file/SaaS/object rows; NoSQL rows have source profile snapshots and require reviewed projection materialization. |",
        "| Context & Policy Modeler | local PDF/DOCX/PPTX, Web URL, Feishu Docs/Wiki, TOS context objects | Context evidence and lineage exist; OpenHuman-compatible extraction adapter provenance is not yet verified in runtime metadata. |",
        "| Blocked projection/modeling | none | Current matrix has no blocked rows; beta rows still list hardening gaps individually. |",
        "",
        "## OpenHuman Provenance",
        "",
        "- Fetched `OpenHuman Memory Source 抽取链路说明` from Lark document `BJr1dJ2n7ocNuJxPEtacjfiOnEd`, revision `4`, using `lark-cli docs +fetch --as user` on 2026-08-16.",
        "- Confirmed reference chain: source reader -> canonicalize -> raw document/archive -> chunk -> score/extract -> entity/relation extraction -> tree/summary.",
        "- Confirmed Composio/OAuth and workspace source are separate scheduling/dedup chains.",
        "- Fetched `OpenHuman 同类型竞品分析` from Lark document `KfMPd4ibMougsFxG1SJcsCbRnRg`, revision `5`; it states OpenHuman's open-source license as GPL-3.0.",
        "- Runtime adapter status: `UNVERIFIED`. This repo does not yet persist `algorithm_name`, `algorithm_version`, `config_digest`, `source_revision`, `confidence`, `evidence_locator`, `provenance`, and `warnings` from a verified OpenHuman implementation for semi-structured extraction.",
        "",
        "## Matrix",
        "",
        "| source_type | provider / adapter | availability | auth / config contract | browse / select / import contract | snapshot / raw artifact | parser / profile contract | modeling mode | fixture | API journey | UI journey | lineage / evidence | retry / revoke | final status | blocker reason |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                _cell(value)
                for value in (
                    row.source_type,
                    row.provider_adapter,
                    row.availability,
                    row.auth_config_contract,
                    row.browse_select_import_contract,
                    row.snapshot_raw_artifact,
                    row.parser_profile_contract,
                    row.modeling_mode,
                    row.fixture,
                    row.api_journey,
                    row.ui_journey,
                    row.lineage_evidence,
                    row.retry_revoke,
                    row.final_status,
                    row.blocker_reason,
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Current Gap Report",
            "",
            "- Local Parquet/JSON/JSONL now enter the governed `SourceResource` upload contract with snapshots, evidence, projected datasets, and projection manifests; nested/semi-structured JSON projection review remains beta hardening.",
            "- SQL Server now enters the structured Source Understanding path from cached/refreshable schema evidence; live-driver E2E credentials and dialect-specific profiling remain beta hardening.",
            "- MongoDB and DynamoDB now create Source Understanding profile snapshots and evidence with a `document_projection` handoff; reviewed projection materialization and semantic drafts remain beta hardening.",
            "- Planned catalog tiles are intentionally read-only roadmap entries until adapter, auth, picker, snapshot, parser/profile, fixture, and UI journey evidence exists.",
            "- Semi-structured context extraction records native KnowledgeProvider evidence today; OpenHuman algorithm version/license/source-code verification is not wired into runtime metadata.",
            "",
        ]
    )
    return "\n".join(lines)


def _join(values: list[str] | tuple[str, ...]) -> str:
    return "`, `".join(str(value) for value in values)


def _cell(value: Any) -> str:
    return str(value).replace("\n", "<br>").replace("|", "\\|")


def write_matrix(path: Path = OUTPUT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(), encoding="utf-8")


if __name__ == "__main__":
    write_matrix()
