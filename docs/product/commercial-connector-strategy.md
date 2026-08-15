# Commercial Connector Strategy

This document answers the commercial-source question directly:

- Do we still use PostgreSQL for knowledge storage?
- Do we use OpenViking connectors?
- Which connectors does Byaan own?
- How many connectors should v1 commit to?

## Recommendation

Do not use PostgreSQL as the commercial knowledge/chunk/vector store.

Use PostgreSQL-like relational storage only as a control-plane database when needed: tenants, source records, sync runs, permissions, job state, and metadata. Raw content, parsed artifacts, context index payloads, and retrieval state should live outside the control-plane database.

Use OpenViking as a context provider behind Byaan's source snapshots, not as the primary connector layer.

Byaan should own the connector layer for commercial sources. OpenViking connectors can be allowed for demos, long-tail public imports, and migration tools, but they should not own source identity, OAuth, ACL, snapshot lineage, or the user-facing Add Source workflow.

The practical answer for v1:

- Build Byaan-owned connectors for first-party commercial flows.
- Use OpenViking as the knowledge/context substrate after Byaan has captured and normalized source snapshots.
- Keep OpenViking connectors out of the main Add Source path unless the connector is clearly labeled demo, marketplace, community, or migration-only.
- Commit to 8 source families and roughly 8-10 production adapter groups, not 30 individual first-party connectors.
- Show 20+ catalog tiles only when unsupported entries are explicitly marked `planned` and cannot be mistaken for production support.

## Commercial Answer

The sellable architecture is:

```text
Byaan Source Control Plane
-> Byaan Connector SDK and first-party adapters
-> snapshot, parse, normalize, evidence locator
-> KnowledgeProvider
-> OpenViking or another context backend
```

This means OpenViking is behind the datasource product, not in front of it. Users buy Byaan Sources, not an OpenViking connector catalog.

Commercial connector commitments should be split into three promises:

| Milestone | Promise | Connector count |
|---|---|---|
| Commercial beta | Sell the core loop for China-first customers: files, Feishu/Lark, web, SQL, object storage, and the existing Databricks path wrapped as a Source. | 6 production adapter groups. |
| V1 GA | Add global enterprise coverage and harden the family picker: Google Workspace and Microsoft 365 become first-party or one is first-party while the other is explicitly beta, depending on customer segment. | 8 source families, roughly 8-10 production adapter groups. |
| V1.5 / V2 | Expand through SDK and marketplace before first-party support. Promote only connectors that pass governance gates. | 12-13 families plus SDK; catalog can show 20+ entries only with clear availability labels. |

Build ourselves:

- Files: PDF, CSV, Excel, Docx, PPT.
- Web: URL, sitemap, page group, crawl policy.
- Feishu/Lark: Docs, Wiki, Sheets, Base, Drive-style picker.
- SQL databases: common dialects behind one source contract.
- Object storage: S3-compatible contract, with TOS as the first concrete adapter.
- Warehouse/lakehouse: Databricks wrapper first; add Snowflake/BigQuery/Redshift by customer demand.
- Google Workspace and Microsoft 365 when entering global enterprise sales.

Do not build as first-party v1:

- Notion, Confluence/Jira, Slack/Teams, GitHub/GitLab.
- Dingtalk, Tencent Docs, WeCom files unless a real launch customer requires them.
- Every SQL dialect as a separate product connector.
- Every object storage vendor as a separate product connector.

Do not use OpenViking connectors for:

- Enterprise OAuth or admin consent.
- Resource picker ownership.
- ACL/permission state.
- Snapshot lineage.
- Parsed dataset projection.
- Semantic model lineage.
- Dashboard consumer impact.

Use OpenViking connectors only for:

- Demo seed data.
- Public web/Git imports with no enterprise ACL promise.
- One-off migration from an existing OpenViking library.
- Marketplace/community adapters that are clearly not first-party production support.

## PostgreSQL Policy

The commercial rule is not "never run PostgreSQL." The rule is "do not make PostgreSQL the knowledge substrate."

Allowed:

- Local development metadata.
- Small self-hosted deployments when used as control-plane storage.
- Query/cache metadata with TTL.
- Agent session metadata.
- Connector records, source records, sync runs, and lineage IDs.

Not allowed as the commercial design:

- Long-lived chunk storage.
- Vector store.
- Evidence text store at production scale.
- Raw file store.
- Parser artifact store.
- Customer knowledge-base portability layer.

Migration path from the current native provider:

1. Keep `NativeKnowledgeProvider` for local/dev fallback.
2. Add provider metadata to `KnowledgeResource`.
3. Add `OpenVikingKnowledgeProvider` behind the existing `KnowledgeProvider` module.
4. Store raw content and parser artifacts in object storage.
5. Store only evidence locators, hashes, and provider references in the control plane.
6. Backfill existing native evidence into the external provider tenant by tenant.
7. Gate production deployments so new source ingestion defaults to the external provider.
8. Fail fast in commercial/self-hosted deployments when `byaan-native` would be selected. `APP_MODE=self-hosted`, `KNOWLEDGE_PROVIDER_REQUIRE_EXTERNAL=true`, or `KNOWLEDGE_PROVIDER_MODE=commercial|production|prod|enterprise` must require an external `KnowledgeProvider`; `KNOWLEDGE_PROVIDER_ALLOW_NATIVE=true` is only for explicit local diagnostics or migration drills.

## Why Byaan Owns Core Connectors

The current code already points in this direction:

- `server/services/source_connectors.py` defines `SourceConnectorAdapter`, with Feishu and TOS adapters behind it.
- `server/models/source_connections.py` stores connector authorization state, encrypted credentials, external account identity, token expiry, and capabilities.
- `server/models/source_resources.py` stores selected resources, resource type, visibility, sync mode, current status, and latest snapshot.
- `server/models/source_snapshots.py` stores immutable snapshot metadata, external revision, content hash, parser version, raw storage URI, and error state.
- `server/services/knowledge_provider.py` defines `KnowledgeProvider`, which is the right module for native versus OpenViking-backed context storage.

This means connector ownership and context-provider ownership are already two different modules. Keep them separate.

If OpenViking owns core connectors, Byaan loses locality on the product states users care about:

- OAuth and reauthorization.
- Admin application configuration.
- Required scopes and missing scopes.
- Resource picker hierarchy, search, already-added state, and selection tray.
- Permission loss versus deleted source versus transient API failure.
- Immutable snapshots and external revisions.
- Raw object retention and delete/reindex behavior.
- Parsed tables and projected datasets.
- Semantic model and dashboard consumer impact.

OpenViking should receive a normalized source snapshot and return context retrieval capability. It should not decide what a Feishu document, warehouse table, or object storage prefix means inside the commercial workspace.

## Connector Count

Use three different counts, because mixing them creates bad product promises.

| Count | Meaning | Current / target |
|---|---|---|
| Production adapters | Backend adapters that can be sold with support | Current: 2 source adapters (`feishu`, `volcengine_tos`) plus existing database execution connectors. Target v1: 8-10 production adapters. |
| Connector families | User-facing groups in Add Source | Target v1: 8 families. |
| Catalog entries | Available + beta + planned tiles shown in the connector catalog | Can be 20+, but only if planned entries are clearly marked and not presented as supported. |

Commercial v1 should commit to 8 connector families, not dozens of individual first-party connectors.

## Add Source Ordering

The Add Source entry point should order families by commercial value and readiness:

1. Files
2. Business docs
3. Databases
4. Warehouses
5. Object storage
6. Web
7. API/Webhook
8. More connectors

Within each family, sort by:

1. Available production adapter.
2. Beta adapter with explicit limitations.
3. Planned catalog tile.

Do not sort alphabetically if it hides the supported path. For example, Feishu/Lark should appear before planned Confluence/Jira in China-focused deployments; Google Workspace or Microsoft 365 can move above Feishu in global deployments when their adapters become production-ready.

## Deployment-Specific Priorities

China-focused commercial deployments:

- Feishu/Lark first in Business docs.
- TOS and S3-compatible object storage first in Object storage.
- Databricks only if target customers already use it; otherwise prioritize common SQL and domestic warehouses by demand.
- Dingtalk/Tencent Docs/WeCom can be planned or beta, but should not displace Feishu until their adapters pass readiness gates.

Global commercial deployments:

- Google Workspace and Microsoft 365 should move ahead of Feishu once production-ready.
- Snowflake, BigQuery, Databricks, and Redshift should be the warehouse ordering.
- S3, GCS, Azure Blob, and S3-compatible storage should be the object storage ordering.

The connector SDK should support deployment-specific ordering without changing the underlying source object model.

## V1 Connector Families

These are the v1 source families Byaan should own:

| Family | Production commitment | Notes |
|---|---|---|
| Files | Build ourselves | PDF, CSV, Excel, Docx, PPT uploads. Most important for first-run value and evidence UX. |
| Web | Build ourselves | URL, sitemap, page group. Needs crawl policy, snapshot refresh, robots/allowlist policy. |
| Feishu/Lark | Build ourselves | Core China enterprise workflow. OAuth, Wiki/Doc/Sheet/Base picker, permission state, and admin config are product-critical. |
| Google Workspace | Build ourselves after Feishu pattern stabilizes | Drive, Docs, Sheets. Same picker/OAuth/snapshot contract as Feishu. |
| Microsoft 365 | Build ourselves after Google | SharePoint, OneDrive, Excel. Enterprise customers expect this. |
| SQL databases | Own through the existing database connector module, then wrap into Source contract | PostgreSQL, MySQL, SQLite, SQL Server, Oracle, ClickHouse. These produce schemas, samples, and semantic-ready datasets. |
| Warehouse/lakehouse | Build high-value adapters, not every warehouse at once | Databricks exists today as a warehouse connection flow; wrap it into the Source contract before adding Snowflake/BigQuery/Redshift. |
| Object storage | Build common S3-compatible adapter, then vendor aliases | Current TOS adapter should evolve into an object storage contract for S3/TOS/GCS/Azure Blob-compatible flows. |

V1 individual adapter target:

- Files adapter group: 1 ingestion module covering PDF/CSV/Excel/Docx/PPT.
- Web adapter: 1.
- Feishu/Lark adapter: 1.
- Google Workspace adapter: 1.
- Microsoft 365 adapter: 1.
- SQL adapter group: 1 interface with several dialect adapters already partly present.
- Warehouse adapter group: 1-2, starting by wrapping the existing Databricks flow into the Source contract.
- Object storage adapter group: 1 S3-compatible contract plus TOS as the first concrete adapter.

That means v1 should aim for roughly 8-10 production adapters or adapter groups, exposed as 8 source families.

## Build Versus Use OpenViking Connectors

Commercial connector ownership should be decided by how much product state Byaan must govern.

| Source | V1 ownership | Why |
|---|---|---|
| PDF/CSV/Excel/Docx/PPT uploads | Byaan-owned | Upload UX, parsing warnings, table extraction, retention, evidence locators, and delete behavior are core product surfaces. |
| Web URL/sitemap/page group | Byaan-owned | Crawl policy, allowlist, snapshot refresh, page-level evidence, and legal/compliance behavior need first-party control. |
| Feishu/Lark Docs/Wiki/Sheets/Base | Byaan-owned | China enterprise critical path; OAuth, scopes, picker, permission loss, and Feishu object taxonomy are product-critical. |
| Google Drive/Docs/Sheets | Byaan-owned when prioritized | Same enterprise governance shape as Feishu; do not delegate OAuth and ACL semantics to a generic context importer. |
| Microsoft SharePoint/OneDrive/Excel | Byaan-owned when prioritized | Enterprise buyers expect admin consent, tenant policy, and permission state to be first-class. |
| SQL databases | Byaan-owned through database connector layer | Produces schemas, samples, profiles, and semantic-ready datasets, not just text context. |
| Warehouses/lakehouses | Byaan-owned for top vendors | Produces governed datasets and semantic model contracts. Databricks should be wrapped into the Source contract before adding more warehouses. |
| Object storage | Byaan-owned common contract | Prefix/object selection, storage IAM, file typing, raw artifact URI, and sync policy are part of source governance. |
| Public Git/public websites/demo corpora | OpenViking connector allowed | Useful for demo and long tail when there are no enterprise OAuth/ACL promises. |
| Customer's existing OpenViking library | OpenViking migration/import bridge | Treat as migration into Byaan Source/Snapshot/KnowledgeResource records, not as the source-of-truth product model. |
| Partner or customer-specific SaaS | SDK/marketplace first | Byaan owns the SDK contract and readiness gates; individual adapters can be partner-owned until demand justifies first-party support. |

Rule of thumb:

- If the source affects permissions, lineage, semantic models, dashboards, or auditability, Byaan owns the connector.
- If the source is just context content with weak governance needs, OpenViking or a marketplace adapter can ingest it.
- If the source is customer-specific, ship it through a connector SDK with clear support ownership.

## Production Adapter Target

V1 should support these production adapter groups:

| Priority | Adapter group | Must be first-party? | Commercial promise |
|---|---|---|---|
| P0 | File upload/import | Yes | Users can upload PDF/CSV/Excel/Docx/PPT and get durable source snapshots, parse warnings, evidence locators, and optional dataset projections. |
| P0 | Feishu/Lark | Yes | Users can authorize, browse, select, sync, reauth, and inspect permission/snapshot state for Docs/Wiki/Sheets/Base. |
| P0 | SQL database contract | Yes | Users can connect common SQL databases, inspect schema/sample/profile, and generate semantic-ready datasets. |
| P0 | Web import/crawl | Yes | Users can import URL/page group/sitemap with crawl policy, snapshot refresh, and page evidence. |
| P0 | Object storage contract | Yes | Users can browse bucket/prefix/object, import files, and sync through a vendor-neutral object storage contract. |
| P1 | Databricks Source wrapper | Yes | The existing Databricks flow becomes a Source with schema/profile handoff, Source detail links, and semantic model next actions instead of staying a separate warehouse wizard. |
| P1 | Google Workspace | Yes for global beta | Drive/Docs/Sheets follow the same source contract as Feishu; ship after the picker and ACL model are proven. |
| P1 | Microsoft 365 | Yes for global beta | SharePoint/OneDrive/Excel support admin consent and permission state; prioritize based on target customers. |
| P2 | Snowflake/BigQuery/Redshift | Yes for selected top vendors | Add only after Databricks Source wrapper and SQL contract are stable. |

Do not put these into the v1 production commitment:

- Dingtalk, Tencent Docs, WeCom files, Notion, Confluence/Jira, Slack/Teams, GitHub/GitLab.
- Every domestic SQL dialect as a separate supported connector.
- Every object storage vendor as a separate first-party adapter.
- OpenViking connector imports as a substitute for Byaan source governance.

These can appear as planned catalog tiles, beta adapters, SDK examples, or marketplace adapters when the UI makes support status explicit.

Current implementation note:

- The unified Source upload endpoint is `/source-resources/files`; the legacy `/source-resources/pdf` endpoint remains compatible.
- Supported commercial beta file uploads are PDF, CSV, Excel `.xlsx/.xlsm`, Docx, and PPTX. Legacy binary `.xls` and `.ppt` require a conversion/parser worker before they can be promoted from roadmap wording to available support.
- PDF, Docx, and PPTX become immutable Source snapshots plus context evidence through the configured `KnowledgeProvider`.
- CSV and Excel `.xlsx/.xlsm` also create a projected dataset from the same Source snapshot, so Data Modeling can distinguish projection-ready sources from context-only sources.
- Uploaded raw bytes are preserved through snapshot/raw artifact plumbing; the control plane records URIs, hashes, parser versions, metadata, projection manifests, and provider status rather than treating PostgreSQL as the commercial raw/chunk/vector store.
- TOS/object-storage large objects now surface as `needs_confirmation` with a sync-run terminal state and actions to review object size and confirm large-object sync, instead of being collapsed into an unrecoverable parser failure.

Data Modeling must consume this same Source contract instead of silently filtering to SQL-only datasources. The handoff status should distinguish `supported`, `needs_projection`, `context_only`, `permission_required`, `reauthorization_required`, `source_unavailable`, `processing`, `failed`, `planned`, and `unsupported`. Only relational and warehouse sources with profile evidence can enter production semantic generation directly. Sources with `projected_dataset_id`, parsed table assets, CSV/Excel projections, Feishu Sheets/Base, and extracted tables require projection review; docs, Wiki, PDF, Docx/PPTX, web pages, and object-storage objects that only have indexed evidence are context-assisted evidence unless a confirmed projection exists.

## V1.5 / V2 Connector Expansion

Add these after the source -> semantic model -> dashboard loop is strong:

| Family | Timing | Ownership |
|---|---|---|
| Notion | v1.5 | Byaan-owned if customer demand is real; otherwise SDK/community. |
| Confluence/Jira | v1.5 | Byaan-owned for enterprise support. |
| Slack/Teams | v2 | Byaan-owned only if permissions and retention can be governed well. |
| GitHub/GitLab | v2 | Byaan-owned for code/issue context, or SDK adapter first. |
| Generic API/OpenAPI/Webhook | v2 | Byaan-owned framework, customer/partner-owned individual endpoints. |

The long-term target is 12-13 families plus a connector SDK. Avoid building 30 first-party connectors before the core workflow is excellent.

## OpenViking Usage Policy

Local OpenViking docs show a useful `add_resource` resource-management layer:

- It supports files, URLs, Git resources, PDFs, Docx, Excel, PPT, HTML, Markdown, and Feishu/Lark URL-based resources.
- Its pipeline is `Source Input -> Parse -> Resource Tree Build -> Persistence -> Semantic Processing`.
- It provides semantic processing, vector indexing, and watch-based incremental updates.
- Its user-facing resource namespace is `viking://resources/...`.

This is strong evidence for using OpenViking as the context/resource backend. It is not enough reason to delegate Byaan's commercial connector layer, because Byaan still needs source identity, enterprise authorization, resource pickers, snapshots, parsed datasets, semantic model lineage, dashboard consumers, and audit behavior.

Use OpenViking for:

- Context storage and retrieval.
- L0/L1/L2 summaries.
- Evidence recall.
- Retrieval trajectories for debugging.
- Optional customer-managed context backend.
- Long-tail or demo imports where governance is not product-critical.

Do not use OpenViking connectors for v1 core flows:

- Feishu/Lark.
- Google Workspace.
- Microsoft 365.
- SQL databases.
- Warehouses/lakehouses.
- Object storage.
- Enterprise file uploads.

Allowed exceptions:

- Demo workspace seed data.
- Public website or public Git resources with no enterprise ACL promises.
- One-off migration from a customer's existing OpenViking knowledge base into Byaan's Source/Snapshot model.
- Marketplace/SDK adapters clearly marked as community or unsupported.

## Storage Model

Commercial source ingestion should write to these stores:

| Concern | Store |
|---|---|
| Source metadata, sync runs, permissions, lineage IDs | Control-plane relational store |
| OAuth tokens, API keys, credentials | KMS/Vault-backed encrypted secrets |
| Raw files and exported SaaS payloads | Object storage |
| Parser artifacts, images, table extracts | Object storage |
| Structured projections | Iceberg/Delta/ClickHouse/DuckDB cache, depending on deployment |
| Context index and retrieval metadata | OpenViking/VikingDB-backed provider or another `KnowledgeProvider` adapter |
| Jobs and retries | Queue/Temporal/Celery/RQ-style worker system |

The current native provider stores `EvidenceFragment.text` in the database. Treat that as a local/dev fallback, not the commercial path.

Commercial deployments must select the context backend through `KNOWLEDGE_PROVIDER`. Connector-captured snapshots should record both identities separately: `metadata_json.provider` remains the source connector (`web`, `feishu`, `volcengine_tos`, etc.), while `metadata_json.knowledge_provider` records the context backend that indexed the snapshot.

The first `SourceOverview` backend slice keeps this boundary: it exposes product-facing `context_index_status`, parse status, snapshot ids, evidence counts, projected dataset ids, and partial consumer counts, while keeping OpenViking/provider internals out of the Add Source and inventory surface.

Commercial `KnowledgeResource` should gain provider metadata:

- `context_uri`
- `provider_status`
- `last_indexed_at`
- `provider_error`
- `retrieval_debug_uri`
- optional `provider_metadata_json`

Evidence returned to users should be mapped back to Byaan locators:

- source resource id
- source snapshot id
- external revision
- source URL
- page/range/block/table locator
- content hash

## Interface Shape

Keep two modules deep and separate.

### Source Connector Adapter

Owns:

- authorize/configure
- browse/search
- select resources
- sync resources
- snapshot metadata
- permission and retry classification
- raw capture URI
- parser hints

It should not own semantic modeling or dashboard generation.

### Knowledge Provider

Owns:

- ingest parsed snapshot content and artifacts
- index context
- search
- read evidence
- delete/reindex
- map provider results to evidence locators

It should not browse Feishu, Google Drive, object storage, or warehouses for core commercial workflows.

This separation gives leverage: a single connector can work with Native, OpenViking, or another provider; a single provider can index content from many connectors.

## Add Source UX Implications

The Add Source flow should show families, not backend engine names:

```text
Choose family
-> choose connector
-> authorize/configure
-> browse/select resources
-> preview parse and outputs
-> confirm sync policy
-> processing
-> next action
```

OpenViking should not appear as a normal family tile. Users should see:

- Context: pending / indexing / ready / failed.
- Evidence: available / partial / failed.
- Provider: only in admin/debug metadata.

## Commercial Readiness Gates

A connector is commercial-ready only when it supports:

1. Tenant-isolated authorization and encrypted credentials.
2. Resource picker or explicit import contract.
3. Already-added state.
4. Immutable snapshot with external revision and content hash.
5. Raw artifact URI outside control DB.
6. Parser version and parser warnings.
7. Context indexing status through `KnowledgeProvider`.
8. Permission, reauthorization, unavailable, retryable failure states.
9. Source detail page payload: snapshots, parsed assets, evidence, lineage, consumers.
10. Delete/revoke/reindex behavior.

Anything missing one of these gates can be beta or planned, but not a supported v1 production connector.

## Sellable Scope By Milestone

### Now: Technical Preview

Can be shown:

- Feishu/Lark source import.
- TOS/object import.
- Uploaded files, URLs, PDF/web source resources if parser limitations are clear.
- Existing SQL/database analysis flows.
- Semantic model readiness/publish prototype.
- Generated dashboards as artifacts.

Do not sell yet as production:

- Google Workspace, Microsoft 365, Notion, Confluence/Jira.
- OpenViking connectors as a replacement for Byaan Sources.
- Full governance for dashboard refresh and semantic impact.
- PG-backed evidence text as a scalable knowledge store.

### V1 Commercial Beta

Must be production-supported:

- Source page renamed and reorganized.
- Add Source family picker.
- Feishu/Lark, files, web, SQL, the existing Databricks warehouse flow wrapped into the Source contract, and object storage.
- OpenViking or equivalent provider behind `KnowledgeProvider`.
- Source detail with snapshots, context readiness, tables/evidence, and consumers.
- Semantic publish gate with dashboard impact.
- Dashboard workspace listing freshness and latest successful snapshot.

### V1 General Availability

Must add:

- Google Workspace or Microsoft 365, based on target customer segment.
- Connector availability governance in Admin.
- Delete/revoke/reindex behavior.
- Scheduled sync and retry policies.
- Audit trail for source access and dashboard publish.
- Customer migration from native evidence storage to provider-backed context.
