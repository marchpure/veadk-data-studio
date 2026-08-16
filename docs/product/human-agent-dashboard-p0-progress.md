# Human + Agent Dashboard P0 Progress

Branch: `agent/dashboard-human-agent-p0`
Worktree: `/Users/bytedance/worktrees/byaan-dashboard-p0`
Remote: `veadk-data-studio`
Upstream: `veadk-data-studio/agent/dashboard-human-agent-p0`
Base SHA: `24c6b69a1f816a831ee6ce94d8515817b4752913`
Integration source to observe only: `veadk-data-studio/agent/data-studio-p0`

## Baseline Self-Check

Executed on 2026-08-16 before edits:

| Command | Result |
| --- | --- |
| `pwd` | `/Users/bytedance/worktrees/byaan-dashboard-p0` |
| `git status --short --branch` | `## agent/dashboard-human-agent-p0...veadk-data-studio/agent/dashboard-human-agent-p0` |
| `git branch --show-current` | `agent/dashboard-human-agent-p0` |
| `git rev-parse HEAD` | `24c6b69a1f816a831ee6ce94d8515817b4752913` |
| `git rev-parse '@{upstream}'` | `24c6b69a1f816a831ee6ce94d8515817b4752913` |
| `git log -5 --oneline --decorate` | `24c6b69 data-studio: add nosql source profile snapshots`; `e2effcf data-studio: enable mssql source understanding`; `80b3bda data-studio: support local parquet json sources`; `230c89c data-studio: add source matrix audit`; `86fbace Type source processing step contract` |
| `git remote -v` | `origin=https://github.com/byaan-ai/byaan.git`; `veadk-data-studio=https://github.com/marchpure/veadk-data-studio.git` |

Result: baseline matches required worktree, branch, upstream, and start SHA. Worktree was clean.

## Phase Ledger

### Phase 0: Current-State Audit

Status: first audit and viewer query-binding regression/fix slices complete.

Allowlist for first slice:

- `docs/product/human-agent-dashboard-p0.md`
- `docs/product/human-agent-dashboard-p0-progress.md`
- `server/tests/test_dashboard_security_regressions.py`

Shared files: none.

Current-state audit summary:

- Legacy Dashboard persistence is `dashboards` HTML rows keyed by notebook/version, without stable asset, manifest, lifecycle, validation, ETag, actor metadata, or immutable published state.
- Folder/dashboard sharing stores dashboard version IDs in `folder_dashboards` and grants viewer access through folder membership/public folders.
- Viewer Dashboard batch and preflight endpoints check dashboard access, then trust caller-supplied saved query IDs.
- Query execution service runs saved query IDs directly and does not accept a dashboard/version binding context.
- Dashboard cache refresh enumerates all queries for the notebook and records per-query cache freshness, not a canonical DashboardRun.
- MCP Dashboard tools are HTML edit tools and filter/saved-query helpers; there are no governed Dashboard asset/state/query/explain MCP tools yet.
- Frontend Dashboard is iframe/HTML-first with URL rewriting and injected viewer config; no structured manifest/run renderer exists yet.

Initial security regression coverage:

- Added strict xfail for viewer batch execution with a caller-supplied query ID that is not proven bound to the dashboard. This reproduces the current missing boundary without breaking the Phase 0 audit commit.
- Next security slice must remove the xfail by enforcing dashboard/notebook/tenant query binding before calling `QueryService`.

Tests:

- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_dashboard_security_regressions.py` -> passed with `1 xfailed` in 0.18s. The xfail is strict and records the current arbitrary-query-ID boundary before the fix slice.
- `cd server && uv run ruff check tests/test_dashboard_security_regressions.py` -> passed.

Commit:

- `4a4f4e1` `dashboard: audit human agent contract`

Migration head:

- No migration added in Phase 0 first slice.

Risks and dependencies:

- Existing viewer batch/preflight routes now reject saved query IDs that are not bound to the selected dashboard notebook and tenant. Remaining Phase 2 work must replace raw query-ID execution with structured manifest `data_view_id` execution and add share revocation/RLS/column-policy coverage.
- Existing share `is_snapshot` flags are not backed by immutable DashboardRun/result artifacts.
- Semantic model published versions exist, but Dashboard does not pin them.
- Integration Gate will need to reconcile shared route/model registration and any Alembic heads after later phases.

### Phase 2 Security Slice: Viewer Batch Query Binding

Status: implemented before broader schema work because it closes the prompt's mandatory safety boundary.

Allowlist:

- `server/routers/folders.py` - conditional shared file; additive binding check only for viewer dashboard batch/preflight routes.
- `server/tests/test_dashboard_security_regressions.py`
- `docs/product/human-agent-dashboard-p0-progress.md`

Behavior:

- Viewer dashboard batch execution and preflight resolve the selected dashboard, collect query IDs from `query_ids` or `queries_with_filters`, and reject any query not in the same dashboard notebook and tenant before calling `QueryService`.
- Rejection uses `403` with a generic dashboard-scoped message so cross-tenant or unbound query object names are not leaked.
- This keeps legacy compatibility shape while blocking arbitrary query-ID execution. It is not the final structured manifest/data-view execution contract.

Tests:

- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_dashboard_security_regressions.py` -> passed, `5 passed`.
- `cd server && uv run ruff check routers/folders.py tests/test_dashboard_security_regressions.py` -> passed.
- `git diff --check` -> passed.

Commit:

- `033b526` `dashboard: enforce viewer query binding`

### Phase 1 Schema Slice: Manifest And Run Contracts

Status: implemented.

Allowlist:

- `server/schemas/dashboard.py`
- `server/tests/test_dashboard_contract_schemas.py`
- `docs/product/human-agent-dashboard-p0-progress.md`

Behavior:

- Added strict Pydantic contracts for `dashboard.manifest.v1` and `dashboard.run.v1`.
- Manifest requires the product-mandated top-level sections and validates stable data-view/tile/filter references.
- Data views require exactly one matching binding for `semantic_metric`, `saved_query`, or `context_search`.
- Semantic bindings must pin published model versions.
- `pinned_snapshot` runs require immutable result artifact IDs for successful views.

Tests:

- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_dashboard_contract_schemas.py` -> passed, `7 passed`.
- `cd server && uv run ruff check schemas/dashboard.py tests/test_dashboard_contract_schemas.py` -> passed.
- `git diff --check` -> passed.

Commit:

- `be5e4a7` `dashboard: add manifest run schemas`

### Phase 1 Persistence Slice: Asset, Version Metadata, Run, Audit Tables

Status: implemented.

Allowlist:

- `server/models/dashboard.py`
- `server/models/__init__.py` - conditional shared model registration; additive imports only.
- `server/migrations/versions/add_governed_dashboard_assets.py`
- `server/tests/test_dashboard_persistence_migration.py`
- `server/tests/test_migration_chain_hardening.py`
- `docs/product/human-agent-dashboard-p0-progress.md`

Behavior:

- Added `DashboardAsset`, `DashboardRun`, and `DashboardAuditEvent` ORM models.
- Existing `dashboards` rows remain the version table and keep `html_content`; new metadata columns are additive and nullable/defaulted for legacy compatibility.
- Migration creates stable asset/run/audit tables and version metadata columns without deleting legacy data.
- Migration head is now `add_governed_dashboard_assets`, extending the current worktree head `add_file_source_resource_type`.

Tests:

- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_dashboard_persistence_migration.py tests/test_migration_chain_hardening.py` -> passed, `6 passed`.
- `cd server && uv run ruff check models/dashboard.py models/__init__.py migrations/versions/add_governed_dashboard_assets.py tests/test_dashboard_persistence_migration.py tests/test_migration_chain_hardening.py` -> passed.
- `cd server && uv run alembic heads` -> `add_governed_dashboard_assets (head)`.
- `git diff --check` -> passed.

Commit:

- `ad4f6f3` `dashboard: persist governed asset foundation`

### Phase 1 Lifecycle Slice: Validation, ETag, Publish Primitives

Status: implemented.

Allowlist:

- `server/repositories/dashboard.py`
- `server/services/dashboard.py`
- `server/tests/test_dashboard_lifecycle_service.py`
- `docs/product/human-agent-dashboard-p0-progress.md`

Behavior:

- Added `DashboardService` as the shared lifecycle entry point for later REST/MCP wrappers.
- Supports strict manifest validation, stable canonical digests, structured draft creation, ETag conflict rejection, draft patching as new version rows, validation summaries, immutable publish state, pinned model/source extraction, and audit events.
- Keeps legacy HTML/version rows intact. P0 structured draft creation currently requires `notebook_id` to satisfy the existing non-null version relation; notebookless assets remain a later migration/service extension.

Tests:

- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_dashboard_lifecycle_service.py` -> passed, `3 passed`.
- `cd server && uv run ruff check repositories/dashboard.py services/dashboard.py tests/test_dashboard_lifecycle_service.py` -> passed.
- `git diff --check` -> passed.

Commit:

- `da3b2d2` `dashboard: add lifecycle service primitives`

### Phase 2 Execution Slice: Manifest-Bound DashboardRun Query

Status: implemented initially for governed `saved_query` compatibility views; post-handoff audit extended execution to `semantic_metric` and `context_search`.

Allowlist:

- `server/services/dashboard.py`
- `server/tests/test_dashboard_execution_service.py`
- `docs/product/human-agent-dashboard-p0-progress.md`

Behavior:

- Added `DashboardService.query_dashboard` as the canonical execution entry point for later REST/MCP wrappers.
- Query accepts `data_view_ids`, not arbitrary query IDs; the service resolves selected views from the published manifest.
- Initial slice supported reviewed `saved_query` compatibility binding; later completion-audit slice `e564dae` executes published semantic-model `semantic_metric` and provider-neutral evidence `context_search` views through governed service bindings.
- Persists `DashboardRun` with filter digest, pinned versions, execution plan digest, cache/stale/as_of, warnings/errors, and audit event.
- `pinned_snapshot` requests are honestly blocked until immutable result artifacts exist.

Tests:

- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_dashboard_execution_service.py` -> passed, `3 passed`.
- `cd server && uv run ruff check services/dashboard.py tests/test_dashboard_execution_service.py` -> passed.
- `git diff --check` -> passed.

Commit:

- `0d05215` `dashboard: bind dashboard run execution`

### Phase 3 REST Slice: Governed Dashboard Asset API

Status: implemented.

Allowlist:

- `server/routers/dashboard.py`
- `server/main.py` - conditional shared API registration; additive import and router include only.
- `server/repositories/dashboard.py` - conditional shared repository file; additive asset version/audit read helpers for REST state, version, lineage, and audit endpoints.
- `server/auth/scopes.py` - conditional shared auth file; additive governed Dashboard create/edit/publish/query scopes so REST mutations do not reuse unrelated permissions.
- `server/tests/test_dashboard_rest_api.py`
- `docs/product/human-agent-dashboard-p0-progress.md`

Behavior:

- Added `/api/dashboard-assets` REST endpoints for list, create draft, get asset, get version, patch draft, validate, publish, query, state, lineage, and audit.
- REST delegates lifecycle and execution behavior to `DashboardService` and accepts `data_view_ids` for query execution, not raw saved query IDs.
- Create and patch verify the bound notebook belongs to the active tenant and follows existing own-notebook access rules.
- Governed asset REST endpoints reject viewer-role access in this slice; legacy shared viewer access remains through existing folder/viewer routes until governed share policy is wired.
- Added explicit role scopes for dashboard create/edit/publish/query. Owners/admins can publish; members can create/edit/query/read; viewers remain on viewer-specific routes.

Tests:

- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_dashboard_rest_api.py` -> passed, `2 passed`.
- `cd server && uv run ruff check routers/dashboard.py main.py repositories/dashboard.py auth/scopes.py tests/test_dashboard_rest_api.py` -> passed.
- `git diff --check` -> passed.

Commit:

- `4de07e7` `dashboard: expose dashboard rest contract`

### Phase 3 MCP Slice: Governed Dashboard Tool Contract

Status: implemented.

Allowlist:

- `server/mcp/tool_wrappers.py` - conditional shared MCP wrapper file; additive governed Dashboard wrappers and scope checks over `DashboardService`.
- `server/mcp/tools.py` - conditional shared MCP registration file; additive governed Dashboard tool registrations only.
- `server/services/dashboard.py` - shared service file; additive JSON Patch and preview primitives so REST/MCP do not duplicate lifecycle/execution logic.
- `server/routers/dashboard.py` - shared REST file; additive preview endpoint and JSON Patch draft support to keep REST/MCP contract parity.
- `server/tests/test_dashboard_mcp_contract.py`
- `docs/product/human-agent-dashboard-p0-progress.md`

Behavior:

- Added MCP tools for `search_dashboards`, `describe_dashboard`, `get_dashboard_state`, `query_dashboard`, `explain_dashboard_tile`, `get_dashboard_lineage`, `create_dashboard_draft`, `patch_dashboard_draft`, `validate_dashboard`, `preview_dashboard`, and `publish_dashboard`.
- MCP wrappers resolve an explicit tenant/user principal, enforce dashboard read/query/create/edit/publish scopes from tenant role, and call the shared `DashboardService`.
- MCP query accepts `data_view_ids` and validated filters, never raw saved query IDs, and returns compact bounded run JSON with pagination metadata.
- Added shared allowlisted JSON Patch support for draft edits with ETag conflict handling; REST draft patch now accepts JSON Patch as well as full manifest compatibility.
- Added shared draft preview support through `DashboardService.preview_dashboard`; REST exposes `/api/dashboard-assets/{id}/preview`.
- Publish through MCP requires `dashboard.publish`; member principals can create/edit/query but cannot publish.

Tests:

- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_dashboard_rest_api.py tests/test_dashboard_mcp_contract.py tests/test_dashboard_lifecycle_service.py` -> passed, `7 passed`.
- `cd server && uv run ruff check services/dashboard.py routers/dashboard.py mcp/tool_wrappers.py mcp/tools.py tests/test_dashboard_mcp_contract.py tests/test_dashboard_rest_api.py tests/test_dashboard_lifecycle_service.py` -> passed.
- `git diff --check` -> passed.

Commit:

- `c3e28b1` `dashboard: expose dashboard mcp contract`

### Phase 4 Human Workspace Slice: Inventory, View, Data, Lineage

Status: implemented for the first human workspace vertical slice.

Allowlist:

- `client/src/features/dashboard/pages/DashboardWorkspacePage.tsx`
- `client/src/services/dashboard.ts`
- `client/src/types/dashboard.ts`
- `client/src/App.tsx` - conditional shared route registration for `/dashboard-assets`.
- `client/src/components/CollapsibleSidebar.tsx` - conditional shared navigation registration for governed Dashboards.
- `client/src/constants/scopes.ts` - conditional shared scope constants for governed Dashboard read/query/create/edit/publish separation.
- `docs/product/human-agent-dashboard-p0-progress.md`

Behavior:

- Added a governed Dashboard workspace under the existing React app routes, with inventory, selected asset/version detail, manifest filters, review state, validation entry point, reload, and draft title JSON Patch.
- Added a structured renderer that consumes `dashboard.manifest.v1` and `dashboard.run.v1` types from the REST Dashboard asset contract, including canonical `data_view_id` execution.
- Added Dashboard/Data/Lineage tabs with tile state rendering, accessible table equivalents, freshness/filter/content hash signals, pinned model/source versions, lineage locators, and evidence locators.
- Added a dashboard-specific frontend REST client that preserves existing hosted/Tauri backend resolution, auth token use, active tenant header, and `/api/dashboard-assets` contract boundaries.
- This slice does not yet complete the full edit/review/publish/reload semantic diff, share/export compatibility, or browser screenshot acceptance gates; those remain Phase 4 follow-up slices.

Tests:

- `cd client && pnpm build:check` -> passed.
- `cd client && pnpm lint` -> passed with warnings only from existing frontend lint debt.
- `git diff --check` -> passed.

Commit:

- `33130f5` `dashboard: render structured dashboard workspace`

### Phase 4 Workflow Slice: Review, Preview, Publish, Reload Draft

Status: implemented.

Allowlist:

- `server/services/dashboard.py` - shared DashboardService lifecycle addition for governed reload draft creation and semantic diff metadata.
- `server/routers/dashboard.py` - REST contract addition for `/api/dashboard-assets/{id}/reload`.
- `server/tests/test_dashboard_rest_api.py`
- `client/src/features/dashboard/pages/DashboardWorkspacePage.tsx`
- `client/src/services/dashboard.ts`
- `client/src/types/dashboard.ts`
- `docs/product/human-agent-dashboard-p0-progress.md`

Behavior:

- Added governed reload draft creation that requires current ETag, preserves the published immutable version, creates a new draft from the published manifest, stores semantic/source diff metadata, marks the asset `in_review`, and audits `dashboard.reload`.
- Added REST `/api/dashboard-assets/{id}/reload` behind `dashboard.edit` scope and notebook access checks.
- Extended the human workspace to switch versions, run published versions, preview draft versions, validate, patch title through JSON Patch, create reload review drafts, publish blocker-free drafts, and show semantic diff plus recent audit events.
- Frontend calls remain bounded to the existing `/api/dashboard-assets` contract and still consume canonical `dashboard.manifest.v1` / `dashboard.run.v1`.
- This slice does not yet implement share/export compatibility or browser screenshot acceptance.

Tests:

- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_dashboard_rest_api.py tests/test_dashboard_lifecycle_service.py` -> passed, `5 passed`.
- `cd server && uv run ruff check services/dashboard.py routers/dashboard.py tests/test_dashboard_rest_api.py` -> passed.
- `cd client && pnpm build:check` -> passed.
- `cd client && pnpm lint` -> passed with warnings only from existing frontend lint debt.
- `git diff --check` -> passed.

Commit:

- `d9ac360` `dashboard: add review reload workflow`

### Phase 4 Compatibility Slice: Share, Export, Legacy Fallback

Status: implemented.

Allowlist:

- `server/services/dashboard.py` - shared DashboardService export helper and deterministic structured HTML renderer.
- `server/routers/dashboard.py` - REST export endpoint for governed Dashboard assets.
- `server/tests/test_dashboard_rest_api.py`
- `client/src/features/dashboard/pages/DashboardWorkspacePage.tsx`
- `client/src/services/dashboard.ts`
- `client/src/types/dashboard.ts`
- `docs/product/human-agent-dashboard-p0-progress.md`

Behavior:

- Added `/api/dashboard-assets/{id}/export/html` with `dashboard.export` scope, published-version enforcement, audit, deterministic manifest-based structured HTML export, and preserved legacy HTML fallback for unstructured versions.
- Extended REST coverage to assert structured export content, attachment filename, and `dashboard.export` audit.
- Added human workspace actions for exporting published structured versions and sharing published dashboard version IDs into existing folder sharing, without duplicating folder share logic.
- Added a visible legacy fallback panel for `legacy_unstructured` assets that keeps rollback/read paths explicit and avoids claiming agent-ready status.

Tests:

- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_dashboard_rest_api.py` -> passed, `2 passed`.
- `cd server && uv run ruff check services/dashboard.py routers/dashboard.py tests/test_dashboard_rest_api.py` -> passed.
- `cd client && pnpm build:check` -> passed.
- `cd client && pnpm lint` -> passed with warnings only from existing frontend lint debt.
- `git diff --check` -> passed.

Commit:

- `77bfd98` `dashboard: preserve share export compatibility`

### Phase 5 Migration Slice: Legacy Asset Backfill

Status: implemented and pushed.

Allowlist:

- `server/migrations/versions/backfill_legacy_dashboard_assets.py`
- `server/tests/test_dashboard_persistence_migration.py`
- `server/tests/test_migration_chain_hardening.py`
- `client/src/features/dashboard/pages/DashboardWorkspacePage.tsx`
- `docs/product/human-agent-dashboard-p0-progress.md`

Behavior:

- Added an additive Alembic migration that backfills one stable `dashboard_assets` row per legacy notebook/dashboard family where existing `dashboards.asset_id` is null.
- Linked preserved legacy dashboard HTML version rows to the generated asset without parsing HTML, DOM, screenshots, or guessed query/tile intent.
- Marked generated assets and linked rows as `legacy_unstructured`, with validation blockers requiring structured review before agent-ready publish.
- Preserved existing `html_content`; `published_version_id` points to the latest legacy dashboard row and `manifest_json` remains null.
- Downgrade unlinks and deletes only generated `legacy-*` assets while keeping the original dashboard HTML rows.
- Updated migration-chain hardening so the branch Alembic head is `backfill_legacy_dashboard_assets`.
- The human inventory now labels `legacy_unstructured` assets as needing structured review.

Tests:

- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_dashboard_persistence_migration.py tests/test_migration_chain_hardening.py` -> passed, `7 passed`.
- `cd server && uv run ruff check migrations/versions/backfill_legacy_dashboard_assets.py tests/test_dashboard_persistence_migration.py tests/test_migration_chain_hardening.py` -> passed.
- `cd client && pnpm build:check` -> passed, with existing CSS/chunk warnings.
- `cd client && pnpm lint` -> passed with existing `355 warnings` and `0 errors`.
- `git diff --check` -> passed.

Commit:

- `817fca6` `dashboard: backfill legacy dashboard assets`

### Phase 6 Acceptance Slice: REST/MCP Query Parity

Status: implemented and pushed.

Allowlist:

- `server/services/dashboard.py`
- `server/mcp/tool_wrappers.py` - conditional shared MCP wrapper; compact run serialization only.
- `server/tests/test_dashboard_rest_api.py`
- `server/tests/test_dashboard_mcp_contract.py`
- `docs/product/human-agent-dashboard-p0-progress.md`

Behavior:

- Preserved `as_of`/`cached_at` from the underlying saved-query execution result in canonical Dashboard run view results, falling back to run time only when the query executor does not provide freshness metadata.
- Extended compact MCP query responses with canonical run fields needed for Human/MCP parity: actor/correlation/idempotency/mode, normalized filters, and execution plan digest.
- Added REST-to-MCP parity coverage for the same tenant principal, dashboard version, filters, data view, run digests, pinned versions, freshness, values, schema, warnings, and `as_of`.
- Added MCP query guard coverage proving unknown data views and unsupported cursor pagination fail before saved-query execution.

Tests:

- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_dashboard_rest_api.py tests/test_dashboard_mcp_contract.py` -> passed, `6 passed`.
- `cd server && uv run ruff check services/dashboard.py mcp/tool_wrappers.py tests/test_dashboard_rest_api.py tests/test_dashboard_mcp_contract.py` -> passed.
- `git diff --check` -> passed.

Commit:

- `17588a6` `dashboard: add rest mcp query parity`

### Phase 6 Security Slice: Policy Ref Execution Guard

Status: implemented and pushed.

Allowlist:

- `server/services/dashboard.py`
- `server/tests/test_dashboard_execution_service.py`
- `server/tests/test_dashboard_rest_api.py`
- `docs/product/human-agent-dashboard-p0-progress.md`

Behavior:

- Added a shared DashboardService guard for manifests declaring unresolved `row_policy_refs`, `column_policy_refs`, or `redaction_policy_refs`.
- Query and preview now return auditable `permission_denied` view results with `policy_not_enforced` errors and `blocked` freshness instead of executing saved-query bindings when such policy refs are present.
- The guard lives in the shared service path, so REST and MCP inherited execution behavior without route-specific policy forks.
- Added service and REST tests proving saved-query execution is not called when row/column/redaction policy refs are declared but not resolved.

Tests:

- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_dashboard_execution_service.py tests/test_dashboard_rest_api.py` -> passed, `8 passed`.
- `cd server && uv run ruff check services/dashboard.py tests/test_dashboard_execution_service.py tests/test_dashboard_rest_api.py` -> passed.
- `git diff --check` -> passed.

Commit:

- `6e0decc` `dashboard: guard unresolved policy refs`

### Phase 6 Acceptance Slice: Browser Workspace Smoke

Status: implemented, evidence captured, and pushed in `b5c679e`.

Allowlist:

- `client/scripts/dashboard-workspace-smoke.mjs`
- `client/package.json`
- `client/pnpm-lock.yaml`
- `client/src/features/dashboard/pages/DashboardWorkspacePage.tsx`
- `docs/product/dashboard-browser-smoke/dashboard-data-1440.png`
- `docs/product/dashboard-browser-smoke/dashboard-lineage-1440.png`
- `docs/product/dashboard-browser-smoke/dashboard-permission-denied-1440.png`
- `docs/product/dashboard-browser-smoke/dashboard-legacy-1440.png`
- `docs/product/dashboard-browser-smoke/dashboard-mobile-390.png`
- `docs/product/human-agent-dashboard-p0-progress.md`

Behavior:

- Added a reproducible `pnpm smoke:dashboard` script backed by a local `playwright` dev dependency.
- The smoke seeds real fixtures through REST APIs, then visits real governed Dashboard workspace routes in Chromium at `1440x900` and `390x844`.
- The journey covers structured published data, Data tab, Lineage/Evidence tab, unresolved policy permission-denied state, and legacy-review fallback state.
- The runner asserts zero page errors, console errors, failed requests, and HTTP 5xx responses; it also checks horizontal overflow and desktop interactive-element overlap.
- Tightened the Dashboard workspace to dedupe repeated manifest/run lineage and evidence display, preventing React duplicate-key console errors without changing canonical IDs.
- Legacy fallback now renders when the selected version migration state is `legacy_unstructured`, so review drafts visibly preserve rollback/legacy status even if the stable asset lifecycle is `draft`.

Evidence:

- Screenshot directory: `docs/product/dashboard-browser-smoke/`
- Captured `dashboard-data-1440.png`, `dashboard-lineage-1440.png`, `dashboard-permission-denied-1440.png`, `dashboard-legacy-1440.png`, and `dashboard-mobile-390.png`.
- `sips -g pixelWidth -g pixelHeight docs/product/dashboard-browser-smoke/*.png` -> desktop screenshots are `1440x900`; mobile screenshot is `390x844`.

Commands and results:

- Initial fresh SQLite startup on `.tmp/dashboard-browser-smoke/app.db` exposed an unrelated source-resource migration-chain blocker: `add_file_source_resource_type` attempted to drop SQLite check constraint `ck_source_resources_ck_source_resources_resource_type`. No source/modeling/connector migration was modified in this Dashboard browser slice.
- For browser evidence only, the temp DB was inspected and already had `resource_type IN (..., 'file', ...)` in `source_resources`; it was stamped from `add_knowledge_provider_metadata` to `add_file_source_resource_type`, then upgraded to Dashboard head.
- `cd server && DATABASE_URL=sqlite+aiosqlite:///$PWD/../.tmp/dashboard-browser-smoke/app.db uv run alembic current` -> `backfill_legacy_dashboard_assets (head)`.
- Backend: `DATABASE_URL=sqlite+aiosqlite:///$PWD/.tmp/dashboard-browser-smoke/app.db APP_MODE=community CORS_ORIGINS=http://127.0.0.1:5179,http://localhost:5179 uv run uvicorn server.main:app --host 127.0.0.1 --port 8123`; `/health` -> healthy.
- Frontend: `cd client && FRONTEND_PORT=5179 VITE_API_URL=http://127.0.0.1:8123 pnpm dev --host 127.0.0.1 --port 5179` -> Vite ready.
- `cd client && BASE_URL=http://127.0.0.1:5179 API_URL=http://127.0.0.1:8123 SCREEN_DIR=../docs/product/dashboard-browser-smoke pnpm smoke:dashboard` -> passed with `pageerror=0`, `consoleError=0`, `requestfailed=0`, `http5xx=0`.
- `cd client && node --check scripts/dashboard-workspace-smoke.mjs` -> passed.
- `cd client && pnpm lint` -> passed with existing `355 warnings`, `0 errors`.
- `cd client && pnpm build:check` -> passed with existing CSS/chunk warnings.
- `git diff --check` -> passed.

Commit:

- `b5c679e` `dashboard: add browser smoke evidence`

### Phase 6 Acceptance Slice: Focused Backend, MCP, Security, Migration Evidence

Status: evidence recorded and pushed in `3e39d3d`.

Allowlist:

- `docs/product/human-agent-dashboard-p0-progress.md`

Evidence scope:

- Dashboard manifest/run contract validation.
- Shared DashboardService lifecycle, ETag, publish, reload, query, policy guard, and audit behavior.
- REST governed asset lifecycle/query/state/lineage/audit/export, tenant/notebook boundaries, REST/MCP parity, and policy-ref guard behavior.
- MCP lifecycle/query/explain/lineage contract, scoped publish authorization, and query guard behavior.
- Viewer Dashboard arbitrary saved-query ID binding protection, including cross-notebook and cross-tenant rejection.
- Dashboard persistence migrations, legacy backfill, SQLite upgrade/downgrade, and migration-chain hardening.

Commands and results:

- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_dashboard_contract_schemas.py tests/test_dashboard_execution_service.py tests/test_dashboard_lifecycle_service.py tests/test_dashboard_mcp_contract.py tests/test_dashboard_persistence_migration.py tests/test_dashboard_rest_api.py tests/test_dashboard_security_regressions.py tests/test_migration_chain_hardening.py` -> initially passed, `33 passed`, `56 warnings`; post-handoff completion audit after semantic/context data-view execution passed, `36 passed`, `69 warnings`; after legacy HTML tool gating passed, `40 passed`, `69 warnings`; after MCP legacy tool deprecation marking passed, `41 passed`, `69 warnings`.
- `cd server && uv run ruff check schemas/dashboard.py models/dashboard.py repositories/dashboard.py services/dashboard.py routers/dashboard.py mcp/tool_wrappers.py mcp/tools.py tests/test_dashboard_contract_schemas.py tests/test_dashboard_execution_service.py tests/test_dashboard_lifecycle_service.py tests/test_dashboard_mcp_contract.py tests/test_dashboard_persistence_migration.py tests/test_dashboard_rest_api.py tests/test_dashboard_security_regressions.py tests/test_migration_chain_hardening.py` -> passed.
- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_dashboard_execution_service.py` after semantic/context data-view execution -> passed, `7 passed`, `34 warnings`.
- `cd server && uv run ruff check services/dashboard.py tests/test_dashboard_execution_service.py` after semantic/context data-view execution -> passed.
- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_dashboard_legacy_tool_gating.py tests/test_dashboard_mcp_contract.py` after legacy HTML tool gating -> passed, `7 passed`, `17 warnings`.
- `cd server && uv run ruff check tools/agentic.py tests/test_dashboard_legacy_tool_gating.py` after legacy HTML tool gating -> passed.
- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_dashboard_mcp_contract.py tests/test_dashboard_legacy_tool_gating.py` after MCP legacy tool deprecation marking -> passed, `8 passed`, `17 warnings`.
- `cd server && uv run ruff check mcp/tools.py tests/test_dashboard_mcp_contract.py` after MCP legacy tool deprecation marking -> passed.
- `cd server && uv run alembic heads` -> `backfill_legacy_dashboard_assets (head)`.
- Disposable SQLite migration evidence DB: `.tmp/dashboard-migration-evidence-20260816-1208/app.db`.
- `DATABASE_URL=sqlite+aiosqlite:///$PWD/../.tmp/dashboard-migration-evidence-20260816-1208/app.db uv run alembic upgrade add_knowledge_provider_metadata` -> passed.
- The disposable DB at `add_knowledge_provider_metadata` already contained `source_resources` check constraint values including `'file'`; applying `add_file_source_resource_type` directly still hits the unrelated SQLite constraint-name issue documented in the browser slice, so evidence stamped only this disposable DB to `add_file_source_resource_type` before testing Dashboard migrations.
- `DATABASE_URL=sqlite+aiosqlite:///$PWD/../.tmp/dashboard-migration-evidence-20260816-1208/app.db uv run alembic stamp add_file_source_resource_type && ... uv run alembic upgrade head && ... uv run alembic current` -> `backfill_legacy_dashboard_assets (head)`.
- SQLite inspection after upgrade confirmed `dashboard_assets`, `dashboard_runs`, and `dashboard_audit_events` exist, and `dashboards` has additive `asset_id`, `manifest_json`, `migration_state`, and `is_published_immutable` columns.
- `... uv run alembic downgrade add_governed_dashboard_assets && ... uv run alembic current && ... uv run alembic upgrade head && ... uv run alembic current` -> downgraded backfill to `add_governed_dashboard_assets`, then upgraded to `backfill_legacy_dashboard_assets (head)`.
- `... uv run alembic downgrade add_file_source_resource_type && ... uv run alembic current` -> downgraded through the governed Dashboard migration to `add_file_source_resource_type`; SQLite inspection confirmed Dashboard additive tables/columns were gone while legacy `dashboards.html_content` remained.
- `... uv run alembic upgrade head && ... uv run alembic current` -> returned to `backfill_legacy_dashboard_assets (head)`.

Commit:

- `3e39d3d` `dashboard: record backend acceptance evidence`

## Commit Ledger

| SHA | Subject | Phase | Tests | Push |
| --- | --- | --- | --- | --- |
| `4a4f4e1` | `dashboard: audit human agent contract` | Phase 0 | `pytest tests/test_dashboard_security_regressions.py` -> 1 strict xfail; `ruff check tests/test_dashboard_security_regressions.py` -> passed | Pushed to `veadk-data-studio/agent/dashboard-human-agent-p0`; HEAD matched upstream after push |
| `033b526` | `dashboard: enforce viewer query binding` | Phase 2 security slice | `pytest tests/test_dashboard_security_regressions.py` -> 5 passed; `ruff check routers/folders.py tests/test_dashboard_security_regressions.py` -> passed | Pushed to `veadk-data-studio/agent/dashboard-human-agent-p0`; HEAD matched upstream after push |
| `be5e4a7` | `dashboard: add manifest run schemas` | Phase 1 schema slice | `pytest tests/test_dashboard_contract_schemas.py` -> 7 passed; `ruff check schemas/dashboard.py tests/test_dashboard_contract_schemas.py` -> passed | Pushed to `veadk-data-studio/agent/dashboard-human-agent-p0`; HEAD matched upstream after push |
| `ad4f6f3` | `dashboard: persist governed asset foundation` | Phase 1 persistence slice | `pytest tests/test_dashboard_persistence_migration.py tests/test_migration_chain_hardening.py` -> 6 passed; `ruff check models/dashboard.py models/__init__.py migrations/versions/add_governed_dashboard_assets.py tests/test_dashboard_persistence_migration.py tests/test_migration_chain_hardening.py` -> passed; `alembic heads` -> `add_governed_dashboard_assets` | Pushed to `veadk-data-studio/agent/dashboard-human-agent-p0`; HEAD matched upstream after push |
| `da3b2d2` | `dashboard: add lifecycle service primitives` | Phase 1 lifecycle slice | `pytest tests/test_dashboard_lifecycle_service.py` -> 3 passed; `ruff check repositories/dashboard.py services/dashboard.py tests/test_dashboard_lifecycle_service.py` -> passed | Pushed to `veadk-data-studio/agent/dashboard-human-agent-p0`; HEAD matched upstream after push |
| `0d05215` | `dashboard: bind dashboard run execution` | Phase 2 execution slice | `pytest tests/test_dashboard_execution_service.py` -> 3 passed; `ruff check services/dashboard.py tests/test_dashboard_execution_service.py` -> passed | Pushed to `veadk-data-studio/agent/dashboard-human-agent-p0`; HEAD matched upstream after push |
| `4de07e7` | `dashboard: expose dashboard rest contract` | Phase 3 REST slice | `pytest tests/test_dashboard_rest_api.py` -> 2 passed; `ruff check routers/dashboard.py main.py repositories/dashboard.py auth/scopes.py tests/test_dashboard_rest_api.py` -> passed; `git diff --check` -> passed | Pushed to `veadk-data-studio/agent/dashboard-human-agent-p0`; HEAD matched upstream after push |
| `c3e28b1` | `dashboard: expose dashboard mcp contract` | Phase 3 MCP slice | `pytest tests/test_dashboard_rest_api.py tests/test_dashboard_mcp_contract.py tests/test_dashboard_lifecycle_service.py` -> 7 passed; `ruff check services/dashboard.py routers/dashboard.py mcp/tool_wrappers.py mcp/tools.py tests/test_dashboard_mcp_contract.py tests/test_dashboard_rest_api.py tests/test_dashboard_lifecycle_service.py` -> passed; `git diff --check` -> passed | Pushed to `veadk-data-studio/agent/dashboard-human-agent-p0`; HEAD matched upstream after push |
| `33130f5` | `dashboard: render structured dashboard workspace` | Phase 4 human workspace inventory/view slice | `pnpm build:check` -> passed; `pnpm lint` -> passed with warnings only; `git diff --check` -> passed | Pushed to `veadk-data-studio/agent/dashboard-human-agent-p0`; HEAD matched upstream after push |
| `d9ac360` | `dashboard: add review reload workflow` | Phase 4 review/preview/publish/reload slice | `pytest tests/test_dashboard_rest_api.py tests/test_dashboard_lifecycle_service.py` -> 5 passed; `ruff check services/dashboard.py routers/dashboard.py tests/test_dashboard_rest_api.py` -> passed; `pnpm build:check` -> passed; `pnpm lint` -> passed with warnings only; `git diff --check` -> passed | Pushed to `veadk-data-studio/agent/dashboard-human-agent-p0`; HEAD matched upstream after push |
| `77bfd98` | `dashboard: preserve share export compatibility` | Phase 4 share/export/legacy compatibility slice | `pytest tests/test_dashboard_rest_api.py` -> 2 passed; `ruff check services/dashboard.py routers/dashboard.py tests/test_dashboard_rest_api.py` -> passed; `pnpm build:check` -> passed; `pnpm lint` -> passed with warnings only; `git diff --check` -> passed | Pushed to `veadk-data-studio/agent/dashboard-human-agent-p0`; HEAD matched upstream after push |
| `817fca6` | `dashboard: backfill legacy dashboard assets` | Phase 5 legacy asset backfill slice | `pytest tests/test_dashboard_persistence_migration.py tests/test_migration_chain_hardening.py` -> 7 passed; `ruff check migrations/versions/backfill_legacy_dashboard_assets.py tests/test_dashboard_persistence_migration.py tests/test_migration_chain_hardening.py` -> passed; `pnpm build:check` -> passed; `pnpm lint` -> passed with existing 355 warnings; `git diff --check` -> passed | Pushed to `veadk-data-studio/agent/dashboard-human-agent-p0`; HEAD matched upstream after push |
| `17588a6` | `dashboard: add rest mcp query parity` | Phase 6 REST/MCP query parity slice | `pytest tests/test_dashboard_rest_api.py tests/test_dashboard_mcp_contract.py` -> 6 passed; `ruff check services/dashboard.py mcp/tool_wrappers.py tests/test_dashboard_rest_api.py tests/test_dashboard_mcp_contract.py` -> passed; `git diff --check` -> passed | Pushed to `veadk-data-studio/agent/dashboard-human-agent-p0`; HEAD matched upstream after push |
| `6e0decc` | `dashboard: guard unresolved policy refs` | Phase 6 policy/ref security slice | `pytest tests/test_dashboard_execution_service.py tests/test_dashboard_rest_api.py` -> 8 passed; `ruff check services/dashboard.py tests/test_dashboard_execution_service.py tests/test_dashboard_rest_api.py` -> passed; `git diff --check` -> passed | Pushed to `veadk-data-studio/agent/dashboard-human-agent-p0`; HEAD matched upstream after push |
| `b5c679e` | `dashboard: add browser smoke evidence` | Phase 6 browser workspace smoke slice | `pnpm smoke:dashboard` -> passed against real REST/UI on `8123`/`5179` with 0 page errors, console errors, failed requests, and HTTP 5xx; `node --check scripts/dashboard-workspace-smoke.mjs` -> passed; `pnpm lint` -> passed with existing 355 warnings; `pnpm build:check` -> passed with existing CSS/chunk warnings; `git diff --check` -> passed | Pushed to `veadk-data-studio/agent/dashboard-human-agent-p0`; HEAD matched upstream after push |
| `3e39d3d` | `dashboard: record backend acceptance evidence` | Phase 6 backend/MCP/security/migration evidence slice | Dashboard focused pytest suite -> 33 passed; Dashboard backend ruff surface -> passed; Alembic head/current evidence -> `backfill_legacy_dashboard_assets`; disposable SQLite Dashboard upgrade/downgrade evidence -> passed with source-resource stamp workaround documented | Pushed to `veadk-data-studio/agent/dashboard-human-agent-p0`; HEAD matched upstream after push |
| `e564dae` | `dashboard: execute semantic and context views` | Phase 6 completion-audit execution slice | `pytest tests/test_dashboard_execution_service.py` -> 7 passed; Dashboard focused pytest suite -> 36 passed; `ruff check services/dashboard.py tests/test_dashboard_execution_service.py` -> passed; `git diff --check` -> passed | Pushed to `veadk-data-studio/agent/dashboard-human-agent-p0`; HEAD matched upstream after push |
| `7a0f83d` | `dashboard: gate legacy html tools` | Phase 6 completion-audit legacy tool slice | `pytest tests/test_dashboard_legacy_tool_gating.py tests/test_dashboard_mcp_contract.py` -> 7 passed; Dashboard focused pytest suite with legacy gating -> 40 passed; `ruff check tools/agentic.py tests/test_dashboard_legacy_tool_gating.py` -> passed; `git diff --check` -> passed | Pushed to `veadk-data-studio/agent/dashboard-human-agent-p0`; HEAD matched upstream after push |
| `eb924f2` | `dashboard: mark legacy html mcp tools deprecated` | Phase 6 completion-audit MCP legacy-tool description slice | `pytest tests/test_dashboard_mcp_contract.py tests/test_dashboard_legacy_tool_gating.py` -> 8 passed; Dashboard focused pytest suite with deprecation marking -> 41 passed; `ruff check mcp/tools.py tests/test_dashboard_mcp_contract.py` -> passed; `git diff --check` -> passed | Pushed to `veadk-data-studio/agent/dashboard-human-agent-p0`; HEAD matched upstream after push |

## Acceptance Evidence

Browser workspace evidence captured under `docs/product/dashboard-browser-smoke/` for structured data, lineage/evidence, permission-denied policy guard, legacy fallback, and mobile layout. Backend/MCP/security/migration evidence is recorded above, including post-handoff coverage that executes all P0 data-view kinds (`saved_query`, `semantic_metric`, and `context_search`) through governed service bindings, blocks deprecated legacy HTML tools from reading or mutating structured Dashboard versions, and marks those MCP tools as deprecated legacy-only. Real `8080` has not been verified in this isolated Dashboard worktree.

## Final Integration Handoff

Status: post-handoff completion audit fixed missing `semantic_metric`/`context_search` data-view execution in `e564dae`, legacy HTML tool gating in `7a0f83d`, and MCP deprecation marking in `eb924f2`; ledger update prepared after `HEAD == @{upstream}` verification.

Final branch/evidence state recorded by the handoff ledger before this doc-only update:

- Base SHA: `24c6b69a1f816a831ee6ce94d8515817b4752913`
- Dashboard evidence HEAD before post-handoff audit: `98adf4db32de12582824b887c89c66c68cc7bd27`
- Latest implementation evidence HEAD before this doc-only update: `e564dae8763c490c82d5f0097a621b36e9774a68`
- Latest legacy-tool gate implementation HEAD before this doc-only update: `7a0f83dbfd724da331c1494297137b2580f1513a`
- Latest MCP deprecation marking HEAD before this doc-only update: `eb924f256ca2653502f31f5990a2331ff2e3b1da`
- Remote branch: `veadk-data-studio/agent/dashboard-human-agent-p0`
- Integration source observed only: `veadk-data-studio/agent/data-studio-p0` at `9718bf6431c177c0b48e6fc21c36626a9057c47a`
- Merge base with integration source: `24c6b69a1f816a831ee6ce94d8515817b4752913`
- Migration head on Dashboard branch: `backfill_legacy_dashboard_assets`
- Prior handoff ledger SHA: `59de7027f40b2122d4a27b1382ddccb299873ffa`

Ordered Dashboard commits:

```text
4a4f4e1 dashboard: audit human agent contract
2049aa9 dashboard: record audit evidence
033b526 dashboard: enforce viewer query binding
0d7eaec dashboard: record query binding evidence
be5e4a7 dashboard: add manifest run schemas
43a9594 dashboard: record schema evidence
ad4f6f3 dashboard: persist governed asset foundation
a87a0b0 dashboard: record persistence evidence
da3b2d2 dashboard: add lifecycle service primitives
a3c9937 dashboard: record lifecycle evidence
0d05215 dashboard: bind dashboard run execution
2916b2c dashboard: record execution evidence
4de07e7 dashboard: expose dashboard rest contract
bd34e77 dashboard: record rest evidence
c3e28b1 dashboard: expose dashboard mcp contract
04452a0 dashboard: record mcp evidence
33130f5 dashboard: render structured dashboard workspace
e534f14 dashboard: record workspace evidence
d9ac360 dashboard: add review reload workflow
f90531a dashboard: record workflow evidence
77bfd98 dashboard: preserve share export compatibility
00daa29 dashboard: record compatibility evidence
817fca6 dashboard: backfill legacy dashboard assets
bfc075a dashboard: record backfill evidence
17588a6 dashboard: add rest mcp query parity
904f83c dashboard: record parity evidence
6e0decc dashboard: guard unresolved policy refs
642b0ae dashboard: record policy guard evidence
b5c679e dashboard: add browser smoke evidence
0cddb90 dashboard: record browser evidence
3e39d3d dashboard: record backend acceptance evidence
98adf4d dashboard: record backend evidence sha
1b5a348 dashboard: document integration handoff
59de702 dashboard: finalize handoff ledger
738f33a dashboard: correct final handoff sha
e564dae dashboard: execute semantic and context views
bb54fc0 dashboard: record semantic context execution evidence
7a0f83d dashboard: gate legacy html tools
4db0a34 dashboard: record legacy tool gate evidence
eb924f2 dashboard: mark legacy html mcp tools deprecated
```

`git diff --name-status 24c6b69a1f816a831ee6ce94d8515817b4752913..HEAD`:

```text
M	client/package.json
M	client/pnpm-lock.yaml
A	client/scripts/dashboard-workspace-smoke.mjs
M	client/src/App.tsx
M	client/src/components/CollapsibleSidebar.tsx
M	client/src/constants/scopes.ts
A	client/src/features/dashboard/pages/DashboardWorkspacePage.tsx
A	client/src/services/dashboard.ts
A	client/src/types/dashboard.ts
A	docs/product/dashboard-browser-smoke/dashboard-data-1440.png
A	docs/product/dashboard-browser-smoke/dashboard-legacy-1440.png
A	docs/product/dashboard-browser-smoke/dashboard-lineage-1440.png
A	docs/product/dashboard-browser-smoke/dashboard-mobile-390.png
A	docs/product/dashboard-browser-smoke/dashboard-permission-denied-1440.png
A	docs/product/human-agent-dashboard-p0-progress.md
A	docs/product/human-agent-dashboard-p0.md
M	server/auth/scopes.py
M	server/main.py
M	server/mcp/tool_wrappers.py
M	server/mcp/tools.py
A	server/migrations/versions/add_governed_dashboard_assets.py
A	server/migrations/versions/backfill_legacy_dashboard_assets.py
M	server/models/__init__.py
M	server/models/dashboard.py
M	server/repositories/dashboard.py
A	server/routers/dashboard.py
M	server/routers/folders.py
A	server/schemas/dashboard.py
A	server/services/dashboard.py
A	server/tests/test_dashboard_contract_schemas.py
A	server/tests/test_dashboard_execution_service.py
A	server/tests/test_dashboard_lifecycle_service.py
A	server/tests/test_dashboard_mcp_contract.py
A	server/tests/test_dashboard_persistence_migration.py
A	server/tests/test_dashboard_rest_api.py
A	server/tests/test_dashboard_security_regressions.py
M	server/tests/test_migration_chain_hardening.py
```

Conditional shared files and reasons:

- `server/main.py`: additive governed Dashboard REST router registration.
- `server/auth/scopes.py`: additive Dashboard read/query/create/edit/publish/export scope constants.
- `server/models/__init__.py`: additive Dashboard model registration.
- `server/models/dashboard.py` and `server/repositories/dashboard.py`: existing Dashboard persistence evolved additively to stable asset/version/run/audit semantics.
- `server/routers/folders.py`: minimal viewer batch/preflight query binding guard and legacy folder/share compatibility.
- `server/mcp/tool_wrappers.py` and `server/mcp/tools.py`: additive governed Dashboard MCP wrappers/tool registrations that call shared `DashboardService`.
- `client/src/App.tsx`, `client/src/components/CollapsibleSidebar.tsx`, `client/src/constants/scopes.ts`: additive route/navigation/scope registration for the governed Dashboard workspace.
- `client/package.json`, `client/pnpm-lock.yaml`: added reproducible `smoke:dashboard` script and local Playwright dev dependency.
- `server/tests/test_migration_chain_hardening.py`: expected Alembic head updated to Dashboard head and Dashboard migration chain assertions added.

Acceptance evidence summary:

- Contract schemas: `dashboard.manifest.v1` and `dashboard.run.v1` covered by `tests/test_dashboard_contract_schemas.py`.
- Data-view execution: `tests/test_dashboard_execution_service.py` covers manifest-bound `saved_query`, published semantic-model `semantic_metric`, provider-neutral evidence `context_search`, data-view allowlist rejection, pinned snapshot honesty, and unresolved policy blocking.
- Legacy HTML tool gating: `tests/test_dashboard_legacy_tool_gating.py` covers deprecated HTML tools allowing `legacy_unstructured` rows and rejecting structured manifest-backed Dashboard versions before HTML read/edit; `tests/test_dashboard_mcp_contract.py` also covers MCP tool descriptions marking those tools deprecated legacy-only.
- Security: viewer arbitrary saved-query ID execution blocked for other notebook/cross-tenant/filter cases; unresolved row/column/redaction policy refs return auditable `permission_denied` without saved-query execution.
- REST/MCP parity: same tenant principal, dashboard version, filters, digests, values, schema, cache/freshness, `as_of`, warnings, evidence, and lineage covered in `tests/test_dashboard_rest_api.py` and `tests/test_dashboard_mcp_contract.py`.
- Lifecycle: draft creation, JSON Patch allowlist, stale ETag `409`, validate, preview, publish, reload review draft, export, audit, lineage, and state covered by focused tests.
- Migration/legacy: additive Dashboard tables/columns, legacy HTML preservation, backfill/downgrade, and SQLite Dashboard upgrade/downgrade evidence recorded above.
- UI/browser: real API/UI smoke on `8123`/`5179`, screenshots at `1440x900` and `390x844`, and zero page errors/console errors/request failures/HTTP 5xx.
- Frontend: `pnpm lint` passed with existing 355 warnings; `pnpm build:check` passed with existing CSS/chunk warnings.

Integration drift against `veadk-data-studio/agent/data-studio-p0`:

- Shared modified file: `server/tests/test_migration_chain_hardening.py`.
- Integration source also modifies `server/migrations/versions/add_file_source_resource_type.py` to make the source-resource SQLite constraint update idempotent by inspecting SQL text and using `op.f(...)`.
- Dashboard branch currently documents a source-resource stamp workaround for disposable fresh SQLite evidence because it intentionally did not modify source-resource internals. Integration should take the `agent/data-studio-p0` source-resource migration fix before/with Dashboard migrations, then remove the need for that workaround and keep/adjust the fresh SQLite chain test.
- Suggested merge order: first merge the latest `agent/data-studio-p0` source-resource/self-hosted hardening, then merge Dashboard; resolve `server/tests/test_migration_chain_hardening.py` by keeping the fresh SQLite chain test from integration source and updating expected heads/lineage to `backfill_legacy_dashboard_assets`.
- No Alembic merge migration should be needed if the integration source keeps `add_file_source_resource_type` as the parent of `add_governed_dashboard_assets`; verify with `cd server && uv run alembic heads`.

Known residual risks and dependencies:

- `pinned_snapshot` mode remains intentionally blocked until immutable run result artifacts exist.
- Real `8080` target was not touched or verified by this isolated Dashboard session.
- Source-resource migration freshness is owned by the integration/source session; Dashboard evidence used a disposable DB stamp workaround only for the pre-existing source-resource constraint state.
- Existing frontend lint warnings and build CSS/chunk warnings remain outside Dashboard scope.

Final status after final handoff commit is pushed and `HEAD == @{upstream}`:

```text
DASHBOARD_BRANCH_READY_FOR_INTEGRATION / 8080_PENDING_INTEGRATION
```
