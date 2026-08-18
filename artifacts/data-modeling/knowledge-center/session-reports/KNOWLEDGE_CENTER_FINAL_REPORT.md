# Knowledge Center Final Report - BYAAN Data Studio

Date: 2026-08-18

Branch: `integration/knowledge-center`

Starting base hash: `7a6cef9f0938bcdb2fe76b635311ca4eb25df0ca`

## Release Decision

PASS for the BYAAN side of the Knowledge Center integration gate.

The final gate was rerun against a real Team/self-hosted stack:

- `APP_MODE=self-hosted`
- PostgreSQL-backed BYAAN database
- Team organization: `Knowledge Center Team Gate`
- Auth role: `owner`
- `/api/app/config` flags:
  - `enterprise_licensed=true`
  - `team_sharing_enabled=true`
  - `communityBootstrapPresent=false`

No feature flag was faked in frontend code. Secrets and Team credentials were stored only under `/tmp` with mode `0600`.

## BYAAN Changes

- Added a dedicated Embedded Layout for `/embedded/knowledge-center/*`.
- Embedded mode removes the full BYAAN application shell:
  - no global sidebar
  - no account/team menu
  - no context sidebar
  - no MCP banner
  - no standalone app floating entry
- Embedded tabs are stable and compact:
  - Sources
  - Data Models
  - Dashboards
  - Evaluation
  - Folders
- Root embedded route redirects to Data Models instead of notebook/home content.
- Internal Knowledge Center navigation preserves embedded paths after refresh and iframe navigation.
- Full BYAAN Team UI remains unchanged for direct access, including Team and Integrations entries.
- External asset REST query responses include SQL, metric definition, and permission-policy evidence needed by generated agents.

## Live Team Seed

Seed script: `server/scripts/knowledge_center_live_seed.py`

Machine-readable result:

- `artifacts/data-modeling/knowledge-center/session-reports/live/byaan-live-seed-result.json`

Redacted env evidence:

- `artifacts/data-modeling/knowledge-center/session-reports/live/byaan-live-env.sh`

Real secret env:

- `/tmp/session-f-team-20260818100622.env`
- `/tmp/session-f-team-20260818100622.byaan-live-env.sh`
- Both are `0600` and not committed.

Live query result:

- Status: `completed`
- Rows:
  - East: `150`
  - West: `80`
- SQL evidence:
  - `SELECT "revenue"."region" AS "revenue_region", SUM(revenue.revenue) AS "revenue_revenue" FROM "revenue" AS "revenue" GROUP BY "revenue"."region"`
- Metric definition: `Sum of revenue.revenue.`
- Permission policy evidence:
  - Allowed metrics: `revenue_revenue`
  - Allowed dimensions: `revenue_region`, `revenue_paid_at`
  - Decision: `allowed`

Knowledge provider note: local Team gate used native ingestion with `KNOWLEDGE_PROVIDER_ALLOW_NATIVE=true` for diagnostics data loading. Team flags, auth, PostgreSQL, and external REST queries remained real.

## Verification

- BYAAN targeted external/query tests: `20 passed`
  - `uv run pytest server/tests/test_external_assets_api.py server/tests/test_semantic_modeling_api.py -q`
- BYAAN full backend tests: `1016 passed, 2 skipped`
  - `uv run pytest -q`
- BYAAN frontend lint: passed with existing warnings
  - `corepack pnpm lint`
- BYAAN frontend type/build check: passed with existing build warnings
  - `corepack pnpm build:check`
- Team live seed: passed
- Secret scan: passed
  - exact secret-value scan across source, reports, generated result JSON, and screenshots
  - no real Team password, app secret, API key, or owner email found in committed paths

## Release Artifacts

- `artifacts/data-modeling/knowledge-center/session-reports/live/byaan-live-seed-result.json`
- `artifacts/data-modeling/knowledge-center/session-reports/live/byaan-live-env.sh`
- `artifacts/data-modeling/knowledge-center/session-reports/KNOWLEDGE_CENTER_FINAL_REPORT.md`

## Rollback

Rollback BYAAN by reverting the final `integration/knowledge-center` commit on this repository. This removes:

- Embedded Knowledge Center shell
- Team live seed script and report artifacts
- external REST query evidence additions

The Team gate PostgreSQL container and `/tmp/session-f-team-*` env files are local-only diagnostics state and are not part of rollback.
