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
  raw_artifact_uri?: string
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
  modeling_status?: 'supported' | 'needs_projection' | 'context_only' | 'permission_required' | 'reauthorization_required' | 'source_unavailable' | 'processing' | 'failed' | 'planned' | 'unsupported'
  modeling_mode?: 'relational' | 'warehouse' | 'projection' | 'context_assisted' | 'business_object' | 'event' | 'semantic_import'
  modeling_reason?: string
  modeling_next_action?: string
  modeling_evidence_summary?: string
  modeling_can_load_profile?: boolean
  created_at: string
  updated_at?: string
}
```

Backend source of truth for the first implementation:

- Keep current `/datasources` for compatibility.
- Build the overview facade from `Dataset`, `Connection`, `SourceResource`, `SourceSnapshot`, and `KnowledgeResource`.
- For unavailable or expensive counts, return `0` plus `counts_partial: true` or omit the field instead of doing ad hoc joins that can stall the inventory.
- Do not expose OpenViking internals; expose `context_index_status`, `context_uri` only in admin/debug or Source detail metadata.
- Use this facade for `Sources`, source picker next actions, and Overview health cards.

Current implementation:

- `GET /sources/overview` is implemented as the canonical Sources facade.
- `GET /datasources/overview` is implemented as a compatibility alias.
- The backend service aggregates visible `Dataset`, `Connection`, `SourceResource`, `SourceSnapshot`, `KnowledgeResource`, and evidence counts into `SourceOverviewItem`.
- Statuses are normalized to product labels such as `Ready`, `Needs confirmation`, `Authorization required`, `Permission lost`, `Source unavailable`, and `Failed`.
- `consumer_counts.semantic_models`, notebooks, dashboards, and analysis artifacts are populated from current model/notebook references where available. Dashboard inventory counts include both legacy HTML dashboards and AnalysisArtifact-backed dashboard apps created from consuming notebooks; MCP counts remain `0` with `counts_partial: true` until tool bindings become first-class records.
- `next_actions` is populated for connection, dataset, and source-resource rows so the inventory can point users toward reauthorization, retry, evidence search, projection review, schema refresh, or semantic model generation without opening a detail page first.
- Source-resource rows expose `raw_artifact_uri` from the latest immutable snapshot so Source detail can verify where the captured artifact lives without expanding PostgreSQL into raw/chunk/vector storage.
- `SourceOverviewItem` now exposes a backend-derived Data Modeling handoff: `modeling_status`, `modeling_mode`, `modeling_reason`, `modeling_next_action`, `modeling_evidence_summary`, and `modeling_can_load_profile`. The Data Modeling picker consumes these fields first and only falls back to local inference for older responses, so connectors can publish one Source contract instead of relying on page-specific family heuristics.
- Source-resource projection counts fall back from current sync config to the latest snapshot metadata and projection manifest, so CSV/Excel/Sheet/Base/object-storage projections still show table/file counts after reindex, snapshot reuse, or metadata-only migration paths.
- Frontend API types and `useSourceOverview()` are available.
- `client/src/pages/Databases.tsx` now renders the Sources inventory from `SourceOverviewItem` instead of the legacy datasource card list.
- Desktop uses a scan-oriented table with Source, Status, Freshness, Parsed assets, Context, Semantic, Dashboards, Owner, and Actions columns.
- The inventory uses product family labels rather than raw enum values, so `documents` displays as `Business docs` consistently with Add Source while the API contract remains stable for Data Modeling.
- Narrow viewports keep a compact mobile card layout.
- The inventory includes `All` and `Needs attention` tabs. Needs attention uses `attention_state` plus non-ready/non-processing product statuses.
- Source mutations invalidate both legacy `datasources` queries and the `source-overview` facade so the table stays fresh after create, import, delete, and visibility changes.
- Databricks connection-backed datasets are surfaced as `family = warehouses` with warehouse-specific next actions. The overview facade now checks safe OAuth metadata from the legacy connection object so missing OAuth blocks, missing refresh tokens, and expired access tokens show `Authorization required` or `Reauthorization required` instead of `Ready`; token values are not exposed. TOS/object-storage source resources surface as `family = object_storage` with evidence/projection next actions.
- TOS prefix and bucket snapshots now expose object manifests through snapshot metadata and `projection_manifest.files`, so Sources overview can count listed objects and Source Detail Parsed content can show bucket/key/etag locators without creating a fake projected dataset.
- Connector resource picker failures now persist as source connection health. Reauthorization, permission, and upstream availability errors update `SourceConnection.status` and non-secret `capabilities.last_error` metadata, making picker failures visible to Sources list, Source Detail settings, and the Add Source recovery path instead of disappearing as transient request errors.
- Sources overview also reads non-secret `SourceConnection.capabilities.last_error.code` when a connector-backed connection is failed, so permission picker failures surface as `Permission lost` instead of collapsing into a generic unavailable state.
- SQL and warehouse connection-backed Sources now gate readiness on schema/profile health. Missing or empty schema profiles show `Pending` with `Refresh schema profile`, invalid schema caches show `Failed` with profile recovery, and only non-empty table profiles are exposed as `Ready` for Data Modeling.

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
- Existing setup forms are preserved behind the selected concrete option: uploads, file URL import, PDF, web page, supported SQL databases, Oracle, Databricks, Feishu/Lark, and TOS. Legacy MongoDB/DynamoDB code paths remain for compatibility, but the commercial Add Source picker shows them only as planned roadmap entries and does not open setup forms for them.
- Databricks appears under `Warehouses` and reuses the existing OAuth/catalog/schema wizard.
- Databricks warehouse creation keeps the Add Source flow open after batch create, shows created warehouse Sources, and links users to `Open source`, `Create model`, and the Sources inventory instead of closing directly back to the list.
- Connector catalog entries are mapped into families from `ConnectorDefinition.category`; `documents` maps to `Business docs`, `object_storage` maps to `Object storage`, `data_lake` maps to `Warehouses`, and database catalog entries map to `Databases`.
- Each source option shows availability (`available`, `beta`, `planned`) and output chips (`Context`, `Dataset`, `Semantic-ready`, `Dashboard-ready`) where applicable.
- Connector catalog payloads now expose `provider`, `family`, `limitations`, `required_scopes`, `resource_picker_type`, `status`, `modeling_modes`, `entry_kind`, and structured `readiness_gates`, so the UI can show readiness constraints without hardcoding them into the Add Source dialog.
- The catalog now covers the six commercial beta adapter groups as available entries: Files, Feishu/Lark, Web, SQL databases, TOS object storage, and Databricks warehouse. Files/Web/SQL/Databricks are `embedded_flow` entries that attach readiness metadata to existing Add Source forms; Feishu/TOS stay `connector_backed` entries that open the connector picker/import panel.
- Available entries can now report `passed`, `partial`, or `not_applicable` readiness gates. This keeps commercial beta connectors selectable while making incomplete hardening work explicit. Planned entries still report the same gate list as `missing` and cannot open setup forms. The Add Source picker and connector panels show passed/partial gate summaries plus the first non-passed gates.
- Feishu/Lark advertises an OAuth drive picker and `context_assisted` / `projection` modeling modes; TOS advertises an object-storage browser and `projection` / `context_assisted` modes.
- Planned entries use `planned:<connector_id>` and never set `selectedType`, so they cannot open a working setup form by accident.
- NoSQL connectors such as MongoDB and DynamoDB are planned-only in the commercial Add Source picker until a governed business-object adapter passes the same readiness gates as the six beta adapter groups.
- Selecting a planned entry shows a read-only commercial readiness message sourced from the catalog limitations, including roadmap-only picker status and commercial readiness gates.
- If a family only has planned entries, the dialog automatically selects the first planned entry instead of keeping the previous family's setup form visible.
- Connector import results now carry explicit already-added state: initial imports return `resource_action = created`, repeat imports reuse the existing Source Resource with `resource_action = reused` / `already_added = true`, and the processing card labels the result as `Already in Sources` with open/reindex next actions.
- The `AddSourceDialog` component extraction is intentionally deferred until post-import processing and source detail work define the reusable boundaries; this keeps this slice focused on behavior without moving a large mixed form tree.

Acceptance:

- Feishu/Lark is found under Business docs, not buried below PDF/Web.
- Databricks appears under Warehouses.
- Upload, PDF, Excel/CSV, and web are visually distinct.
- Power users can still pick the exact connector in one extra click.

## P1 Slice: Files Source Upload Expansion

Goal:

- Move the first-run file path from PDF-only context ingestion to a unified Files Source path that can support context evidence and projection handoff.

Files:

- `server/routers/source_resources.py`
- `server/services/source_resources.py`
- `server/services/source_connectors.py`
- `server/services/source_overview.py`
- `server/schemas/source_resources.py`
- `client/src/pages/Databases.tsx`
- `client/src/services/api.ts`
- `client/src/hooks/useDBConnections.ts`

Current implementation:

- `POST /source-resources/files` accepts PDF, CSV, Excel `.xlsx/.xlsm`, Docx, and PPTX uploads.
- `POST /source-resources/pdf` remains a compatibility endpoint and delegates to the unified file upload path.
- PDF uploads keep `resource_type = pdf` for existing consumers; CSV, Excel, Docx, and PPTX use `resource_type = file`.
- All supported files create immutable Source snapshots with `provider = local_file_upload`, original filename, file type, parser version, content hash, raw artifact URI, and `KnowledgeProvider` metadata.
- CSV and Excel `.xlsx/.xlsm` additionally create projected datasets and attach the projection manifest to both the source resource and snapshot metadata.
- PDF, Docx, and PPTX enter the Source layer as context evidence only unless a reviewed projection is created later.
- PPTX text extraction is supported for OpenXML presentations; legacy `.ppt` and binary `.xls` are not marked available until a conversion/parser worker exists.
- The Sources overview facade includes `resource_type = file`, so file uploads appear in the unified inventory.
- The Add Source Files option is labeled `Files as Source` and communicates that CSV/Excel can project to datasets while PDF/Docx/PPTX remain context-assisted.

Acceptance:

- Uploading CSV through `/source-resources/files` yields a Source snapshot, context evidence, and a projected dataset id.
- Uploading Docx or PPTX yields context evidence without falsely claiming semantic-ready dataset projection.
- Legacy `/source-resources/pdf` callers still work.
- Unsupported old Office binary formats fail before users see a false available path.

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
- The backend processing payload now returns structured `steps` with `pending`, `running`, `succeeded`, `skipped`, or `failed` status so import cards and Source Detail consume the same Source processing contract instead of each view guessing readiness from a single stage.
- Connector import cards and direct Files/Web creation cards now render the backend `steps` contract directly when present, including skipped and failed steps, so stale snapshots with current authorization or permission blockers are not displayed as a generic front-end progress guess.
- Failed imports keep their resource row visible with the connector error and do not hide successful capture/parse state for other selected resources.
- Backend `next_actions` are shown as small action chips so the user sees whether to retry sync, reauthorize, attach to a notebook asset, or use knowledge retrieval.
- Object-storage large object imports surface as `Needs confirmation` with `Review object size` and `Confirm large object sync` actions. The processing card uses a confirmation tone instead of presenting the item as a generic failed import.
- Processing state is short-polled only while the backend stage is not terminal.
- Direct Files as Source and Web source creation in `Databases.tsx` now also keep the Add Source dialog open after create success.
- Direct file/web results render the same standard processing steps and poll `GET /source-resources/{resource_id}/processing` through `useSourceResourceProcessing()`.
- Direct file/web result cards expose next actions for `Open source`, `Search evidence`, `Create model`, and `Add another source`; the primary create button is disabled while the created source is being reviewed to prevent accidental duplicate submission.

Acceptance:

- Importing a Feishu doc does not simply close the dialog or return to a flat list.
- Creating a direct PDF/CSV/Excel/Docx/PPTX or Web source does not close the dialog before processing state and next actions are visible.
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
- For `source_kind = connection` or `dataset`, the page renders a SourceOverview-backed detail and calls `GET /datasources/{datasource_id}/schema` to show schema/profile tables where available.
- `SourceOverviewItem` now carries optional `connection_id` for connection-backed sources. Database and warehouse detail pages expose a non-destructive `Refresh profile` action that calls the existing connection schema refresh API, then reloads Sources overview and schema/profile detail.
- The page shows metric cards for snapshot capture, dataset projection, context index status, and evidence count.
- The Processing section uses the backend `steps` contract with the same commercial labels as post-import processing: `Capture`, `Parse`, `Detect tables`, `Normalize dataset`, `Index context`, `Generate semantic suggestions`, and `Ready`.
- Overview shows external identity, source URL, sync mode, and timestamps.
- Lineage is backed by the support API and shows source resource, source connection, latest snapshot, knowledge resource, and projected dataset nodes with captured/indexed/projected edges.
- Parsed content and Tables are read-only and backed by the support API. They show parser version, parser warnings, content hash, raw artifact URI, detected files, detected tables, projected dataset id, and evidence count.
- Source Detail support APIs resolve projected dataset ids and parsed projection assets from the current sync config or latest snapshot metadata/projection manifest, keeping detail, lineage, consumers, and the Sources overview consistent after reindex, snapshot reuse, and metadata-only migration paths.
- Evidence search is scoped to the current source resource and shows evidence type, confidence, text preview, and locator chips such as snapshot, URL, document token, block, page, table, row, revision, and content hash. Evidence cards now open a full context dialog backed by `GET /api/evidence/{id}`, showing the complete evidence text, source resource, source snapshot, user-facing context readiness, raw locator JSON, and snapshot metadata; provider/debug metadata is kept in a collapsed diagnostics section.
- Source Detail exposes stable section anchors for Overview, Snapshots, Parsed content, Tables, Evidence, Lineage, Consumers, and Settings. Links such as `/sources/{id}#evidence` land on the evidence section, and empty evidence searches return the latest source-scoped evidence instead of searching for a literal wildcard token.
- Consumers is backed by the support API and shows semantic models, notebooks, dashboards, and analysis artifacts that reference the source or its latest knowledge resource.
- Settings exposes visibility, context readiness, last indexed time, evidence count, delete behavior, and reindex behavior. KnowledgeProvider provider names, context URIs, retrieval debug URIs, provider metadata, and provider errors are available only inside a collapsed `Context diagnostics` section so ordinary source management does not expose OpenViking or native storage internals. Destructive source and connector actions now show downstream consumer impact counts before confirmation so users can review semantic models, notebooks, dashboards, and artifacts that will lose fresh sync or modeling handoff.
- Connector-backed Source Detail now includes a redacted source-owned authorization summary from the backing `SourceConnection`: provider, auth mode, account, connection status, token expiry, granted scopes, and non-secret capabilities. This keeps OAuth/scope/permission recovery visible without exposing credentials or delegating the UX to OpenViking.
- Source-resource detail and processing payloads inherit backing `SourceConnection` health. If a connector is disconnected, expired, permission-lost, or upstream-unavailable, Source Detail and post-import processing cards show the same authorization or permission blocker as Sources overview while preserving any previously captured snapshot for lineage and recovery.
- Source-resource detail now exposes a non-destructive `Retry sync` / `Reindex source` action for connector-backed resources, web URLs, and uploaded Files/PDF Sources with local raw artifacts. The action calls `POST /source-resources/{resource_id}/sync` and refreshes overview, processing, snapshot, parsed asset, lineage, consumer, and evidence state so recovery is visible in place.
- Uploaded file reindex reads only the current resource's own raw artifact URI, re-runs parsing/context/projection, and records the sync run. Missing or invalid raw artifacts surface as `Source unavailable` with a retry/re-upload path rather than silently faking connector output.
- Source processing payloads now return user-facing recovery copy and product actions such as `Search evidence`, `Attach to notebook`, `Retry parse from raw artifact`, `Reauthorize source`, and `Review crawl policy`. Internal implementation phrases such as connector-supplied content or POST content are kept out of the Sources UI contract.
- Source-resource detail now exposes a confirmation-gated `Remove source` action. It calls the existing `DELETE /source-resources/{resource_id}` tombstone flow, refreshes Sources overview and legacy datasource caches, then returns to `/sources`. The backend keeps a deletion marker snapshot so lineage remains explicit while the source disappears from active inventory.
- Source detail now promotes `Reauthorize source` next actions into a concrete `Reconnect Feishu` CTA for Feishu-backed sources. It starts the existing Feishu OAuth flow, listens for the OAuth popup callback, polls the OAuth result as fallback, and refreshes source overview, source connection, and source-resource state after authorization succeeds.
- Connector-backed Source detail now exposes a confirmation-gated `Disconnect connector` authorization action. It calls the existing `DELETE /source-connections/{connection_id}` disconnect flow, clears saved credentials, leaves existing resources in inventory, and refreshes overview/resource state so affected rows move to `Authorization required` with `Reauthorize source` as the recovery action.

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
  - `needs_projection` for sources with a confirmed `projected_dataset_id`, parsed table assets, Feishu Sheets/Base, extracted tables, and tabular file projections such as CSV/Excel.
  - `context_only` for documents, web sources, PDF/Docx/PPTX uploads, and object-storage objects that only provide indexed evidence. They can support definitions, policies, examples, and evidence but cannot be the production fact source for metrics.
  - `permission_required` for upstream permission loss.
  - `reauthorization_required` for sources that need connector authorization before modeling handoff.
  - `source_unavailable` when the upstream system or resource cannot be reached.
  - `processing` while sync, parsing, or source analysis is still running.
  - `failed` for parser, context indexing, or source processing failures.
  - `planned` for roadmap/request-access entries that must not pretend to be production-ready.
  - `unsupported` only for source families without a production modeling handoff contract.
- The Create Model picker shows every connected source with its family, modeling mode, status, next action, and blocker reason instead of only showing `No supported datasource found`.
- Selecting any blocked SourceOverview-backed handoff now offers an `Open source detail` action that closes the generator dialog and sends the user to `/sources/:sourceId`, where schema/profile refresh, reauthorization, retry, reindex, projection, context, lineage, and consumers are visible.
- Profile loading and semantic generation are guarded so only `supported` sources with a relational/warehouse profile can continue into production generation.
- Projection, context, permission, reauthorization, processing, failed, planned, and unsupported sources stay visible but disabled for production generation until the corresponding Source next action is resolved.

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
- `KnowledgeProvider.search()` and `KnowledgeProvider.read()` now return provider-neutral evidence payloads instead of ORM `EvidenceFragment` rows. The native provider still materializes local/dev fallback evidence rows, but API callers consume the provider payload shape so an external provider can return equivalent evidence without leaking storage internals.
- `NativeKnowledgeProvider` remains the default local/dev fallback and writes `byaan-native://...` context/debug URIs plus metadata that explicitly marks control-plane text storage as local fallback behavior.
- `OpenVikingKnowledgeProvider` exists as a provider boundary selected by `KNOWLEDGE_PROVIDER=openviking`, but it fails fast until a real OpenViking client is configured. This keeps OpenViking behind `KnowledgeProvider` and prevents accidental use of OpenViking connectors as the Add Source layer.
- Commercial/self-hosted deployments now fail fast if they would select `byaan-native`: `APP_MODE=self-hosted`, `KNOWLEDGE_PROVIDER_REQUIRE_EXTERNAL=true`, or `KNOWLEDGE_PROVIDER_MODE=commercial|production|prod|enterprise` require an external provider unless `KNOWLEDGE_PROVIDER_ALLOW_NATIVE=true` is set for an explicit local diagnostic or migration drill.
- Connector-captured snapshots now follow the configured default `KnowledgeProvider` instead of hardcoding native evidence storage. Snapshot metadata keeps the source connector provider such as `web`, `feishu`, or `volcengine_tos`, and records the context backend separately as `knowledge_provider`.
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
