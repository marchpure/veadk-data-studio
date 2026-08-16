# Evaluation + Sharing Governance P0 Progress

CURRENT_PHASE: Phase 0 — Sharing 安全止血. Completed slices: integration worktree init, dashboard merge integration gates, focused migration/security gates, share/manage secret redaction, worker-backed notebook share/export object authorization, viewer session governed-asset binding, structured dashboard manifest data-view/filter validation, share/MCP error redaction. Next slice: Phase 0 completion audit, then Phase 1 Evaluation authoritative model.

## Phase 0 Slice Checklist

- [x] `GET /notebooks/{id}/share`, JSON share list, and manage endpoints never return `password`, `verifier`, or raw token.
- [x] `ShareModal.tsx` removes display/copy of saved passwords; password is input-only during create/rotate and is never read back.
- [~] share/create/delete/rotate/export use correct share/export action scope and unified object authorization for tenant, owner/grant, asset, version, and action. Worker-backed notebook share/export/manage endpoints now enforce tenant + owner + action scope through `server.auth.object_authorizer`; folder share/version manage and future canonical grant checks remain.
- [x] viewer sessions bind and validate issuer, audience, user, tenant, grant, asset, version, token id, issued-at, not-before, expiry, and revocation/rotation identity.
- [x] structured dashboard query only accepts immutable manifest `data_view_id` plus validated filters; legacy path is tenant/dashboard-version/notebook bound.
- [x] errors, logs, and audit events never leak password, token, verifier, credentials, cross-tenant objects, or unauthorized SQL.

## Environment Side-Effect Registration

- `2026-08-16 13:11 CST`: this session previously created test data on the existing `127.0.0.1:8080` runtime while working on an unrelated dashboard validation task before goal correction.
- Created folder: ID `b268fd5a-8bb4-4ee6-9447-03edc9c142f0`; name not confirmed from read-only evidence and must be verified during the Release Gate.
- Shared dashboard: ID `9775fc11-8891-493d-8715-ee6dfbc31cbc`; selected dashboard notebook ID `1acfaeff-4dae-434f-aa0b-eba828c18669`.
- Reason: temporary validation data for dashboard sharing behavior on the active 8080 instance.
- Current state: data is still present in the 8080 runtime and has not been cleaned up.
- Cleanup owner/timing: this governance integration session should verify and clean up the test folder during the final 8080 Release Gate, after Phase 0-5 implementation and local gates pass. Do not delete it earlier because 8080 is read-only for this goal until Release Gate.

## 2026-08-16 13:22 CST - Integration Worktree Initialized

Branch: `integration/evaluation-sharing-governance-p0`

Remote: `veadk-data-studio`

Worktree: `/Users/bytedance/worktrees/byaan-governance-integration-p0`

Base: `9718bf6431c177c0b48e6fc21c36626a9057c47a`

Data Studio head: `9718bf6431c177c0b48e6fc21c36626a9057c47a`

Dashboard head: `d6c4c2ea1b602a2c6ee84902f457054b79947045`

Preflight evidence:

- `git -C /Users/bytedance/byaan fetch veadk-data-studio` passed.
- Data Studio worktree status was clean and `HEAD == @{upstream}` at `9718bf6431c177c0b48e6fc21c36626a9057c47a`.
- Dashboard worktree status was clean and `HEAD == @{upstream}` at `d6c4c2ea1b602a2c6ee84902f457054b79947045`.
- Process check found only this session's read commands, no continuing writers in the upstream worktrees.
- Data Studio session final status: `8080_READY`.
- Dashboard session final status: `DASHBOARD_BRANCH_READY_FOR_INTEGRATION / 8080_PENDING_INTEGRATION`.
- Integration path and branch did not exist before creation.
- New integration branch was pushed and tracks `veadk-data-studio/integration/evaluation-sharing-governance-p0`.

Pending immediate checks:

- Initial integration base Alembic head: `add_file_source_resource_type`.
- Direct `uv run alembic heads` in the new worktree stalled during first-time dependency setup, before running Alembic. It was interrupted because it was this session's own command, then re-run with `PYTHONPATH=..:tests /Users/bytedance/worktrees/byaan-data-studio-p0/.venv/bin/python -m alembic heads` against the integration worktree code.
- Dashboard merge has not started.

Current status: `INTEGRATION_WORKTREE_INITIALIZED`.

## 2026-08-16 13:31 CST - Dashboard Merge Integration

Merge commit: `4ce525cd6d3a749a8b60ee255b4c245f8ea03220`

Merged: `veadk-data-studio/agent/dashboard-human-agent-p0` at `d6c4c2ea1b602a2c6ee84902f457054b79947045`

Conflict resolution:

- `server/tests/test_migration_chain_hardening.py` was the only content conflict.
- Kept the Data Studio fresh-SQLite migration chain test.
- Kept Dashboard migration chain assertions and set the final head assertion to `backfill_legacy_dashboard_assets`.

Integration evidence:

- `cd server && PYTHONPATH=..:tests /Users/bytedance/worktrees/byaan-data-studio-p0/.venv/bin/python -m alembic heads` -> `backfill_legacy_dashboard_assets (head)`.
- `cd server && PYTHONPATH=..:tests /Users/bytedance/worktrees/byaan-data-studio-p0/.venv/bin/python -m pytest tests/test_migration_chain_hardening.py` -> `5 passed, 8 warnings`.
- Dashboard focused backend suite -> `42 passed, 69 warnings`.
- Dashboard backend ruff surface -> passed.
- Data Studio focused connector/source/modeling suite -> `77 passed, 216 warnings`.
- Data Studio backend ruff surface -> passed.
- `cd client && pnpm install --frozen-lockfile` -> passed using the existing lockfile after the new worktree had no `node_modules`.
- `cd client && pnpm lint` -> passed with `0 errors, 357 warnings`.
- `cd client && pnpm build:check` -> passed with existing CSS/chunk warnings.

Environment note:

- First-time `uv run alembic heads` in the new worktree stalled during dependency setup. Current Python gates used the already-installed Data Studio `.venv` interpreter against this integration worktree via `PYTHONPATH=..:tests`. A dedicated integration `.venv` still needs repair before broader full-suite runs.

Current status: `DASHBOARD_MERGED_INTEGRATION_GATES_FOCUSED_PASS`.

## 2026-08-16 13:37 CST - Migration And Security Gate Evidence

Migration evidence:

- `alembic heads` -> `backfill_legacy_dashboard_assets (head)`.
- Fresh SQLite `alembic upgrade head` -> `backfill_legacy_dashboard_assets (head)`.
- Existing SQLite path `upgrade add_file_source_resource_type -> upgrade head -> downgrade add_governed_dashboard_assets -> upgrade head` -> `backfill_legacy_dashboard_assets (head)`.
- Existing SQLite evidence DB retained at `/var/folders/y5/s7wzkl8d44q4z4lj2ljg4lrc0000gn/T/byaan-integration-existing-XXXXXX.TyIhjNqGoD/existing.db`.
- Fresh SQLite evidence DB retained at `/var/folders/y5/s7wzkl8d44q4z4lj2ljg4lrc0000gn/T/byaan-integration-fresh-XXXXXX.cChPhthAjn/fresh.db`.

Security/compatibility evidence:

- `tests/test_dashboard_security_regressions.py tests/test_dashboard_rest_api.py tests/test_dashboard_mcp_contract.py tests/test_source_connectors_api.py::test_feishu_admin_config_status_is_admin_only_and_never_returns_secret tests/test_source_connectors_api.py::test_source_connection_encrypts_credentials_and_redacts_secret` -> `15 passed, 37 warnings`.

Current status: `THREE_LAYER_INTEGRATION_GATE_FOCUSED_PASS`.

## 2026-08-16 14:24 CST - Phase 0 Share Secret Redaction

Commit: `164cacb7729379e8021f7392893629d6ac759111`.

Scope:

- Added focused regression coverage for worker-backed share management endpoints using a fake worker response that includes `password`, `verifier`, and raw token fields.
- Changed dashboard share and notebook JSON share serializers so manage/list responses expose only safe metadata: IDs, URLs where applicable, timestamps, and `has_password`.
- Updated `ShareModal.tsx` and API typings so saved passwords are never displayed, copied, or read back; password remains write-only during create/change/remove flows.

Evidence:

- `PYTHONPATH=..:tests /Users/bytedance/worktrees/byaan-data-studio-p0/.venv/bin/python -m pytest server/tests/test_share_secret_redaction.py -q` -> `1 passed, 7 warnings`.
- `PYTHONPATH=..:tests /Users/bytedance/worktrees/byaan-data-studio-p0/.venv/bin/python -m ruff check server/routers/exports.py server/tests/test_share_secret_redaction.py` -> passed with existing removed-rule warning.
- `cd client && pnpm build:check` -> passed with existing CSS/chunk warnings.

## 2026-08-16 14:34 CST - Phase 0 Worker-Backed Share Object Authorization

Commit: `5ac631cf7a9f42161e34b062eea63086d6556799`.

Scope:

- Added a shared notebook object authorizer for worker-backed export/share/manage actions.
- `GET /notebooks/{id}/export/pdf`, `GET /notebooks/{id}/export/compiled-html`, and `GET /notebooks/{id}/export/json` now require `dashboard.export` plus same-tenant ownership.
- Dashboard HTML share and notebook JSON share create/list/delete/password-manage paths now require `dashboard.share` plus same-tenant ownership before any export or worker call.
- Added regression coverage proving a same-tenant member cannot export or manage owner notebook shares, and that denial happens before export/worker execution.

Evidence:

- `PYTHONPATH=..:tests /Users/bytedance/worktrees/byaan-data-studio-p0/.venv/bin/python -m pytest server/tests/test_share_object_authorization.py server/tests/test_share_secret_redaction.py -q` -> `10 passed, 7 warnings`.
- `PYTHONPATH=..:tests /Users/bytedance/worktrees/byaan-data-studio-p0/.venv/bin/python -m ruff check server/routers/exports.py server/auth/object_authorizer.py server/tests/test_share_object_authorization.py server/tests/test_share_secret_redaction.py` -> passed with existing removed-rule warning.

## 2026-08-16 14:43 CST - Phase 0 Viewer Session Governed-Asset Binding

Commit: `a48a18ab5cab7a68a9b2c41df993412a12d2ed9d`.

Scope:

- Extended viewer session tokens with `iss`, `aud`, `uid`, `tid`, `grant_id`, `asset_id`, `version_id`, `jti`, `iat`, `nbf`, and `exp`.
- Viewer dashboard responses now sign the `viewer_session` cookie against the concrete folder-dashboard grant, dashboard asset, and immutable dashboard version.
- Viewer query and filter preflight endpoints now reject tokens for a different dashboard version, tenant mismatch, asset mismatch, missing required claims, and revoked/rotated folder grants.

Evidence:

- `PYTHONPATH=..:tests /Users/bytedance/worktrees/byaan-data-studio-p0/.venv/bin/python -m pytest server/tests/test_dashboard_security_regressions.py server/tests/test_share_object_authorization.py server/tests/test_share_secret_redaction.py -q` -> `17 passed, 7 warnings`.
- `PYTHONPATH=..:tests /Users/bytedance/worktrees/byaan-data-studio-p0/.venv/bin/python -m ruff check server/services/viewer_session_service.py server/routers/folders.py server/tests/test_dashboard_security_regressions.py` -> passed with existing removed-rule warning.

## 2026-08-16 14:58 CST - Dashboard Full Validation And Preview Route Fix

Commit: `c070788514189038d776dd316d82ee0db237c16d`.

Scope:

- Ran dashboard backend, filter/share adjacent, migration, frontend build, and browser smoke validation from the integration worktree without touching the existing `127.0.0.1:8080` runtime.
- Reproduced a direct `/notebook/{id}/preview` browser bug: notebooks with zero chat messages rendered the empty chat state instead of the split dashboard preview panel.
- Fixed `ChatPreview.tsx` so the `/notebook/:id/preview` route explicitly opens the dashboard preview panel and bypasses the centered empty chat branch.
- Fixed `DashboardPreviewPanel.tsx` so version `1` is not automatically treated as blank; only the actual default placeholder content is hidden from iframe preview.
- Extended `client/scripts/dashboard-workspace-smoke.mjs` to cover direct notebook preview routes before dashboard asset pages.

Evidence:

- `PYTHONPATH=..:tests /Users/bytedance/worktrees/byaan-data-studio-p0/.venv/bin/python -m pytest server/tests/test_dashboard_contract_schemas.py server/tests/test_dashboard_execution_service.py server/tests/test_dashboard_legacy_tool_gating.py server/tests/test_dashboard_lifecycle_service.py server/tests/test_dashboard_mcp_contract.py server/tests/test_dashboard_persistence_migration.py server/tests/test_dashboard_rest_api.py server/tests/test_dashboard_security_regressions.py server/tests/test_filter_bootstrap.py server/tests/test_filter_pipeline.py server/tests/test_filter_tools_config_merge.py server/tests/test_share_object_authorization.py server/tests/test_share_secret_redaction.py -q` -> `92 passed, 68 warnings`.
- `PYTHONPATH=..:tests /Users/bytedance/worktrees/byaan-data-studio-p0/.venv/bin/python -m pytest server/tests/test_migration_chain_hardening.py -q` -> `5 passed, 7 warnings`.
- `PYTHONPATH=..:tests /Users/bytedance/worktrees/byaan-data-studio-p0/.venv/bin/python -m pytest server/tests/test_dashboard_contract_schemas.py server/tests/test_dashboard_execution_service.py server/tests/test_dashboard_legacy_tool_gating.py server/tests/test_dashboard_lifecycle_service.py server/tests/test_dashboard_mcp_contract.py server/tests/test_dashboard_persistence_migration.py server/tests/test_dashboard_rest_api.py server/tests/test_dashboard_security_regressions.py -q` -> `39 passed, 68 warnings`.
- `cd client && pnpm lint` -> passed with existing `0 errors, 357 warnings`.
- `cd client && pnpm build:check` -> passed with existing CSS/chunk warnings.
- Temporary full browser smoke on `127.0.0.1:15173` frontend + `127.0.0.1:18080` backend + fresh SQLite DB -> `ok: true`, `pageerror=0`, `consoleError=0`, `requestfailed=0`, `http5xx=0`; screenshots retained under `/tmp/byaan-dashboard-full-verify-1786862803/screens-after-fix-4`.
- `git diff --check` -> passed.

## 2026-08-16 15:24 CST - Phase 0 Structured Dashboard Query Manifest Filters

Commit: `858e72282357478a5cd8805fcfacf0e8fd4dd040`.

Scope:

- Structured dashboard query and preview now resolve requested `data_view_ids` from the selected immutable manifest and validate filters before any saved-query, semantic metric, or context execution.
- Filter payloads are accepted only when the key matches an applicable manifest filter `id` or `field`, the filter is scoped to the selected data view, and the field is declared in that data view's `filter_fields`.
- Accepted filters are normalized into manifest field names for `DashboardRun.normalized_filters`, filter digest, saved-query filter compilation, REST responses, and MCP compact runs.
- Required filters, conflicting `id`/`field` aliases, basic type mismatches, and values outside manifest `domain` are rejected before execution.
- REST and MCP regression coverage now proves unknown raw filters such as `raw_sql` are rejected before query execution. The legacy viewer batch path remains covered by `test_dashboard_security_regressions.py` for same-tenant/dashboard-notebook binding.

Evidence:

- `PYTHONPATH=..:tests /Users/bytedance/worktrees/byaan-data-studio-p0/.venv/bin/python -m pytest server/tests/test_dashboard_execution_service.py server/tests/test_dashboard_rest_api.py server/tests/test_dashboard_mcp_contract.py server/tests/test_dashboard_security_regressions.py -q` -> `29 passed, 79 warnings`.
- `PYTHONPATH=..:tests /Users/bytedance/worktrees/byaan-data-studio-p0/.venv/bin/python -m ruff check server/services/dashboard.py server/tests/test_dashboard_execution_service.py server/tests/test_dashboard_rest_api.py server/tests/test_dashboard_mcp_contract.py` -> passed with existing removed-rule warning.
- `git diff --check` -> passed.

## 2026-08-16 15:31 CST - Phase 0 Share And MCP Error Redaction

Commit: `b4310756f9682eca81ca10e8da417ef120f71c0a`.

Scope:

- Extended `server.utils.error_sanitizer` to redact free-form and nested error payloads containing password, token, raw token, verifier, credential, connection strings, and SQL/query text.
- `CustomLogger` now sanitizes messages and PostHog context before emitting logs/events, reducing leak risk when callers pass raw worker or exception details.
- Worker-backed notebook share/export routes now sanitize worker error bodies and generic exception details before logs and HTTP responses.
- MCP `_json_error` now sanitizes both HTTPException details and generic exception messages before returning errors to agents.
- Added regression coverage proving worker errors and MCP errors do not leak password, token, verifier, credential, or unauthorized SQL strings.

Evidence:

- `PYTHONPATH=..:tests /Users/bytedance/worktrees/byaan-data-studio-p0/.venv/bin/python -m pytest server/tests/test_error_sanitizer.py server/tests/test_share_secret_redaction.py server/tests/test_share_object_authorization.py server/tests/test_dashboard_execution_service.py server/tests/test_dashboard_rest_api.py server/tests/test_dashboard_mcp_contract.py server/tests/test_dashboard_security_regressions.py -q` -> `43 passed, 80 warnings`.
- `PYTHONPATH=..:tests /Users/bytedance/worktrees/byaan-data-studio-p0/.venv/bin/python -m ruff check server/utils/error_sanitizer.py server/utils/custom_logger.py server/routers/exports.py server/mcp/tool_wrappers.py server/tests/test_error_sanitizer.py server/tests/test_share_secret_redaction.py server/tests/test_dashboard_mcp_contract.py` -> passed with existing removed-rule warning.
- `git diff --check` -> passed.

## 2026-08-16 15:41 CST - Dashboard Full Validation Refresh

Scope:

- Re-ran the dashboard validation matrix from the integration worktree without mutating or restarting the existing `127.0.0.1:8080` runtime.
- Used a fresh isolated SQLite database and app server at `127.0.0.1:18080`.
- Validated both Vite dev frontend at `127.0.0.1:15173` and production preview frontend at `127.0.0.1:15174`.
- Browser smoke seeded structured, policy-guarded, and legacy dashboard fixtures, then covered direct `/notebook/{id}/preview`, governed dashboard data, lineage, policy denial, legacy fallback, and mobile rendering.

Evidence:

- `PYTHONPATH=..:tests /Users/bytedance/worktrees/byaan-data-studio-p0/.venv/bin/python -m pytest tests/test_dashboard_contract_schemas.py tests/test_dashboard_execution_service.py tests/test_dashboard_legacy_tool_gating.py tests/test_dashboard_lifecycle_service.py tests/test_dashboard_mcp_contract.py tests/test_dashboard_persistence_migration.py tests/test_dashboard_rest_api.py tests/test_dashboard_security_regressions.py tests/test_filter_bootstrap.py tests/test_filter_pipeline.py tests/test_filter_tools_config_merge.py tests/test_share_object_authorization.py tests/test_share_secret_redaction.py tests/test_migration_chain_hardening.py -q` -> `106 passed, 87 warnings`.
- `PYTHONPATH=..:tests /Users/bytedance/worktrees/byaan-data-studio-p0/.venv/bin/python -m ruff check server/services/dashboard.py server/routers/dashboard.py server/mcp/tool_wrappers.py server/tests/test_dashboard_execution_service.py server/tests/test_dashboard_rest_api.py server/tests/test_dashboard_mcp_contract.py server/tests/test_dashboard_security_regressions.py server/tests/test_filter_pipeline.py` -> passed.
- `cd client && pnpm lint` -> passed with existing `0 errors, 357 warnings`.
- `cd client && pnpm build:check` -> passed with existing CSS/chunk warnings.
- `BASE_URL=http://127.0.0.1:15173 API_URL=http://127.0.0.1:18080 SCREEN_DIR=/tmp/byaan-dashboard-full-verify-NNsQJt/screens pnpm smoke:dashboard` -> `ok: true`, `pageerror=0`, `consoleError=0`, `requestfailed=0`, `http5xx=0`.
- `BASE_URL=http://127.0.0.1:15174 API_URL=http://127.0.0.1:18080 SCREEN_DIR=/tmp/byaan-dashboard-full-verify-NNsQJt/screens-preview pnpm smoke:dashboard` -> `ok: true`, `pageerror=0`, `consoleError=0`, `requestfailed=0`, `http5xx=0`.
- Screenshots retained under `/tmp/byaan-dashboard-full-verify-NNsQJt/screens` and `/tmp/byaan-dashboard-full-verify-NNsQJt/screens-preview`.
