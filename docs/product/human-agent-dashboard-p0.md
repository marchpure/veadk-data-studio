# Human + Agent Governed Dashboard P0

Status: authoritative Dashboard P0 contract for `agent/dashboard-human-agent-p0` after current-code audit on 2026-08-16.

This branch delivers Dashboard in the isolated worktree `/Users/bytedance/worktrees/byaan-dashboard-p0`. It does not write the Unified development branch. Integration into Unified and any real `8080` release remain separate serialized work.

## Baseline Audit

Current Dashboard is valuable but HTML-first:

| Area | Current files | Current behavior | P0 requirement |
| --- | --- | --- | --- |
| Version storage | `server/models/dashboard.py`, `server/repositories/dashboard.py`, `server/migrations/versions/4e084a86c962_add_dashboards_table.py` | `dashboards` rows store `tenant_id`, `notebook_id`, `version_num`, `html_content`, `created_at`. Versions are rows, but there is no stable asset, manifest, status, ETag, actor, validation, or immutable publish contract. | Add stable `DashboardAsset`; evolve `dashboards` as additive version records that retain HTML and store validated manifest metadata. |
| Notebook relation | `server/models/notebooks.py`, `server/routers/notebooks.py`, `server/services/notebook.py` | Notebook owns dashboards and saved queries. HTML endpoints return version HTML and set viewer cookies. | Keep existing notebook/version URLs as legacy read path; structured API must expose stable asset/version identities. |
| Query execution | `server/services/query_service.py`, `server/repositories/queries.py`, `server/schemas/query.py` | Batch endpoints accept caller-supplied query IDs or query/filter payloads. `QueryService.execute_batch_saved_queries` executes IDs without a dashboard binding argument. | Dashboard query accepts `data_view_id` only. Server resolves query/model/source from selected immutable manifest and validates tenant, share, row/column policy, redaction, and credential scope. |
| Viewer sharing | `server/routers/folders.py`, `server/services/folder_service.py`, `server/models/folder_dashboard.py`, `server/services/viewer_session_service.py` | Folder dashboard shares grant access to a dashboard HTML version. Viewer batch route checks dashboard access, then forwards caller query IDs. | Viewer batch compatibility must prove every legacy query belongs to the same dashboard version/notebook/tenant. Structured route must not accept raw query IDs. |
| Cache/freshness | `server/services/dashboard_cache_service.py`, `server/services/dashboard_refresh_service.py`, `server/routers/cache.py`, `server/services/query_cache.py` | Dashboard cache refresh enumerates all saved queries for a notebook and stores per-query cache. Stale state is not a DashboardRun contract. | `DashboardRun` reports `as_of`, cache/stale, partial failures, source/model pins, evidence, and lineage per data view. |
| Folder snapshot/export | `server/models/folder_dashboard.py`, `server/models/folder_notebook.py`, `server/services/notebook_export_service.py`, `server/routers/exports.py` | Snapshot columns exist for folder shares; PDF/compiled HTML export renders or embeds HTML. There is no immutable DashboardRun artifact. | Preserve share/export URLs. Only call `pinned_snapshot` when immutable run/result artifacts exist; otherwise report blocked or live honestly. |
| MCP | `server/mcp/tools.py`, `server/mcp/tool_wrappers.py`, `server/mcp/auth.py`, `server/mcp/session_manager.py` | MCP has semantic model tools and Dashboard HTML edit tools: `get_existing_html`, `apply_html_patch`, `dashboard_search_replace`, plus saved-query and filter helpers. | Add Dashboard MCP tools over the same `DashboardService` as REST. Legacy HTML tools remain only for `legacy_unstructured` dashboards and cannot publish structured versions. |
| Semantic model | `server/models/semantic_models.py`, `server/services/semantic_model_service.py`, `server/routers/semantic_models.py` | Published versions, entities, metrics, dimensions, readiness, lineage, and MCP preview exist separately from Dashboard. | Manifest pins published semantic model versions, source snapshots, allowed metrics/dimensions, and lineage/evidence locators. Draft/blocked models cannot publish dashboards. |
| Frontend | `client/src/components/DashboardPreviewPanel.tsx`, `client/src/utils/dashboardHtml.ts`, `client/src/utils/dashboardFilters.ts`, `client/src/services/api.ts` | UI previews and edits generated HTML in an iframe, rewrites backend URLs, injects viewer config and batch query/filter behavior. | Add structured Dashboard workspace in existing navigation: inventory, view, data, lineage/evidence, edit/review, validate, preview, publish, reload, share/export. Renderer consumes manifest/run only. |

## Product Contract

Dashboard P0 is one governed asset with two consumers:

- Human UI consumes the versioned manifest and run response through REST.
- REST/MCP Agent tools consume the same manifest, service, authorization, execution, evidence, lineage, and audit.
- HTML is a deterministic renderer/export artifact or a `legacy_unstructured` compatibility format. Agents never infer business meaning from HTML, DOM, screenshots, chart pixels, or regex.
- Existing dashboards, HTML, folder shares, viewer URLs, exports, saved queries, semantic models, and MCP auth/session infrastructure are reused through additive migration.

## Stable Asset And Immutable Versions

Add `DashboardAsset` as the stable identity:

- `tenant_id`, stable slug/name/description, owner, tags, lifecycle, access policy, default freshness policy, consumer/health summaries, and ETag.
- `current_draft_version_id` and `published_version_id`.
- Lifecycle values: `legacy_unstructured`, `draft`, `in_review`, `published`, `archived`.

Evolve `dashboards` rows as version records without dropping existing columns:

- Keep `notebook_id`, `version_num`, `html_content`, existing share/export references, and existing URLs.
- Add `asset_id`, `manifest_schema_version`, `manifest_json`, `content_hash`, `status`, actor/change metadata, pinned semantic/source refs, validation result, renderer version, and migration state.
- Draft changes use the controlled `PATCH /api/dashboard-assets/{id}/draft` entry point with allowlisted JSON Patch plus `If-Match`/`base_etag`; stale edits return structured `409`.
- The canonical Human/Agent edit payload is `json_patch`. Compatibility full-`manifest` submissions are accepted only when the top-level changed-key set is within the same allowlist: `title`, `description`, `audience`, `semantic_bindings`, `data_views`, `filters`, `layout`, `tiles`, `actions`, `freshness_policy`, `access_policy`, and `migration`. Any full manifest update that changes `schema_version`, `dashboard_id`, `provenance`, or another non-allowlisted top-level key returns `403`.
- Publish validates a draft and creates an immutable published version. Published versions never drift when model/source data changes.
- Reload creates a new draft and semantic diff; it never mutates the published version.

## `dashboard.manifest.v1`

Manifest validation uses typed Pydantic models and JSON Schema. Top-level fields:

- `schema_version`, `dashboard_id`, `title`, `description`, `audience`
- `semantic_bindings`, `data_views`, `filters`, `layout`, `tiles`, `actions`
- `freshness_policy`, `access_policy`, `provenance`, `migration`

`semantic_bindings` pin published model versions, source snapshot IDs, allowed metrics, and allowed dimensions.

P0 `data_views`:

- `semantic_metric`: metric, dimensions, grain, allowed filters, sort, limit, output schema, evidence/lineage.
- `saved_query`: explicit compatibility binding with saved query ID, output schema, filter contract, dataset/source lineage, and compatibility reason.
- `context_search`: evidence-bearing context results only; it cannot masquerade as a numeric metric.

Filters use semantic fields or bound query contracts. The server validates type, operator, domain, timezone, and affected data views. Clients never compose SQL.

Tiles use stable IDs and support `kpi`, `line`, `bar`, `area`, `table`, `text`, `evidence`, and `status`. Each tile includes business question, data-view binding, encoding/formatting, interactions, and accessible table/text fallback. Structured assets cannot execute arbitrary HTML/JavaScript tiles.

## `DashboardRun`

Every human and agent execution produces or references the same canonical run contract:

- dashboard asset/version, actor type/ID, session/correlation ID, idempotency key;
- normalized filters and filter digest;
- pinned semantic/source versions and execution plan digest;
- per-view status, result/schema, row count, cache/stale, `as_of`, warnings, errors, evidence, and lineage;
- started/completed timestamps, overall freshness, pagination, and result artifact references.

Modes:

- `live`: executes or reads cache under policy and always reports `as_of`, cache/stale, and partial failure state.
- `pinned_snapshot`: reads immutable stored run/result artifacts only. Missing artifacts return blocked.

## Security Matrix

| Boundary | Current risk | Required control | Initial evidence |
| --- | --- | --- | --- |
| Viewer batch arbitrary query ID | `server/routers/folders.py` checked access to a dashboard, then forwarded supplied query IDs to `QueryService.execute_batch_saved_queries`. | Resolve dashboard version first and reject every query not bound to that dashboard version/notebook/tenant. Structured path accepts only `data_view_id`. | Implemented and covered by `server/tests/test_dashboard_security_regressions.py` for same-notebook allow, other-notebook reject, filtered-query reject, and cross-tenant reject. |
| Preflight arbitrary query ID | Viewer preflight validated caller query IDs without dashboard binding. | Same binding check as execution before compiling filters. | Implemented in the viewer binding guard and covered by the dashboard security regression suite. |
| Cross tenant | Repository tenant context filters some CRUD calls, but several relation queries join by IDs directly. | Every Dashboard asset/version/query/share lookup includes tenant and authorized principal. | Covered by `server/tests/test_dashboard_rest_api.py`, `server/tests/test_dashboard_security_regressions.py`, and the shared `DashboardRepository` tenant-scoped reads. |
| Share revocation | Viewer session token proves identity; folder access is checked at request time. | Revoked/unshared dashboard must fail for REST/viewer/MCP consistently. | Existing folder/viewer access remains the compatibility boundary; Dashboard-specific tests cover unshared/notebook and tenant boundary rejection. |
| MCP ambient owner access | MCP wrappers receive session tenant/user/notebook IDs and call agentic HTML tools. | MCP API key resolves explicit principal/scopes; no ambient owner bypass. | Governed MCP wrappers enforce tenant-role scopes and call `DashboardService`; legacy HTML tools are marked deprecated and blocked for structured versions. |
| Snapshot honesty | Share models expose `is_snapshot`, but Dashboard lacks immutable run artifacts. | `pinned_snapshot` only when result artifacts exist; otherwise blocked. | Implemented as explicit `409`/blocked behavior and covered by `server/tests/test_dashboard_execution_service.py` plus `DashboardRun` schema validation. |
| Secret/SQL leakage | Query errors may include execution details from lower services. | Dashboard errors redact SQL, credentials, cross-tenant names, and secrets. | Dashboard service returns structured generic errors for saved query, semantic metric, context search, and unresolved policy failures; focused tests assert policy and execution blocking behavior. |

## REST And MCP Surface

REST routes will be implemented under `/api/dashboard-assets` and call one `DashboardService`:

- `GET /api/dashboard-assets`
- `POST /api/dashboard-assets`
- `GET /api/dashboard-assets/{id}`
- `GET /api/dashboard-assets/{id}/versions/{version}`
- `PATCH /api/dashboard-assets/{id}/draft`
  - Controlled draft mutation entry point for Human UI and Agent/MCP parity.
  - Preferred payload: `json_patch` operations using `base_etag`.
  - Compatibility payload: full `manifest`, constrained by the same top-level allowlist as JSON Patch.
- `POST /api/dashboard-assets/{id}/validate`
- `POST /api/dashboard-assets/{id}/preview`
- `POST /api/dashboard-assets/{id}/publish`
- `POST /api/dashboard-assets/{id}/reload`
- `POST /api/dashboard-assets/{id}/query`
- `GET /api/dashboard-assets/{id}/state`
- `GET /api/dashboard-assets/{id}/lineage`
- `GET /api/dashboard-assets/{id}/audit`

MCP tools call the same service and serialize compact bounded JSON:

- `search_dashboards`
- `describe_dashboard`
- `get_dashboard_state`
- `query_dashboard`
- `explain_dashboard_tile`
- `get_dashboard_lineage`
- `create_dashboard_draft`
- `patch_dashboard_draft`
- `validate_dashboard`
- `preview_dashboard`
- `publish_dashboard`

## Human Workspace

The UI remains inside the existing `client/` app and Dashboard navigation. It must not become a standalone demo.

Workflow:

```text
inventory -> published view -> filter -> data table -> definition/evidence/lineage
-> open/create draft -> edit manifest tile/filter/layout -> validate -> preview
-> semantic diff review -> publish -> reload -> share/export
```

Inventory is a dense table/list showing owner, published/draft versions, model/version, freshness, readiness/warnings, consumers, and last update.

View mode shows identity, version, filters, `as_of`, freshness, warnings, primary tiles, and tabs for Dashboard/Data/Lineage-Evidence. Filter state persists across tabs.

Edit/review mode uses toolbar, outline, canvas, inspector, JSON Patch allowlist, ETag conflict handling, semantic diff, blockers, and publish gating.

Each tile must have loading, empty, partial, stale, permission denied, and error states plus accessible table/text fallback and inspector evidence.

## Legacy Migration

Migration is additive and rollback-safe:

1. Backfill stable assets by notebook/dashboard version family.
2. Preserve HTML, hash, share/export/viewer URL, and version rows.
3. Generate manifest candidates only from structured relations: notebook, saved query, output schema, filter contract, semantic model link, source lineage.
4. Do not infer intent from arbitrary HTML, DOM, screenshots, chart pixels, or naming guesses.
5. Unproven bindings remain `needs_review` and `legacy_unstructured`.
6. New and reviewed dashboards publish manifest-first.
7. SQLite and PostgreSQL migration paths must be tested; merge heads are reported for Integration Gate.

## Acceptance Evidence

Completion requires current evidence for:

- Human REST/UI and MCP parity for run/version/filter digest, values, units, freshness, `as_of`, warnings, evidence, and lineage.
- Structured renderer consumes canonical manifest/run only.
- Cross-tenant, unshared, revoked, RLS/column restriction, arbitrary query ID, ETag conflict, publish scope, semantic pin, reload diff, snapshot honesty, audit, and legacy compatibility tests.
- Frontend lint/build and browser journeys at 1440x900 and 390px with no page errors, console errors, failed requests, HTTP 5xx, overlap, or horizontal overflow.
- Clean worktree, pushed commits, migration head, drift report, and final `DASHBOARD_BRANCH_READY_FOR_INTEGRATION / 8080_PENDING_INTEGRATION` unless a real integration release verifies `8080`.
