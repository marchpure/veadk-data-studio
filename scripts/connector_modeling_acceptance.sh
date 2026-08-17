#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[acceptance] worktree: $ROOT"
echo "[acceptance] branch: $(git rev-parse --abbrev-ref HEAD)"
echo "[acceptance] head: $(git rev-parse HEAD)"
echo "[acceptance] merge-base with original baseline: $(git merge-base HEAD 290679967d4e823077861fbd9875c860d698b4b9)"
echo "[acceptance] merge-base with parallel baseline: $(git merge-base HEAD 13ed502b79d0e5f3b936af54316b2ab571e735a7)"

if [[ "$(git merge-base HEAD 290679967d4e823077861fbd9875c860d698b4b9)" != "290679967d4e823077861fbd9875c860d698b4b9" ]]; then
  echo "[acceptance] refusing branch that is not descended from original baseline 290679967d4e823077861fbd9875c860d698b4b9" >&2
  exit 2
fi

if [[ "$(git merge-base HEAD 13ed502b79d0e5f3b936af54316b2ab571e735a7)" != "13ed502b79d0e5f3b936af54316b2ab571e735a7" ]]; then
  echo "[acceptance] refusing branch that is not descended from parallel baseline 13ed502b79d0e5f3b936af54316b2ab571e735a7" >&2
  exit 2
fi

(
  cd server
  PYTHONPATH=..:tests uv run python scripts/generate_connector_modeling_acceptance.py --check
  PYTHONPATH=..:tests uv run pytest tests/test_data_studio_p0_source_matrix.py tests/test_connector_modeling_commercial_acceptance.py -q
  PYTHONPATH=..:tests uv run pytest \
    tests/test_source_connectors_api.py::test_connector_catalog_marks_only_real_connectors_available \
    tests/test_source_connectors_api.py::test_picker_import_sync_and_idempotency_use_source_connection_not_placeholder \
    tests/test_source_connectors_api.py::test_feishu_picker_import_syncs_real_resource_types_without_placeholder_state \
    tests/test_source_connectors_api.py::test_local_json_jsonl_source_upload_creates_governed_snapshot_evidence_and_projection \
    tests/test_source_connectors_api.py::test_local_parquet_source_upload_creates_governed_snapshot_evidence_and_projection \
    tests/test_source_connectors_api.py::test_projection_review_api_records_current_review_and_lineage \
    tests/test_source_connectors_api.py::test_tos_parser_contracts_cover_supported_formats_and_actionable_errors \
    tests/test_source_connectors_api.py::test_tos_object_sync_maps_large_missing_and_permission_errors \
    tests/test_source_connectors_api.py::test_feishu_refresh_failure_marks_connection_reauthorization_required \
    tests/test_source_connectors_api.py::test_source_connection_browse_requires_authorization_without_fake_empty_success \
    tests/test_source_connectors_api.py::test_tos_resource_listing_persists_picker_permission_failure -q
  PYTHONPATH=..:tests uv run pytest \
    tests/test_source_understanding_api.py::test_database_source_understanding_generates_profile_relationship_evidence_and_review \
    tests/test_source_understanding_api.py::test_verified_source_candidates_create_semantic_model_draft_with_lineage \
    tests/test_source_understanding_api.py::test_sqlite_source_understanding_creates_semantic_model_draft \
    tests/test_source_understanding_api.py::test_mssql_source_understanding_creates_snapshots_evidence_and_semantic_model_draft \
    tests/test_source_understanding_api.py::test_mongo_source_understanding_creates_profile_snapshots_without_semantic_candidates \
    tests/test_source_understanding_api.py::test_dynamodb_source_understanding_creates_profile_snapshots_without_semantic_candidates \
    tests/test_source_understanding_api.py::test_projected_dataset_source_understanding_creates_semantic_draft_with_projection_lineage \
    tests/test_semantic_modeling_api.py::test_data_models_validate_publish_and_query_metric_use_persisted_model \
    tests/test_semantic_modeling_api.py::test_publish_creates_immutable_version_and_query_uses_published_snapshot \
    tests/test_semantic_modeling_api.py::test_projected_dataset_semantic_model_publish_and_mcp_query -q
  PYTHONPATH=..:tests uv run pytest tests/test_databricks_connector.py tests/test_mongo_connector.py -q
)

git diff --check
git status --short --branch
