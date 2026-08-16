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

## Commit Ledger

| SHA | Subject | Phase | Tests | Push |
| --- | --- | --- | --- | --- |
| `4a4f4e1` | `dashboard: audit human agent contract` | Phase 0 | `pytest tests/test_dashboard_security_regressions.py` -> 1 strict xfail; `ruff check tests/test_dashboard_security_regressions.py` -> passed | Pushed to `veadk-data-studio/agent/dashboard-human-agent-p0`; HEAD matched upstream after push |
| `033b526` | `dashboard: enforce viewer query binding` | Phase 2 security slice | `pytest tests/test_dashboard_security_regressions.py` -> 5 passed; `ruff check routers/folders.py tests/test_dashboard_security_regressions.py` -> passed | Pushed to `veadk-data-studio/agent/dashboard-human-agent-p0`; HEAD matched upstream after push |

## Acceptance Evidence

No final acceptance evidence yet. Current branch is not ready for integration and has not verified real `8080`.
