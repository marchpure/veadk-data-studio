# Data Studio Commercial P0 Verification Report

Owner role: Data Studio Commercial Verification Owner.

This report is evidence-first and does not claim overall READY. The verification
branch was created from Coordinator BASE_SHA
`e9358ea56554cc0ecdf93b723359eee711cb13b1` as
`verification/data-studio-commercial-p0`.

## Current Verdict

Status: `PARTIAL`.

Reason: `e9358ea` contains real dashboard and evaluation UI/backend surfaces,
and isolated runtime proved self-hosted auth plus all configured commercial API
probes on fresh SQLite, existing SQLite, and PostgreSQL. The route matrix still
has failing Playwright evidence: `/data-modeling` is not registered, the default
specified dashboard asset path is not a UUID-backed seeded asset, and PostgreSQL
with seeded legacy dashboard assets triggers a dashboard React error. No
whole-product READY claim is made here.

## Branch / Build Provenance

| Field | Evidence |
|---|---|
| BASE_SHA | `e9358ea56554cc0ecdf93b723359eee711cb13b1` |
| Verification HEAD | `03eb6fdcbea41d9a566592049f0f30c5183ae30d` |
| Verification branch | `verification/data-studio-commercial-p0` |
| Exact remote branch | `veadk-data-studio/verification/data-studio-commercial-p0` -> `03eb6fdcbea41d9a566592049f0f30c5183ae30d` |
| Stale wrong-baseline backup | Old remote tip `9c2a2d9cfb1280569df927ded583bfec7c7a591c` preserved as `veadk-data-studio/backup/verification-data-studio-commercial-p0-86fbace-remote`. |
| Auxiliary safe branch | `veadk-data-studio/verification/data-studio-commercial-p0-e9358ea` also points to `03eb6fdcbea41d9a566592049f0f30c5183ae30d`. |
| Worktree | `/Users/bytedance/worktrees/byaan-commercial-verification-p0` |
| Backend port | `18123` |
| Frontend port | `15179` |
| 8080 policy | Not stopped, restarted, probed, or occupied by this verifier. |
| Image revision | Not set; `COMMERCIAL_P0_IMAGE` was not provided. |
| Clean status | `true` in all collected `result.json` files. |

## Migration Evidence

| Gate | Evidence | Current status |
|---|---|---|
| Fresh SQLite | `/Users/bytedance/.codex/data-studio-commercial-p0-evidence/20260817Tcommercial-sqlite-fresh/result.json`; DB at `runtime/sqlite/app.db`; backend/frontend logs under `logs/`. | `PARTIAL`: startup and all API probes passed; browser route matrix has known failures. |
| Existing SQLite | `/Users/bytedance/.codex/data-studio-commercial-p0-evidence/20260817Tcommercial-sqlite-existing/result.json`; reused fresh SQLite DB path. | `PARTIAL`: idempotent startup and all API probes passed; same browser route failures as fresh SQLite. |
| PostgreSQL | `/Users/bytedance/.codex/data-studio-commercial-p0-evidence/20260817Tcommercial-postgres/result.json`; container `byaan-commercial-p0-postgres`; volume `byaan-commercial-p0-postgres-data`; port `15432`. | `PARTIAL`: startup and all API probes passed; dashboard browser route also hit a React error with seeded legacy assets. |
| Single Alembic head | Contracted by existing `server/tests/test_migration_chain_hardening.py`; not rerun in this verification commit. | Not independently rerun here. |
| Upgrade / downgrade | Existing self-hosted entrypoint tests cover command contract; runtime startup exercised upgrade path on isolated DBs. | Downgrade not independently rerun here. |
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

## Modeling Evidence

Required modeling checks include source understanding, profile, projection
review, semantic draft, publish, reload, MCP `query_metric`, lineage/evidence,
honest partial/blocked states, and OpenHuman runtime provenance.

Current status: `PARTIAL`. `/api/data-models`, `/api/semantic-models`, and the
real `/data-models` UI route passed in all three runtime runs at both viewports.
The requested `/data-modeling` route failed in every run by redirecting to `/`.
OpenHuman runtime adapter status remains `UNVERIFIED`; MongoDB and DynamoDB
remain beta until reviewed projection materialization proves they do not present
semantic-ready prematurely.

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
in all three runtime runs at both viewports. Deeper suite lifecycle, worker,
MCP parity, and advisor/promotion flows were not independently run in this
verification pass.

## Sharing Evidence

Required sharing checks include authorization, binding, secret redaction,
rotation, revoke, audit, folder/dashboard/notebook/worker, and self-hosted
external-sharing policy.

Current status: `PARTIAL`. Authenticated `/api/folders` passed in all three
runtime runs, and dashboard/folder routers are present. This verification pass
did not independently exercise share creation, rotation, revoke, external
sharing policy, or audit trail flows.

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
- Run deeper dashboard/evaluation/sharing smoke flows after fixture setup is
  made deterministic for this isolated self-hosted verifier.
