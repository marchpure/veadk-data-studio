# Commercial Architecture Opportunities

This document records architecture opportunities found during the commercial console review. It uses the repository's current modules and focuses only on datasource, semantic model, dashboard, and context storage.

## 1. Deepen `KnowledgeProvider` Into The Context Store Interface

Files:

- `server/services/knowledge_provider.py`
- `server/models/knowledge_resources.py`
- `server/services/source_resources.py`

Problem:

- `KnowledgeProvider` is the right module, but the current `NativeKnowledgeProvider` stores `EvidenceFragment.text` in the control database.
- The current interface returns database `EvidenceFragment` rows directly, which makes the provider seam shallow. An external provider still has to mimic local database behavior instead of returning provider-native retrieval results mapped to Byaan evidence locators.
- `KnowledgeResource` has provider and provider resource id, but lacks commercial provider metadata such as context URI, provider status, last indexed time, and provider error.

Solution:

- Keep `NativeKnowledgeProvider` as local/dev fallback.
- Add an `OpenVikingKnowledgeProvider` adapter behind the existing module.
- Change the external interface to return provider-neutral evidence payloads, not ORM rows as the only shape.
- Add provider metadata fields to `KnowledgeResource`.
- Store evidence locators and hashes in the control plane; keep long-lived text/chunks in OpenViking or another provider.

Benefits:

- Leverage: every source connector can index into Native, OpenViking, or another provider without changing connector code.
- Locality: context-store changes stay in one module instead of spreading into Feishu, PDF, web, source detail, and agent search callers.
- UX impact: Sources can show `Context ready`, `Indexing`, or `Failed` without exposing vector or OpenViking internals.

## 2. Turn `SourceConnectorAdapter` Into A Commercial Connector SDK

Files:

- `server/services/source_connectors.py`
- `server/services/source_connections.py`
- `server/services/connector_catalog.py`
- `server/models/source_connections.py`
- `server/models/source_resources.py`
- `server/models/source_snapshots.py`

Problem:

- `SourceConnectorAdapter` already has useful depth: test, list resources, sync resource.
- The commercial connector contract is broader than the current interface: authorize, browse, select, snapshot, parse hints, permission taxonomy, delete/revoke, and parsed asset summaries.
- `connector_catalog.py` has many planned entries, but only two production source adapters are available. Without stricter readiness gates, the UI can overpromise.

Solution:

- Keep `SourceConnectorAdapter` as the core seam and deepen it into a connector SDK.
- Add readiness gates before any connector is marked `available`.
- Add a connector manifest that distinguishes production adapter, beta adapter, and planned catalog tile.
- Standardize permission errors across adapters.
- Standardize captured snapshot metadata, parser hints, and raw artifact URIs.

Benefits:

- Leverage: one Add Source workflow can support Feishu, Google, Microsoft, object storage, and warehouses.
- Locality: connector-specific OAuth and picker details stay in adapters; `Sources` UI consumes one stable interface.
- UX impact: `Available`, `Beta`, and `Planned` become honest product states, not visual labels.

## 3. Add Source Detail As The Trust Hub

Files:

- `client/src/pages/Databases.tsx`
- new `client/src/pages/SourceDetailPage.tsx`
- `server/services/source_resources.py`
- `client/src/services/api.ts`

Problem:

- Current source management is still list/action oriented.
- Users cannot inspect snapshots, parsed tables, evidence, context readiness, lineage, or downstream consumers in one place.
- Without a Source detail page, semantic model and dashboard generation feel like jumps rather than governed transitions.

Solution:

- Add `/sources/:sourceId`.
- Start read-only with existing resource, snapshot, processing, and knowledge search APIs.
- Add summary endpoints for consumers, parsed assets, and lineage.
- Make Source detail the place where users decide whether a source is safe to use.

Benefits:

- Leverage: one page supports files, Feishu docs, web, object storage, and database-derived resources.
- Locality: trust, freshness, evidence, and consumer impact are no longer scattered across list cards, notebook assets, and semantic model pages.
- UX impact: users can move from `Source ready` to `Generate semantic model` or `Create dashboard` with visible proof.

## 4. Keep Semantic Models As The Publish Gate

Files:

- `client/src/features/data-modeling/pages/DataModelsHomePage.tsx`
- `client/src/features/data-modeling/pages/DataModelBuilderPage.tsx`
- `client/src/features/data-modeling/publish/PublishWorkspace.tsx`
- `client/src/features/data-modeling/types.ts`

Problem:

- The semantic model UX is already relatively strong: readiness, drift, publish state, consumers, MCP exposure.
- The missing connection is upstream source health and concrete downstream dashboard impact.
- The current builder labels `Explore / Model / Publish` are usable, but commercial users need validation and consumers to be first-class.

Solution:

- Add latest source snapshot and source status to model list/detail.
- Add dashboard consumer impact to publish review.
- Evolve builder tabs toward `Profile / Model / Validate / Publish / Consumers`.
- Keep direct source-to-dashboard only as exploration; production dashboards should prefer published semantic models.

Benefits:

- Leverage: semantic models become the contract used by Agent, MCP, and dashboards.
- Locality: metric changes are reviewed once before downstream dashboards consume them.
- UX impact: users see which dashboards may change before publishing metric or relationship edits.

## 5. Converge Dashboards Around Analysis Artifacts

Files:

- `server/models/dashboard.py`
- `server/models/analysis_artifacts.py`
- `server/services/analysis_artifacts.py`
- `server/services/dashboard_cache_service.py`
- `server/services/dashboard_refresh_service.py`
- `client/src/types/folder.ts`
- `client/src/components/home/SharedDashboardsSection.tsx`

Problem:

- Existing dashboards are mostly shared HTML render artifacts with notebook/version metadata.
- `AnalysisArtifact` already contains a better root for commercial dashboard apps: objective, definition, status, version, latest result snapshot, source snapshot refs, and semantic model version refs.
- Listing and viewing dashboards through folder/share concepts hides freshness, run state, source lineage, and semantic model dependencies.

Solution:

- Create a `/dashboards` workspace that lists both legacy HTML dashboards and `AnalysisArtifact`-backed dashboard apps.
- Treat old `Dashboard.html_content` as a render artifact, not the source of truth.
- Treat `AnalysisArtifact.definition_json` as the likely dashboard app definition root.
- Add a unified dashboard summary API.

Benefits:

- Leverage: one dashboard workspace can cover generated HTML, analysis artifacts, refresh snapshots, share state, and folders.
- Locality: refresh state, latest successful snapshot, and source/model references live in dashboard app metadata instead of being inferred from viewer pages.
- UX impact: users can distinguish draft, published, stale, failed refresh, permission blocked, and live latest versus snapshot sharing.

## 6. Replace `Databases` Product Copy With `Sources` Without Renaming Backends Yet

Files:

- `client/src/App.tsx`
- `client/src/components/CollapsibleSidebar.tsx`
- `client/src/pages/Databases.tsx`

Problem:

- `Databases` is now a misleading product word. The page includes uploaded files, PDFs, web pages, Feishu resources, object storage, datasets, and databases.
- Backend names can remain stable, but user-facing copy should reflect the product shape.

Solution:

- Add `/sources` route alias and keep `/databases`.
- Change visible label to `Sources`.
- Move Add Source to a family-first picker.
- Keep backend/API renames out of the first slice.

Benefits:

- Leverage: the same page can represent the full source layer without creating a parallel UX.
- Locality: route/copy change is low risk and does not disturb connection/dataset APIs.
- UX impact: users do not have to infer that Feishu docs and PDFs live under a database page.
