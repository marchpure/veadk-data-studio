# Data Studio Commercial P0 Verification Report

Owner role: Data Studio Commercial Verification Owner.

This report is evidence-first and does not claim overall READY. The verification
branch was created from Coordinator BASE_SHA
`e9358ea56554cc0ecdf93b723359eee711cb13b1` as
`verification/data-studio-commercial-p0`.

## Current Verdict

Status: `PARTIAL`.

Reason: `e9358ea` contains real dashboard and evaluation UI/backend surfaces,
isolated runtime proved self-hosted auth plus all configured commercial API
probes on fresh SQLite, existing SQLite, and PostgreSQL, and focused
backend/MCP/smoke contracts now pass for migration, connector/modeling,
dashboard, evaluation, and sharing gates. The required route matrix still has
failing Playwright evidence: `/data-modeling` is not registered, the default
specified dashboard asset path is not a UUID-backed seeded asset, and PostgreSQL
with seeded legacy dashboard assets triggers a dashboard React error. No
whole-product READY claim is made here.

## Branch / Build Provenance

| Field | Evidence |
|---|---|
| BASE_SHA | `e9358ea56554cc0ecdf93b723359eee711cb13b1` |
| Verification HEAD | Verification branch tip; verify with `git ls-remote --heads veadk-data-studio verification/data-studio-commercial-p0`. |
| Verification branch | `verification/data-studio-commercial-p0` |
| Exact remote branch | `veadk-data-studio/verification/data-studio-commercial-p0` points at this verification branch tip. |
| Stale wrong-baseline backup | Old remote tip `9c2a2d9cfb1280569df927ded583bfec7c7a591c` preserved as `veadk-data-studio/backup/verification-data-studio-commercial-p0-86fbace-remote`. |
| Auxiliary safe branch | `veadk-data-studio/verification/data-studio-commercial-p0-e9358ea` also points at this verification branch tip. |
| Worktree | `/Users/bytedance/worktrees/byaan-commercial-verification-p0` |
| Backend port | `18123` |
| Frontend port | `15179` |
| 8080 policy | Not stopped, restarted, probed, or occupied by this verifier. |
| Image revision | Not set; `COMMERCIAL_P0_IMAGE` was not provided. |
| Clean status | Runtime collector recorded `true` in all collected `result.json` files; final post-push `git status --short --branch` was clean and tracking `veadk-data-studio/verification/data-studio-commercial-p0`. |

## Migration Evidence

| Gate | Evidence | Current status |
|---|---|---|
| Fresh SQLite | `/Users/bytedance/.codex/data-studio-commercial-p0-evidence/20260817Tcommercial-sqlite-fresh/result.json`; DB at `runtime/sqlite/app.db`; backend/frontend logs under `logs/`. | `PARTIAL`: startup and all API probes passed; browser route matrix has known failures. |
| Existing SQLite | `/Users/bytedance/.codex/data-studio-commercial-p0-evidence/20260817Tcommercial-sqlite-existing/result.json`; reused fresh SQLite DB path. | `PARTIAL`: idempotent startup and all API probes passed; same browser route failures as fresh SQLite. |
| PostgreSQL | `/Users/bytedance/.codex/data-studio-commercial-p0-evidence/20260817Tcommercial-postgres/result.json`; container `byaan-commercial-p0-postgres`; volume `byaan-commercial-p0-postgres-data`; port `15432`. | `PARTIAL`: startup and all API probes passed; dashboard browser route also hit a React error with seeded legacy assets. |
| Single Alembic head | `uv run pytest server/tests/test_migration_chain_hardening.py server/tests/test_dashboard_persistence_migration.py server/tests/test_sharing_persistence_migration.py server/tests/test_evaluation_persistence_migration.py -q`; `APP_MODE=self-hosted DATABASE_URL=postgresql+asyncpg://...@127.0.0.1:15432/byaan_commercial_p0 uv run alembic -c alembic.ini heads/current` from `server/`. | Passed: `12 passed`; live PostgreSQL reported the single head `add_canonical_sharing_model (head)`. |
| Upgrade / downgrade | Same focused migration command; runtime startup also exercised upgrade path on isolated SQLite and PostgreSQL DBs; live PostgreSQL one-step command `uv run alembic -c alembic.ini downgrade -1 && uv run alembic -c alembic.ini current && uv run alembic -c alembic.ini upgrade head && uv run alembic -c alembic.ini current`. | Passed: downgrade moved `add_canonical_sharing_model -> add_evaluation_authoritative_model`, then upgrade returned to `add_canonical_sharing_model (head)`. Full historical PostgreSQL downgrade to base was not attempted. |
| Persistent Docker volume | `docker volume inspect byaan-commercial-p0-postgres-data` returned mountpoint `/var/lib/docker/volumes/byaan-commercial-p0-postgres-data/_data`. | Proven for dedicated volume creation/persistence during run. |

## Connector Evidence Matrix

The authoritative generated source matrix is
`docs/product/data-studio-p0-source-matrix.md`: `0` ready, `14` beta, `26`
planned, `0` blocked, `40` total; final source status is `PARTIAL`.

Each commercial connector row must include auth, browse/import,
snapshot/profile, parser, warnings, retry, permission, delete/reindex,
lineage/evidence, fixture, and final status. The executable verification subset
is `scripts/commercial_p0_matrix.json`.

| Connector | Status | Evidence note |
|---|---|---|
| Files | `beta` | Governed upload, snapshots, projection review, parsed assets, lineage, and source tests exist; large-file/customer fixtures remain beta hardening. |
| Web | `beta` | Public URL capture, sync, evidence, lineage, and adapter tests exist; crawl/table extraction policy remains beta. |
| Feishu/Lark | `beta` | OAuth/picker/import contracts and fake adapter tests exist; live tenant credentials and OpenHuman extraction provenance are unverified. |
| Volcengine TOS | `beta` | Bucket/prefix/object import contracts and fake adapter tests exist; real credentials/incremental sync proof remain beta. |
| PostgreSQL/MySQL/SQLite/MSSQL/Oracle | `beta` | Structured source understanding, semantic draft/publish/reload, and MCP paths exist; live-driver dialect E2E remains beta. |
| Databricks | `beta` | OAuth, warehouse/catalog path, source overview, and semantic handoff exist; live OAuth/profile freshness proof remain beta. |
| MongoDB | `beta` | Source profile snapshots/evidence exist; reviewed projection materialization must be proven before semantic-ready. |
| DynamoDB | `beta` | Key/item profile snapshots/evidence exist; reviewed projection materialization must be proven before semantic-ready. |

Runtime API evidence: all three runs passed `connector_definitions`,
`sources_overview`, `datasources`, `source_resources`, `data_models`,
`semantic_models`, `folders`, and `mcp_stdio_config` probes with authenticated
`Authorization` and `X-Tenant-ID` headers.

Focused connector/modeling evidence:
`uv run pytest server/tests/test_source_connectors_api.py server/tests/test_source_understanding_api.py server/tests/test_semantic_modeling_api.py server/tests/test_sources_overview_api.py server/tests/test_data_studio_p0_source_matrix.py -q`
passed with `79 passed`. This covers connector catalog availability, credential
redaction, Feishu OAuth/picker/import/sync and reauthorization contracts, TOS
object/prefix parser and permission contracts, source sync retry/checkpoint
contracts, source overview states for SQL/Databricks/MongoDB/DynamoDB/TOS, source
understanding profile/evidence/review contracts, semantic draft/publish/reload,
MCP `query_metric`, and the generated source matrix. It remains contract/fixture
evidence, not live credentials for every external provider.

## Modeling Evidence

Required modeling checks include source understanding, profile, projection
review, semantic draft, publish, reload, MCP `query_metric`, lineage/evidence,
honest partial/blocked states, and OpenHuman runtime provenance.

Current status: `PARTIAL`. `/api/data-models`, `/api/semantic-models`, and the
real `/data-models` UI route passed in all three runtime runs at both viewports.
The requested `/data-modeling` route failed in every run by redirecting to `/`.
Focused modeling contracts passed for source understanding, profile,
projection review, semantic draft/publish/reload, MCP `query_metric`, and
lineage/evidence. MongoDB and DynamoDB profile contracts passed without
creating semantic candidates before reviewed projection handoff. OpenHuman
runtime adapter status remains `UNVERIFIED`, so the source matrix stays beta and
the modeling gate is not claimed READY.

## Dashboard Evidence

Required dashboard checks include legacy asset reproduction, blocker state,
read-only preview, structured migration entry, `saved_query`,
`semantic_metric`, `context_search`, live/preview/publish/reload,
lineage/audit/share, pinned snapshot blocked, permission denied, and legacy tool
gating.

Current status: `PARTIAL`. Static inspection confirms `client/src/App.tsx`
registers `/dashboard-assets` and `/dashboard-assets/:assetId`, and
`server/main.py` includes `dashboard_router`. `/api/dashboard-assets` passed in
all three runtime runs.

Focused dashboard evidence:
`uv run pytest server/tests/test_dashboard_rest_api.py server/tests/test_dashboard_mcp_contract.py server/tests/test_dashboard_lifecycle_service.py server/tests/test_dashboard_execution_service.py server/tests/test_dashboard_legacy_tool_gating.py server/tests/test_dashboard_security_regressions.py -q`
passed with `42 passed`. This covers REST lifecycle/query/state/lineage/audit,
MCP lifecycle/query/explain, draft ETag conflicts, publish freeze, `saved_query`,
`semantic_metric`, `context_search`, pinned-snapshot blocking, unresolved policy
blocking, tenant/notebook boundaries, permission-denied viewer sessions, and
legacy HTML tool gating. The browser blockers below still prevent a dashboard
READY claim.

Browser blockers:

- Fresh/existing SQLite: `/dashboard-assets` passed at both viewports, but
  `/dashboard-assets/commercial-verification-asset` produced two 422 console
  errors per run because the placeholder path is not a valid UUID asset id.
- PostgreSQL: `/dashboard-assets` redirected to a seeded legacy asset and hit
  `TypeError: Cannot read properties of undefined (reading '0')` in
  `DashboardWorkspacePage.tsx` `normalizeEditorSelection`; the error boundary
  rendered "Something went wrong". The placeholder specified asset path still
  produced 422 console errors.

## Evaluation Evidence

Required evaluation checks include empty suite onboarding, create/import/publish,
preflight, claim/heartbeat/complete/failures, compare, advisor, promotion,
REST/MCP parity, tenant isolation, idempotency, and audit.

Current status: `PARTIAL`. Static inspection confirms `client/src/App.tsx`
registers `/evaluation` and `/evaluation/:suiteId`, and `server/main.py`
includes `evaluation_router`. `/api/evaluation/suites` and `/evaluation` passed
in all three runtime runs at both viewports.

Focused evaluation evidence:
`uv run pytest server/tests/test_evaluation_rest_api.py server/tests/test_evaluation_feedback_advisor_api.py server/tests/test_evaluation_mcp_contract.py server/tests/test_evaluation_runner_service.py server/tests/test_evaluation_service.py -q`
passed with `17 passed`. This covers REST create/import/publish, read surfaces,
preflight tenant scope, claim/heartbeat/complete/failure artifacts, idempotent
preflight, compare, advisor review/verify/regress/apply surfaces, promotion
gate evidence, REST/MCP parity, redaction, and published-suite immutability.

Additional isolated SQLite MCP parity smoke:
`DATABASE_URL=sqlite+aiosqlite:////Users/bytedance/.codex/data-studio-commercial-p0-evidence/20260817Tcommercial-focused/runtime/evaluation-mcp/app.db APP_MODE=desktop SKILL_LOOP_ENABLED=false POSTHOG_DISABLED=true uv run python - <<'PY' ... PY`
ran migrations, seeded the evaluation smoke fixture, and passed
`server/scripts/evaluation_mcp_parity_smoke.py` with output `ok: true`,
`case_count: 3`, `failure_count: 2`, `regression_count: 2`,
`advisor_verification_status: queued`, and `advisor_regression_status: queued`.
This is backend/MCP smoke evidence, not a browser-driven suite authoring flow.

## Sharing Evidence

Required sharing checks include authorization, binding, secret redaction,
rotation, revoke, audit, folder/dashboard/notebook/worker, and self-hosted
external-sharing policy.

Current status: `PARTIAL`. Authenticated `/api/folders` passed in all three
runtime runs, and dashboard/folder routers are present.

Focused sharing evidence:
`uv run pytest server/tests/test_share_secret_redaction.py server/tests/test_share_object_authorization.py server/tests/test_sharing_canonical_service.py server/tests/test_sharing_read_surface.py -q`
passed with `24 passed`. This covers share authorization, folder notebook and
dashboard binding, secret redaction, canonical grant binding, revoke handling,
viewer-session object/version binding, tenant-scoped read surfaces, and
REST/MCP redaction parity.

Additional in-memory governance smoke:
`uv run python server/scripts/sharing_governance_smoke.py` passed with `ok:
true`, `canonical_dashboard_grant_count: 1`, canonical notebook surfaces
`folder_notebook`, `html_notebook_share`, and `json_notebook_share`,
`json_has_password_after_rotation: true`, and revoked notebook statuses for all
three surfaces. The smoke uses a fake worker and in-memory DB, so it proves
policy/redaction/compatibility behavior rather than a live external worker.

## Playwright Route Evidence

The verifier exercised each route at `1440x900` and `390x844`, recording
`pageerror`, `consoleError`, `requestfailed`, `http5xx`, screenshots, final
URL/path, marker status, and horizontal overflow.

| Run | Result JSON | API failures | Browser failures | Notes |
|---|---|---:|---:|---|
| Fresh SQLite | `/Users/bytedance/.codex/data-studio-commercial-p0-evidence/20260817Tcommercial-sqlite-fresh/result.json` | 0 | 4 | Failing routes: specified dashboard asset at both viewports, `/data-modeling` at both viewports. |
| Existing SQLite | `/Users/bytedance/.codex/data-studio-commercial-p0-evidence/20260817Tcommercial-sqlite-existing/result.json` | 0 | 4 | Same failure set as fresh SQLite while reusing the same SQLite DB. |
| PostgreSQL | `/Users/bytedance/.codex/data-studio-commercial-p0-evidence/20260817Tcommercial-postgres/result.json` | 0 | 6 | Adds `/dashboard-assets` failures at both viewports due dashboard React error with seeded legacy asset. |

Passed route evidence across all runs: `/login`, `/evaluation`, `/data-models`,
`/databases`, and `/sources` at both required viewports. SQLite also passed
`/dashboard-assets` at both viewports.

## Commands Run

```bash
uv run pytest tests/commercial_p0 -q
uv run pytest server/tests/test_migration_chain_hardening.py server/tests/test_dashboard_persistence_migration.py server/tests/test_sharing_persistence_migration.py server/tests/test_evaluation_persistence_migration.py -q
uv run pytest server/tests/test_dashboard_rest_api.py server/tests/test_dashboard_mcp_contract.py server/tests/test_dashboard_lifecycle_service.py server/tests/test_dashboard_execution_service.py server/tests/test_dashboard_legacy_tool_gating.py server/tests/test_dashboard_security_regressions.py -q
uv run pytest server/tests/test_evaluation_rest_api.py server/tests/test_evaluation_feedback_advisor_api.py server/tests/test_evaluation_mcp_contract.py server/tests/test_evaluation_runner_service.py server/tests/test_evaluation_service.py -q
uv run pytest server/tests/test_share_secret_redaction.py server/tests/test_share_object_authorization.py server/tests/test_sharing_canonical_service.py server/tests/test_sharing_read_surface.py -q
uv run pytest server/tests/test_source_connectors_api.py server/tests/test_source_understanding_api.py server/tests/test_semantic_modeling_api.py server/tests/test_sources_overview_api.py server/tests/test_data_studio_p0_source_matrix.py -q
uv run python server/scripts/sharing_governance_smoke.py
DATABASE_URL='sqlite+aiosqlite:////Users/bytedance/.codex/data-studio-commercial-p0-evidence/20260817Tcommercial-focused/runtime/evaluation-mcp/app.db' APP_MODE=desktop SKILL_LOOP_ENABLED=false POSTHOG_DISABLED=true uv run python - <<'PY'
from server.utils.migrations import run_migrations

run_migrations()

import asyncio
import json
import os

async def main() -> None:
    from server.scripts.seed_evaluation_smoke import seed
    fixture = await seed()
    os.environ["EVALUATION_SMOKE_FIXTURE_JSON"] = json.dumps(fixture)
    from server.scripts.evaluation_mcp_parity_smoke import main as parity_main
    await parity_main()

asyncio.run(main())
PY
APP_MODE=self-hosted DATABASE_URL='postgresql+asyncpg://byaan:byaan_commercial_p0@127.0.0.1:15432/byaan_commercial_p0' uv run alembic -c alembic.ini heads
APP_MODE=self-hosted DATABASE_URL='postgresql+asyncpg://byaan:byaan_commercial_p0@127.0.0.1:15432/byaan_commercial_p0' uv run alembic -c alembic.ini current
APP_MODE=self-hosted DATABASE_URL='postgresql+asyncpg://byaan:byaan_commercial_p0@127.0.0.1:15432/byaan_commercial_p0' uv run alembic -c alembic.ini downgrade -1
APP_MODE=self-hosted DATABASE_URL='postgresql+asyncpg://byaan:byaan_commercial_p0@127.0.0.1:15432/byaan_commercial_p0' uv run alembic -c alembic.ini upgrade head
node --check scripts/commercial_p0_verification.mjs
bash -n scripts/commercial_p0_verification.sh
git diff --check
RUN_ID=20260817Tcommercial-sqlite-fresh bash scripts/commercial_p0_verification.sh sqlite
SQLITE_DB=/Users/bytedance/.codex/data-studio-commercial-p0-evidence/20260817Tcommercial-sqlite-fresh/runtime/sqlite/app.db RUN_ID=20260817Tcommercial-sqlite-existing bash scripts/commercial_p0_verification.sh sqlite
RUN_ID=20260817Tcommercial-postgres bash scripts/commercial_p0_verification.sh postgres
```

The runtime commands used isolated ports `18123` and `15179`, isolated SQLite,
and the dedicated PostgreSQL container/volume names from
`scripts/commercial_p0_matrix.json`. They did not run against shared Coordinator
databases.

## Open Items

- Product follow-up: add/redirect the requested `/data-modeling` route or amend
  the acceptance contract to use `/data-models`.
- Product follow-up: seed/provide a concrete dashboard asset path for the
  specified asset route, or let the verifier create one before browser probes.
- Product follow-up: fix the PostgreSQL dashboard legacy-asset React error in
  `DashboardWorkspacePage.tsx` `normalizeEditorSelection`.
- After those route blockers are resolved, rerun the full browser/API verifier
  on fresh SQLite, existing SQLite, and PostgreSQL; optionally add browser-level
  deep workflows for dashboard/evaluation/sharing on top of the focused
  backend/MCP/smoke contracts captured here.
