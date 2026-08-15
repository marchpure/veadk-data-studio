# Console UX Implementation Plan

This plan converts the UX blueprint into concrete implementation slices. It is intentionally scoped to the current Byaan console so that each slice can be reviewed, shipped, and tested independently.

Connector ownership, OpenViking usage, and production connector count are defined in `docs/product/commercial-connector-strategy.md`. Architecture deepening opportunities are recorded in `docs/product/commercial-architecture-opportunities.md`.

## Implementation Principles

- Preserve existing behavior while adding clearer routes and copy.
- Keep `/databases` as a compatibility path while introducing `/sources`.
- Reuse existing API types and hooks before adding new backend contracts.
- Add missing commercial fields through summary endpoints, not ad hoc client-side joins.
- Keep OpenViking behind provider metadata and context readiness; do not expose it as a core source connector.
- Make failure states visible and recoverable.
- Separate production adapters from planned catalog entries. Planned catalog tiles must not imply commercial support.

## P0 Slice: Rename Datasources to Sources

Goal:

- Make the current product surface match the actual scope: files, docs, web, object storage, databases, and warehouses.

Files:

- `client/src/App.tsx`
- `client/src/components/CollapsibleSidebar.tsx`
- `client/src/pages/Databases.tsx`
- `client/src/pages/HomePage.tsx`
- `client/src/pages/Integrations.tsx`

Tasks:

1. Add `/sources` route pointing to `DatabasesPage`.
2. Keep `/databases` route.
3. Update sidebar active-state logic to treat `/sources` and `/databases` as the same section.
4. Change visible sidebar label from `Datasources` to `Sources`.
5. Change page title from `Datasources` to `Sources`.
6. Change empty state from `No Database Connections` to `No Sources`.
7. Change loading copy from `Loading database connections...` to `Loading sources...`.
8. Change add button from `New datasource` to `Add source`.
9. Update first-run Home empty-state action to point to `/sources`.
10. Update Integrations data-source handoff copy to point users back to `Sources`.
11. Keep API names unchanged.

Acceptance:

- `/sources` and `/databases` both render the same page.
- Existing add/edit/delete behavior still works.
- No visible first-screen copy implies that only databases are supported.

Current branch status:

- Implemented route alias in `client/src/App.tsx`.
- Implemented sidebar link/active behavior in `client/src/components/CollapsibleSidebar.tsx`.
- Implemented first-screen and create/delete visible copy updates in `client/src/pages/Databases.tsx`.
- Implemented precise source-resource status copy in `client/src/pages/Databases.tsx`.
- Implemented Home empty-state link/copy update in `client/src/pages/HomePage.tsx`.
- Implemented Integrations Feishu data handoff link/copy update in `client/src/pages/Integrations.tsx`.

Implementation caution:

- `client/src/pages/Databases.tsx` is a large mixed page with create forms, Databricks OAuth, direct file upload, direct web/PDF resources, and connector catalog handling.
- Do not rewrite it wholesale in the rename slice.
- First slice should only add route alias, active nav behavior, and visible copy changes.
- Extract `AddSourceDialog` only in the family picker slice after the rename is reviewed.

## P0 Slice: Connector Catalog Honesty

Goal:

- Make the connector catalog commercially honest before adding more tiles.

Files:

- `server/services/connector_catalog.py`
- `client/src/pages/Databases.tsx`
- `client/src/components/SourceConnectorImportPanel.tsx`

Tasks:

1. Show `Available`, `Beta`, and `Planned` consistently.
2. For `Planned`, show request-access or roadmap copy; do not open a fake connection form.
3. In admin/debug views, show whether a tile has a production `SourceConnectorAdapter`.
4. Group planned vendor variants under their family instead of making the Add Source dialog look like dozens of supported connectors.
5. Define acceptance gates from `commercial-connector-strategy.md` before promoting any planned connector to available.

Acceptance:

- A customer cannot confuse planned catalog entries with supported production connectors.
- The commercial beta promise remains 6 production adapter groups, and v1 GA remains 8 source families, with adapter readiness visible internally.

## P1 Slice: Source List Density and Status

Goal:

- Replace large cards with a commercial table/list optimized for scanning.
- Introduce a source summary contract before the table becomes dependent on scattered client-side joins.

Files:

- `client/src/pages/Databases.tsx`
- optional extracted component: `client/src/components/sources/SourceListTable.tsx`

Tasks:

1. Introduce source tabs:
   - All
   - Files
   - Documents
   - SaaS apps
   - Databases
   - Warehouses
   - Object storage
   - Needs attention
2. Add summary metrics:
   - total sources
   - ready
   - needs attention
   - processing
   - projected datasets
3. Render desktop table with columns:
   - Source
   - Status
   - Type
   - Freshness
   - Output
   - Consumers
   - Owner/visibility
   - Actions
4. Keep current card layout only for narrow mobile.
5. Add filter logic based on current fields:
   - `source_type`
   - `resource_type`
   - `type`
   - `status`
   - `projected_dataset_id`

Current fields available:

- `Datasource.id`
- `Datasource.name`
- `Datasource.type`
- `Datasource.source_type`
- `Datasource.resource_type`
- `Datasource.status`
- `Datasource.latest_snapshot_id`
- `Datasource.projected_dataset_id`
- `Datasource.files_count`
- `Datasource.created_at`
- `Datasource.is_public`

Missing but not blocking:

- semantic model count
- dashboard count
- evidence count
- table count
- true freshness

Recommended summary API:

```text
GET /sources/overview
```

or, if preserving the old route namespace for one slice:

```text
GET /datasources/overview
```

Response shape:

```ts
type SourceOverviewItem = {
  id: string
  source_kind: 'connection' | 'dataset' | 'source_resource'
  family: 'files' | 'documents' | 'saas' | 'databases' | 'warehouses' | 'object_storage' | 'web' | 'api'
  provider: string
  resource_type?: string
  name: string
  status: string
  attention_state?: 'none' | 'auth' | 'permission' | 'parse' | 'index' | 'stale' | 'policy'
  freshness_status?: 'fresh' | 'stale' | 'unknown'
  last_synced_at?: string
  latest_snapshot_id?: string
  projected_dataset_id?: string
  context_index_status?: 'pending' | 'indexing' | 'indexed' | 'failed' | 'unavailable'
  parse_status?: 'pending' | 'parsed' | 'failed'
  parsed_asset_counts?: {
    blocks?: number
    tables?: number
    files?: number
    evidence?: number
  }
  consumer_counts?: {
    semantic_models: number
    dashboards: number
    notebooks: number
    mcp_tools: number
  }
  owner?: {
    id: string
    name?: string
  }
  visibility: 'private' | 'workspace' | 'team' | 'public'
  next_actions?: string[]
  created_at: string
  updated_at?: string
}
```

Backend source of truth for the first implementation:

- Keep current `/datasources` for compatibility.
- Build the overview facade from `Dataset`, `Connection`, `SourceResource`, `SourceSnapshot`, and `KnowledgeResource`.
- For unavailable counts, return `0` plus `counts_partial: true` or omit the field instead of doing expensive ad hoc joins.
- Do not expose OpenViking internals; expose `context_index_status`, `context_uri` only in admin/debug or Source detail metadata.
- Use this facade for `Sources`, source picker next actions, and Overview health cards.

Current implementation:

- `GET /sources/overview` is implemented as the canonical Sources facade.
- `GET /datasources/overview` is implemented as a compatibility alias.
- The backend service aggregates visible `Dataset`, `Connection`, `SourceResource`, `SourceSnapshot`, `KnowledgeResource`, and evidence counts into `SourceOverviewItem`.
- Statuses are normalized to product labels such as `Ready`, `Needs confirmation`, `Authorization required`, `Permission lost`, `Source unavailable`, and `Failed`.
- `consumer_counts.semantic_models` and notebook counts are populated from current model/notebook references where available; dashboard and MCP counts remain `0` with `counts_partial: true`.
- `next_actions` is populated for connection, dataset, and source-resource rows so the inventory can point users toward reauthorization, retry, evidence search, projection review, schema refresh, or semantic model generation without opening a detail page first.
- Frontend API types and `useSourceOverview()` are available.
- `client/src/pages/Databases.tsx` now renders the Sources inventory from `SourceOverviewItem` instead of the legacy datasource card list.
- Desktop uses a scan-oriented table with Source, Status, Freshness, Parsed assets, Context, Semantic, Dashboards, Owner, and Actions columns.
- Narrow viewports keep a compact mobile card layout.
- The inventory includes `All` and `Needs attention` tabs. Needs attention uses `attention_state` plus non-ready/non-processing product statuses.
- Source mutations invalidate both legacy `datasources` queries and the `source-overview` facade so the table stays fresh after create, import, delete, and visibility changes.
- Databricks connection-backed datasets are surfaced as `family = warehouses` with warehouse-specific next actions; TOS/object-storage source resources surface as `family = object_storage` with evidence/projection next actions.

Acceptance:

- A mixed workspace with files, source resources, and database connections is readable without opening every item.
- Source resources never show as `Connector required` when status is simply non-ready; they show a precise state.
- `Needs attention` tab isolates authorization, failed, stale, permission lost, and source unavailable states.

## P1 Slice: Add Source Family Picker

Goal:

- Replace the long left-side connector list with a family-first selection model.

Files:

- `client/src/pages/Databases.tsx`
- optional extracted component: `client/src/components/sources/AddSourceDialog.tsx`

Tasks:

1. Extract current create dialog into `AddSourceDialog` before changing interaction shape.
2. Add an initial `family` state before `selectedType`.
3. Render family tiles:
   - Files
   - Business docs
   - Databases
   - Warehouses
   - Object storage
   - Web
   - API
4. Show available connectors inside the selected family.
5. Preserve existing forms behind each selected connector.
6. Show each connector output:
   - Context
   - Dataset
   - Semantic-ready
   - Dashboard-ready
7. Show availability:
   - Available
   - Beta
   - Planned
8. For planned connectors, show request-access copy instead of a disabled dead end.
9. Keep Databricks wizard behavior unchanged while visually moving it under Warehouses.

Current implementation:

- `client/src/pages/Databases.tsx` now renders a family-first sidebar inside `Add Source`.
- Families are `Files`, `Business docs`, `Databases`, `Warehouses`, `Object storage`, `Web`, and `API / More`.
- The legacy long connector list has been removed from the dialog DOM; users pick a family first, then choose the exact source option.
- Existing setup forms are preserved behind the selected concrete option: uploads, file URL import, PDF, web page, SQL databases, MongoDB, DynamoDB, Oracle, Databricks, Feishu/Lark, and TOS.
- Databricks appears under `Warehouses` and reuses the existing OAuth/catalog/schema wizard.
- Connector catalog entries are mapped into families from `ConnectorDefinition.category`; `documents` maps to `Business docs`, `object_storage` maps to `Object storage`, `data_lake` maps to `Warehouses`, and database catalog entries map to `Databases`.
- Each source option shows availability (`available`, `beta`, `planned`) and output chips (`Context`, `Dataset`, `Semantic-ready`, `Dashboard-ready`) where applicable.
- Connector catalog payloads now expose `provider`, `family`, `limitations`, `required_scopes`, `resource_picker_type`, `status`, and `modeling_modes`, so the UI can show readiness constraints without hardcoding them into the Add Source dialog.
- Feishu/Lark advertises an OAuth drive picker and `context_assisted` / `projection` modeling modes; TOS advertises an object-storage browser and `projection` / `context_assisted` modes.
- Planned entries use `planned:<connector_id>` and never set `selectedType`, so they cannot open a working setup form by accident.
- Selecting a planned entry shows a read-only commercial readiness message sourced from the catalog limitations, including roadmap-only picker status and commercial readiness gates.
- If a family only has planned entries, the dialog automatically selects the first planned entry instead of keeping the previous family's setup form visible.
- The `AddSourceDialog` component extraction is intentionally deferred until post-import processing and source detail work define the reusable boundaries; this keeps this slice focused on behavior without moving a large mixed form tree.

Acceptance:

- Feishu/Lark is found under Business docs, not buried below PDF/Web.
- Databricks appears under Warehouses.
- Upload, PDF, Excel/CSV, and web are visually distinct.
- Power users can still pick the exact connector in one extra click.

## P1 Slice: Post-import Processing View

Goal:

- Keep users oriented after import and lead them into semantic/dashboard generation.

Files:

- `client/src/components/SourceConnectorImportPanel.tsx`
- `client/src/pages/Databases.tsx`
- `client/src/services/api.ts`

Tasks:

1. After import success, keep the panel open.
2. Show a processing stepper:
   - Capture
   - Parse
   - Detect tables
   - Normalize dataset
   - Index context
   - Generate semantic suggestions
   - Ready
3. Use current import results immediately.
4. Poll `/source-resources/{resource_id}/processing` when available.
5. Show next actions:
   - Open source
   - Generate semantic model
   - Create dashboard
6. Show partial success when multiple resources were selected.

Current implementation:

- `SourceConnectorImportPanel` keeps imported resources visible after `Import and sync`.
- Import results now render as processing cards instead of a flat success/failure list.
- The cards call `GET /source-resources/{resource_id}/processing` through `ApiService.getSourceResourceProcessing()` and `useSourceResourceProcessing()`.
- Each card shows the standard processing steps: `Capture`, `Parse`, `Detect tables`, `Normalize dataset`, `Index context`, `Generate semantic suggestions`, and `Ready`.
- Current backend stages are mapped conservatively: `waiting_for_connector`, `captured`, `indexed`, and `failed` drive the stepper while existing `latest_snapshot_id` and `projected_dataset_id` fill in partial readiness.
- Failed imports keep their resource row visible with the connector error and do not hide successful capture/parse state for other selected resources.
- Backend `next_actions` are shown as small action chips so the user sees whether to retry sync, reauthorize, attach to a notebook asset, or use knowledge retrieval.
- Processing state is short-polled only while the backend stage is not terminal.

Acceptance:

- Importing a Feishu doc does not simply close the dialog or return to a flat list.
- User can see whether content is indexed and whether a dataset projection exists.
- User has an obvious next step.
- Context indexing failure does not hide a successful capture/parse; the user sees partial readiness and retry.
- Parser confirmation required is a state, not a generic failure.

## P2 Slice: Source Detail Page

Goal:

- Give every source a home for snapshots, parsed assets, evidence, lineage, and consumers.

Files:

- `client/src/App.tsx`
- new `client/src/pages/SourceDetailPage.tsx`
- new `client/src/components/sources/SourceProcessingStepper.tsx`
- new `client/src/components/sources/SourceSnapshotsTable.tsx`
- new `client/src/components/sources/SourceEvidencePanel.tsx`
- `client/src/services/api.ts`

API support:

- `GET /source-resources/{resource_id}`
- `GET /source-resources/{resource_id}/snapshots`
- `GET /source-resources/{resource_id}/processing`
- `POST /knowledge/search`
- `GET /source-resources/{resource_id}/consumers`
- `GET /source-resources/{resource_id}/parsed-assets`
- `GET /source-resources/{resource_id}/lineage`

Tabs:

- Overview
- Snapshots
- Parsed content
- Tables
- Evidence
- Lineage
- Consumers
- Settings

Current implementation:

- `client/src/pages/SourceDetailPage.tsx` implements the read-only MVP for every `SourceOverviewItem`.
- `/sources/:sourceId` is registered in enterprise, community/local, and legacy local route trees.
- The Sources inventory links every source row to `/sources/:sourceId`; database and warehouse rows still keep the existing edit sidebar as a separate action.
- The page first resolves the row through `GET /sources/overview` so it can render connection, dataset, and source-resource sources without guessing the backing table.
- For `source_kind = source_resource`, the page reads `GET /source-resources/{resource_id}`, `GET /source-resources/{resource_id}/snapshots`, `GET /source-resources/{resource_id}/processing`, `GET /source-resources/{resource_id}/parsed-assets`, `GET /source-resources/{resource_id}/lineage`, `GET /source-resources/{resource_id}/consumers`, and `POST /knowledge/search`.
- For `source_kind = connection` or `dataset`, the page renders a SourceOverview-backed read-only detail and calls `GET /datasources/{datasource_id}/schema` to show schema/profile tables where available.
- The page shows metric cards for snapshot capture, dataset projection, context index status, and evidence count.
- The Processing section uses the same commercial step labels as post-import processing: `Capture`, `Parse`, `Detect tables`, `Normalize dataset`, `Index context`, `Generate semantic suggestions`, and `Ready`.
- Overview shows external identity, source URL, sync mode, and timestamps.
- Lineage is backed by the support API and shows source resource, source connection, latest snapshot, knowledge resource, and projected dataset nodes with captured/indexed/projected edges.
- Parsed content and Tables are read-only and backed by the support API. They show parser version, parser warnings, content hash, raw artifact URI, detected files, detected tables, projected dataset id, and evidence count.
- Evidence search is scoped to the current source resource and shows evidence type, confidence, and text preview.
- Consumers is backed by the support API and shows semantic models, notebooks, dashboards, and analysis artifacts that reference the source or its latest knowledge resource.
- Settings exposes visibility, context provider, provider status, last indexed time, retrieval debug URI, delete behavior, reindex behavior, and provider error metadata for admin/debug use.
- Source-resource detail now exposes a non-destructive `Retry sync` / `Reindex source` action for connector-backed resources and web URLs. The action calls `POST /source-resources/{resource_id}/sync` and refreshes overview, processing, snapshot, parsed asset, lineage, consumer, and evidence state so recovery is visible in place.

Acceptance:

- Opening a source explains whether it is safe to use for semantic model/dashboard generation.
- Source detail can answer: where did this data come from, when was it captured, how was it parsed, who uses it?
- Source detail links every blocker to the next action: reconnect, retry parse, confirm parser, retry index, regenerate semantic suggestions, or review consumers.

## P1 Slice: Data Modeling Source Handoff

Goal:

- Make the Data Modeling source picker consume the commercial Sources contract instead of silently filtering to legacy SQL datasources.
- Show why each connected source can or cannot produce a production semantic model.

Files:

- `client/src/features/data-modeling/adapters/dataModelingAdapter.ts`
- `client/src/features/data-modeling/components/CreateModelPanel.tsx`
- `client/src/features/data-modeling/store/useDataModelingStore.ts`
- `client/src/features/data-modeling/types.ts`

Current implementation:

- `dataModelingAdapter.listDatasources()` now prefers `GET /sources/overview` and falls back to the legacy `/datasources` API only when the Sources facade is unavailable.
- SourceOverview rows are mapped into explicit modeling handoff states:
  - `supported` for ready relational database sources.
  - `supported` with `warehouse` mode for ready Databricks/warehouse sources.
  - `needs_projection` for files, object storage, Feishu Sheets/Base, extracted tables, and any source with `projected_dataset_id`.
  - `context_only` for documents and web sources that can support definitions, policies, examples, and evidence but cannot be the production fact source for metrics.
  - `unsupported` for permission, auth, parser, source availability, and unsupported-family blockers.
- The Create Model picker shows every connected source with its family, modeling mode, status, next action, and blocker reason instead of only showing `No supported datasource found`.
- Profile loading and semantic generation are guarded so only `supported` sources with a relational/warehouse profile can continue into production generation.
- Projection and context sources stay visible but disabled for production generation until their projection or modeling contract is confirmed.

Acceptance:

- A workspace with only Feishu Docs/Web/PDF shows clear context/projection blockers instead of an empty SQL-only state.
- A workspace with SQL or Databricks sources still loads schema/profile evidence and can generate a draft.
- Token expiry, permission loss, parser failure, source unavailable, and in-progress states are visible in the picker with next action copy.
- The picker does not call profile/generation APIs for context-only, projection-needed, planned, or unsupported source families.

## P2 Slice: Dashboards Workspace

Goal:

- Make dashboards first-class instead of hiding them inside notebooks and folders.
- Expose `Dashboard` / `Dashboard App` in product copy while keeping `AnalysisArtifact` as an internal implementation root for this slice.

Files:

- `client/src/App.tsx`
- new `client/src/pages/DashboardsPage.tsx`
- existing `client/src/components/home/SharedDashboardsSection.tsx`
- `client/src/services/api.ts`

Current API support:

- viewer dashboard list/detail
- folder dashboard list/share/update APIs
- dashboard cache status
- dashboard refresh API
- analysis artifact list/detail/render/latest-successful-snapshot APIs

Decision:

- List both legacy HTML dashboards and `AnalysisArtifact`-backed dashboard apps.
- Treat old `Dashboard.html_content` as a render artifact.
- Treat `AnalysisArtifact.definition_json` as closer to the future dashboard app definition.

Needed API:

- `GET /dashboards/overview` or `GET /dashboard-apps`
- unified dashboard item shape:
  - id
  - type: `html_dashboard` or `analysis_artifact`
  - title
  - status
  - semantic model refs
  - source snapshot refs
  - latest successful result snapshot
  - freshness
  - share status
  - owner

Acceptance:

- A user can find all dashboards without knowing which notebook created them.
- Dashboard list shows freshness and refresh failure.
- Dashboard creation can start from a published semantic model.
- Failed refresh keeps the latest successful result visible.
- Dashboard rows show whether they are backed by legacy HTML dashboard artifacts or `AnalysisArtifact` definitions.

## P2 Slice: Semantic Model Impact Review

Goal:

- Make semantic model edits feel governed.

Files:

- `client/src/features/data-modeling/pages/DataModelsHomePage.tsx`
- `client/src/features/data-modeling/pages/DataModelBuilderPage.tsx`
- `client/src/features/data-modeling/publish/PublishWorkspace.tsx`

Tasks:

1. Add source health to the model list.
2. Add dashboard consumer impact to model detail.
3. Change builder tabs from `Explore / Model / Publish` toward:
   - Profile
   - Model
   - Validate
   - Publish
   - Consumers
4. During publish, show impacted dashboards/MCP tools.

Acceptance:

- Publishing a metric change shows which dashboards may change.
- Drift is tied back to source snapshots.
- Draft changes do not affect MCP/dashboard consumers until published.
- Publish review shows source health and latest source snapshot freshness.
- Draft generation can start from captured/parsed snapshots, but publishing requires stable source snapshot references and successful validation.

## P3 Slice: Context Provider Boundary

Goal:

- Make the knowledge provider swappable and ready for OpenViking without exposing storage internals to users.
- Stop growing PostgreSQL-backed long-lived chunk/evidence text storage for commercial deployments.

Files:

- `server/services/knowledge_provider.py`
- `server/models/knowledge_resources.py`
- migrations
- `server/services/source_resources.py`

Tasks:

1. Add provider metadata fields:
   - context URI
   - provider status
   - last indexed at
   - provider error
   - retrieval debug URI
   - provider metadata JSON
2. Change `KnowledgeProvider` search/read methods to return provider-neutral evidence payloads instead of requiring callers to depend on ORM `EvidenceFragment` rows.
3. Add `OpenVikingKnowledgeProvider`.
4. Keep `NativeKnowledgeProvider` as local/dev fallback.
5. Store raw/chunk-heavy payloads outside the control database.
6. Store only evidence locators, content hashes, provider refs, and small previews in the control plane.
7. Map OpenViking retrieval results back to Byaan evidence locators.
8. Add a migration/backfill job from existing native evidence to the external provider.
9. Add deployment config:
   - local/dev: `NativeKnowledgeProvider` allowed
   - commercial beta: OpenViking/default external provider required for new ingestion
   - migration mode: dual-read or dual-write until backfill is complete

Current implementation:

- `KnowledgeResource` now has provider metadata fields for `context_uri`, `provider_status`, `last_indexed_at`, `provider_error`, `retrieval_debug_uri`, and `provider_metadata_json`.
- `add_knowledge_provider_metadata` adds those columns idempotently for existing deployments.
- `KnowledgeResourceRead`, `ApiService` types, and `SourceResourceService._knowledge_resource_payload()` return the metadata to Source Detail.
- `NativeKnowledgeProvider` remains the default local/dev fallback and writes `byaan-native://...` context/debug URIs plus metadata that explicitly marks control-plane text storage as local fallback behavior.
- `OpenVikingKnowledgeProvider` exists as a provider boundary selected by `KNOWLEDGE_PROVIDER=openviking`, but it fails fast until a real OpenViking client is configured. This keeps OpenViking behind `KnowledgeProvider` and prevents accidental use of OpenViking connectors as the Add Source layer.
- No Add Source family or connector entry exposes OpenViking to ordinary users.

Acceptance:

- Source import can index to OpenViking without changing the UX.
- Source detail shows context readiness, not vector/chunk internals.
- The system can switch provider by configuration.
- Production source ingestion no longer creates new long-lived chunk bodies in the control database.

## Suggested Order

1. Rename + route alias.
2. Source list density and status.
3. Add Source family picker.
4. Post-import processing view.
5. Source detail page.
6. Dashboard workspace.
7. Semantic impact review.
8. OpenViking provider boundary.

This order improves visible UX first while keeping backend risk contained.

Rationale:

- Rename + route alias has the smallest blast radius and fixes the biggest product-language mismatch.
- Source list density should come before source detail, because it defines the summary fields source detail must explain.
- Family picker should come before adding more adapters, because it prevents connector count from becoming the product structure.
- Post-import processing should land before OpenViking integration, because it creates the UI place where provider readiness can appear.
- Source detail should land before dashboard workspace, because dashboards need credible freshness, lineage, and consumer references.
- OpenViking provider integration can proceed in parallel technically, but it should stay behind `KnowledgeProvider` and not change the Add Source mental model.

## Parallel Work Plan

The three layers can move in parallel only if their contracts are explicit.

| Workstream | Can run now? | Depends on | Output contract |
|---|---|---|---|
| Sources P0 rename/copy | Yes | none | `/sources` route, compatibility `/databases`, user-facing `Sources` copy. |
| Connector catalog honesty | Yes | current catalog | `available/beta/planned` behavior and readiness gates. |
| Source overview API | Shipped first backend slice | current `/datasources`, `SourceResource`, `SourceSnapshot`, `KnowledgeResource` | `SourceOverviewItem` facade for Sources and Overview health cards. |
| Add Source family picker | Yes, after P0 | current `DatabasesPage` create dialog | family -> connector -> existing forms without backend rename. |
| OpenViking provider boundary | Yes, backend parallel | `KnowledgeProvider`, `KnowledgeResource` migration | provider metadata, external context URI, provider-neutral evidence payload. |
| Source detail page | Yes, after overview shape | source resource/snapshot/knowledge APIs | source trust hub with snapshots, parsed assets, evidence, lineage, consumers. |
| Semantic impact review | Partially | source overview/source detail contracts | publish gate showing source snapshot refs and dashboard consumers. |
| Dashboards workspace | Partially | dashboard overview facade, published semantic model refs | unified dashboard list with freshness, latest-success snapshot, source/model lineage. |

Hard sequencing rules:

- Do not make OpenViking a visible Add Source connector for core enterprise flows.
- Do not make direct source-to-dashboard a production/shared path unless it is rebound to a published semantic model.
- Do not expand connector count before Add Source can distinguish available, beta, and planned.
- Do not move dashboard semantic definitions into dashboard-only state; dashboard can draft local metrics, but team-level semantics must publish through Semantic Models.
- Do not keep adding long-lived evidence/chunk bodies to the control database once the provider boundary is available.
