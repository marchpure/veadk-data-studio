export type DashboardLifecycle = 'legacy_unstructured' | 'draft' | 'in_review' | 'published' | 'archived'
export type DashboardTileType = 'kpi' | 'line' | 'bar' | 'area' | 'table' | 'text' | 'evidence' | 'status'
export type DashboardRunViewStatus =
  | 'pending'
  | 'running'
  | 'success'
  | 'empty'
  | 'partial'
  | 'stale'
  | 'permission_denied'
  | 'error'
  | 'blocked'

export interface DashboardOutputField {
  name: string
  data_type: string
  description?: string
  unit?: string | null
  nullable?: boolean
  sensitivity?: string
}

export interface DashboardEvidenceLocator {
  id: string
  kind: string
  title: string
  locator?: Record<string, unknown>
  confidence?: number | null
}

export interface DashboardLineageRef {
  id: string
  kind: string
  name: string
  ref: string
  version?: string | null
}

export interface DashboardSemanticBinding {
  id: string
  model_slug: string
  model_version: string
  source_snapshot_ids?: string[]
  allowed_metrics?: string[]
  allowed_dimensions?: string[]
  readiness?: string
}

export interface DashboardDataView {
  id: string
  kind: 'semantic_metric' | 'saved_query' | 'context_search'
  question: string
  output_schema?: DashboardOutputField[]
  filter_fields?: string[]
  sensitivity?: string
  row_limit?: number
  byte_limit?: number
  timeout_seconds?: number
  evidence?: DashboardEvidenceLocator[]
  lineage?: DashboardLineageRef[]
  semantic_metric?: {
    semantic_binding_id: string
    metric: string
    dimensions?: string[]
    grain?: string | null
  } | null
  saved_query?: {
    query_id: string
    compatibility_reason: string
    filter_contract?: Record<string, unknown>
    lineage?: DashboardLineageRef[]
  } | null
}

export interface DashboardFilter {
  id: string
  label: string
  source: 'semantic_field' | 'saved_query_contract'
  field: string
  filter_type: string
  operators: string[]
  affected_data_view_ids?: string[]
  default_value?: unknown
  required?: boolean
  domain?: unknown[] | null
  timezone?: string | null
}

export interface DashboardTile {
  id: string
  title: string
  tile_type: DashboardTileType
  business_question: string
  data_view_id?: string | null
  encoding?: Record<string, unknown>
  formatting?: Record<string, unknown>
  interactions?: Record<string, unknown>[]
  accessible_fallback?: {
    summary?: string
    table_fields?: string[]
  }
}

export interface DashboardManifest {
  schema_version: 'dashboard.manifest.v1'
  dashboard_id: string
  title: string
  description?: string
  audience: string[]
  semantic_bindings: DashboardSemanticBinding[]
  data_views: DashboardDataView[]
  filters: DashboardFilter[]
  layout: {
    sections: Array<{
      id: string
      title?: string
      tile_ids: string[]
    }>
  }
  tiles: DashboardTile[]
  actions: Array<Record<string, unknown>>
  freshness_policy: Record<string, unknown>
  access_policy: Record<string, unknown>
  provenance: Record<string, unknown>
  migration: {
    state: string
    blockers?: string[]
    legacy_dashboard_id?: string | null
    reviewed_by?: string | null
    reviewed_at?: string | null
  }
}

export interface DashboardAsset {
  id: string
  tenant_id: string
  notebook_id: string | null
  slug: string
  name: string
  description: string
  owner_id: string | null
  tags: string[]
  lifecycle: DashboardLifecycle
  current_draft_version_id: string | null
  published_version_id: string | null
  access_policy: Record<string, unknown>
  freshness_policy: Record<string, unknown>
  consumer_summary: Record<string, unknown>
  health_summary: Record<string, unknown>
  etag: string
  created_at: string | null
  updated_at: string | null
}

export interface DashboardVersionSummary {
  id: string
  asset_id: string | null
  notebook_id: string
  version_num: number
  manifest_schema_version: string | null
  content_hash: string | null
  status: string
  created_by: string | null
  actor_type: string | null
  change_summary: string
  pinned_model_versions: Record<string, string>
  pinned_source_snapshots: string[]
  validation_result: {
    valid?: boolean
    blockers?: string[]
    warnings?: string[]
    validated_at?: string
    semantic_diff?: DashboardSemanticDiff
  }
  renderer_version: string | null
  migration_state: string
  is_published_immutable: boolean
  created_at: string | null
}

export interface DashboardAssetDetail extends DashboardAsset {
  versions: DashboardVersionSummary[]
}

export interface DashboardVersion extends DashboardVersionSummary {
  manifest: DashboardManifest
}

export interface DashboardRunView {
  data_view_id: string
  status: DashboardRunViewStatus
  result: Array<Record<string, unknown>> | Record<string, unknown> | null
  schema?: DashboardOutputField[]
  row_count: number
  cached: boolean
  stale: boolean
  as_of?: string | null
  warnings?: string[]
  error?: {
    code: string
    message: string
    retryable?: boolean
    policy_reason?: string | null
  } | null
  evidence?: DashboardEvidenceLocator[]
  lineage?: DashboardLineageRef[]
  pagination?: {
    cursor?: string | null
    has_more?: boolean
    limit?: number
  }
}

export interface DashboardRun {
  contract_version: 'dashboard.run.v1'
  run_id: string
  dashboard_id: string
  dashboard_version_id: string
  actor_type: string
  actor_id: string
  correlation_id?: string | null
  mode: 'live' | 'pinned_snapshot'
  normalized_filters: Record<string, unknown>
  filter_digest: string
  pinned_versions: {
    semantic_models?: Record<string, string>
    source_snapshots?: string[]
  }
  execution_plan_digest: string
  started_at: string
  completed_at?: string | null
  overall_freshness: string
  views: DashboardRunView[]
  warnings?: string[]
  errors?: unknown[]
  preview?: boolean
}

export interface DashboardSemanticDiff {
  base_version_id?: string | null
  base_version_num?: number | null
  draft_version_id?: string | null
  draft_version_num?: number | null
  model_version_changes?: Array<{
    binding_id: string
    model_slug: string
    from: string
    to: string
  }>
  source_snapshot_changes?: Array<{
    binding_id: string
    model_slug: string
    from: string[]
    to: string[]
  }>
  filter_changes?: unknown[]
  tile_changes?: unknown[]
  policy_changes?: unknown[]
  warnings?: string[]
  blockers?: string[]
}

export interface DashboardState {
  asset: DashboardAsset
  versions: DashboardVersionSummary[]
  draft_version_id: string | null
  published_version_id: string | null
}

export interface DashboardAuditEvent {
  id: string
  asset_id: string | null
  version_id: string | null
  run_id: string | null
  actor_type: string
  actor_id: string
  action: string
  correlation_id?: string | null
  before_digest?: string | null
  after_digest?: string | null
  outcome: string
  details: Record<string, unknown>
  created_at: string | null
}

export interface DashboardFolderShare {
  id: string
  folder_id: string
  dashboard_id: string
  created_at?: string | null
  is_snapshot?: boolean
}
