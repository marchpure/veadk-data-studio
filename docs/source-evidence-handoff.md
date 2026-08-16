# Source & Evidence handoff

Status:

- **CODE COMPLETE:** yes for the local Source/Evidence contract slice.
- **CONTRACT E2E COMPLETE:** yes for repeatable local Feishu Sheet and TOS fake provider fixtures.
- **REAL E2E BLOCKED:** yes; controlled non-production Feishu/TOS credentials and resources are not present in this environment.
- **DEPLOYMENT PENDING:** yes; no deployment/merge is claimed from this branch.

This branch contains an independently mergeable Source & Evidence vertical slice for Web, Feishu Sheet/Base-style table resources, and Volcengine TOS object resources. It does not claim production completion because real Feishu/TOS credential E2E has not been proven in this environment.

## 1. Branch, worktree, HEAD

- Worktree: `/Users/bytedance/byaan-team-source-evidence`
- Branch: `feature/team-source-evidence-v2`
- Implementation base HEAD: `09f3f241f77ac3d16b9eb501f0291d85be2a6299`
- Contract implementation commit: `5d2c59ab736a46a7fe6c719e82a8c030eb37ac54`
- Final branch tip: use the remote branch ref; the delivery owner reports the verified SHA after pushing this handoff.
- Worktree status before this update: clean.
- Shared worktree: `/Users/bytedance/byaan`
- Shared worktree status at latest check: dirty on `integration/team-semantic-modeling` with Integration Owner collaboration/migration files; no development continued there.

## 2. Isolated domain files

Primary changed areas:

- `server/services/source_resources.py`
- `server/services/source_connectors.py`
- `server/services/source_redaction.py`
- `server/services/source_connections.py`
- `server/services/knowledge_provider.py`
- `server/services/web_source_adapter.py`
- `server/routers/source_resources.py`
- `server/routers/source_connections.py`
- `server/routers/datasources.py`
- `server/schemas/source_resources.py`
- `server/tests/test_web_source_adapter.py`
- `server/tests/test_multi_source_artifacts_api.py`
- `server/tests/test_source_connectors_api.py`
- `server/tests/test_source_evidence_contract_fixtures.py`
- `server/tests/test_real_source_connector_e2e.py`
- `docs/source-evidence-real-e2e-runbook.md`
- `docs/source-evidence-migration-proposal.md`
- `docs/source-evidence-handoff.md`

No public migration files are part of this handoff slice.

## 3. Cherry-pick sequence

The Source/Evidence core is already present on `integration/team-semantic-modeling` as equivalent commits. If replay is needed on another branch, apply these Source/Evidence commits in order, then this handoff doc commit:

```bash
git cherry-pick 0646d15
git cherry-pick 1dded0e
git cherry-pick d434f0c
git cherry-pick d869227
git cherry-pick 3c9d964
git cherry-pick fb6172a
git cherry-pick 32d64bc
git cherry-pick 87492c9
git cherry-pick 50d48e4
git cherry-pick 1d3ae11
git cherry-pick 8111867
git cherry-pick 6a4e5c0
git cherry-pick 93f9a3d
git cherry-pick 3b5a7d5
git cherry-pick dba6e10
git cherry-pick fc02b3c
git cherry-pick 6bf340e
git cherry-pick d974bc2
```

Do **not** cherry-pick `017ad9d` as part of this Source/Evidence handoff. It crosses into Agent Asset Discovery, unified agent tools, and Analysis Artifact runtime contracts. That work has been split to:

- Branch: `feature/agent-asset-discovery-contract`
- Worktree used for split: `/private/tmp/byaan-agent-asset-discovery-contract-20260815`
- Commit: `57e69b505103f893b5d8088eea6e19463824f24f` (`Add agent asset discovery contract`)

Integration Owner review points for that separate branch:

- whether it duplicates or should replace existing `search_datasets`
- whether Asset should become a formal public abstraction
- whether Dataset, Semantic Model, and Knowledge Resource permissions are consistent in search/describe
- whether `describe_asset` can expose evidence the caller should not see
- whether agent discovery is strictly read-only and cannot trigger sync/query execution
- whether Analysis Artifact dependency preflight belongs in the same change

## 4. Source → Snapshot → Evidence → Dataset journey

### Web

1. `POST /api/source-resources` with `resource_type=web` and a public URL.
2. `WebSourceAdapter` validates URL, DNS/IP, redirect targets, MIME, size, and timeout constraints.
3. A `SourceSnapshot` is created with canonical URL, final URL, redirect chain, ETag/Last-Modified where present, parser version, raw size, content hash, and captured time.
4. `NativeKnowledgeProvider` indexes extracted text into `KnowledgeResource` and `EvidenceFragment`.
5. Manual `POST /api/source-resources/{id}/sync` records a SyncRun and reuses identical snapshots.

### Feishu Sheet/Base

1. `SourceConnection` stores OAuth connection state; resource selection goes through picker/listing contracts.
2. Imported `feishu_sheet` and `feishu_base` resources create `SourceSnapshot`, `KnowledgeResource`, `EvidenceFragment`, and a normalized Dataset projection.
3. Sheet projection keeps a redacted spreadsheet ref, sheet id, range, row mappings, column mappings, cell mappings, and coordinate system.
4. Base projection keeps a redacted app ref, table id, view id, field mappings, and record row mappings.

### TOS object

1. `SourceConnection` stores encrypted access-key credentials.
2. Picker lists bucket/prefix/object resources; object import creates snapshot and evidence.
3. CSV/XLSX/XLSM/JSON/JSONL/Parquet objects can project to normalized Dataset.
4. Projection manifest keeps redacted bucket/key refs, version id, ETag, last_modified, file checksum, and source snapshot id.

## 5. Supported and deferred resources

Supported in this slice:

- Web: public HTTP/HTTPS pages with static HTML/text content.
- Feishu: Doc/Wiki locator contracts; Sheet and Base table projection contracts.
- TOS: CSV, XLSX, XLSM, JSON, JSONL, Parquet for Dataset projection; TXT/MD/HTML/DOCX/PDF basic parse for knowledge/evidence where applicable.
- PDF: local upload snapshot and basic text extraction fallback.

Deferred / not claimed complete:

- Real Feishu OAuth browser flow E2E in this environment.
- Real TOS bucket/object E2E in this environment.
- Docling/OCR/layout PDF parsing. Current PDF fallback marks `pdf_parser_deferred` when text extraction fails and does not claim full PDF evidence completion.
- Versioned asset dependency tables. MVP stores dependency data in JSON fields; formal schema is proposed separately.

## 6. Reliability evidence

- Same-content sync reuses existing snapshots.
- Content update creates a new `SourceSnapshot`; same-content sync remains idempotent.
- Connector sync failures preserve previous successful snapshot.
- Dataset projection failures do not publish a new latest snapshot and do not orphan created Dataset/File records.
- Web sync failures now record failed SyncRun and preserve previous snapshot.
- Dataset projection failure deletes created Dataset/File records and reports `dataset_projection_failed`.
- Source delete writes a tombstone SourceSnapshot and hides removed resources from list APIs.
- Authorization/connection stale states surface as `reauthorization_required` or disconnected status instead of continuing to show ready.
- Feishu/TOS authorization failure, missing resource, permission loss, timeout, rate limit, revoked grant, and token-expired contract cases are covered by local fake provider tests.
- SyncRun status contract is `queued/running/succeeded/failed/partial/cancelled`.
- Feishu Sheet/Base and TOS connector evidence text is stored as a content ref; locators, projection manifests, raw storage URIs, snapshot metadata, and sync errors use redacted refs instead of tokens, full URLs, bucket names, object keys, app secrets, access tokens, refresh tokens, or TOS keys.

## 7. Evidence locator matrix

| Source type | Locator fields covered |
| --- | --- |
| Common | `source_connection_id`, `source_resource_id`, `source_snapshot_id`, `external_revision`, `content_hash`, `parser_version`, `captured_at` |
| Web | `source_url`, `final_url`, `selector`, `text_range.chunk` |
| Feishu Doc/Wiki | `document_token`, `wiki_token`, `block_id`, `revision`, `heading_path`, `original_url` |
| Feishu Sheet | `spreadsheet_ref`, `sheet_id`, `range`, `cell_range`; Dataset manifest includes row/column/cell mappings |
| Feishu Base | `app_ref`, `table_id`, `view_id`, `record_id`, `field_id`; Dataset manifest includes field/record mappings |
| TOS object | `bucket_ref`, `key_ref`, `version_id`, `etag`, `last_modified`; Dataset manifest includes source locator |
| PDF | `page`, `bbox`, `pdf_parser_deferred` |

## 8. Migration proposal

See `docs/source-evidence-migration-proposal.md`.

The implementation intentionally avoids public migrations. Recommended future schema work:

- `source_sync_runs`
- tombstone/removed status formalization
- versioned projection lineage / asset dependencies
- evidence locator schema enforcement

## 9. Tests

Target local validation:

```bash
/Users/bytedance/byaan/.venv/bin/python -m pytest \
  server/tests/test_web_source_adapter.py \
  server/tests/test_multi_source_artifacts_api.py \
  server/tests/test_source_connectors_api.py \
  server/tests/test_source_evidence_contract_fixtures.py \
  server/tests/test_real_source_connector_e2e.py \
  -q -rs
```

Observed result:

```text
48 passed.
2 skipped because real Feishu/TOS credentials/resources are missing.
```

Do not count skipped real E2E tests as passed completion evidence.

Static checks:

```bash
/Users/bytedance/byaan/.venv/bin/python -m ruff check \
  server/services/source_resources.py \
  server/services/knowledge_provider.py \
  server/services/source_connections.py \
  server/services/source_redaction.py \
  server/services/source_connectors.py \
  server/services/web_source_adapter.py \
  server/routers/source_resources.py \
  server/routers/datasources.py \
  server/schemas/source_resources.py \
  server/tests/test_source_connectors_api.py \
  server/tests/test_source_evidence_contract_fixtures.py \
  server/tests/test_multi_source_artifacts_api.py \
  server/tests/test_web_source_adapter.py \
  server/tests/test_real_source_connector_e2e.py

git diff --check
```

Observed result:

```text
ruff: all checks passed
git diff --check: passed
```

No frontend files were changed in this slice, so frontend typecheck/build was not run.

## 10. Real credential E2E blocker

Real E2E tests are available but skipped without full credentials/resources:

```bash
/Users/bytedance/byaan/.venv/bin/python -m pytest server/tests/test_real_source_connector_e2e.py -q -rs
```

Required for TOS:

- `BYAAN_REAL_TOS_ENDPOINT`
- `BYAAN_REAL_TOS_REGION`
- `BYAAN_REAL_TOS_ACCESS_KEY_ID`
- `BYAAN_REAL_TOS_SECRET_ACCESS_KEY`
- `BYAAN_REAL_TOS_BUCKET`
- `BYAAN_REAL_TOS_OBJECT_KEY`

Required for Feishu Sheet:

- `BYAAN_REAL_FEISHU_ACCESS_TOKEN`
- `BYAAN_REAL_FEISHU_SPREADSHEET_TOKEN`
- `BYAAN_REAL_FEISHU_SHEET_ID`
- `BYAAN_REAL_FEISHU_RANGE`

Do not write credential values to git, logs, or handoff notes.

See `docs/source-evidence-real-e2e-runbook.md` for permissions, resource preparation, commands, expected results, cleanup, and rollback.

Current status remains **REAL E2E BLOCKED** until these real tests pass against explicitly authorized controlled Feishu/TOS resources. After real E2E passes, create a separate completion audit commit/report for Integration Owner review.
