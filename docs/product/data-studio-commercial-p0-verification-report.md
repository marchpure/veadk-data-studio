# Data Studio Commercial P0 Verification Report

Owner role: Data Studio Commercial Verification Owner.

This report is evidence-first and does not claim overall READY. The verification
branch was created from Coordinator BASE_SHA
`e9358ea56554cc0ecdf93b723359eee711cb13b1` as
`verification/data-studio-commercial-p0`.

## Current Verdict

Status: `PARTIAL`.

Reason: `e9358ea` contains real dashboard and evaluation UI/backend surfaces, but
Commercial P0 still requires fresh runtime proof for migrations, connector
families, modeling, dashboard governance, evaluation governance, sharing, and
Playwright route health. No whole-product READY claim is made here.

## Branch / Build Provenance

| Field | Evidence |
|---|---|
| BASE_SHA | `e9358ea56554cc0ecdf93b723359eee711cb13b1` |
| Verification branch | `verification/data-studio-commercial-p0` |
| Worktree | `/Users/bytedance/worktrees/byaan-commercial-verification-p0` |
| Backend port | `18123` |
| Frontend port | `15179` |
| 8080 policy | Do not stop, restart, probe, or occupy `8080`. |
| Image revision | Captured by `scripts/commercial_p0_verification.mjs` when `COMMERCIAL_P0_IMAGE` is set. |
| Clean status | Captured in each `result.json` under `provenance.clean`. |

## Migration Evidence

| Gate | Required evidence | Current status |
|---|---|---|
| Fresh SQLite | Start backend in self-hosted mode with `DATABASE_URL=sqlite+aiosqlite:///$EVIDENCE_DIR/runtime/sqlite/app.db`; record migration logs and API readiness. | Pending runtime run |
| Existing SQLite | Re-run against the same SQLite file; record idempotent startup and unchanged head. | Pending runtime run |
| PostgreSQL | `scripts/commercial_p0_verification.sh postgres` uses dedicated container `byaan-commercial-p0-postgres`, volume `byaan-commercial-p0-postgres-data`, and port `15432`. | Pending runtime run |
| Single Alembic head | `server/tests/test_migration_chain_hardening.py` asserts the expected single head in this base. | Test to run |
| Upgrade / downgrade | Existing self-hosted entrypoint contract test covers serialized upgrade and downgrade commands. | Test to run |
| Persistent Docker volume | PostgreSQL mode must include Docker ps/volume evidence in `result.json` and logs. | Pending runtime run |

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

## Modeling Evidence

Required modeling checks include source understanding, profile, projection
review, semantic draft, publish, reload, MCP `query_metric`, lineage/evidence,
honest partial/blocked states, and OpenHuman runtime provenance.

Current status: `PARTIAL`. The generated source matrix says OpenHuman runtime
adapter status is `UNVERIFIED`. MongoDB and DynamoDB must not display
semantic-ready without reviewed projection evidence; the verifier keeps these as
beta until runtime evidence proves the guard.

## Dashboard Evidence

Required dashboard checks include legacy asset reproduction, blocker state,
read-only preview, structured migration entry, `saved_query`,
`semantic_metric`, `context_search`, live/preview/publish/reload,
lineage/audit/share, pinned snapshot blocked, permission denied, and legacy tool
gating.

Current status: `PARTIAL`. Static inspection confirms `client/src/App.tsx`
registers `/dashboard-assets` and `/dashboard-assets/:assetId`, and
`server/main.py` includes `dashboard_router`. Runtime dashboard API and browser
evidence remain pending.

## Evaluation Evidence

Required evaluation checks include empty suite onboarding, create/import/publish,
preflight, claim/heartbeat/complete/failures, compare, advisor, promotion,
REST/MCP parity, tenant isolation, idempotency, and audit.

Current status: `PARTIAL`. Static inspection confirms `client/src/App.tsx`
registers `/evaluation` and `/evaluation/:suiteId`, and `server/main.py`
includes `evaluation_router`. Runtime REST, browser, and MCP parity evidence
remain pending.

## Sharing Evidence

Required sharing checks include authorization, binding, secret redaction,
rotation, revoke, audit, folder/dashboard/notebook/worker, and self-hosted
external-sharing policy.

Current status: `PARTIAL`. Folder, notebook, dashboard share, and viewer routes
exist in the base, but this verification report still needs isolated runtime
evidence for policy behavior, redaction, rotation/revoke, and audit trails.

## Playwright Route Evidence

The verifier must exercise these routes at `1440x900` and `390x844`, recording
`pageerror`, `consoleError`, `requestfailed`, `http5xx`, screenshot paths, final
URL/path, marker status, and horizontal overflow:

| Route | Current expectation before runtime run |
|---|---|
| `/login` | Present under self-hosted mode. |
| `/dashboard-assets` | Present; protected route requires verifier login. |
| `/dashboard-assets/commercial-verification-asset` | Dynamic route present; default asset may show missing-asset behavior unless `COMMERCIAL_P0_ASSET_PATH` points to a seeded asset. |
| `/evaluation` | Present; protected route requires verifier login. |
| `/data-modeling` | Requested alias; may fail or redirect because e9358ea canonical route is `/data-models`. |
| `/data-models` | Real e9358ea modeling route, included as compatibility evidence. |
| `/databases` | Present; protected route requires verifier login. |
| `/sources` | Present; protected route requires verifier login. |

Runtime output location:
`$HOME/.codex/data-studio-commercial-p0-evidence/<run-id>/result.json`.

## Commands

```bash
cd /Users/bytedance/worktrees/byaan-commercial-verification-p0
uv run pytest tests/commercial_p0 -q
node --check scripts/commercial_p0_verification.mjs
bash -n scripts/commercial_p0_verification.sh
git diff --check
scripts/commercial_p0_verification.sh sqlite
scripts/commercial_p0_verification.sh postgres
```

The runtime commands use isolated ports `18123` and `15179`, isolated SQLite,
and the dedicated PostgreSQL container/volume names from
`scripts/commercial_p0_matrix.json`. They must not run against shared
Coordinator databases.

## Open Items

- Execute the SQLite runtime pass and update this report with generated evidence
  paths, screenshots, route counters, and API statuses.
- Re-run SQLite against the same database file for existing-DB idempotency.
- Execute the PostgreSQL runtime pass if Docker is available.
- Run focused dashboard and evaluation smoke scripts when fixture setup is
  available.
- If Coordinator provides a concrete dashboard asset path, rerun with
  `COMMERCIAL_P0_ASSET_PATH=<path>`.
