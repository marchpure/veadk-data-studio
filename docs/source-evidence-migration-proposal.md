# Source & Evidence migration proposal

Status: proposal only. Do not apply as a public migration in this slice.

This slice keeps the MVP contract in existing JSON fields so it can be merged independently without changing shared migrations. The following schema changes should be owned by the Integration Owner when Source/Evidence moves beyond MVP compatibility.

## 1. Versioned sync runs

Add `source_sync_runs`:

- `id uuid primary key`
- `tenant_id uuid not null index`
- `resource_id uuid not null references source_resources(id)`
- `connection_id uuid null references source_connections(id)`
- `trigger text not null` with values `manual`, `scheduled`, `event`, `retry`
- `status text not null` with values `queued`, `running`, `succeeded`, `failed`, `partial`, `cancelled`
- `attempt int not null default 1`
- `checkpoint_json jsonb null`
- `started_at timestamp null`
- `finished_at timestamp null`
- `error_json jsonb null`
- `created_at timestamp not null default now()`

Indexes:

- `(tenant_id, resource_id, created_at desc)`
- `(tenant_id, status, created_at desc)`

Rollback:

- Drop table only after backfilling `source_resources.sync_config_json.latest_sync_run` for rows still needed by older code.

## 2. Resource tombstones

Extend `source_resources.status` check constraint with `removed` after all deployed environments have the migration.

Add nullable columns:

- `removed_at timestamp null`
- `removed_by uuid null`
- `deletion_marker_json jsonb null`

Compatibility:

- Current MVP does not write `status = "removed"` because this slice does not change the public check constraint.
- Current MVP stores `deletion_marker.status = "removed"` in `sync_config_json`, keeps the row on a constraint-compatible status, and writes a `source-resource-tombstone-v1` SourceSnapshot.
- List APIs must exclude rows with `sync_config_json.deletion_marker.status = "removed"` in MVP, and exclude `status = "removed"` after the formal migration.

Rollback:

- Convert `removed` rows to `failed` with `sync_config_json.deletion_marker.status = "removed"` before reverting the check constraint.

## 3. Projection lineage

Add `source_projection_files`:

- `id uuid primary key`
- `tenant_id uuid not null index`
- `resource_id uuid not null references source_resources(id)`
- `snapshot_id uuid not null references source_snapshots(id)`
- `dataset_id uuid not null references datasets(id)`
- `file_id uuid not null references files(id)`
- `source_locator_json jsonb not null`
- `row_mapping_json jsonb null`
- `created_at timestamp not null default now()`

Indexes:

- `(tenant_id, snapshot_id)`
- `(tenant_id, dataset_id)`
- `(tenant_id, resource_id, created_at desc)`

Compatibility:

- Current MVP stores this as `source_snapshots.metadata_json.projection_manifest` and `source_resources.sync_config_json.projected_dataset`.

Rollback:

- Backfill JSON manifests from `source_projection_files`, then drop table.

## 4. Asset dependencies

Replace `projected_dataset_id` JSON compatibility with versioned dependencies:

Add `asset_dependencies`:

- `id uuid primary key`
- `tenant_id uuid not null index`
- `source_asset_type text not null`
- `source_asset_id text not null`
- `target_asset_type text not null`
- `target_asset_id text not null`
- `snapshot_id uuid null references source_snapshots(id)`
- `dependency_policy_json jsonb not null default '{}'`
- `status text not null default 'active'`
- `created_at timestamp not null default now()`
- `updated_at timestamp not null default now()`

Indexes:

- `(tenant_id, source_asset_type, source_asset_id)`
- `(tenant_id, target_asset_type, target_asset_id)`
- `(tenant_id, snapshot_id)`

Behavior:

- Published Skill/Semantic Model/Analysis Artifact should bind to fixed `snapshot_id`.
- Source updates create `update_available` or `needs_review`; they must not silently mutate published outputs.

## 5. Evidence locator hardening

Keep `evidence_fragments.locator_json` but enforce a JSON schema at write boundaries:

- common: `source_connection_id`, `source_resource_id`, `source_snapshot_id`, `content_hash`, `parser_version`, `captured_at`
- web: `final_url`, optional `selector`, `text_range`
- Feishu Doc/Wiki: `document_token`, optional `wiki_token`, `block_id`, `heading_path`
- Feishu Sheet: `spreadsheet_token`, `sheet_id`, `range` / `cell_range`
- Feishu Base: `app_token`, `table_id`, optional `view_id`, `record_id`, `field_id`
- TOS: `bucket`, `key`, optional `version_id`, `etag`, `last_modified`
- PDF: `page`, optional `bbox`, parser identifier

Migration path:

- Backfill common fields from `source_snapshots` and `source_resources`.
- Leave unknown legacy locators readable but mark them `locator_quality = "legacy"`.
