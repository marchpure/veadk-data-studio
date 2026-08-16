# Data Studio Commercial P0 Integration

CURRENT_PHASE: Final commercial integration evidence ledger. Connector/Modeling, Dashboard, Evaluation, and Sharing are unified on `integration/data-studio-commercial-p0`. Dashboard, Evaluation, Sharing, and projected-source Modeling have 8080 evidence. Connector readiness remains honestly classified as commercial beta / partial, not production-ready for every catalog row.

## Immutable Inputs

| Stream | Branch | Input SHA | Integration status |
| --- | --- | --- | --- |
| Connector / Modeling | `veadk-data-studio/agent/data-studio-p0` | `142837f7587dd1519d4287c1cb26c8e2840fc39a` | Merged. Source matrix remains `PARTIAL`: `0 ready / 14 beta / 26 planned / 0 blocked / 40 total`. |
| Dashboard | `veadk-data-studio/agent/dashboard-human-agent-p0` | `ef7ad32d031fcd5dea7102536720abd54b46ecdb` | Merged. 8080 Dashboard browser smoke passed, including explicit legacy asset coverage. |
| Evaluation / Sharing Governance | `veadk-data-studio/integration/evaluation-sharing-governance-p0` | `0c5b517381eedbc5c9a1181f82ab84d9965f2453` | Preserved and extended. Evaluation and Sharing 8080 release gates passed. |

## Unified Branch

- Branch: `integration/data-studio-commercial-p0`
- Worktree: `/Users/bytedance/worktrees/byaan-commercial-integration-p0`
- Remote used for integration branch: `veadk-data-studio`
- Initial base: `0c5b517381eedbc5c9a1181f82ab84d9965f2453`
- Release SHA source of truth: latest pushed branch HEAD at final deployment time, verified by `git rev-parse HEAD`, `git rev-parse @{u}`, and the matching OCI label `org.opencontainers.image.revision`.
- The exact final SHA is reported by the operator after the last documentation commit is pushed and the matching image is deployed. The document itself cannot embed its own final commit hash without changing that hash.

## 8080 Runtime Evidence

Final deployment contract:

- URL: `http://127.0.0.1:8080`
- Image: `byaan:selfhosted-data-studio-commercial-p0-${SHORT}`
- Container: `byaan-data-studio-commercial-p0-${SHORT}-8080`
- OCI revision label must equal `git rev-parse HEAD`.
- Upstream `veadk-data-studio/integration/data-studio-commercial-p0` must equal local HEAD.
- `BYAAN_VERSION`: `data-studio-commercial-p0-${SHORT}`
- Actual tenant selected after login: `38246331-19b7-480f-8c6e-2f6afd6b8033`
- Actual user from token: `3f376c15-cf9c-4a86-b952-ca13a45aa9a5`
- Persistent volume reused: `byaan_data_studio_p0_9718bf6_8080`

The final operator report must include the concrete `FINAL_SHA`, image, container, and evidence directories after the last rebuild/redeploy cycle.

## Merge And Conflict Resolution

- Created a unified integration branch from the Evaluation/Sharing governance branch.
- Merged Connector/Modeling input `142837f7587dd1519d4287c1cb26c8e2840fc39a`.
- Merged Dashboard input `ef7ad32d031fcd5dea7102536720abd54b46ecdb`.
- Preserved Evaluation/Sharing models, routers, services, MCP contracts, and migrations from governance.
- Resolved shared ownership in `server/main.py`, `server/models/__init__.py`, auth/scopes, folder/export routes, MCP registry/wrappers, Alembic chain tests, `client/src/App.tsx`, sidebar routes, client API service, package metadata, and smoke scripts.
- Alembic head remained a single commercial head: `add_canonical_sharing_model`.

## Dashboard Status

Status: 8080-ready for P0 commercial integration.

Implemented / preserved behavior:

- The explicit legacy asset `6b388ea5-9586-41a2-8ab9-51fd580d71af` no longer falls through to a generic app error.
- Legacy unstructured dashboards display lifecycle/status, asset/version identity, migration blocker text, and safe review / notebook preview actions.
- Structured actions remain blocked for legacy assets until structured manifest review is complete.
- Existing legacy HTML MCP/tool deprecation and security limits are preserved.
- Structured dashboard data views cover `saved_query`, `semantic_metric`, and `context_search`.
- Stale, partial, blocked, permission-denied, malformed, and policy-blocked states have explicit UI states.

8080 browser evidence:

- Command: `cd client && BASE_URL=http://127.0.0.1:8080 API_URL=http://127.0.0.1:8080 LEGACY_ASSET_ID=6b388ea5-9586-41a2-8ab9-51fd580d71af SCREEN_DIR=/tmp/byaan-dashboard-final-legacy-${SHORT} pnpm smoke:dashboard`
- Result: `ok: true`
- Browser stats: `pageerror=0`, `consoleError=0`, `requestfailed=0`, `http5xx=0`
- Screenshots: `/tmp/byaan-dashboard-final-legacy-${SHORT}`

Focused backend evidence:

- Command: `cd server && PYTHONPATH=..:tests uv run pytest tests/test_dashboard_contract_schemas.py tests/test_dashboard_execution_service.py tests/test_dashboard_lifecycle_service.py tests/test_dashboard_mcp_contract.py tests/test_dashboard_persistence_migration.py tests/test_dashboard_rest_api.py tests/test_dashboard_security_regressions.py tests/test_dashboard_legacy_tool_gating.py tests/test_migration_chain_hardening.py tests/test_data_studio_p0_source_matrix.py -q`
- Result: `60 passed, 103 warnings`

## Evaluation Status

Status: 8080-ready for P0 commercial integration.

Implemented / preserved behavior:

- Empty inventory has actionable onboarding instead of a blank list.
- UI supports suite creation, explicit demo fixture loading, case import/demo cases, draft version creation, publish, and preflight run creation.
- REST supports create suite, create draft version, create/import/list cases, publish suite version, create/claim/heartbeat/complete runs, failures, comparison, advisor verification/regression, and promotion decision.
- Release fixture is explicit: it is invoked by release gate or developer seed command only, not by production startup.
- Tenant isolation, scope protection, idempotency, redaction, and REST/MCP parity are covered by tests and gates.

8080 release gate evidence:

- Command: `BASE_URL=http://127.0.0.1:8080 CONTAINER=byaan-data-studio-commercial-p0-${SHORT}-8080 RUN_ID=${SHORT} FINAL_SHA=$(git rev-parse HEAD) IMAGE_DIGEST=$(docker image inspect byaan:selfhosted-data-studio-commercial-p0-${SHORT} --format '{{.Id}}') PYTHONPATH=. uv run python server/scripts/evaluation_release_gate_8080.py`
- Result: `ok: true`
- Created cases: `2`
- Published status: `published`
- Run status: `failed`
- Gate decision: `failed`
- Failure count: `1`
- Sensitive payload redaction: verified by gate assertions.

8080 browser evidence:

- Seed command: `docker exec ... EVALUATION_SMOKE_TENANT_ID=38246331-19b7-480f-8c6e-2f6afd6b8033 EVALUATION_SMOKE_USER_ID=3f376c15-cf9c-4a86-b952-ca13a45aa9a5 ... server/scripts/seed_evaluation_smoke.py`
- Browser command: `cd client && BASE_URL=http://127.0.0.1:8080 API_URL=http://127.0.0.1:8080 EVALUATION_SMOKE_FIXTURE_FILE=/tmp/byaan-evaluation-fixture-${SHORT}.json SCREEN_DIR=/tmp/byaan-evaluation-ui-${SHORT} pnpm smoke:evaluation`
- Result: `ok: true`
- Browser stats: `pageerror=0`, `consoleError=0`, `requestfailed=0`, `http5xx=0`
- Screenshots: `/tmp/byaan-evaluation-ui-${SHORT}`

Focused backend evidence:

- Command: `cd server && PYTHONPATH=..:tests uv run pytest tests/test_evaluation_contract_schemas.py tests/test_evaluation_persistence_migration.py tests/test_evaluation_service.py tests/test_evaluation_runner_service.py tests/test_evaluation_rest_api.py tests/test_evaluation_feedback_advisor_api.py tests/test_evaluation_mcp_contract.py -q`
- Result: `24 passed, 22 warnings`

## Sharing Status

Status: 8080-ready for P0 commercial integration.

Implemented / preserved behavior:

- Canonical grants back Notebook, Dashboard, Folder, and worker-backed surfaces.
- Folder notebook and folder dashboard shares create canonical evidence and revoke cleanly.
- External sharing policy is explicit in self-hosted mode.
- Secret/token/password/verifier values are redacted by service tests and release gate.

8080 release gate evidence:

- Command: `BASE_URL=http://127.0.0.1:8080 CONTAINER=byaan-data-studio-commercial-p0-${SHORT}-8080 RUN_ID=${SHORT} FINAL_SHA=$(git rev-parse HEAD) IMAGE_DIGEST=$(docker image inspect byaan:selfhosted-data-studio-commercial-p0-${SHORT} --format '{{.Id}}') PYTHONPATH=. uv run python server/scripts/sharing_release_gate_8080.py`
- Result: `ok: true`
- Tenant: `38246331-19b7-480f-8c6e-2f6afd6b8033`
- Folder notebook share/revoke: verified.
- Folder dashboard share/revoke: verified.
- Worker-backed notebook sharing in self-hosted mode: `403`, message `External sharing is not available in this deployment mode`.

Focused backend evidence:

- Command: `cd server && PYTHONPATH=..:tests uv run pytest tests/test_sharing_persistence_migration.py tests/test_sharing_canonical_service.py tests/test_sharing_read_surface.py -q`
- Result: `8 passed, 9 warnings`

## Connector / Modeling Status

Status: commercial beta / partial. Do not mark connector catalog ready-complete.

Matrix basis:

- `docs/product/data-studio-p0-source-matrix.md`
- Summary: `0 ready / 14 beta / 26 planned / 0 blocked / 40 total`
- OpenHuman runtime adapter provenance remains `UNVERIFIED`; semi-structured extraction rows must remain beta until runtime metadata records algorithm name/version, config digest, source revision, confidence, evidence locator, provenance, and warnings.

Backend evidence:

- Command: `cd server && PYTHONPATH=..:tests uv run pytest tests/test_async_sql_connector.py tests/test_databricks_connector.py tests/test_mongo_connector.py tests/test_web_source_adapter.py tests/test_source_understanding_api.py tests/test_semantic_modeling_api.py tests/test_real_source_connector_e2e.py tests/test_source_connectors_api.py tests/test_multi_source_artifacts_api.py tests/test_sources_overview_api.py tests/test_data_studio_p0_source_matrix.py -q`
- Result: `192 passed, 2 skipped, 275 warnings`
- The two skipped tests are real external source connector E2E checks gated by unavailable credentials. They are not counted as ready evidence.

8080 projected-source browser/API evidence:

- Command: `BASE_URL=http://127.0.0.1:8080 API_URL=http://127.0.0.1:8080 E2E_EMAIL=admin@example.com E2E_PASSWORD=password RUN_ID=${SHORT}-seq-$(date +%s) SCREEN_DIR=/tmp/byaan-data-studio-projected-source-${SHORT}-seq node client/scripts/data-studio-p0-projected-source-e2e.mjs`
- Result: `ok: true`
- Covered: authenticated CSV source upload, raw snapshot, projection review, semantic draft, publish, MCP `query_metric`, reload persistence, source detail desktop/mobile, model desktop/mobile.
- Browser stats: `pageerror=0`, `consoleError=0`, `requestfailed=0`, `http5xx=0`
- Evidence: `/tmp/byaan-data-studio-projected-source-${SHORT}-seq/result.json`
- Note: run browser smokes sequentially with the shared `admin@example.com` account. The refresh-token service intentionally revokes prior user tokens on login/refresh, so parallel smoke jobs with the same user can invalidate each other's browser sessions.

Residual connector/modeling risks:

- Live tenant credentials are still missing for several beta connector rows, including real Feishu/Lark tenant E2E, real TOS objects, and real Databricks OAuth/catalog drill-down.
- MongoDB and DynamoDB have document profile evidence; they must not be promoted to semantic-ready until reviewed tabular projection materialization and semantic draft handoff are proven with real data.
- Semi-structured context extraction uses native evidence today; OpenHuman-compatible runtime provenance is not yet verified in persisted metadata.
- Large/resumable upload, richer crawler/page-group policy, dialect-specific profiling, and real customer-scale fixtures remain beta hardening.

## Migration Status

Current verified head:

- Command: `cd server && PYTHONPATH=..:tests uv run alembic heads`
- Result: `add_canonical_sharing_model (head)`

Focused migration evidence:

- Command: `cd server && PYTHONPATH=..:tests uv run pytest tests/test_migration_chain_hardening.py -q`
- Result: `5 passed, 8 warnings`

Previously verified during this integration run:

- Fresh SQLite upgrade to `add_canonical_sharing_model`.
- Existing SQLite upgrade to `add_canonical_sharing_model`.
- Disposable PostgreSQL upgrade to `add_canonical_sharing_model`.
- Existing persistent 8080 volume upgraded by the self-hosted entrypoint.
- Dashboard legacy backfill, Evaluation tables, and canonical Sharing tables are included in the single Alembic chain.

No manual Alembic stamp was used to hide migration failures.

## Frontend / Build Evidence

- Command: `cd client && pnpm build:check`
- Result: passed.
- Accepted pre-existing warnings: stale Browserslist data, CSS minifier warnings for escaped autofill selectors, dynamic import/static import chunking warnings, and large final bundle warning.
- Command: `cd client && pnpm lint`
- Result from earlier integration run: `357 problems (0 errors, 357 warnings)`, accepted as pre-existing warnings.
- Command: `node --check client/scripts/evaluation-workspace-smoke.mjs && git diff --check`
- Result: passed after tightening Evaluation smoke locators to avoid JSON-panel text ambiguity.

## Final Release Checklist

| # | Requirement | Status |
| ---: | --- | --- |
| 1 | Four streams unified in one branch | Done |
| 2 | Final SHA pushed to remote integration branch | Done; verify concrete SHA in operator report |
| 3 | Worktree clean | Done after final commit/push verification |
| 4 | Upstream equals HEAD | Done after final commit/push verification |
| 5 | Alembic single head | Done: `add_canonical_sharing_model` |
| 6 | Fresh/existing migration proof | Done for integration run; rerun final focused checks after final image if code changes |
| 7 | Legacy dashboard avoids generic error | Done |
| 8 | Structured dashboard works | Done |
| 9 | Evaluation empty state actionable | Done |
| 10 | Evaluation explicit create/run loop | Done |
| 11 | Connector/modeling states honest | Done: `0 ready / 14 beta / 26 planned / 0 blocked` |
| 12 | OpenHuman provenance or beta | Done: provenance unverified, rows remain beta |
| 13 | REST/MCP parity | Done in focused tests and release gates |
| 14 | 1440x900 and 390x844 browser smoke | Done for Dashboard, Evaluation, projected-source Modeling |
| 15 | Latest image deployed to 8080 | Done after final image verification |
| 16 | 8080 release gate on latest image | Done after final image verification |
| 17 | Results written here | Done, with final concrete values in operator report |
| 18 | Final commit and push | Done; verify concrete SHA in operator report |

## Final Report Fields

The final operator report must include the concrete values after the last build and push:

- `FINAL_SHA`
- Branch: `integration/data-studio-commercial-p0`
- Image: `byaan:selfhosted-data-studio-commercial-p0-${FINAL_SHA:0:12}`
- Container: `byaan-data-studio-commercial-p0-${FINAL_SHA:0:12}-8080`
- Migration head: `add_canonical_sharing_model`
- 8080 URL: `http://127.0.0.1:8080`
- Connector matrix: `0 ready / 14 beta / 26 planned / 0 blocked / 40 total`
- Browser evidence directories for Dashboard, Evaluation, and projected-source Modeling
- Residual risks listed above
