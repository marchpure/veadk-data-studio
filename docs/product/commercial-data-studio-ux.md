# Commercial Data Studio UX and Connector Strategy

## Decision Summary

Byaan should become a commercial data studio built around one continuous journey:

`Connect sources -> Understand sources -> Govern semantic models -> Generate dashboards -> Publish context/API/MCP`

The current console already has the raw pieces, but the experience is split across `Datasources`, `Data Models`, notebook chat, shared dashboards, and `Integrations`. For a commercial product, the console should present a single data workspace with visible state transitions and governance checkpoints.

Detailed connector ownership, OpenViking usage, and production connector count are defined in `docs/product/commercial-connector-strategy.md`.

Key decisions:

- Do not use PostgreSQL as the knowledge/chunk/vector store in the commercial architecture.
- Keep Byaan-owned connectors for enterprise sources, identity, permissions, snapshots, lineage, and normalized datasets.
- Use OpenViking as a context store/provider behind Byaan, not as the primary connector layer.
- Ship 6 production adapter groups for commercial beta, reach 8 connector families for v1 GA, then expand to 12-13 families through a connector SDK and marketplace.
- Rename and reorganize `Databases` into `Sources`, because the page now handles files, web, Feishu, object storage, and databases.

## Current Console Evidence

Current routes and pages:

- `client/src/App.tsx` exposes `/databases`, `/data-models`, `/data-models/:modelId`, `/integrations`, notebook routes, folders, and dashboard viewer routes.
- `client/src/pages/Databases.tsx` is already more than databases: it handles database connections, upload, URL upload, PDF, web pages, connector definitions, Feishu resources, and TOS-like resources.
- `client/src/features/data-modeling/pages/DataModelsHomePage.tsx` is a semantic model workspace with model readiness, drift, consumers, and generate-from-data.
- `client/src/features/data-modeling/pages/DataModelBuilderPage.tsx` has an Explore / Model / Publish flow for semantic assets.
- Dashboard is still mostly notebook/share/viewer-oriented through `ChatPreview`, shared dashboard lists, folder sharing, and generated HTML.

UX gap:

- Users must mentally stitch together source import, indexing, semantic modeling, notebook/chat generation, dashboard sharing, and integrations.
- `Integrations` explains Feishu data source authorization versus bot install, but the core resource journey still starts in `/databases`.
- Source health, snapshot lineage, indexing status, semantic readiness, and dashboard consumers are not shown as one product graph.

## Product Boundary

### Source Layer

Purpose:

- Connect external systems.
- Let users browse and select resources.
- Capture immutable snapshots.
- Parse raw content into blocks, tables, and evidence locators.
- Produce normalized datasets when the source contains structured or semi-structured tables.

User-visible objects:

- Source connection
- Resource
- Snapshot
- Parse/index status
- Permission/reauthorization state
- Evidence and lineage
- Normalized dataset

Engineering objects:

- `SourceConnection`
- `SourceResource`
- `SourceSnapshot`
- raw object URI
- parsed blocks/tables
- `EvidenceFragment` compatible locator
- OpenViking context URI

### Semantic Layer

Purpose:

- Convert discovered resources and schemas into governed business contracts.
- Create entities, dimensions, relationships, metrics, approved SQL, definitions, and tool schemas.
- Provide a publish gate before Agent, MCP, and Dashboard use.

User-visible objects:

- Data Model
- Draft
- Published version
- Readiness score
- Drift alert
- Consumer list

Engineering objects:

- `SemanticModel`
- semantic model version
- metric registry entry
- source snapshot references
- validation log
- MCP tool contract

### Dashboard Layer

Purpose:

- Present business-facing analysis results generated from governed sources and semantic models.
- Let users review, edit, refresh, share, and schedule dashboards.
- Act as a visual Data Skill output that agents can invoke when it is bound to a published semantic model version.

User-visible objects:

- Dashboard app
- Canvas
- Cards/widgets
- Filters
- Result snapshot
- Refresh policy
- Share target
- Version history

Engineering objects:

- dashboard app metadata
- dashboard run
- run plan
- result snapshot
- HTML artifact
- filter contract
- share contract

Boundary:

- Dashboard can create local Metric Drafts while a user is exploring.
- Team-level semantics must be promoted through Semantic Models before production dashboards, MCP tools, or agents depend on them.
- A Dashboard Skill is a specialized Data Skill: it has layout, filters, explanations, refresh policy, delivery/share policy, and a result snapshot. It is not the central semantic layer.

## Commercial Storage Architecture

PostgreSQL can remain acceptable for local development, but the commercial architecture should avoid it as the knowledge/chunk/vector backbone.

Recommended stores:

| Concern | Commercial store | Notes |
|---|---|---|
| Metadata/control plane | MySQL, TiDB, Spanner, DynamoDB, or CockroachDB | Tenant, connection, resource, snapshot, sync status, lineage, ACL references. |
| Secrets | KMS/Vault/Secrets Manager | OAuth tokens, refresh tokens, API keys, app secrets. |
| Raw files and parser artifacts | S3/TOS/GCS/Azure Blob | PDF, HTML, exported docs, CSV/Excel, parse intermediate files. |
| Structured data | Iceberg/Delta/ClickHouse/DuckDB cache | Tables extracted from Excel, Sheet, Base, HTML tables, PDFs, and database samples. |
| Context/knowledge | OpenViking, VikingDB-backed OpenViking, or pluggable vector/context store | L0/L1/L2 context, semantic retrieval, evidence recall, agent context. |
| Jobs | Temporal, Celery/RQ, cloud queue workers | Sync, parse, embed, summarize, validate, publish, refresh. |

The Source Layer should only store metadata in the control plane. It should not persist long-term chunks in the control database.

## OpenViking Boundary

Use OpenViking for context storage and retrieval:

- `SourceSnapshot -> OpenViking resource`
- parsed blocks/tables/evidence -> `viking://resources/{tenant}/{workspace}/{source}/{resource}/{snapshot}`
- L0/L1/L2 summaries for agent context
- retrieval trajectory for debugging
- returned snippets mapped back to Byaan evidence locators

Do not use OpenViking as the primary connector layer for core commercial sources.

Why:

- Byaan needs product-grade OAuth, tenant isolation, ACL checks, resource picker UX, incremental sync, retries, lineage, and normalized datasets.
- OpenViking connectors are useful importers, but they should not own business-critical source identity and permission state.
- Keeping connectors ours makes the product independent of one context backend. OpenViking can be replaced or offered as one deployment option.

Allowed OpenViking connector usage:

- Demo importers.
- Long-tail importers.
- Public web/Git/repo resources when enterprise governance is not required.
- Agent memory/resource import.

Not allowed for v1 core:

- Feishu/Lark
- Google Workspace
- Microsoft 365
- SQL databases
- Warehouses/lakehouses
- Enterprise object storage

## Connector Portfolio

### Commercial Beta: 6 Production Adapter Groups

Commercial beta should sell the end-to-end loop before broad connector coverage:

| Adapter group | Includes | Why beta |
|---|---|---|
| Local files | PDF, CSV, Excel, Docx, PPT | Fastest path to user value; must support upload, parse, table extraction, and source citations. |
| Web | URL, sitemap, page group | Required for competitive research and public business pages; needs crawl policy and snapshot refresh. |
| Feishu/Lark | Docx, Wiki, Sheets, Base, Drive picker | Core China enterprise workflow; OAuth and permission details are product-critical. |
| SQL databases | PostgreSQL, MySQL, SQLite, SQL Server, Oracle, ClickHouse as one family | Needed for structured analysis and semantic modeling. |
| Warehouse/lakehouse wrapper | Databricks first | Wrap the existing Databricks flow into the Source contract before broadening warehouses. |
| Object storage | S3-compatible contract with TOS first | Enterprise data lake and batch ingestion without one connector per storage vendor. |

### Commercial V1 GA: 8 Connector Families

These should be Byaan-owned connectors.

| Family | Includes | Why v1 |
|---|---|---|
| Local files | PDF, CSV, Excel, Docx, PPT | Fastest path to user value; must support upload, parse, table extraction, and source citations. |
| Web | URL, sitemap, page group | Required for competitive research and public business pages; needs crawl policy and snapshot refresh. |
| Feishu/Lark | Docx, Wiki, Sheets, Base, Drive picker | Core China enterprise workflow; OAuth and permission details are product-critical. |
| Google Workspace | Drive, Docs, Sheets | Core global enterprise workflow. |
| Microsoft 365 | SharePoint, OneDrive, Excel | Core enterprise workflow. |
| SQL databases | PostgreSQL, MySQL, SQLite, SQL Server, Oracle, ClickHouse as one family | Needed for structured analysis and semantic modeling. |
| Warehouse/lakehouse | Snowflake, BigQuery, Databricks, Redshift | Needed for commercial BI comparison. |
| Object storage | S3, TOS, GCS, Azure Blob | Enterprise data lake and batch ingestion. |

Google Workspace and Microsoft 365 are GA/global-enterprise commitments, not blockers for the China-first commercial beta. Pick the first global connector by customer segment: Google Workspace for startup/product-led teams, Microsoft 365 for large enterprise/procurement-led teams.

### Commercial v1.5 / v2: Add 5 Families

| Family | Rationale |
|---|---|
| Notion | Common lightweight knowledge source. |
| Confluence/Jira | Enterprise product/project knowledge. |
| Slack/Teams | Conversation-derived operational context. |
| GitHub/GitLab | Code and issue context for managed agents. |
| Generic API/OpenAPI/Webhook | Extensibility without writing one-off connectors. |

Target:

- commercial beta: 6 production adapter groups.
- v1 GA: 8 connector families, roughly 8-10 production adapter groups.
- v1.5: 10-11 families.
- v2: 12-13 families plus connector SDK.

Avoid promising dozens of first-party connectors before the source, semantic, and dashboard loop is excellent.

## Connector Contract

Every Byaan-owned connector should implement the same commercial contract:

1. Authorize
   - OAuth/API key/service account.
   - Explicit granted scopes.
   - Tenant and user identity mapping.

2. Browse
   - Resource picker.
   - Search.
   - Folder hierarchy.
   - Already-added state.
   - Permission errors as first-class states.

3. Select
   - Resource identity.
   - Selection config.
   - User-visible name.
   - Sync mode.

4. Snapshot
   - External revision.
   - Content hash.
   - Raw object URI.
   - Parser version.
   - Captured metadata.

5. Parse
   - Blocks.
   - Tables.
   - Images/attachments metadata.
   - Entity candidates.
   - Quality warnings.

6. Normalize
   - Dataset projection for structured parts.
   - Schema inference.
   - Field mapping.
   - Type normalization.

7. Index context
   - OpenViking context URI.
   - Evidence locator mapping.
   - Retrieval status.

8. Govern
   - Lineage.
   - ACL propagation.
   - Retention.
   - Deletion and reindex behavior.

This contract matters more than the number of connectors.

## UX Information Architecture

Replace the current top-level shape:

`Home / Notebooks / Datasources / Data Models / Integrations`

With a commercial data workspace:

```text
Workspace
  Overview
  Sources
  Semantic Models
  Dashboards
  Automation
  Integrations
  Settings
```

### Overview

Purpose:

- Show the whole workspace health.
- Expose the next best action.

Key panels:

- Source coverage: connected, syncing, failing, permission required.
- Semantic readiness: draft, review needed, published, drift.
- Dashboard status: stale snapshots, failed refresh, shared dashboards.
- Agent activity: recent generation, failed runs, pending approvals.

Primary action:

- `Add source`
- `Generate model`
- `Create dashboard`

### Sources

Replace `Databases`.

Tabs:

- All
- Files
- SaaS apps
- Databases
- Warehouses
- Object storage
- Failed/needs attention

Resource row should show:

- name
- source type
- owner
- last snapshot
- parse/index status
- tables found
- semantic models using it
- dashboards using it
- permission state

Add source flow:

```text
Choose connector
-> Authorize/configure
-> Browse/select resources
-> Preview parse and tables
-> Confirm sync policy
-> Create source
-> Watch processing
-> Next action: generate semantic model or dashboard
```

### Semantic Models

Current `Data Models` direction is good. Tighten it:

- Source-first creation.
- Model readiness is the main status.
- Drift and consumers are visible.
- Publish gate is explicit.
- Local draft versus published version is clear.

Flow:

```text
Select sources
-> Agent profiles data
-> Propose entities/relationships/metrics
-> User reviews conflicts
-> Validate with sample queries
-> Publish model
-> Expose to Agent/MCP/Dashboard
```

### Dashboards

Create a first-class `Dashboards` workspace instead of hiding it inside notebooks/folders.

Dashboard page layout:

```text
Left rail: dashboard list, folders, status filters
Top bar: title, freshness, version, share, refresh
Main: canvas
Right panel: Inspector / Prompt edit / Data lineage / Runs
Bottom or side drawer: run history and snapshot diff
```

Flow:

```text
Choose semantic model or source
-> Agent proposes analysis plan
-> Generate dashboard canvas
-> User edits cards and prompts
-> Validate metrics and filters
-> Save version
-> Configure refresh
-> Share snapshot or live latest
```

### Integrations

Keep it, but make it admin-oriented:

- App credentials
- OAuth callback status
- Connector availability
- Bot installation
- global policies

Do not make users begin normal datasource work from Integrations.

## Current Console Refactor Plan

### P0: Rename and regroup

- Rename route copy from `Databases` to `Sources`.
- Keep `/databases` as compatibility route; add `/sources`.
- Move connector tiles into grouped families.
- Make Feishu data authorization appear inside `Sources -> Feishu`, with `Integrations` as admin fallback.

### P1: Source detail page

Add `/sources/:sourceId`.

Sections:

- Overview
- Snapshots
- Parsed content
- Tables
- Evidence
- Lineage
- Consumers
- Sync settings

### P2: Processing journey

After adding a resource, do not return users to a flat list only.

Show:

```text
Capturing -> Parsing -> Table detection -> Context indexing -> Semantic suggestions -> Ready
```

Each step should expose logs and retry where useful.

### P3: Dashboard workspace

Add `/dashboards`.

Unify:

- generated dashboard artifacts
- shared dashboard viewer entries
- refresh status
- folders
- snapshot/live share mode

### P4: Commercial connector SDK

Expose a server-side SDK:

- connector manifest
- auth handler
- browse handler
- sync handler
- parser plugins
- schema mapper
- evidence locator contract

Long-tail sources should use this SDK, not ad hoc page logic.

## User Journeys

### Journey 1: Business user imports a Feishu report and gets a dashboard

1. Opens `Workspace -> Sources`.
2. Clicks `Add source`.
3. Selects `Feishu`.
4. Sees whether admin app is configured.
5. Completes OAuth.
6. Browses Wiki/Doc/Sheet resources.
7. Selects a report doc and sheet.
8. Preview shows detected tables and key text blocks.
9. Confirms sync policy.
10. Processing screen shows snapshot and index progress.
11. Clicks `Generate semantic model`.
12. Reviews proposed metrics.
13. Clicks `Create dashboard`.
14. Edits dashboard with prompt and Inspector.
15. Shares latest-success snapshot with team.

Failure and recovery path:

- If OAuth scope is missing, the Add Source flow shows required scope and sends the user to reauthorize or asks an admin to enable the app scope.
- If a selected Sheet contains ambiguous headers, processing stops at `Needs confirmation` and asks the user to pick header rows before creating a projected dataset.
- If context indexing fails after parsing succeeds, the source remains usable for structured tables while context search shows `Index failed` with retry.

### Journey 2: Data analyst connects warehouse and publishes metrics

1. Opens `Sources -> Add source -> Warehouse`.
2. Connects Snowflake/BigQuery/Databricks.
3. Selects catalogs/schemas/tables.
4. Agent profiles schemas and sample rows.
5. Analyst reviews relationships and metric definitions.
6. Publishes semantic model.
7. Model becomes available to Agent, MCP, and dashboards.

Failure and recovery path:

- If warehouse OAuth expires, source health changes to `Reauthorization required` and dashboards keep their last successful result snapshot.
- If schema drift changes a metric field, the semantic model moves to `Review required` and publish shows impacted dashboards before accepting the change.
- If sample queries fail, the model can stay draft; Agent/MCP consumers keep using the previous published version.

### Journey 3: Admin governs connector estate

1. Opens `Integrations`.
2. Checks connector availability by family.
3. Configures Feishu/Google/Microsoft app credentials.
4. Sets tenant policy: allowed connectors, retention, private/public scope.
5. Monitors failed authorizations and stale tokens.
6. Does not need to manage individual imported resources here.

Failure and recovery path:

- If a connector is planned but not supported, Admin sees it as `Planned` and can record demand without enabling it for users.
- If a tenant disables a connector family, existing sources enter a policy-blocked state and users see the reason plus owner/admin contact.
- If OpenViking or another context provider is unavailable, source sync can still capture snapshots while context readiness shows `Indexing unavailable`.

## Commercial UX Principles

- One object should have one home. Sources live in `Sources`, semantic contracts in `Semantic Models`, dashboards in `Dashboards`.
- Every async job needs a visible state and retry path.
- Permission problems are not generic errors; they are product states.
- Freshness and lineage should be visible before users trust a dashboard.
- Draft versus published must be explicit for semantic models and dashboards.
- OpenViking details should be mostly hidden. Users see context readiness and evidence, not backend storage internals.

## Implementation Notes

Immediate code-aligned changes:

- Introduce `/sources` route while preserving `/databases`.
- Rename UI labels in `CollapsibleSidebar` and `DatabasesPage`.
- Add source family grouping in the add source dialog.
- Add source processing stepper using current `SourceResource` and `SourceSnapshot` status.
- Add OpenViking provider behind `KnowledgeProvider`, leaving `NativeKnowledgeProvider` as fallback.
- Add `context_uri` or provider metadata to `KnowledgeResource` / resource metadata for source-snapshot to OpenViking mapping.
- Avoid expanding PG chunk storage; start moving raw content and chunk/index payloads out of the control database.

Non-goals for the next iteration:

- Do not build 20+ first-party connectors.
- Do not move Feishu browsing into OpenViking connectors.
- Do not make dashboard the source of truth for semantic definitions.
- Do not expose vector/chunk implementation details in primary UX.
