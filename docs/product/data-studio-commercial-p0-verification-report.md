# Data Studio Commercial P0 Verification Report

Owner role: Data Studio Commercial Verification Owner.

This report is evidence-first and does not claim overall READY. The verification
branch was created from Coordinator BASE_SHA
`86fbace663a68dff40d1a2e8713056d4599b60d8` as
`verification/data-studio-commercial-p0`.

## Current Verdict

Status: `PARTIAL`.

Reason: the base branch contains source, modeling, asset search, folder sharing,
and semantic model surfaces, but the requested commercial dashboard and
evaluation UI routes are not present on this BASE_SHA. Verification must record
those as blocked/missing until Coordinator merges or provides the product branch
that owns them. No whole-product READY claim is made here.

## Branch / Build Provenance

| Field | Evidence |
|---|---|
| BASE_SHA | `86fbace663a68dff40d1a2e8713056d4599b60d8` |
| Verification branch | `verification/data-studio-commercial-p0` |
| Worktree | `/Users/bytedance/worktrees/byaan-data-studio-commercial-verification-p0` |
| Backend port | `18123` |
| Frontend port | `15179` |
| 8080 policy | Do not stop, restart, or occupy `8080`; existing listeners are only recorded. |
| Image revision | Captured by `scripts/commercial_p0_verification.mjs` when `COMMERCIAL_P0_IMAGE` is set. |
| Clean status | Captured in each `result.json` under `provenance.clean`. |

## Migration Evidence

| Gate | Required evidence | Current status |
|---|---|---|
| Fresh SQLite | Start backend with `DATABASE_URL=sqlite+aiosqlite:///$EVIDENCE_DIR/runtime/sqlite/app.db`; record migration logs and API readiness. | Pending runtime run |
| Existing SQLite | Re-run against same SQLite file; record idempotent startup and unchanged head. | Pending runtime run |
| PostgreSQL | Optional runner mode `scripts/commercial_p0_verification.sh postgres` uses dedicated container `byaan-commercial-p0-postgres` and volume `byaan-commercial-p0-postgres-data`. | Pending runtime run |
| Single Alembic head | `server/tests/test_migration_chain_hardening.py` already asserts the expected single head in this base. | Test to run |
| Upgrade / downgrade | Existing self-hosted entrypoint contract test covers serialized upgrade and downgrade commands. | Test to run |
| Persistent Docker volume | PostgreSQL mode uses a named volume; the result must include Docker ps/volume evidence. | Pending runtime run |

## Connector Evidence Matrix

Each row must include auth, browse/import, snapshot/profile, parser, warnings,
retry, permission, delete/reindex, lineage/evidence, fixture, and final status.
The executable source for this matrix is
`scripts/commercial_p0_matrix.json`.

| Connector | Auth | Browse/import | Snapshot/profile | Parser | Warnings/retry/permission/delete | Lineage/evidence | Fixture | Status |
|---|---|---|---|---|---|---|---|---|
| Files | Local upload | File upload/import API | Source resource snapshot and parsed assets | CSV/XLSX/PDF/file parsers where available | Parser warnings, sync retry, tenant permission, delete/reimport | Parsed assets, lineage, evidence endpoints | Source connector tests and uploaded fixture files | `beta` |
| Web | Public URL or policy block | URL upload/import path | Captured content snapshot | Web adapter extraction | Fetch/parser warnings, sync retry, tenant permission, delete/reimport | Knowledge/evidence endpoints | Web source adapter tests | `beta` |
| Feishu/Lark | OAuth/admin config required | Resource picker and import | Doc/wiki/sheet/base snapshots | Feishu contract parser | Reauth/permission loss, refresh retry, disconnect/delete/reimport | Resource lineage and evidence locators | Fake Feishu connector tests | `blocked` |
| Volcengine TOS | Access key required | Bucket/prefix/object picker | Object snapshot/profile | Object bytes parser | Missing/forbidden object, sync retry, ACL failures, delete/reimport | Raw storage URI and metadata locators | Fake TOS connector tests | `blocked` |
| PostgreSQL | DB credentials | Connection and datasource listing | Schema cache/source understanding | SQL schema/profile parser | Connection/schema warnings, refresh retry, tenant permission, delete/recreate | Source understanding and semantic lineage | SQLite-first plus optional live PG | `beta` |
| MySQL | DB credentials | Connection and datasource listing | Schema/profile when live driver exists | MySQL dialect parser | Connection/schema warnings, refresh retry, tenant permission, delete/recreate | Source understanding resources | Connector contract tests | `beta` |
| SQLite | Local DB path | Connection and datasource listing | Schema cache/source understanding | SQLite parser | Path/schema warnings, refresh retry, tenant permission, delete/recreate | Source understanding and semantic lineage | Local SQLite fixtures | `beta` |
| MSSQL | DB credentials | Connection and datasource listing | Schema/profile when live driver exists | SQL Server parser | Driver/schema warnings, refresh retry, tenant permission, delete/recreate | Source understanding resources | Connector contract tests | `beta` |
| Oracle | DB credentials | Connection and datasource listing | Schema/profile when live driver exists | Oracle parser | Driver/schema warnings, refresh retry, tenant permission, delete/recreate | Source understanding resources | Connector contract tests | `beta` |
| Databricks | OAuth/PAT required | Warehouse discovery | Schema/profile when live auth exists | Databricks SQL parser | Missing OAuth/expired token, retry, ACL failures, delete/recreate | Source overview and semantic lineage | Databricks connector tests | `blocked` |
| MongoDB | DB credentials | Connection and datasource listing | Collection profile snapshot | Document shape profile | Connection/profile warnings, retry, tenant permission, delete/recreate | Profile evidence only until projection review | Mongo connector tests | `planned` |
| DynamoDB | AWS credentials | Connection and datasource listing | Table/key profile snapshot | Item shape profile | Credential/table warnings, retry, IAM/tenant permission, delete/recreate | Profile evidence only until projection review | DynamoDB connector tests | `planned` |

## Modeling Evidence

Required modeling checks:

- Source understanding, profile, projection review, semantic draft, publish,
  reload, MCP `query_metric`, lineage/evidence, and honest partial/blocked
  states are listed in `scripts/commercial_p0_matrix.json`.
- MongoDB and DynamoDB must not display semantic-ready without reviewed
  projection evidence. The current matrix keeps both as `planned`.
- OpenHuman runtime provenance fields are not verified on this BASE_SHA and
  must remain `UNVERIFIED` until runtime evidence proves otherwise.

Current status: `PARTIAL`, pending focused runtime/API evidence from the
verification runner.

## Dashboard Evidence

Required dashboard checks include legacy asset reproduction, blocker state,
read-only preview, structured migration entry, `saved_query`,
`semantic_metric`, `context_search`, live/preview/publish/reload,
lineage/audit/share, pinned snapshot blocked, permission denied, and legacy
tool gating.

Current status: `blocked` on this BASE_SHA for the commercial dashboard UI
because `/dashboard-assets` and `/dashboard-assets/<asset>` are not registered
routes in `client/src/App.tsx`. Backend `/api/assets/search` exists and is
covered by the verifier as an API probe; that is not enough to mark dashboard
P0 ready.

## Evaluation Evidence

Required evaluation checks include empty suite onboarding, create/import/publish,
preflight, claim/heartbeat/complete/failures, compare, advisor, promotion,
REST/MCP parity, tenant isolation, idempotency, and audit.

Current status: `blocked` on this BASE_SHA because `/evaluation` is not a
registered route and no `evaluation` backend router is included in
`server/main.py`.

## Sharing Evidence

Required sharing checks include authorization, binding, secret redaction,
rotation, revoke, audit, folder/dashboard/notebook/worker, and self-hosted
external-sharing policy.

Current status: `partial`. Folder, notebook, dashboard share, and viewer routes
exist in the base, while canonical sharing/evaluation governance surfaces from
later integration commits are not part of this BASE_SHA. Self-hosted mode also
sets `external_sharing_enabled=false` unless worker configuration enables a
non-self-hosted external share path.

## Playwright Route Evidence

The verifier must exercise these routes at `1440x900` and `390x844`, recording
`pageerror`, `consoleError`, `requestfailed`, `http5xx`, screenshot paths, final
URL/path, and marker status:

| Route | Status before runtime run |
|---|---|
| `/login` | Pending; expected only under self-hosted enterprise route tree |
| `/dashboard-assets` | Expected missing on BASE_SHA |
| `/dashboard-assets/commercial-verification-asset` | Expected missing unless `COMMERCIAL_P0_ASSET_PATH` is set to a Coordinator asset route on a branch that supports it |
| `/evaluation` | Expected missing on BASE_SHA |
| `/data-modeling` | Expected missing or redirect on BASE_SHA; current app route is `/data-models` |
| `/databases` | Pending runtime run |
| `/sources` | Pending runtime run |

Runtime output location:
`$HOME/.codex/data-studio-commercial-p0-evidence/<run-id>/result.json`.

## Commands

```bash
cd /Users/bytedance/worktrees/byaan-data-studio-commercial-verification-p0
uv run pytest tests/commercial_p0
scripts/commercial_p0_verification.sh sqlite
scripts/commercial_p0_verification.sh postgres
```

The PostgreSQL command uses dedicated container and volume names from
`scripts/commercial_p0_matrix.json`. It must not be run against shared
Coordinator databases.

## Open Items

- Execute the SQLite runtime pass and update this report with the generated
  evidence path, screenshots, route counters, and API statuses.
- Execute the PostgreSQL runtime pass if Docker can pull or use the configured
  Postgres image.
- If the Coordinator provides a concrete dashboard asset id/path, rerun with
  `COMMERCIAL_P0_ASSET_PATH=<path>`.
- Hand dashboard/evaluation route gaps back to the owning product branches;
  this verification branch does not modify product implementation files.
