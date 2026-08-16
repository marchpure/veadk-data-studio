# Evaluation + Sharing Governance P0 Progress

CURRENT_PHASE: Complete — real `127.0.0.1:8080` Release Gate passed on the current governance integration branch. Completed slices: integration worktree init, dashboard merge integration gates, Phase 0 Sharing 安全止血, Phase 1 Evaluation 权威模型, Phase 2 runner lease/gate tracer, Phase 2 runner resumability/artifact tracer, Phase 2 promotion blocking, Phase 3 Evaluation REST runner/promotion API, Phase 3 feedback-to-case and advisor draft compatibility API, Phase 3/4 Evaluation MCP wrappers/shared serializers, Phase 3/4 Evaluation REST read surface, Phase 3/4 Human UI workspace and advisor verify/regress/review/apply REST surfaces, Phase 3/4 browser/MCP parity smoke, Phase 5 canonical Sharing grant/secret/viewer-session foundation, Phase 5 folder dashboard canonical compatibility, Phase 5 worker-backed notebook share canonical compatibility, Phase 5 canonical Sharing read surface and folder notebook compatibility, Phase 5 local canonical Sharing integration smoke, migration bridge for the inherited 8080 database, canonical Sharing timestamp compatibility, and final real 8080 Release Gate. Next slice: release handoff only; no implementation work remains in this P0 branch.

## Phase 0 Slice Checklist

- [x] `GET /notebooks/{id}/share`, JSON share list, and manage endpoints never return `password`, `verifier`, or raw token.
- [x] `ShareModal.tsx` removes display/copy of saved passwords; password is input-only during create/rotate and is never read back.
- [x] share/create/delete/rotate/export use correct share/export action scope and unified object authorization for tenant, owner/grant, asset, version, and action. Worker-backed notebook share/export/manage endpoints and folder-backed notebook/dashboard share/version/snapshot manage endpoints now enforce tenant + owner + action scope through `server.auth.object_authorizer`; future canonical grant checks remain for Phase 5.
- [x] viewer sessions bind and validate issuer, audience, user, tenant, grant, asset, version, token id, issued-at, not-before, expiry, and revocation/rotation identity.
- [x] structured dashboard query only accepts immutable manifest `data_view_id` plus validated filters; legacy path is tenant/dashboard-version/notebook bound.
- [x] errors, logs, and audit events never leak password, token, verifier, credentials, cross-tenant objects, or unauthorized SQL.

## Environment Side-Effect Registration

- `2026-08-16 13:11 CST`: this session previously created test data on the existing `127.0.0.1:8080` runtime while working on an unrelated dashboard validation task before goal correction.
- Created folder: ID `b268fd5a-8bb4-4ee6-9447-03edc9c142f0`; name not confirmed from read-only evidence and must be verified during the Release Gate.
- Shared dashboard: ID `9775fc11-8891-493d-8715-ee6dfbc31cbc`; selected dashboard notebook ID `1acfaeff-4dae-434f-aa0b-eba828c18669`.
- Reason: temporary validation data for dashboard sharing behavior on the active 8080 instance.
- Current state: cleaned during the final `127.0.0.1:8080` Release Gate; `REGISTERED_FOLDER_ID=b268fd5a-8bb4-4ee6-9447-03edc9c142f0` was present before cleanup, delete returned `204`, and post-delete lookup returned `404`.
- Cleanup owner/timing: completed by this governance integration session during the final Release Gate after Phase 0-5 implementation and local gates passed.

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

## 2026-08-16 15:55 CST - Phase 0 Folder-Backed Share Object Authorization

Scope:

- Folder notebook share/unshare now uses `dashboard.share` and the shared notebook object authorizer before writing folder share rows.
- Folder notebook snapshot refresh now uses `dashboard.export` and the shared notebook object authorizer before exporting snapshot data.
- Folder dashboard share/unshare/version update now resolves the dashboard version to its notebook and uses `dashboard.share` plus the same tenant/owner/action authorizer before mutating the folder grant.
- Frontend folder-share affordances now follow `dashboard.share` rather than the legacy `folder.share_notebook` scope.
- Added regression coverage proving a same-tenant member with legacy folder scope cannot folder-share their own notebook/dashboard without `dashboard.share`, cannot refresh an owner notebook snapshot before object authorization, and cannot manage folder dashboard grants; owner positive sharing remains valid.

Evidence:

- `PYTHONPATH=..:tests /Users/bytedance/worktrees/byaan-data-studio-p0/.venv/bin/python -m pytest tests/test_share_object_authorization.py tests/test_share_secret_redaction.py tests/test_dashboard_security_regressions.py -q` -> `24 passed, 8 warnings`.
- `PYTHONPATH=..:tests /Users/bytedance/worktrees/byaan-data-studio-p0/.venv/bin/python -m ruff check routers/folders.py auth/object_authorizer.py tests/test_share_object_authorization.py` -> passed with existing removed-rule warning.
- `cd client && pnpm lint` -> passed with existing `0 errors, 357 warnings`.
- `cd client && pnpm build:check` -> passed with existing CSS/chunk warnings.
- `git diff --check` -> passed.

## 2026-08-16 17:34 CST - Phase 1 Evaluation Authoritative Model

Commit:

- Atomic Phase 1 commit message: `governance: add evaluation authoritative model`.
- Commit SHA authority after push: `git log -1 --format=%H` for the above commit. A commit cannot contain its own final SHA without changing that SHA; the session handoff records the pushed SHA after commit creation.

Scope:

- Added strict Evaluation contract schemas for case manifests and target snapshots, including read-only ground-truth SQL validation and required pin blocker reporting.
- Added registered SQLAlchemy models for the authoritative Evaluation domain: suites, suite versions, cases, target snapshots, runs, case runs, assessments, overrides, artifacts, advisor change sets, advisor suggestions, promotion decisions, and audit events.
- Added additive Alembic revision `add_evaluation_authoritative_model` after `backfill_legacy_dashboard_assets`; it creates only new Evaluation tables/indexes and leaves `conversation_evaluations` and `skill_suggestions` untouched.
- Added repository/service primitives for Phase 2 runner work: target snapshot persistence, preflight run creation, audit event persistence, suite version publish, and immutable published manifest enforcement.
- Updated migration-chain hardening so the single Alembic head is now `add_evaluation_authoritative_model`.

Evidence:

- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_evaluation_contract_schemas.py tests/test_evaluation_persistence_migration.py tests/test_evaluation_service.py tests/test_migration_chain_hardening.py -q` -> `14 passed, 9 warnings`.
- `cd server && uv run ruff check schemas/evaluation.py models/evaluation.py repositories/evaluation.py services/evaluation.py migrations/versions/add_evaluation_authoritative_model.py tests/test_evaluation_contract_schemas.py tests/test_evaluation_persistence_migration.py tests/test_evaluation_service.py tests/test_migration_chain_hardening.py` -> passed with the existing removed-rule warning.
- `cd server && PYTHONPATH=..:tests uv run alembic heads` -> `add_evaluation_authoritative_model (head)`.
- `cd server && uv run python - <<'PY' ... import server.models ...` -> confirmed `evaluation_suites` and `evaluation_audit_events` are registered in `Base.metadata`.

Phase 2 next steps:

- Implement DB-backed Evaluation runner leasing, run/case-run execution state transitions, heartbeat/stop behavior, idempotency, artifact capture, and resumability.
- Wire grader gate evaluation over stored case results with security hard-fail semantics from `gate_policy_json`.
- Add regression coverage for runner retry/idempotency, immutable suite version execution, and promotion blocking when verification/regression gates fail.

## 2026-08-16 17:45 CST - Phase 2 Evaluation Runner Lease And Gate Tracer

Scope:

- Added DB-backed runner claim flow for queued Evaluation runs, including lease holder, lease expiry, heartbeat timestamp, running status, and audit event.
- Added run completion flow that persists immutable case runs and assessments for every suite case in a published suite version.
- Added gate summary calculation from stored case outcomes plus `gate_policy_json`, including security hard-fail semantics and overall pass-rate enforcement.
- Added regression coverage proving a second worker cannot steal an active lease, case results are persisted as immutable DB rows, hard-fail assessments are recorded, and the run finishes failed when the gate policy demands it.

Evidence:

- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_evaluation_runner_service.py -q` -> `1 passed, 11 warnings`.
- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_evaluation_contract_schemas.py tests/test_evaluation_persistence_migration.py tests/test_evaluation_service.py tests/test_evaluation_runner_service.py tests/test_migration_chain_hardening.py -q` -> `15 passed, 12 warnings`.
- `cd server && uv run ruff check repositories/evaluation.py services/evaluation.py tests/test_evaluation_runner_service.py tests/test_evaluation_service.py` -> passed with the existing removed-rule warning.

Remaining Phase 2 work:

- Add heartbeat refresh, stop-request handling, expired-lease reclaim, and retry/resume idempotency semantics.
- Persist evaluation artifacts for runner inputs/outputs and grader diagnostics.
- Wire promotion decisions so advisor/promote flows are blocked unless verification and regression Evaluation runs satisfy gate policy.

## 2026-08-16 17:56 CST - Phase 2 Runner Resumability And Artifact Tracer

Scope:

- Made preflight run creation idempotent per suite version and idempotency key so retries return the existing run instead of tripping the DB uniqueness constraint or creating duplicate target snapshots.
- Extended runner leasing with expired-lease reclaim semantics; a different worker can claim an expired running run and the attempt counter advances.
- Added heartbeat refresh with worker ownership checks; stale workers cannot heartbeat or complete runs after reclaim.
- Added stop-request handling so a leased worker sees `stop_requested`, marks the run `canceled`, records audit, and stops extending the run as active work.
- Added run-level artifact persistence with immutable `evaluation_artifacts` rows and content hashes for runner diagnostics.

Evidence:

- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_evaluation_runner_service.py -q` -> `3 passed, 14 warnings`.
- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_evaluation_contract_schemas.py tests/test_evaluation_persistence_migration.py tests/test_evaluation_service.py tests/test_evaluation_runner_service.py tests/test_migration_chain_hardening.py -q` -> `17 passed, 15 warnings`.
- `cd server && uv run ruff check repositories/evaluation.py services/evaluation.py tests/test_evaluation_runner_service.py tests/test_evaluation_service.py` -> passed with the existing removed-rule warning.

Remaining Phase 2 work:

- Wire promotion decisions so advisor/promote flows are blocked unless verification and regression Evaluation runs satisfy gate policy.
- Add promotion-decision audit evidence for accepted/rejected advisor changesets.

## 2026-08-16 18:05 CST - Phase 2 Promotion Gate Blocking

Scope:

- Added promotion-decision service flow for advisor change sets.
- Promotion is accepted only when both verification and regression Evaluation runs have gate decisions of `passed`; missing/failed/canceled/blocked runs reject promotion.
- Rejected promotions update the advisor change set to `rejected`; accepted promotions update it to `promoted`.
- Promotion decisions persist verification/regression run IDs, actor/audit metadata, rationale, and gate outcomes for release review.
- Added regression coverage for a failed regression gate blocking promotion and a subsequent passed regression gate allowing promotion.

Evidence:

- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_evaluation_runner_service.py -q` -> `4 passed, 14 warnings`.
- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_evaluation_contract_schemas.py tests/test_evaluation_persistence_migration.py tests/test_evaluation_service.py tests/test_evaluation_runner_service.py tests/test_migration_chain_hardening.py -q` -> `18 passed, 15 warnings`.
- `cd server && uv run ruff check repositories/evaluation.py services/evaluation.py tests/test_evaluation_runner_service.py tests/test_evaluation_service.py` -> passed with the existing removed-rule warning.

Phase 3 next steps:

- Expose Evaluation suite/run/promotion primitives through REST/MCP APIs with tenant/action authorization.
- Add UI/API wiring for feedback-to-evaluation-case and advisor change-set review.
- Add end-to-end tests showing feedback creates cases, advisor changesets require Evaluation gates, and promotion evidence is visible without leaking secrets.

## 2026-08-16 18:32 CST - Phase 3 Evaluation REST Runner And Promotion API

Scope:

- Added `server/routers/evaluation.py` and registered it under `/api/evaluation`.
- Exposed tenant-scoped REST endpoints for Evaluation runner preflight, claim, heartbeat, stop, artifact recording, completion, and advisor change-set promotion decisions.
- REST endpoints call the existing `EvaluationService` primitives rather than duplicating runner or promotion logic.
- Runner endpoints require authenticated tenant action scope via existing dashboard query scope; promotion decisions require dashboard publish scope so member users cannot promote advisor changesets.
- Response serializers return stable run/artifact/promotion evidence and omit raw artifact content, preventing submitted diagnostic payloads from leaking back through API responses.
- Added API regression coverage for idempotent preflight, runner lease lifecycle, artifact redaction, completion gate summary, tenant scoping, and promotion authorization/evidence.

Evidence:

- `cd server && PYTHONPATH=..:tests /Users/bytedance/worktrees/byaan-data-studio-p0/.venv/bin/python -m pytest tests/test_evaluation_rest_api.py tests/test_evaluation_runner_service.py tests/test_evaluation_service.py -q` -> `9 passed, 18 warnings`.
- `cd server && PYTHONPATH=..:tests /Users/bytedance/worktrees/byaan-data-studio-p0/.venv/bin/python -m pytest tests/test_evaluation_contract_schemas.py tests/test_evaluation_persistence_migration.py tests/test_evaluation_service.py tests/test_evaluation_runner_service.py tests/test_evaluation_rest_api.py tests/test_migration_chain_hardening.py -q` -> `21 passed, 18 warnings`.
- `cd server && PYTHONPATH=..:tests /Users/bytedance/worktrees/byaan-data-studio-p0/.venv/bin/python -m ruff check routers/evaluation.py tests/test_evaluation_rest_api.py ../server/main.py` -> passed with the existing removed-rule warning.
- `git diff --check` -> passed.

Remaining Phase 3 work:

- Add feedback-to-evaluation-case REST adapter and compatibility hooks for `ConversationEvaluation` / `SkillSuggestion`.
- Add advisor change-set review/apply surfaces that expose typed patch evidence while preserving Evaluation gate requirements.
- Add MCP wrapper and Human UI wiring against the same service/auth serializers.

## 2026-08-16 19:05 CST - Phase 3 Feedback-To-Case And Advisor Draft Compatibility API

Scope:

- Added compatibility service flows that keep legacy `ConversationEvaluation` and `SkillSuggestion` intact while creating authoritative Evaluation objects.
- Added a tenant-scoped feedback endpoint that promotes mistake/ambiguous legacy conversation evaluations into draft `EvaluationCase` rows with provenance, taxonomy/missed-instruction metadata, trace/principal fields, and idempotent case-key dedupe.
- Draft feedback cases update the target draft suite version manifest/count and write append-only Evaluation audit events; published suite versions remain immutable.
- Added a tenant-scoped advisor endpoint that converts pending legacy skill suggestions into draft-only `AdvisorChangeSet` plus typed `AdvisorSuggestion` patch rows.
- Advisor compatibility pins stable target refs, base version refs, base etags, evidence, and affected case IDs without mutating the target skill or legacy suggestion.
- Response payloads and stored draft evidence/patches are sanitized through the existing error redaction utility so tokens, passwords, credentials, and SQL do not leak through Evaluation APIs.

Evidence:

- `cd server && PYTHONPATH=..:tests /Users/bytedance/worktrees/byaan-data-studio-p0/.venv/bin/python -m pytest tests/test_evaluation_feedback_advisor_api.py -q` -> `2 passed, 8 warnings`.
- `cd server && PYTHONPATH=..:tests /Users/bytedance/worktrees/byaan-data-studio-p0/.venv/bin/python -m pytest tests/test_evaluation_contract_schemas.py tests/test_evaluation_persistence_migration.py tests/test_evaluation_service.py tests/test_evaluation_runner_service.py tests/test_evaluation_rest_api.py tests/test_evaluation_feedback_advisor_api.py tests/test_migration_chain_hardening.py -q` -> `23 passed, 18 warnings`.
- `cd server && PYTHONPATH=..:tests /Users/bytedance/worktrees/byaan-data-studio-p0/.venv/bin/python -m ruff check repositories/evaluation.py services/evaluation.py routers/evaluation.py tests/test_evaluation_feedback_advisor_api.py tests/test_evaluation_rest_api.py` -> passed with the existing removed-rule warning.
- `git diff --check` -> passed.

Remaining Phase 3/4 work:

- Add explicit advisor verify/regress/review endpoints and MCP wrappers around the same service calls.
- Add Human UI surfaces for suite/case/run/advisor/feedback review.
- Add end-to-end tests proving failed-set verification and full-suite regression are required before advisor apply/promotion.

## 2026-08-16 18:43 CST - Phase 3/4 Evaluation MCP Wrappers And Shared Serializers

Scope:

- Added shared Evaluation serializers under `server/serializers/evaluation.py` and switched the REST Evaluation router to use them so REST and MCP return the same redacted run/case/advisor evidence shapes.
- Added Evaluation service/repository read APIs for suite search/describe, case listing, run reports, run comparison, and failure summaries.
- Added service-backed case draft creation for MCP/Human usage; draft cases validate `EvaluationExpectedContract`, update draft suite manifest/count, and write append-only audit events while published versions stay immutable.
- Added Advisor verification/regression run creation via `EvaluationService.create_advisor_gate_run`; it queues immutable Evaluation runs and pins them onto the draft `AdvisorChangeSet` without applying patches.
- Registered MCP tools: `search_evaluation_suites`, `describe_evaluation_suite`, `list_evaluation_cases`, `create_evaluation_case_draft`, `preview_evaluation_ground_truth`, `run_evaluation`, `get_evaluation_run`, `compare_evaluation_runs`, `describe_evaluation_failure`, `create_advisor_change_set`, `run_advisor_verification`, `run_advisor_regression`, and `submit_evaluation_feedback`.
- MCP wrappers enforce tenant role scopes through the same dashboard action scopes already used by REST: read for inspect/report, query for run creation, edit for draft/advisor/feedback mutation; sensitive SQL/token/password fields are redacted in responses.

Evidence:

- `cd server && PYTHONPATH=..:tests /Users/bytedance/worktrees/byaan-data-studio-p0/.venv/bin/python -m pytest tests/test_evaluation_mcp_contract.py tests/test_evaluation_contract_schemas.py tests/test_evaluation_persistence_migration.py tests/test_evaluation_service.py tests/test_evaluation_runner_service.py tests/test_evaluation_rest_api.py tests/test_evaluation_feedback_advisor_api.py tests/test_migration_chain_hardening.py -q` -> `25 passed, 18 warnings`.
- `cd server && PYTHONPATH=..:tests /Users/bytedance/worktrees/byaan-data-studio-p0/.venv/bin/python -m pytest tests/test_evaluation_rest_api.py tests/test_evaluation_feedback_advisor_api.py -q` -> `5 passed, 11 warnings`.
- `cd server && PYTHONPATH=..:tests /Users/bytedance/worktrees/byaan-data-studio-p0/.venv/bin/python -m ruff check mcp/tool_wrappers.py mcp/tools.py services/evaluation.py repositories/evaluation.py routers/evaluation.py serializers/evaluation.py tests/test_evaluation_mcp_contract.py tests/test_evaluation_rest_api.py tests/test_evaluation_feedback_advisor_api.py` -> passed with the existing removed-rule warning.

Remaining Phase 3/4 work:

- Add Human UI surfaces for suite inventory/detail, case editor, run compare, failure drawer, feedback review, and advisor staged patch review.
- Add explicit REST review/apply endpoints for advisor verification/regression lifecycle if the UI needs review-specific shapes beyond the existing runner/promotion endpoints.
- Add end-to-end browser/MCP parity tests showing failed-set verification plus full-suite regression evidence is visible before promotion/apply.

## 2026-08-16 21:08 CST - Final Real 8080 Release Gate

Scope:

- Fixed the canonical Sharing timestamp compatibility issue found during the first real 8080 gate attempt.
- `SharingService` now writes naive UTC timestamps for `sharing_grants.revoked_at`, `sharing_viewer_sessions.issued_at`, `sharing_viewer_sessions.expires_at`, and `sharing_secrets.rotated_at`, matching the canonical Sharing models' `TIMESTAMP(timezone=False)` columns and the existing server pattern for DB timestamps.
- Added regression assertions proving issued, expiry, revoke, and `_now()` timestamps are naive UTC for DB writes.
- Built and deployed current integration commit `28813672936f417c23cf2e9ada3b76af031055e9` to the real 8080 runtime as image `byaan:selfhosted-governance-p0-2881367`.
- Replaced the previous 8080 container `byaan-governance-p0-976c5cf-8080` with `byaan-governance-p0-2881367-8080`, preserving the existing persistent volume `byaan_data_studio_p0_9718bf6_8080`.
- Added `server/scripts/sharing_release_gate_8080.py`, a real 8080 gate script that logs in as the self-hosted admin, discovers the tenant, creates a temporary folder/notebook/dashboard fixture, verifies canonical folder notebook and folder dashboard Sharing evidence through real REST, verifies worker-backed notebook sharing is safely gated when external sharing is disabled, deletes the temporary fixture, and cleans the previously registered dashboard test folder.

Evidence:

- Timestamp fix commit: `28813672936f417c23cf2e9ada3b76af031055e9` (`governance: use naive utc sharing timestamps`), pushed to `veadk-data-studio/integration/evaluation-sharing-governance-p0`.
- `cd server && uv run ruff check services/sharing.py tests/test_sharing_canonical_service.py scripts/sharing_release_gate_8080.py` -> passed with the existing removed-rule warning.
- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_sharing_canonical_service.py tests/test_share_object_authorization.py tests/test_sharing_read_surface.py tests/test_dashboard_security_regressions.py -q` -> `29 passed, 9 warnings`.
- `PYTHONPATH=. uv run python server/scripts/sharing_governance_smoke.py` -> `ok: true`; canonical notebook surfaces `folder_notebook`, `html_notebook_share`, and `json_notebook_share`; canonical dashboard grant count `1`; revoked notebook surface statuses all `revoked`.
- `cd server && PYTHONPATH=..:tests uv run alembic heads` -> `add_canonical_sharing_model (head)`.
- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_share_secret_redaction.py tests/test_share_object_authorization.py tests/test_dashboard_security_regressions.py tests/test_sharing_canonical_service.py tests/test_sharing_read_surface.py tests/test_sharing_persistence_migration.py tests/test_migration_chain_hardening.py -q` -> `39 passed, 9 warnings`.
- `DOCKER_BUILDKIT=1 docker build -f Dockerfile.self-hosted -t byaan:selfhosted-governance-p0-2881367 .` -> image built successfully with only existing frontend CSS/chunk warnings.
- Current 8080 container: `b4906e451416 byaan:selfhosted-governance-p0-2881367 byaan-governance-p0-2881367-8080`, port mapping `0.0.0.0:8080->80/tcp`.
- Runtime env check: `APP_MODE=self-hosted`, `BYAAN_VERSION=governance-p0-2881367`, `DATA_DIR=/data`, `FRONTEND_URL=http://127.0.0.1:8080`, `PUBLIC_BASE_URL=http://127.0.0.1:8080`, `MASTER_USER_EMAIL=admin@example.com`, `MASTER_USER_PASSWORD=password`.
- Container Alembic current with explicit PostgreSQL `DATABASE_URL` -> `add_canonical_sharing_model (head)`.
- `GET http://127.0.0.1:8080/api/sharing/grants` without auth -> `401`, proving the canonical Sharing route is mounted and protected.
- `POST /api/auth/login` with `admin@example.com / password` -> `200` and bearer token.
- `BASE_URL=http://127.0.0.1:8080 CONTAINER=byaan-governance-p0-2881367-8080 RUN_ID=2881367 PYTHONPATH=. uv run python server/scripts/sharing_release_gate_8080.py` -> `ok: true`.
- Release gate fixture: folder `e0211fe6-47c5-4d8d-9be3-5c4e7fdba471`, notebook `3d20213d-7468-4f45-b967-b01d19d84dbc`, dashboard `82496518-f364-4a34-9f19-125326989165`.
- Canonical folder evidence: folder notebook surface `folder_notebook`, folder dashboard surface `folder_dashboard`, folder notebook revoked status `revoked`.
- Worker-backed notebook share gate: `403`, message `External sharing is not available in this deployment mode`, which is expected for this self-hosted runtime with external sharing disabled.
- Temporary fixture cleanup: folder delete `204`; notebook delete `204`; subsequent folder lookup `404`; notebook no longer appears in `GET /api/notebooks`.
- Registered historical folder cleanup: folder `b268fd5a-8bb4-4ee6-9447-03edc9c142f0` was present before cleanup, delete returned `204`, post-delete lookup returned `404`.
- Container logs since the gate contain no `Traceback`, `ERROR`, `500`, `invalid input`, `offset-naive`, or `offset-aware` matches.

Final status:

- Phase 0-5 implementation and local gates are complete.
- Real `127.0.0.1:8080` Release Gate is complete.
- The previously registered 8080 side-effect folder is cleaned.
- No further implementation slice remains for Governance Integration P0.

## 2026-08-16 19:47 CST - Phase 3/4 Evaluation Browser And MCP Parity Smoke

Scope:

- Added isolated Evaluation seed and parity smoke scripts for a published suite with three cases, baseline/candidate runs, failed-set evidence, advisor ready/draft change sets, verification runs, regression runs, and redaction sentinels.
- Added a browser workspace smoke that exercises the real REST API and rendered Human UI: suite inventory/detail, cases, failed run failures, baseline/candidate comparison, advisor ready apply, draft verification/regression queueing, feedback provenance, settings/manifest, desktop screenshots, and mobile overflow check.
- Added an MCP parity smoke using the same seeded fixture IDs through the service-backed MCP wrappers for suite search/detail, case list, run detail, failure detail, comparison, and advisor verification/regression queueing.
- Fixed the Human UI advisor gate target snapshot pins to include Phase 1 required `prompt.version`, `prompt.prompt_hash`, `tool_registry_hash`, `skill_registry_hash`, and `llm.params_hash`.
- Normalized advisor `target_ref` prefixes such as `custom_skill:*` to a supported Evaluation `target_kind` (`agent_answer` for the seeded suite) before sending verification/regression requests, matching the authoritative backend enum.
- The browser smoke used isolated SQLite plus ports `127.0.0.1:18081` and `127.0.0.1:15175`; it did not touch, restart, or seed `127.0.0.1:8080`.

Evidence:

- `cd client && pnpm exec tsc -b --pretty false` -> passed.
- `cd client && pnpm exec eslint scripts/evaluation-workspace-smoke.mjs src/features/evaluation/pages/EvaluationWorkspacePage.tsx src/types/evaluation.ts` -> passed.
- `uv run ruff check server/scripts/seed_evaluation_smoke.py server/scripts/evaluation_mcp_parity_smoke.py` -> passed with the existing removed-rule warning.
- Isolated MCP parity smoke on a fresh SQLite DB -> `ok: true`, `case_count: 3`, `failure_count: 2`, `regression_count: 2`, `advisor_verification_status: queued`, `advisor_regression_status: queued`; fixture retained under `/tmp/byaan-evaluation-mcp-smoke-latest`.
- Isolated browser smoke on fresh seeded Evaluation fixture -> `ok: true`, `baseURL: http://127.0.0.1:15175`, `apiURL: http://127.0.0.1:18081`, `suiteId: 5b7bc357-5d9a-4427-8853-64677b2101f2`, `pageerror=0`, `consoleError=0`, `requestfailed=0`, `http5xx=0`; screenshots retained under `/tmp/byaan-evaluation-browser-smoke-GghD6x/screens-final`.
- Verified temporary smoke ports `18081` and `15175` were no longer listening after cleanup.

Remaining Phase 5 work:

- Implement canonical Sharing model/service for grants, secrets, immutable version binding, viewer sessions, audit, and revocation across notebook/dashboard/folder share flows.
- Port existing share/export/viewer REST, MCP, and Human UI paths onto the canonical Sharing service while preserving the Phase 0 redaction and authorization guarantees.
- Run the final real `127.0.0.1:8080` Release Gate only after Phase 5 local gates pass, including cleanup/verification of the previously registered dashboard test data.

## 2026-08-16 20:03 CST - Phase 5 Canonical Sharing Model And Service Foundation

Scope:

- Added additive canonical Sharing persistence for `sharing_grants`, `sharing_secrets`, `sharing_viewer_sessions`, `sharing_audit_events`, and `sharing_compatibility_links`.
- Registered canonical Sharing models in SQLAlchemy metadata so fresh test metadata and Alembic migration paths create the same tables.
- Added `SharingService` primitives for immutable dashboard public-link grants, password verifier storage/verification, viewer-session issue/require, grant revocation, viewer-session revocation, and sanitized audit events.
- Canonical grants bind tenant, object type, object id, immutable object version id, and version digest; dashboard grants reject draft or mutable versions.
- Canonical secrets store only salted PBKDF2 verifier hashes plus salt/algorithm metadata; plaintext passwords are never persisted or read back.
- Canonical viewer sessions keep a database token digest and bind the signed viewer token to grant/object/version claims; revoked grants invalidate existing sessions.
- The slice is foundation-only and does not yet replace existing notebook/dashboard/folder REST behavior; the next Phase 5 slice will port legacy share surfaces onto this service with compatibility links.

Evidence:

- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_sharing_persistence_migration.py tests/test_sharing_canonical_service.py tests/test_migration_chain_hardening.py -q` -> `11 passed, 9 warnings`.
- `cd server && uv run ruff check models/sharing.py services/sharing.py migrations/versions/add_canonical_sharing_model.py tests/test_sharing_persistence_migration.py tests/test_sharing_canonical_service.py tests/test_migration_chain_hardening.py` -> passed with the existing removed-rule warning.
- `cd server && PYTHONPATH=..:tests uv run alembic heads` -> `add_canonical_sharing_model (head)`.
- Fresh isolated SQLite `alembic upgrade head && alembic current` -> `add_canonical_sharing_model (head)`; evidence DB retained under `/tmp/byaan-sharing-migration-latest`.
- `PYTHONPATH=.. uv run python` import self-check for `SharingGrant`, `SharingSecret`, `SharingViewerSession`, `SharingAuditEvent`, and `SharingCompatibilityLink` -> `sharing model import ok`.
- `git diff --check` -> passed.

Remaining Phase 5 work:

- Port worker-backed notebook share create/list/delete/password-manage and export/import paths to create/read canonical grants and secrets while continuing to redact password/verifier/raw token fields.
- Port folder notebook/dashboard share and viewer session checks to canonical grants, compatibility links, and canonical viewer-session validation.
- Add REST/MCP serializers for canonical Sharing evidence and retain legacy response compatibility for existing UI flows.
- Run the final real `127.0.0.1:8080` Release Gate only after all Phase 5 local gates pass.

## 2026-08-16 20:18 CST - Phase 5 Folder Dashboard Canonical Sharing Compatibility

Scope:

- Folder dashboard share creation and version updates now upsert a canonical `sharing_grants` row plus a `sharing_compatibility_links` row for the legacy `folder_dashboards.id`.
- Canonical compatibility grants bind tenant, dashboard object type, dashboard asset/version identity, version digest when available, channel `folder`, audience `folder_member`, and active/revoked lifecycle state.
- Viewer dashboard access now issues the `viewer_session` cookie through `SharingService`, storing a canonical `sharing_viewer_sessions` digest while preserving the existing signed viewer token format and cookie contract.
- Viewer query/preflight validation now checks canonical viewer sessions first, including grant/object/version binding and database token digest; legacy token validation remains as a fallback for already-issued sessions.
- Canonical validation also checks that the linked legacy `folder_dashboards` grant still exists and still points at the same dashboard version, so deleting/rotating the legacy share invalidates the canonical viewer session.
- Existing Phase 0 object authorization and redaction behavior remains intact; worker-backed notebook sharing is not yet ported in this slice.

Evidence:

- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_share_object_authorization.py::test_owner_can_folder_share_notebook_and_dashboard_after_dashboard_share_authorization tests/test_dashboard_security_regressions.py::test_viewer_session_accepts_canonical_folder_dashboard_grant_and_rejects_revoked_legacy tests/test_dashboard_security_regressions.py::test_viewer_session_rejects_token_for_different_dashboard tests/test_sharing_canonical_service.py -q` -> `7 passed, 9 warnings`.
- `cd server && uv run ruff check services/sharing.py services/folder_service.py routers/folders.py tests/test_share_object_authorization.py tests/test_dashboard_security_regressions.py tests/test_sharing_canonical_service.py` -> passed with the existing removed-rule warning.
- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_share_object_authorization.py tests/test_share_secret_redaction.py tests/test_dashboard_security_regressions.py tests/test_sharing_canonical_service.py tests/test_sharing_persistence_migration.py tests/test_migration_chain_hardening.py -q` -> `36 passed, 9 warnings`.
- `cd server && PYTHONPATH=..:tests uv run alembic heads` -> `add_canonical_sharing_model (head)`.
- `git diff --check` -> passed.

Remaining Phase 5 work:

- Port worker-backed notebook share create/list/delete/password-manage and export/import paths to canonical grants and secrets without changing existing response redaction.
- Add canonical Sharing serializers/REST read surface for audit/debug evidence while retaining existing UI payload compatibility.
- Port folder notebook shares or explicitly map their legacy rows into canonical compatibility links.
- Run the final real `127.0.0.1:8080` Release Gate only after all Phase 5 local gates pass.

## 2026-08-16 20:32 CST - Phase 5 Worker-Backed Notebook Canonical Sharing Compatibility

Scope:

- Worker-backed HTML notebook share creation now upserts a canonical notebook `sharing_grants` row plus `sharing_compatibility_links` using legacy surface `html_notebook_share` and legacy id `notebook_id`.
- Worker-backed JSON notebook share creation now upserts a canonical notebook grant/link using legacy surface `json_notebook_share` and the worker returned share id.
- Password create/update/remove paths now rotate canonical `sharing_secrets` rows while storing only salted PBKDF2 verifier hashes; plaintext worker passwords are never persisted or returned.
- Worker-backed HTML and JSON share deletion now revokes the matching canonical grant and associated viewer sessions while preserving existing worker API behavior and UI response shapes.
- Existing worker response redaction remains unchanged: `password`, `verifier`, raw token fields, credentials, and SQL-like error details are not returned or logged.
- This slice does not yet expose a new canonical Sharing REST read surface and does not port folder notebook shares.

Evidence:

- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_share_secret_redaction.py tests/test_share_object_authorization.py::test_member_cannot_export_or_manage_owner_notebook_shares tests/test_sharing_canonical_service.py -q` -> `16 passed, 9 warnings`.
- `cd server && uv run ruff check routers/exports.py services/sharing.py tests/test_share_secret_redaction.py tests/test_share_object_authorization.py tests/test_sharing_canonical_service.py` -> passed with the existing removed-rule warning.
- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_share_secret_redaction.py tests/test_share_object_authorization.py tests/test_dashboard_security_regressions.py tests/test_sharing_canonical_service.py tests/test_sharing_persistence_migration.py tests/test_migration_chain_hardening.py -q` -> `37 passed, 9 warnings`.
- `cd server && PYTHONPATH=..:tests uv run alembic heads` -> `add_canonical_sharing_model (head)`.
- `git diff --check` -> passed.

Remaining Phase 5 work:

- Run an end-to-end local smoke covering dashboard folder share, notebook worker share, JSON share password rotation, canonical audit evidence, and legacy response compatibility before the final real `127.0.0.1:8080` Release Gate.

## 2026-08-16 20:23 CST - Phase 5 Canonical Sharing Read Surface And Folder Notebook Compatibility

Scope:

- Folder notebook share creation now upserts canonical `sharing_grants` and `sharing_compatibility_links` rows using legacy surface `folder_notebook` and the `folder_notebooks.id`.
- Folder notebook snapshot refresh updates the canonical grant mode/metadata and compatibility metadata without storing snapshot payloads or secrets in canonical grant metadata.
- Folder notebook unshare now revokes the linked canonical grant and associated viewer sessions before deleting the legacy `folder_notebooks` row.
- Added tenant-scoped REST read endpoints under `/api/sharing/grants` for canonical grant inventory and redacted grant evidence.
- Added MCP tools `list_sharing_grants` and `describe_sharing_grant`, backed by the same serializer as REST.
- Canonical Sharing evidence returns compatibility links, secret counts, `has_secret`, active viewer-session counts, and recent audit events; it does not return `salt`, `verifier_hash`, `token_digest`, plaintext password, raw token, credentials, or SQL-like details.

Evidence:

- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_share_object_authorization.py::test_owner_can_folder_share_notebook_and_dashboard_after_dashboard_share_authorization tests/test_sharing_read_surface.py tests/test_sharing_canonical_service.py -q` -> `7 passed, 9 warnings`.
- `cd server && uv run ruff check services/sharing.py services/folder_service.py serializers/sharing.py routers/sharing.py ../server/main.py mcp/tool_wrappers.py mcp/tools.py tests/test_share_object_authorization.py tests/test_sharing_read_surface.py` -> passed with the existing removed-rule warning.
- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_share_secret_redaction.py tests/test_share_object_authorization.py tests/test_dashboard_security_regressions.py tests/test_sharing_canonical_service.py tests/test_sharing_read_surface.py tests/test_sharing_persistence_migration.py tests/test_migration_chain_hardening.py -q` -> `39 passed, 9 warnings`.
- `cd server && PYTHONPATH=..:tests uv run alembic heads` -> `add_canonical_sharing_model (head)`.
- `git diff --check` -> passed.

Remaining Phase 5 work:

- Run an end-to-end local smoke covering folder dashboard share, folder notebook share, worker HTML/JSON notebook share/password rotation, canonical audit evidence, and legacy response compatibility.
- Run the final real `127.0.0.1:8080` Release Gate only after the local Phase 5 smoke passes, including verification/cleanup of the registered dashboard test folder.

## 2026-08-16 20:39 CST - Phase 5 Local Canonical Sharing Integration Smoke

Scope:

- Added `server/scripts/sharing_governance_smoke.py`, an isolated ASGI/SQLite smoke that does not touch `127.0.0.1:8080`.
- The smoke seeds a tenant, owner, notebook, folder, and immutable dashboard version in an in-memory SQLite database.
- The smoke exercises folder notebook share, folder dashboard share, worker-backed HTML notebook share, worker-backed JSON notebook share, JSON password rotation, canonical Sharing grant read evidence, legacy response redaction, and revocation of all notebook share surfaces.
- Worker, notebook export, compiled HTML export, feature flag, and dashboard cache warm paths are patched in-process so the script stays deterministic and avoids external worker or cache side effects.
- Redaction assertions fail the smoke if payloads expose plaintext passwords, raw tokens, verifier values, salts, restricted table names, credentials, or SQL-like details.

Evidence:

- `PYTHONPATH=. uv run python server/scripts/sharing_governance_smoke.py` -> `ok: true`; canonical notebook surfaces `folder_notebook`, `html_notebook_share`, and `json_notebook_share`; canonical dashboard grant count `1`; revoked notebook surface statuses all `revoked`.
- `cd server && uv run ruff check scripts/sharing_governance_smoke.py` -> passed with the existing removed-rule warning.
- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_share_secret_redaction.py tests/test_share_object_authorization.py tests/test_dashboard_security_regressions.py tests/test_sharing_canonical_service.py tests/test_sharing_read_surface.py tests/test_sharing_persistence_migration.py tests/test_migration_chain_hardening.py -q` -> `39 passed, 9 warnings`.
- `cd server && PYTHONPATH=..:tests uv run alembic heads` -> `add_canonical_sharing_model (head)`.
- `git diff --check` -> passed.

Remaining Phase 5 work:

- Run the final real `127.0.0.1:8080` Release Gate, including verifying the current listener before any interaction, exercising the canonical Sharing flows on the real runtime, and cleaning up the previously registered dashboard test folder only during that gate.

## 2026-08-16 19:17 CST - Phase 3/4 Evaluation Human UI And Advisor REST Lifecycle

Scope:

- Added explicit advisor REST lifecycle endpoints for suite-version change-set inventory, advisor review, verification run creation, regression run creation, and apply/promotion decision.
- Advisor review returns the staged change set, typed suggestions, verification/regression run evidence, promotion history, and a computed `ready_to_apply` gate summary without applying patches directly.
- Advisor verification/regression endpoints call `EvaluationService.create_advisor_gate_run`; apply calls the existing promotion gate decision so published assets are still protected by verification and regression pass evidence.
- Added a client Evaluation API service and typed Evaluation domain models for suites, versions, cases, runs, failures, comparisons, advisor reviews, and target snapshots.
- Added a real `/evaluation` workspace in the existing app shell with suite inventory, suite detail tabs for Cases/Runs/Advisor/Feedback/Settings, run comparison, failure/case-run drilldowns, feedback provenance review, and advisor staged patch review with Verify/Regress/Apply actions.
- Added route coverage for enterprise, community, and legacy local desktop flows plus a sidebar navigation entry using the existing dark operational workspace style.

Evidence:

- `cd server && PYTHONPATH=..:tests /Users/bytedance/worktrees/byaan-data-studio-p0/.venv/bin/python -m pytest tests/test_evaluation_rest_api.py -q` -> `5 passed, 11 warnings`.
- `cd server && PYTHONPATH=..:tests /Users/bytedance/worktrees/byaan-data-studio-p0/.venv/bin/python -m pytest tests/test_evaluation_contract_schemas.py tests/test_evaluation_persistence_migration.py tests/test_evaluation_service.py tests/test_evaluation_runner_service.py tests/test_evaluation_rest_api.py tests/test_evaluation_feedback_advisor_api.py tests/test_evaluation_mcp_contract.py tests/test_migration_chain_hardening.py -q` -> `27 passed, 18 warnings`.
- `cd server && PYTHONPATH=..:tests /Users/bytedance/worktrees/byaan-data-studio-p0/.venv/bin/python -m ruff check routers/evaluation.py services/evaluation.py repositories/evaluation.py tests/test_evaluation_rest_api.py` -> passed with the existing removed-rule warning.
- `cd client && pnpm exec tsc -b --pretty false` -> passed.
- `cd client && pnpm exec eslint src/features/evaluation/pages/EvaluationWorkspacePage.tsx src/services/evaluation.ts src/types/evaluation.ts src/App.tsx src/components/CollapsibleSidebar.tsx --quiet` -> passed.
- `cd client && pnpm lint` -> passed with existing `0 errors, 357 warnings`.
- `cd client && pnpm build:check` -> passed with existing CSS/chunk warnings.

Remaining Phase 3/4 work:

- Add browser/MCP parity smoke evidence for the Evaluation workspace and advisor lifecycle.
- Confirm failed-set verification and full-suite regression evidence remains visible before promotion/apply in rendered UI.
- Start Phase 5 canonical Sharing model/service after Evaluation parity evidence is recorded.

## 2026-08-16 19:03 CST - Phase 3/4 Evaluation REST Read Surface

Scope:

- Added tenant-scoped REST read endpoints for Evaluation suite inventory, suite detail, suite-version case listing, suite-version run listing, run detail, failure summary, and baseline/candidate run comparison.
- REST read endpoints call the existing `EvaluationService` read methods and shared Evaluation serializers so REST and MCP keep the same redacted payload shapes.
- Suite inventory supports query, target kind, lifecycle/status, and bounded limit filtering for Human UI usage.
- Run detail and failure summary return bounded case-run payloads with assessments while redacting result, error, and assessment detail payloads through the shared serializers.
- Added regression coverage proving inventory/detail/case/run/failure/compare responses are tenant-scoped, return the expected shape, and do not leak raw tokens or unauthorized SQL table names.

Evidence:

- `cd server && PYTHONPATH=..:tests /Users/bytedance/worktrees/byaan-data-studio-p0/.venv/bin/python -m ruff check routers/evaluation.py tests/test_evaluation_rest_api.py` -> passed with the existing removed-rule warning.
- `cd server && PYTHONPATH=..:tests /Users/bytedance/worktrees/byaan-data-studio-p0/.venv/bin/python -m pytest tests/test_evaluation_rest_api.py -q` -> `4 passed, 11 warnings`.
- `cd server && PYTHONPATH=..:tests /Users/bytedance/worktrees/byaan-data-studio-p0/.venv/bin/python -m pytest tests/test_evaluation_contract_schemas.py tests/test_evaluation_persistence_migration.py tests/test_evaluation_service.py tests/test_evaluation_runner_service.py tests/test_evaluation_rest_api.py tests/test_evaluation_feedback_advisor_api.py tests/test_evaluation_mcp_contract.py tests/test_migration_chain_hardening.py -q` -> `26 passed, 18 warnings`.

Remaining Phase 3/4 work:

- Add Human UI surfaces for suite inventory/detail, case editor, run compare, failure drawer, feedback review, and advisor staged patch review.
- Add explicit REST review/apply endpoints for advisor verification/regression lifecycle if the UI needs review-specific shapes beyond the existing runner/promotion endpoints.
- Add end-to-end browser/MCP parity tests showing failed-set verification plus full-suite regression evidence is visible before promotion/apply.
