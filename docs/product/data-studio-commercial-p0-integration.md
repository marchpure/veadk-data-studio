# Data Studio Commercial P0 Integration

CURRENT_PHASE: Phase 3 — latest Connector/Modeling `142837f` and Dashboard `ef7ad32` are merged and locally verified on the unified branch. Next: close commercial gaps for Dashboard legacy 8080 path and Evaluation create/import/run fixture, then build the final commercial 8080 image.

## Immutable Inputs

| Stream | Branch | Input SHA | Status at capture |
| --- | --- | --- | --- |
| Connector / Modeling | `veadk-data-studio/agent/data-studio-p0` | `142837f7587dd1519d4287c1cb26c8e2840fc39a` | clean, pushed; documented `PARTIAL` / `8080_PARTIAL` |
| Dashboard | `veadk-data-studio/agent/dashboard-human-agent-p0` | `ef7ad32d031fcd5dea7102536720abd54b46ecdb` | clean, pushed; documented `DASHBOARD_BRANCH_READY_FOR_INTEGRATION / 8080_PENDING_INTEGRATION` |
| Evaluation / Sharing Governance | `veadk-data-studio/integration/evaluation-sharing-governance-p0` | `0c5b517381eedbc5c9a1181f82ab84d9965f2453` | clean, pushed; documented `RELEASE_READY` |

## Unified Branch

- Branch: `integration/data-studio-commercial-p0`
- Worktree: `/Users/bytedance/worktrees/byaan-commercial-integration-p0`
- Remote: `veadk-data-studio`
- Initial base: `0c5b517381eedbc5c9a1181f82ab84d9965f2453`
- Initial push: branch created and tracking `veadk-data-studio/integration/data-studio-commercial-p0`.

## Current 8080 Baseline

- Current URL: `http://127.0.0.1:8080`
- Current image: `byaan:selfhosted-governance-p0-2881367`
- Current container: `byaan-governance-p0-2881367-8080`
- Current `BYAAN_VERSION`: `governance-p0-2881367`
- Current migration: `add_canonical_sharing_model (head)`

This 8080 runtime is not the final commercial baseline. It predates the unified commercial branch and does not include latest Connector/Modeling `142837f` or Dashboard `ef7ad32`.

## Merge Plan

1. Merge latest Connector/Modeling input `142837f7587dd1519d4287c1cb26c8e2840fc39a`.
2. Merge latest Dashboard input `ef7ad32d031fcd5dea7102536720abd54b46ecdb`.
3. Preserve all Evaluation/Sharing Governance code and migrations from `0c5b517381eedbc5c9a1181f82ab84d9965f2453`.
4. Resolve shared files explicitly:
   - `server/main.py`
   - `server/models/__init__.py`
   - `server/auth/scopes.py`
   - `server/routers/folders.py`
   - `server/routers/exports.py`
   - `server/mcp/tools.py`
   - `server/mcp/tool_wrappers.py`
   - `server/tests/test_migration_chain_hardening.py`
   - `client/src/App.tsx`
   - `client/src/components/CollapsibleSidebar.tsx`
   - `client/src/services/api.ts`
   - `client/package.json`
   - `client/pnpm-lock.yaml`
5. Re-run migration, backend, frontend, browser, REST/MCP parity, and 8080 Release Gate from this branch. Historical outputs from the source branches are evidence inputs only, not final pass criteria.

## Known Starting Risks

- Connector/Modeling is intentionally not ready-complete: the source matrix records `0 ready / 14 beta / 26 planned / 0 blocked / 40 total`.
- The latest Dashboard branch includes post-governance browser/editor coverage commits that are not in the old Governance 8080 image.
- The merge must not let either source branch delete Evaluation/Sharing artifacts from the Governance branch.
- External credentials for several connector rows are unavailable; those rows must remain `beta` or `planned`, not be promoted to `ready`.

## 2026-08-17 03:18 CST - Connector / Modeling Merge

Merged input:

- `veadk-data-studio/agent/data-studio-p0`
- SHA: `142837f7587dd1519d4287c1cb26c8e2840fc39a`

Conflict resolution:

- `server/tests/test_migration_chain_hardening.py` was the only content conflict.
- Kept the commercial/governance final Alembic head assertion: `add_canonical_sharing_model`.
- Kept the Connector/Modeling migration chain assertion for `add_blocked_source_resource_status -> add_file_source_resource_type`.
- Preserved Dashboard, Evaluation, and Sharing migration lineage through `merge_ds_dash_20260816`, `add_evaluation_authoritative_model`, and `add_canonical_sharing_model`.

Evidence:

- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_migration_chain_hardening.py tests/test_data_studio_p0_source_matrix.py -q` -> `8 passed, 8 warnings`.
- `cd server && PYTHONPATH=..:tests uv run alembic heads` -> `add_canonical_sharing_model (head)`.
- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_source_connectors_api.py::test_source_connection_browse_requires_authorization_without_fake_empty_success tests/test_multi_source_artifacts_api.py::test_source_processing_step_schema_is_typed_contract tests/test_multi_source_artifacts_api.py::test_web_source_blocks_private_urls tests/test_sources_overview_api.py::test_sources_overview_maps_blocked_and_needs_confirmation_to_product_states tests/test_data_studio_p0_source_matrix.py -q` -> `7 passed, 9 warnings`.
- `cd server && uv run ruff check models/source_resources.py routers/source_connections.py schemas/source_resources.py schemas/source_overview.py services/source_connections.py services/source_overview.py services/source_resources.py tests/test_multi_source_artifacts_api.py tests/test_source_connectors_api.py tests/test_sources_overview_api.py tests/test_data_studio_p0_source_matrix.py migrations/versions/add_blocked_source_resource_status.py scripts/generate_data_studio_p0_source_matrix.py tests/test_migration_chain_hardening.py` -> passed with the existing removed-rule warning.

Commercial readiness note:

- Connector/Modeling remains `PARTIAL`, not ready-complete. The merged source matrix still reports `0 ready / 14 beta / 26 planned / 0 blocked / 40 total`.

## 2026-08-17 03:35 CST - Dashboard Merge

Merged input:

- `veadk-data-studio/agent/dashboard-human-agent-p0`
- SHA: `ef7ad32d031fcd5dea7102536720abd54b46ecdb`

Conflict resolution:

- `client/scripts/dashboard-workspace-smoke.mjs` was the only content conflict.
- Kept the newer Dashboard branch browser acceptance matrix for inventory, view, edit/review, stale/partial, permission-denied, and legacy scenes at `1440x900` and `390x844`.
- Preserved the commercial/governance notebook preview smoke route by returning `notebookId` from the fixture seed and capturing `notebook-preview-route-1440.png` before the governed Dashboard scene matrix.
- Alembic remained a single commercial/governance head after merge: `add_canonical_sharing_model (head)`.

Fixes during verification:

- `tests/test_dashboard_rest_api.py::test_dashboard_rest_query_matches_mcp_contract_for_same_principal` initially failed because its fake query used fixed `as_of=2026-08-16T12:34:56`; the Dashboard service correctly marked it stale under the current clock. The test fixture now uses a fresh runtime `as_of` so the assertion verifies REST/MCP parity without masking stale detection.
- Initial frontend `pnpm build:check` and `pnpm lint` failed because this new worktree had no `client/node_modules`. Ran `cd client && pnpm install --frozen-lockfile`; `client/node_modules` is ignored and not staged. Re-runs passed.

Evidence from unified branch:

- `cd server && PYTHONPATH=..:tests uv run alembic heads` -> `add_canonical_sharing_model (head)`.
- `node --check client/scripts/dashboard-workspace-smoke.mjs` -> passed.
- `git diff --check` -> passed.
- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_dashboard_contract_schemas.py tests/test_dashboard_execution_service.py tests/test_dashboard_lifecycle_service.py tests/test_dashboard_mcp_contract.py tests/test_dashboard_persistence_migration.py tests/test_dashboard_rest_api.py tests/test_dashboard_security_regressions.py tests/test_dashboard_legacy_tool_gating.py tests/test_migration_chain_hardening.py tests/test_data_studio_p0_source_matrix.py -q` -> `60 passed, 103 warnings`.
- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_source_connectors_api.py::test_source_connection_browse_requires_authorization_without_fake_empty_success tests/test_multi_source_artifacts_api.py::test_source_processing_step_schema_is_typed_contract tests/test_multi_source_artifacts_api.py::test_web_source_blocks_private_urls tests/test_sources_overview_api.py::test_sources_overview_maps_blocked_and_needs_confirmation_to_product_states tests/test_data_studio_p0_source_matrix.py -q` -> `7 passed, 9 warnings`.
- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_evaluation_contract_schemas.py tests/test_evaluation_persistence_migration.py tests/test_evaluation_service.py tests/test_evaluation_runner_service.py tests/test_evaluation_rest_api.py tests/test_evaluation_feedback_advisor_api.py tests/test_evaluation_mcp_contract.py -q` -> `22 passed, 18 warnings`.
- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_sharing_persistence_migration.py tests/test_sharing_canonical_service.py tests/test_sharing_read_surface.py -q` -> `8 passed, 9 warnings`.
- `cd server && uv run ruff check services/dashboard.py tests/test_dashboard_execution_service.py tests/test_dashboard_lifecycle_service.py tests/test_dashboard_rest_api.py` -> passed with the existing removed-rule warning.
- `cd client && pnpm build:check` -> passed with existing Browserslist, CSS minify, dynamic import, and chunk-size warnings.
- `cd client && pnpm lint` -> `357 problems (0 errors, 357 warnings)`.

Commercial readiness note:

- Dashboard latest code is now in the unified branch, including REST/MCP governed asset contracts, browser acceptance matrix, legacy backfill, structured data-view execution for `saved_query`, `semantic_metric`, and `context_search`, unresolved policy guards, and legacy HTML tool gating.
- This is still not final `READY`: the real `127.0.0.1:8080` container is still the old Governance image, and the commercial branch has not yet passed a final image Release Gate.
- The explicit legacy asset `6b388ea5-9586-41a2-8ab9-51fd580d71af` still must be verified against the final commercial 8080 image with Playwright before marking Dashboard 8080 ready.
- Evaluation APIs and UI surfaces are present and focused tests pass, but the final commercial gate still needs an explicit non-production fixture proving create/import/publish/run/failure/promotion blocking on the latest image.
