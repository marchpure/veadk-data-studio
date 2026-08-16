# Unified Data Studio P0 Acceptance Correction

This document records acceptance-gate corrections after the prior `8080_READY`
claim. It is intentionally evidence-first: each section names the command,
observed output, and current status.

## Final Readiness Status

- Overall status: `PARTIAL`
- 8080 status: `8080_PARTIAL`
- Matrix basis: `docs/product/data-studio-p0-source-matrix.md` reports `0 ready / 14 beta / 26 planned / 0 blocked / 40 total`.
- 8080 basis: restored strict E2E passed on isolated local port `18096`. The existing `8080` listener was not killed or occupied during this correction session; `lsof -nP -iTCP:8080 -sTCP:LISTEN` showed an existing `ssh` listener, so this run does not prove the restored gate against `8080`.
- OpenHuman basis: matrix provenance keeps runtime adapter status as `UNVERIFIED`; semi-structured context rows cannot be promoted to ready until verified runtime provenance is persisted.

The corrected state is not `8080_READY` because no source row is ready-complete
and the restored strict gate was not rerun against the existing `8080`
deployment.

## Correction Commits

| SHA | subject | status |
|---|---|---|
| `338deed` | `p0: narrow e2e abort and fetch exemptions` | pushed |
| `f868f9e` | `p0: document pre-existing connection encryption failure` | pushed |
| `4325978` | `p0: assert needs_authorization honest states` | pushed |

## Acceptance Evidence

### Restored strict projected-source E2E

- Command: `SCREEN_DIR=/Users/bytedance/.codex/data-studio-p0-evidence/data-studio-p0-18096-strict-e2e-rerun BASE_URL=http://127.0.0.1:18096 node client/scripts/data-studio-p0-projected-source-e2e.mjs`
- Evidence directory: `/Users/bytedance/.codex/data-studio-p0-evidence/data-studio-p0-18096-strict-e2e-rerun`
- Result: `ok=true`
- Counters: `pageerror=0`, `consoleError=0`, `requestfailed=0`, `http5xx=0`
- Exemptions: `ignoredAborts=[]`, `ignoredConsoleErrors=[]`, `navigationExemptionLimitExceeded=false`
- Screenshots:
  - `/Users/bytedance/.codex/data-studio-p0-evidence/data-studio-p0-18096-strict-e2e-rerun/01-source-detail-projection-1440.png`
  - `/Users/bytedance/.codex/data-studio-p0-evidence/data-studio-p0-18096-strict-e2e-rerun/02-data-models-home-1440.png`
  - `/Users/bytedance/.codex/data-studio-p0-evidence/data-studio-p0-18096-strict-e2e-rerun/03-explore-mcp-result-1440.png`
  - `/Users/bytedance/.codex/data-studio-p0-evidence/data-studio-p0-18096-strict-e2e-rerun/04-publish-mcp-console-1440.png`
  - `/Users/bytedance/.codex/data-studio-p0-evidence/data-studio-p0-18096-strict-e2e-rerun/05-reload-persistence-1440.png`
  - `/Users/bytedance/.codex/data-studio-p0-evidence/data-studio-p0-18096-strict-e2e-rerun/06-source-detail-mobile-390.png`
  - `/Users/bytedance/.codex/data-studio-p0-evidence/data-studio-p0-18096-strict-e2e-rerun/07-data-model-mobile-390.png`

### Honest state E2E

- Command: `SCREEN_DIR=/Users/bytedance/.codex/data-studio-p0-evidence/data-studio-p0-honest-states-20260816141308 BASE_URL=http://127.0.0.1:15174 node client/scripts/data-studio-p0-honest-states-e2e.mjs`
- Evidence directory: `/Users/bytedance/.codex/data-studio-p0-evidence/data-studio-p0-honest-states-20260816141308`
- Result: `ok=true`
- Counters: `pageerror=0`, `consoleError=0`, `requestfailed=0`, `http5xx=0`
- Expected browser console event: one expected 403 resource-load line for the `needs_authorization` API path, recorded as `expected-needs-authorization-api-403` and not counted as an unexpected console error.
- Screenshots:
  - `/Users/bytedance/.codex/data-studio-p0-evidence/data-studio-p0-honest-states-20260816141308/01-blocked-source-overview-1440.png`
  - `/Users/bytedance/.codex/data-studio-p0-evidence/data-studio-p0-honest-states-20260816141308/02-needs-authorization-picker-1440.png`
  - `/Users/bytedance/.codex/data-studio-p0-evidence/data-studio-p0-honest-states-20260816141308/03-blocked-source-overview-390.png`

Debug evidence directories from earlier failed honest-state attempts are not
acceptance evidence: `data-studio-p0-honest-states-20260816140817`,
`data-studio-p0-honest-states-20260816140944`, and
`data-studio-p0-honest-states-20260816141128`.

## Final Verification Commands

- Focused backend tests:
  `cd server && PYTHONPATH=..:tests uv run pytest tests/test_source_connectors_api.py::test_source_connection_browse_requires_authorization_without_fake_empty_success tests/test_multi_source_artifacts_api.py::test_source_processing_step_schema_is_typed_contract tests/test_multi_source_artifacts_api.py::test_web_source_blocks_private_urls tests/test_sources_overview_api.py::test_sources_overview_maps_blocked_and_needs_confirmation_to_product_states tests/test_data_studio_p0_source_matrix.py -q`
  Result: `7 passed, 9 warnings in 0.60s`.
- Migration/readiness regression tests:
  `cd server && PYTHONPATH=..:tests uv run pytest tests/test_migration_chain_hardening.py tests/test_data_studio_p0_source_matrix.py -q`
  Result: `8 passed, 8 warnings in 7.78s`.
- Backend ruff:
  `cd server && uv run ruff check models/source_resources.py routers/source_connections.py schemas/source_resources.py schemas/source_overview.py services/source_connections.py services/source_overview.py services/source_resources.py tests/test_multi_source_artifacts_api.py tests/test_source_connectors_api.py tests/test_sources_overview_api.py tests/test_data_studio_p0_source_matrix.py migrations/versions/add_blocked_source_resource_status.py scripts/generate_data_studio_p0_source_matrix.py tests/test_migration_chain_hardening.py`
  Result: `All checks passed!` with the existing removed-rule warning for `UP038`.
- Frontend lint:
  `cd client && pnpm lint`
  Result: `357 problems (0 errors, 357 warnings)`.
- Frontend build check:
  `cd client && pnpm build:check`
  Result: success; existing CSS minify warnings and chunk-size/dynamic-import warnings remain.
- Full backend tests:
  `cd server && PYTHONPATH=..:tests uv run pytest`
  Result: `1 failed, 894 passed, 2 skipped, 362 warnings in 63.09s`.
  Remaining failure is the pre-existing
  `tests/integration/test_connections_workflows.py::TestConnectionEncryptionWorkflow::test_connection_encryption_persistence_workflow`
  failure documented below.

## Beta To Ready Requirements

The source matrix remains the authoritative row-level inventory. In summary,
promoting any beta source to ready still requires real credentials or real
customer-like data, non-trivial profiling evidence, projection or extraction
evidence, and manual review appropriate to that source type:

- Local files: customer-scale fixtures, parser/profiling evidence, projection or extraction review, and hardening for large files and semi-structured edge cases.
- Web: crawler/page-group policy, public-site capture fixtures, richer table extraction, freshness/retry evidence, and compliance review.
- Feishu: live tenant OAuth credentials, real Docs/Wiki/Sheets/Base E2E, permission regression coverage, projection/extraction review, and verified OpenHuman-compatible runtime metadata for context extraction.
- Volcengine TOS: real credentials and objects, incremental sync/freshness proof, parser/profile coverage, projection or extraction review, and S3-compatible vendor normalization where applicable.
- SQL and warehouses: live-driver or live-OAuth credentials, real schema/profile E2E per dialect/provider, deeper dialect profiling, and reviewed semantic draft quality.
- MongoDB and DynamoDB: real credentials/data, nested/key/index profiling evidence, reviewed tabular projection materialization, and semantic draft handoff after review.

## Known Pre-existing Failures

### Connection encryption persistence workflow

- Test: `tests/integration/test_connections_workflows.py::TestConnectionEncryptionWorkflow::test_connection_encryption_persistence_workflow`
- Error summary: `TypeError: 'NoneType' object is not subscriptable` at `assert decrypted["password"] == "SuperSecret123!@#"`
- Current status: pre-existing known failure, not introduced by `agent/data-studio-p0`
- Owner / next step: connection credential encryption owner should investigate tenant-context/session key selection for `Connection.get_decrypted_connection_obj`. This correction session does not repair it because the fix touches credential encryption behavior rather than the Data Studio acceptance gate itself.

Base-SHA reproduction:

```bash
git worktree add --detach /Users/bytedance/worktrees/byaan-data-studio-p0-base86 86fbace663a68dff40d1a2e8713056d4599b60d8
cd /Users/bytedance/worktrees/byaan-data-studio-p0-base86/server
UV_HTTP_TIMEOUT=300 PYTHONPATH=..:tests uv run pytest tests/integration/test_connections_workflows.py::TestConnectionEncryptionWorkflow::test_connection_encryption_persistence_workflow -q
```

Observed base-SHA output:

```text
FAILED tests/integration/test_connections_workflows.py::TestConnectionEncryptionWorkflow::test_connection_encryption_persistence_workflow
tests/integration/test_connections_workflows.py:235: in test_connection_encryption_persistence_workflow
    assert decrypted["password"] == "SuperSecret123!@#"
           ^^^^^^^^^^^^^^^^^^^^^
E   TypeError: 'NoneType' object is not subscriptable
1 failed, 9 warnings in 0.43s
```

Current-HEAD reproduction:

```bash
cd /Users/bytedance/worktrees/byaan-data-studio-p0/server
PYTHONPATH=..:tests uv run pytest tests/integration/test_connections_workflows.py::TestConnectionEncryptionWorkflow::test_connection_encryption_persistence_workflow -q
```

Observed current-HEAD output:

```text
FAILED tests/integration/test_connections_workflows.py::TestConnectionEncryptionWorkflow::test_connection_encryption_persistence_workflow
tests/integration/test_connections_workflows.py:235: in test_connection_encryption_persistence_workflow
    assert decrypted["password"] == "SuperSecret123!@#"
           ^^^^^^^^^^^^^^^^^^^^^
E   TypeError: 'NoneType' object is not subscriptable
1 failed, 9 warnings in 0.48s
```

Pre-existing basis: the same assertion failure reproduces at base SHA
`86fbace663a68dff40d1a2e8713056d4599b60d8`, before the
`agent/data-studio-p0` commits.
