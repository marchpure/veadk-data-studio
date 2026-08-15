# Console UX Decision Log

This is a working decision log for the one-hour commercial console UX review. It complements:

- `docs/product/commercial-data-studio-ux.md`
- `docs/product/console-ux-blueprint.md`
- `docs/product/commercial-connector-strategy.md`
- `docs/product/commercial-architecture-opportunities.md`

## 2026-08-15 16:56 CST Review Baseline

Current implementation evidence:

- `client/src/pages/Databases.tsx` is the current source management page.
- `client/src/components/SourceConnectorImportPanel.tsx` is the most advanced source picker path, especially for Feishu and TOS.
- `client/src/services/api.ts` already exposes `Datasource`, `SourceResource`, `SourceSnapshot`, `KnowledgeResource`, `SourceConnection`, `SourceUnderstanding`, and source-to-semantic-model types.
- `client/src/features/data-modeling` already has a stronger semantic-model product shape.
- Dashboards are split between older `Dashboard` HTML versions and newer `AnalysisArtifact` / result snapshot concepts.

The design should not invent a separate product. It should reorganize existing capability into a clearer commercial console.

## Decision 1: Rename `Databases` to `Sources`

Decision:

- The user-facing page must be `Sources`.
- `/databases` remains a compatibility route.

Reasoning:

- The page already manages uploaded files, URLs, PDFs, web resources, Feishu resources, object storage, Databricks, and SQL DBs.
- Calling it `Databases` makes document and file ingestion feel secondary, which contradicts the commercial direction.

Evidence:

- `Datasource.source_type` includes `connection`, `dataset`, and `source_resource`.
- `DatasourceType` includes connection types, file types, `SourceResourceType`, and `duckdb`.

Implementation note:

- Start with route alias and copy changes.
- Avoid backend table/API rename in the first slice.

## Decision 2: Keep connector UX source-owned, not OpenViking-owned

Decision:

- Byaan owns connector UX and connector state.
- OpenViking is a context store/provider behind source snapshots.

Reasoning:

- Source UX needs OAuth, reauthorization, scope errors, resource pickers, already-added state, source snapshots, sync mode, permissions, parsed tables, lineage, and semantic/dashboard consumers.
- OpenViking is useful after content is captured and parsed.

Existing fields that support this:

- `SourceConnection.status`
- `SourceConnection.capabilities`
- `SourceResource.status`
- `SourceResource.latest_snapshot_id`
- `SourceSnapshot.raw_storage_uri`
- `KnowledgeResource.provider`
- `KnowledgeResource.provider_resource_id`

Missing fields for commercial quality:

- `KnowledgeResource.context_uri`
- `KnowledgeResource.retrieval_provider_status`
- per-resource ACL propagation summary
- per-snapshot parser asset summary

## Decision 3: Source detail is the missing page

Decision:

- Add `/sources/:sourceId` before a new dashboard app page.

Reasoning:

- Without Source detail, users cannot understand whether a source is trustworthy enough to generate a semantic model or dashboard.
- Current source cards expose quick actions but no lineage, snapshot, table, or evidence workspace.

Use existing APIs:

- `GET /source-resources/{resource_id}`
- `GET /source-resources/{resource_id}/snapshots`
- `GET /source-resources/{resource_id}/processing`
- `POST /knowledge/search`
- source understanding APIs for database/source profiling

Needed additions:

- consumer counts by source:
  - semantic models
  - dashboards
  - notebooks
  - MCP tools
- parsed asset summary:
  - block count
  - table count
  - projected dataset id
  - evidence count
- context index metadata:
  - provider
  - context URI
  - index status
  - last indexed time

## Decision 4: Add Source must become a workflow, not a connector list

Decision:

- Replace the flat Add Datasource dialog with a guided Add Source flow.

Current issue:

- `Databases.tsx` renders a long left-hand list: upload, URL, PDF, web, connector catalog, PostgreSQL, MongoDB, MySQL, SQL Server, Oracle, SQLite, DynamoDB, Databricks.
- This is efficient for developers but not understandable for business users.

Target flow:

```text
Choose source family
-> configure/authorize
-> browse/select
-> preview and sync policy
-> processing
-> next action
```

Why this matters:

- It makes Feishu/Google/Microsoft/warehouse import feel like a managed workflow.
- It creates a natural place for permission state, parser warnings, and output explanation.
- It gives the user confidence before launching semantic model or dashboard generation.

## Decision 5: Dashboard should converge on `AnalysisArtifact`, not only old `Dashboard`

Decision:

- New commercial DashboardApp should align with `AnalysisArtifact` concepts.
- Existing `Dashboard` HTML versions remain as legacy/generated HTML dashboard artifacts.

Reasoning:

- `Dashboard` currently stores `notebook_id`, `version_num`, `html_content`, `created_at`.
- This is enough for generated HTML versions and viewer/share behavior.
- It is not enough for commercial DashboardApp concepts: objective, definition, blocks, source snapshots, semantic model versions, result snapshots, latest successful snapshot, and publish state.
- `AnalysisArtifact` already has:
  - `objective`
  - `definition_json`
  - `version`
  - `status`
  - `latest_result_snapshot_id`
  - source snapshot references
  - semantic model version references
  - result snapshot definitions

Implication:

- The first `/dashboards` workspace can list both:
  - existing shared HTML dashboards
  - analysis artifacts with result snapshots
- The long-term DashboardApp model should likely evolve from `AnalysisArtifact`, with HTML dashboard rendering as one output format.

Needed product wording:

- "Dashboard" = business-facing app/view.
- "Result snapshot" = last successful dashboard output.
- "HTML artifact" = one renderable output, not the source of truth.

## Decision 6: Semantic Models should show source and dashboard impact

Decision:

- Keep current semantic model UX direction.
- Add upstream source health and downstream dashboard/MCP consumers.

Reasoning:

- The existing Data Models page already has readiness, drift, owner, datasource, consumer counts.
- Commercial trust requires seeing whether the upstream source is stale or permission-blocked and whether downstream dashboards will be affected by edits.

Needed additions:

- latest source snapshot freshness
- source status
- dashboard consumer count and names
- "impact before publish" review step

## Decision 7: Overview should be operational, not promotional

Decision:

- Overview should be a health board.

Reasoning:

- The product is for repeated work: sources refresh, models drift, dashboards stale, OAuth expires.
- A landing-page style hero would waste the first viewport.

Overview should show:

- sources needing attention
- semantic drafts needing review
- dashboards stale or failed
- recent agent runs
- primary actions: add source, generate model, create dashboard

## Decision 8: Context indexing is asynchronous by default

Decision:

- Add Source completes after capture and initial parse have durable state.
- Context indexing runs asynchronously and can finish later.
- A source can be partially ready: tables or raw snapshots are usable while context indexing is pending or failed.

Reasoning:

- Commercial imports may include large PDFs, folders, object storage prefixes, and SaaS spaces.
- Blocking source creation on context indexing makes the workflow feel unreliable and makes provider outages look like source import failures.
- Users need to distinguish `captured`, `parsed`, `dataset projected`, and `context ready`.

UX implication:

- Processing stepper should show independent statuses for capture, parse, table detection, normalization, context indexing, and semantic suggestions.
- `Context index failed` should offer retry without discarding the source snapshot.
- Dashboard creation from a structured projected dataset can proceed while document context indexing retries, but evidence search should show partial readiness.

## Decision 9: Keep `AnalysisArtifact` internal, expose `Dashboard App` in product

Decision:

- Product copy should use `Dashboard App` or `Dashboard`.
- The internal generic model can remain `AnalysisArtifact` until the dashboard workspace proves the exact object boundary.
- Do not rename the backend model in the first dashboard slice.

Reasoning:

- `AnalysisArtifact` can represent report, dashboard, analysis memo, or dashboard-like generated artifact.
- Renaming the model too early would create migration churn while the old HTML `Dashboard` model still exists.
- The product needs a dashboard workspace before it needs perfect internal naming.

Implementation implication:

- `/dashboards` should return a unified dashboard item shape with `type: html_dashboard | analysis_artifact`.
- UI should show `Dashboard`, `Result snapshot`, and `HTML artifact` as distinct concepts.
- Backend can later introduce `DashboardApp` as a facade or migration target if `AnalysisArtifact` becomes too broad.

## Decision 10: Sources list is unified, details can split connection/resource

Decision:

- The top-level `Sources` page should use one unified table for connections, datasets, source resources, and warehouse/database entries.
- Source detail can show different tabs or sections by object type.
- Admin `Integrations` can still show connector-level configuration separately.

Reasoning:

- Users need one inventory of things usable by agents, semantic models, dashboards, and MCP.
- Splitting the first page into connections versus resources recreates the current mental stitching problem.
- Commercial density is better handled with filters, tabs, status columns, and detail pages than with separate top-level pages.

Implementation implication:

- Keep `Datasource.source_type` in the list payload for now.
- Add summary fields such as context status, parsed table count, semantic model count, and dashboard count.
- In detail views, route to appropriate panels for connection, dataset, source resource, or warehouse table.

## Decision 11: Semantic drafts can start from captured snapshots, publish requires stable snapshots

Decision:

- Semantic model draft creation can start from captured or parsed source snapshots.
- Publishing a semantic model should require stable source snapshot references and successful validation.
- Production MCP/dashboard consumers should use published semantic model versions only.

Reasoning:

- Requiring a fully published source before any draft slows exploration too much.
- Letting draft snapshots power production dashboards creates trust and reproducibility problems.
- The right split is fast draft generation plus strict publish gates.

Implementation implication:

- `Generate semantic model` can appear as soon as a source has enough parse/profile output.
- `Publish` should show source snapshot refs, drift, and validation status.
- If a source changes after publish, semantic model status should show drift and downstream impact.

## Decision 12: Production dashboards use published semantic models; exploratory dashboards can start from sources

Decision:

- Published/shared dashboards should use published semantic model versions whenever metrics are involved.
- Exploratory dashboards can start directly from selected sources for quick analysis.
- Direct source-to-dashboard output must be labeled draft/exploratory until it is validated or bound to a published semantic model.

Reasoning:

- Commercial dashboards need stable metric definitions, reproducible snapshots, and explainable lineage.
- Forcing a semantic model before every exploration slows early value.
- A draft dashboard can be a bridge into semantic model creation.

Implementation implication:

- `Create dashboard` from a ready source should offer `Explore draft` and `Use published model` paths when applicable.
- Sharing should prefer latest successful result from a published dashboard app.
- Direct source dashboards should show warnings before share/publish.

Allowed exploratory source-to-dashboard inputs:

- Uploaded structured files: CSV, Excel, Parquet, JSON when a projected dataset exists.
- SQL databases and warehouses when schema/sample/profile has completed.
- Feishu/Lark Sheets/Base when parsed into a structured projection.
- Object storage files when the selected object resolves to a supported structured file type and projection.
- Web/PDF/Docx/PPT text sources only for evidence-backed narrative/report drafts, not metric dashboards, until a structured extraction or semantic model exists.

Not allowed for shared/production dashboards without a published semantic model:

- Metrics across multiple sources.
- Joins or business definitions that need governed relationships.
- Permission-sensitive docs where evidence ACL propagation has not been validated.
- Any source with failed capture, unresolved parser warnings, permission loss, or stale required snapshots.

## Decision 13: China enterprise is the first-class deployment profile; global follows with Google or Microsoft by segment

Decision:

- Treat China enterprise as the first-class commercial profile for the current branch.
- Treat global enterprise as a parallel roadmap profile, not the first production promise.
- Keep small self-hosted/local team as a constrained profile for evaluation and lower-scale deployments.
- For global enterprise, prioritize Google Workspace for startup/product-led segments and Microsoft 365 for large enterprise/procurement-led segments. Do not build both before the Feishu/OAuth picker contract and source detail are solid.

Reasoning:

- Current production adapters already include Feishu and TOS, which fit China enterprise better than global enterprise.
- Google Workspace and Microsoft 365 both require serious OAuth, admin consent, picker, and ACL work. Building both at once would dilute connector quality.
- Self-hosted/local deployments may still use PostgreSQL-like metadata and native context fallback, but that must not define the commercial architecture.

Implementation implication:

- Connector catalog ordering should be profile-aware.
- China enterprise ordering: Feishu/Lark, Files, SQL, Object storage, Web, Databricks/warehouses.
- Global startup ordering once available: Files, Google Workspace, SQL/warehouses, Web, Object storage, Microsoft 365.
- Global enterprise ordering once available: Microsoft 365, SQL/warehouses, Files, Google Workspace, Object storage, Web.
- Admin should eventually expose enabled connector families per deployment/profile.

## Decision 14: Connector count should be sold as families, implemented as adapter groups

Decision:

- Commercial beta should sell 6 production adapter groups for the core loop: files, Feishu/Lark, web, SQL, object storage, and the existing Databricks path wrapped as a Source.
- Commercial v1 GA should sell 8 source families.
- Engineering v1 GA should target roughly 8-10 production adapter groups.
- The catalog can show 20+ entries only when `available`, `beta`, and `planned` are visually and behaviorally distinct.

Reasoning:

- Families match how users think: files, business docs, databases, warehouses, object storage, web, API, more.
- Adapter groups match how engineering can build leverage: one object storage contract can support TOS/S3-compatible variants; one SQL contract can support multiple dialects.
- Listing dozens of connectors before the core workflow works creates support debt and weakens trust.

Implementation implication:

- Add Source starts with family selection, then available connectors.
- Planned entries never open a fake production flow.
- Beta entries show support limitations and readiness gaps.
- Production promotion requires the readiness gates in `commercial-connector-strategy.md`.

## Decision 15: Dashboard Skill is a consumer, not the central semantic layer

Decision:

- Treat Dashboard Skill as a specialized Data Skill with layout, filters, explanation, refresh policy, delivery policy, and result snapshots.
- Keep Semantic Models as the central team-level semantic contract.
- Allow dashboards to hold local Metric Drafts during exploration, but require promotion to a published semantic model version before production sharing or agent/MCP consumption.

Reasoning:

- The earlier DashboardApp architecture work established that dashboard is a product and governance entry, not a SQL view, materialized view, dynamic table, or workflow by itself.
- The modeling review established that `Datasource` is physical/raw entry, `Semantic Model` is the governed data contract, `Data Skill` is an analysis workflow over a published model, and `Dashboard Skill` is one visual Data Skill form.
- If Dashboard becomes the only semantic source of truth, metric definitions fragment across canvases and agents cannot reliably consume them.

Implementation implication:

- Dashboard creation can start from source exploration, but shared dashboards should bind to a published semantic model version before they become production artifacts.
- Dashboard rows should show semantic model version, latest result snapshot, freshness, and share mode.
- Dashboard editing can include local draft metrics, but publish/review must show which Semantic Model version or draft promotion path is used.
- Agent and MCP default routing should prefer published Semantic Model versions and published Skills, not draft dashboards.

## 2026-08-15 P0 Implementation Note

Implemented in the current branch:

- `/sources` route alias renders the existing `DatabasesPage`.
- `/databases` remains compatible.
- Sidebar now links to `/sources` and treats `/sources` and `/databases` as the same active section.
- User-facing first-screen copy now says `Sources`.
- Add/create/delete visible copy now says `Source` where it is not a backend/internal type name.
- Source-resource status pills now show precise states such as `Syncing`, `Reauthorization required`, `Permission lost`, and `Needs confirmation` instead of a generic connector-required label.

Intentionally not changed yet:

- API and hook names such as `Datasource`, `useDatasources`, and `queryKey: ['datasources']`.
- Backend models and routes.
- The current Add Source dialog structure.
- The connector catalog grouping.

## Data Contract Map

### Sources page

Can use now:

- `Datasource.id`
- `Datasource.name`
- `Datasource.type`
- `Datasource.source_type`
- `Datasource.status`
- `Datasource.latest_snapshot_id`
- `Datasource.projected_dataset_id`
- `Datasource.created_at`
- `Datasource.is_public`

Needs:

- `last_synced_at`
- `freshness_status`
- `semantic_model_count`
- `dashboard_count`
- `evidence_count`
- `table_count`
- `context_index_status`

### Source detail

Can use now:

- `SourceResource`
- `SourceSnapshot`
- `KnowledgeResource`
- `SourceEvidence`
- `SourceUnderstanding`

Needs:

- source consumer endpoint
- parsed asset endpoint
- lineage endpoint
- context provider metadata

### Semantic Models

Can use now:

- semantic model list and detail
- readiness, drift, consumer counts in frontend model type
- publish/validate APIs

Needs:

- real dashboard consumer linkage
- source health join
- review owner/approval state

### Dashboards

Can use now:

- `DashboardListItem`
- `ViewerDashboardDetail`
- dashboard cache status
- dashboard refresh API
- `AnalysisArtifact`
- latest successful analysis artifact snapshot

Needs:

- unified dashboard list combining HTML dashboard versions and analysis artifacts
- dashboard app type/source
- semantic model/source references
- refresh policy
- share mode
- latest result snapshot metadata

## Current Risk Register

| Risk | Why it matters | Mitigation |
|---|---|---|
| Two dashboard models diverge | Old HTML Dashboard and AnalysisArtifact may confuse implementation | Treat old Dashboard as render artifact, AnalysisArtifact as future DashboardApp root. |
| Sources page becomes too dense | Commercial users need scanability, not clutter | Use table plus filters; source detail holds deep data. |
| Add Source flow gets too slow | Power users may prefer fast paths | Keep recent connector shortcuts and command palette actions. |
| OpenViking leaks into UX | Users should not reason about storage internals | Show Context status and Evidence, not backend engine names unless admin/debug. |
| Connector count explodes | More connectors dilute quality | Beta: 6 production adapter groups; v1 GA: 8 families; v1.5/v2: 12-13 families with SDK. |
| PG remains sticky | Existing native provider stores evidence in control DB | Add provider boundary first; migrate chunk/context payloads out after. |

## Next Review Questions

1. Should the first source summary facade ship as `GET /sources/overview` or as compatibility-first `GET /datasources/overview`?
2. Which dashboard app API should become the long-term facade over legacy `Dashboard` and internal `AnalysisArtifact`?
3. Which customer segment should determine the first global connector after Feishu: Google Workspace-led startup/global teams or Microsoft 365-led large enterprise teams?
