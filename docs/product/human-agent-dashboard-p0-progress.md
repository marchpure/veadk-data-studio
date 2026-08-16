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

Status: implemented for governed `saved_query` compatibility views.

Allowlist:

- `server/services/dashboard.py`
- `server/tests/test_dashboard_execution_service.py`
- `docs/product/human-agent-dashboard-p0-progress.md`

Behavior:

- Added `DashboardService.query_dashboard` as the canonical execution entry point for later REST/MCP wrappers.
- Query accepts `data_view_ids`, not arbitrary query IDs; the service resolves selected views from the published manifest.
- Supported P0 execution in this slice is reviewed `saved_query` compatibility binding; unsupported semantic/context views return blocked in the run contract.
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

## Acceptance Evidence

No final acceptance evidence yet. Current branch is not ready for integration and has not verified real `8080`.
