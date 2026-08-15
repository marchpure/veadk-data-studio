# Console UX Blueprint for Commercial Data Studio

## Purpose

This document turns the commercial product strategy into a page-level console design that can be implemented from the current Byaan frontend.

It is based on the current console implementation:

- `client/src/components/CollapsibleSidebar.tsx`
- `client/src/pages/Databases.tsx`
- `client/src/components/SourceConnectorImportPanel.tsx`
- `client/src/features/data-modeling/pages/DataModelsHomePage.tsx`
- `client/src/features/data-modeling/pages/DataModelBuilderPage.tsx`
- dashboard flows in `ChatPreview`, shared dashboards, folders, and viewer APIs

The design goal is a commercial-grade workspace for the loop:

`Sources -> Semantic Models -> Dashboards -> Automation / MCP`

## Current UX Diagnosis

### What works

- Source ingestion exists for SQL, uploaded files, URL uploads, PDF, web, Feishu resources, TOS-like object storage, and Databricks.
- Feishu OAuth and resource browsing have real states: not configured, connected, reauthorization required, scope missing, quick locate, selected resources, import results.
- Semantic Models already have a stronger product shape: readiness, draft/published status, drift, consumers, Explore / Model / Publish.
- Dashboard generation and sharing exist, but they are notebook and folder oriented.

### What is weak

- `Databases` is no longer the correct page name; it hides files, web, Feishu, object storage, and knowledge resources.
- Add Datasource uses a long connector list, not a guided commercial journey.
- The user cannot see the full processing path after import: capture, parse, table detection, context indexing, semantic suggestions, ready.
- Source detail is missing. Cards open edit/delete actions, but not a source lineage and processing workspace.
- Dashboard is not a first-class top-level workspace.
- Integrations mixes admin configuration and user-facing resource work too closely.
- There is no single overview showing health across Sources, Semantic Models, and Dashboards.

## Target Navigation

Current sidebar should evolve from:

```text
Home
Datasources
Data Models
Context
Recents
```

To:

```text
Overview
Sources
Semantic Models
Dashboards
Automation
Integrations
Settings
```

Phase-compatible route mapping:

| New item | Route | Current backing implementation |
|---|---|---|
| Overview | `/` | HomePage, refocused with workspace health |
| Sources | `/sources` | New route alias for `DatabasesPage` during transition |
| Semantic Models | `/data-models` | Existing Data Models pages |
| Dashboards | `/dashboards` | New page backed by existing viewer/share dashboard APIs |
| Automation | `/automation` | Later: schedules, alerts, subscriptions, MCP publishing |
| Integrations | `/integrations` | Existing admin integration page |
| Settings | `/settings` | Existing profile/admin settings can be linked later |

Compatibility:

- Keep `/databases` working.
- Update visible labels to `Sources`.
- Keep old terms in API names until backend migration is needed.

## Overview Page

The commercial home page should answer one question: "What needs attention before the workspace can produce trusted dashboards?"

### Layout

```text
Top: workspace title, global Add Source, Create Dashboard

Row 1: Health cards
  - Sources connected / failing / syncing
  - Semantic models draft / review / published
  - Dashboards fresh / stale / failed refresh
  - Automation enabled / failed

Row 2: Journey board
  Sources needing attention
  Semantic drafts waiting for review
  Dashboards with stale snapshots

Row 3: Recent agent activity
  import runs, model generation, dashboard runs, failed OAuth
```

### Empty state

If no source exists:

```text
Connect your first source
Choose files, business docs, SaaS apps, databases, or warehouses.
Primary: Add source
Secondary: View supported connectors
```

### Do not show

- Marketing-style hero.
- Long explanatory cards.
- Notebook-first prompts before a source exists.

## Sources Page

This replaces the mental model of `Databases`.

The top-level view should be a unified inventory. Connections, datasets, source resources, databases, warehouses, and object storage entries appear in one table, with `Type`, `Status`, `Context`, `Semantic`, and `Dashboards` columns explaining how each item behaves. Object-specific complexity belongs in Source detail, not separate top-level pages.

### Page header

```text
Sources
Business data, documents, files, and warehouses available to agents, semantic models, and dashboards.

Primary: Add source
Secondary: Connector health
```

### Summary row

```text
Connected sources
Needs attention
Processing
Used by semantic models
Used by dashboards
```

### Tabs

```text
All
Files
Documents
SaaS apps
Databases
Warehouses
Object storage
Needs attention
```

### Table columns

Use a table as the default for commercial density. Cards can remain for mobile.

| Column | Meaning |
|---|---|
| Source | Name, provider, resource type |
| Status | Ready, syncing, failed, permission required, stale |
| Freshness | Latest snapshot time and external revision |
| Parsed assets | Blocks, tables, files, records |
| Context | Indexed, indexing, failed, provider metadata available |
| Semantic | Linked models count and readiness |
| Dashboards | Consuming dashboard count |
| Owner | User/team |
| Actions | Open, sync, generate model, create dashboard, more |

### Source status copy

| State | User-facing copy | Primary action |
|---|---|---|
| `pending` | Waiting to start | Start sync |
| `syncing` | Capturing latest content | View run |
| `ready` | Ready | Open |
| `understanding` | Analyzing structure and meaning | View progress |
| `authorization_required` | Authorization required | Connect |
| `reauthorization_required` | Reauthorization required | Reconnect |
| `permission_lost` | Permission lost | Request access / reconnect |
| `source_unavailable` | Source unavailable | Retry |
| `failed` | Processing failed | View error / retry |
| `needs_confirmation` | Needs confirmation | Review |

## Add Source Flow

The current dialog should move from a flat left menu to a guided connector flow.

### Step 1: Choose source family

Grid, not a long list.

```text
Files
  PDF, Excel, CSV, Docx, PPT

Business docs
  Feishu/Lark, Google Drive, Microsoft 365, Notion, Confluence

Databases
  PostgreSQL, MySQL, Oracle, SQL Server, SQLite, ClickHouse

Warehouses
  Databricks, Snowflake, BigQuery, Redshift

Object storage
  S3, TOS, GCS, Azure Blob

Web
  URL, sitemap, page group

API
  OpenAPI, Webhook, custom API
```

Each tile shows:

- availability: available, beta, planned
- auth mode: upload, OAuth, service account, access key
- output: context, dataset, semantic-ready

### Step 2: Configure or authorize

Different by family:

- Upload: select files and name.
- Web: enter URL/sitemap and crawl policy.
- SaaS: OAuth or admin-configured app.
- Database: credentials or OAuth.
- Warehouse: OAuth/service account and catalog/schema selector.
- Object storage: access key/role and bucket/prefix selector.

Admin-only configuration should be linked, not embedded, for normal users.

### Step 3: Browse/select resources

For Feishu, Google, Microsoft, object storage, and warehouses:

```text
Left: folder tree / search / filters
Middle: resource list
Right: selection tray
Bottom: selected count, import button
```

Resource rows show:

- type icon
- name
- owner/modified time
- already added state
- permission state
- whether tables are likely

### Step 4: Preview and policy

Before final import, show:

```text
Selected resources
Expected parser
Estimated tables/blocks
Sync mode: manual / scheduled
Visibility: private / workspace
Retention policy
```

For files:

- show detected file type
- table sheet list for Excel/CSV
- PDF text/table extract warning if scanned

For SaaS docs:

- show selected tokens
- show permission scope and user identity
- show unsupported resource warnings

### Step 5: Processing

After import, do not close directly back to a flat list. Show processing:

```text
Capture
Parse
Detect tables
Normalize dataset
Index context
Generate semantic suggestions
Ready
```

Each step has:

- status
- timestamp
- retry if failed
- evidence/log drawer

### Step 6: Next action

When ready:

```text
Primary: Generate semantic model
Secondary: Create dashboard
Tertiary: Open source detail
```

## Source Detail Page

Route:

```text
/sources/:sourceId
```

### Header

```text
Source name
Provider / resource type
Status / latest snapshot / owner / visibility

Actions: Sync now, Generate model, Create dashboard, Share, Settings
```

### Tabs

```text
Overview
Snapshots
Parsed content
Tables
Evidence
Lineage
Consumers
Settings
```

### Overview

Show:

- latest status
- processing stepper
- source metadata
- context index status
- parsed asset summary
- semantic suggestions
- dashboard consumers

### Snapshots

Table:

- captured time
- external revision
- content hash
- parser version
- raw object URI
- status
- actions: compare, restore, reindex

### Parsed content

For docs/PDF/web:

- block outline
- page/heading sections
- extraction confidence
- images/attachments metadata

### Tables

For Excel/Sheet/Base/PDF/HTML:

- detected tables
- schema inference
- sample rows
- quality warnings
- project to dataset

### Evidence

Searchable evidence list:

- text snippet
- locator
- snapshot
- confidence
- linked metric/model/dashboard

### Lineage

Graph:

```text
Connection -> Resource -> Snapshot -> Parsed asset -> Context URI
                                    -> Normalized Dataset
                                    -> Semantic Model
                                    -> Dashboard
```

### Consumers

List:

- semantic models
- dashboards
- notebooks
- MCP tools
- automations

## Semantic Models UX

Current direction is mostly right. Changes should focus on making Sources and Dashboards visible.

### Home table additions

Add columns:

- Source health
- Latest source snapshot
- Dashboard consumers
- MCP status
- Owner/team approval

### Builder changes

Current tabs:

```text
Explore / Model / Publish
```

Recommended tabs:

```text
Profile
Model
Validate
Publish
Consumers
```

Rationale:

- `Explore` sounds open-ended.
- Commercial users need to know where validation and consumer impact are.

### Model creation from source

The panel should support:

```text
Choose one or more sources
-> select relevant tables/blocks
-> agent profiles structure
-> proposes entities, relationships, metrics
-> user reviews
-> publish
```

### Semantic object statuses

| State | Meaning |
|---|---|
| Draft | Local model can be edited, not used by production dashboards |
| Review required | Validation or owner approval missing |
| Published | Available to Agent/MCP/Dashboard |
| Drift detected | Source changed after publish |
| Deprecated | Kept for old dashboards, not recommended for new work |

## Dashboards UX

Dashboards need a top-level workspace.

### Dashboard list

Route:

```text
/dashboards
```

List columns:

- dashboard name
- semantic model/source
- freshness
- latest successful snapshot
- refresh policy
- owner
- share status
- failed runs
- actions

### Dashboard app page

Route:

```text
/dashboards/:dashboardId
```

Layout:

```text
Top bar:
  title, status, version, freshness, refresh, share, more

Left rail:
  pages, filters, assets

Center:
  editable canvas

Right panel:
  Inspector / Prompt edit / Data / Lineage / Runs

Bottom drawer:
  snapshot diff, errors, run log
```

### Dashboard creation

Flow:

```text
Choose semantic model or source
-> Agent drafts analysis plan
-> User approves questions and metrics
-> Generate dashboard
-> Review metric lineage and filters
-> Save version
-> Configure refresh/share
```

Commercial rule:

- Dashboards shared as production artifacts should use published semantic model versions when metrics are involved.
- Direct source-to-dashboard is allowed for exploratory drafts and should be labeled as such.
- A draft dashboard can later be rebound to a published semantic model before sharing.

### Dashboard status states

| State | Meaning | UX |
|---|---|---|
| Draft | Not shared yet | Save / Publish |
| Published | Shared internally | Open / Share |
| Refreshing | Run in progress | Show previous snapshot |
| Stale | Snapshot older than policy | Refresh |
| Failed refresh | Last run failed | Keep previous successful snapshot |
| Permission blocked | Source/model permission issue | Reconnect or request access |

## Integrations UX

Integrations should be an admin surface, not the primary user journey.

Sections:

- Connector catalog health
- App credentials
- OAuth callback status
- Bot installs
- Tenant policies
- Audit logs

Normal users should start from `Sources -> Add source`, not from Integrations.

For Feishu:

- Integrations configures app credentials and bot install.
- Sources handles user OAuth, browse, select, import, and reauth.

## State and Error Design

### Permission errors

Do not show generic `Load failed`.

Show:

```text
Current authorization cannot read Drive.
Required scope: space:document:retrieve
Action: Reauthorize Feishu
Admin action: Enable scope in Feishu Open Platform
```

### Processing errors

Show:

```text
PDF text extraction failed because this appears to be a scanned file.
Action: Run OCR
```

```text
Context indexing failed.
Source snapshot is safe. Retry indexing or switch provider.
```

### Backend/store errors

Users should never see implementation words such as:

- `PG`
- `json = json`
- `vector`
- raw stack traces

Use product states:

- Source metadata failed to save.
- Context indexing failed.
- Resource already exists.
- Permission changed.

## Three-Layer Journey States

The console should make every object move through visible states.

### Source layer states

```text
New
-> Authorized/configured
-> Resource selected
-> Captured
-> Parsed
-> Context indexed
-> Semantic suggested
-> Ready
```

Blocking states:

- Authorization required.
- Reauthorization required.
- Permission lost.
- Source unavailable.
- Parser confirmation required.
- Context index failed.

### Semantic layer states

```text
Draft
-> Profiled
-> Modeled
-> Validated
-> Review required
-> Published
```

Blocking states:

- Source drift.
- Missing relationship.
- Metric validation failed.
- Owner approval required.
- Downstream impact not reviewed.

### Dashboard layer states

```text
Draft
-> Generated
-> Validated against model
-> Published
-> Refreshing
-> Fresh latest-success
```

Blocking states:

- Stale snapshot.
- Failed refresh.
- Permission blocked.
- Source/model drift.
- Share policy blocked.

The user should always be able to answer:

- What object is blocked?
- Which upstream object caused it?
- Which downstream objects are affected?
- What action moves it forward?

## Visual Direction

The current dark operational UI can remain. Improve density and hierarchy:

- Use tables for source/model/dashboard lists.
- Use cards only for repeated connector tiles and compact summaries.
- Use status pills consistently.
- Avoid marketing hero sections.
- Use one primary orange action per page.
- Keep page headers compact.
- Make right-side inspectors standard across Source detail, Semantic Model builder, and Dashboard app.

## Implementation Slices

### Slice 1: Rename and route

Files:

- `client/src/App.tsx`
- `client/src/components/CollapsibleSidebar.tsx`
- `client/src/pages/Databases.tsx`

Changes:

- Add `/sources` route to `DatabasesPage`.
- Keep `/databases`.
- Change visible copy to `Sources`.
- Change sidebar label and title from `Datasources` to `Sources`.
- Update empty state copy to include files, docs, SaaS apps, databases, warehouses.

### Slice 2: Source family grouping

Files:

- `client/src/pages/Databases.tsx`

Changes:

- Replace the flat Add Datasource sidebar with grouped families.
- Add availability and output labels.
- Make `Feishu/Lark`, `TOS/S3`, files, web, SQL, warehouse visually distinct.
- Keep existing forms behind the selected family.

### Slice 3: Processing state after import

Files:

- `client/src/components/SourceConnectorImportPanel.tsx`
- `client/src/pages/Databases.tsx`
- `client/src/services/api.ts`

Changes:

- After import, show a stepper using existing resource status and processing API.
- Keep dialog open until user chooses next action.
- Add `Generate semantic model`, `Create dashboard`, `Open source` actions.

### Slice 4: Source detail page

Files:

- `client/src/App.tsx`
- new `client/src/pages/SourceDetailPage.tsx`
- `client/src/services/api.ts`

Changes:

- Add `/sources/:sourceId`.
- Render Overview, Snapshots, Tables, Evidence, Lineage, Consumers, Settings.
- Start with read-only data from existing source resource APIs.

### Slice 5: Dashboard workspace

Files:

- `client/src/App.tsx`
- new `client/src/pages/DashboardsPage.tsx`
- existing dashboard viewer/share APIs

Changes:

- Add `/dashboards`.
- List generated/shared dashboards.
- Surface freshness, latest successful snapshot, refresh status, owner, sharing.

### Slice 6: OpenViking provider integration

Files:

- `server/services/knowledge_provider.py`
- source resource ingest service
- migrations/models for provider metadata

Changes:

- Add `OpenVikingKnowledgeProvider`.
- Store context URI/provider metadata.
- Keep native provider fallback.
- Avoid storing long-lived chunks in metadata DB.

## Acceptance Criteria

The UX redesign is moving in the right direction when:

- A new user can start from `Sources`, not `Integrations`, to add Feishu or a PDF.
- After adding a source, the user sees processing progress and next actions.
- A source card/row links to a detail page with snapshots, evidence, tables, and consumers.
- Semantic model creation starts from one or more sources and shows source health.
- Dashboard creation can start from a published semantic model.
- Dashboard list shows freshness and latest successful snapshot.
- Permission errors show the missing scope and direct action.
- The UI no longer calls document/file/web resources "database connections".
- OpenViking is not exposed as a user-facing connector for core enterprise sources.
