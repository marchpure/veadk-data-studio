import { ApiService, type Datasource, type SourceOverviewItem, type SourceSkillCandidate, type SourceUnderstanding } from '../../../services/api'
import type {
  AgentSuggestion,
  ConsumptionEntry,
  DataStudioAsset,
  DataStudioAssetGate,
  DataModelingDatasource,
  DataModelingMode,
  DataModelingStatus,
  DataSourceKind,
  DataSourceProfile,
  FieldRole,
  ProfileField,
  ProfileTable,
  SemanticModel,
  TableCategory,
} from '../types'

const emptyReadiness = {
  score: 0,
  level: 'blocked' as const,
  components: [],
  reliableQuestions: [],
  unreliableQuestions: [],
  blockers: [],
  warnings: [],
}

const emptyExplore = {
  metricId: '',
  dimensionId: '',
  grain: 'month' as const,
  timeRange: '90d' as const,
  filter: '',
  viewMode: 'trend' as const,
  savedQueryCount: 0,
  dashboardAdds: 0,
  skillDrafts: 0,
  confirmedExamples: 0,
}

const defaultConsumptionEntries: ConsumptionEntry[] = [
  { id: 'agent', label: 'Agent', before: 'Draft answers only', after: 'Waiting for publish' },
  { id: 'dashboard', label: 'Dashboard', before: 'Preview binding', after: 'Waiting for publish' },
  { id: 'mcp_api', label: 'MCP API', before: 'Draft not exposed', after: 'Waiting for publish' },
  { id: 'share_link', label: 'Share link', before: 'Preview disabled', after: 'Waiting for publish' },
]

export interface DataModelingAdapter {
  listModels(): Promise<SemanticModel[]>
  getModel(modelId: string): Promise<SemanticModel>
  patchModel(model: SemanticModel, patch: Partial<SemanticModel>): Promise<SemanticModel>
  validateModel(model: SemanticModel): Promise<SemanticModel>
  publishModel(model: SemanticModel): Promise<SemanticModel>
  queryMetric(model: SemanticModel): Promise<SemanticModel['mcp']['lastResult']>
  listDatasources(): Promise<DataModelingDatasource[]>
  loadProfile(datasourceId: string): Promise<DataSourceProfile>
  analyzeDatasource(datasourceId: string, selectedTables: string[]): Promise<SourceUnderstanding>
  reviewCandidate(datasourceId: string, candidateId: string, action: 'accept' | 'edit' | 'reject'): Promise<SourceUnderstanding>
  createDraft(datasourceId: string, payload: { name?: string; domain: string; owner: string; candidateIds: string[] }): Promise<SemanticModel>
}

export function normalizeModel(raw: any): SemanticModel {
  const metrics = Array.isArray(raw?.metrics) ? raw.metrics : []
  const dimensions = Array.isArray(raw?.dimensions) ? raw.dimensions : []
  const firstMetric = metrics[0]?.id ?? ''
  const firstDimension = dimensions[0]?.id ?? ''
  const status = raw?.status ?? 'Draft'
  const publishedVersion = String(raw?.publishedVersion ?? 'v0')
  const readiness = Number(raw?.readiness ?? 0)
  const readinessLevel = raw?.readinessLevel ?? 'blocked'
  const consumers = {
    agents: Number(raw?.consumers?.agents ?? 0),
    mcp: Number(raw?.consumers?.mcp ?? 0),
    skills: Number(raw?.consumers?.skills ?? 0),
    dashboards: Number(raw?.consumers?.dashboards ?? 0),
    savedQueries: Number(raw?.consumers?.savedQueries ?? 0),
  }
  const readinessDetail = normalizeReadiness(raw?.readinessDetail)
  const gate = normalizeGate(raw?.gate, readiness, readinessDetail.blockers)
  const publishState = normalizePublishState(raw?.publishState ?? raw?.publish_state, status, gate.blockers.length)
  const model: SemanticModel = {
    id: String(raw?.id ?? ''),
    name: String(raw?.name ?? 'Untitled Semantic Model'),
    domain: String(raw?.domain ?? 'Unassigned'),
    owner: String(raw?.owner ?? 'Data Team'),
    datasource: String(raw?.datasource ?? raw?.datasourceName ?? 'Unknown datasource'),
    datasourceId: String(raw?.datasourceId ?? ''),
    status,
    revision: Number(raw?.revision ?? 1),
    draftRevision: String(raw?.draftRevision ?? 'draft-1'),
    publishedVersion,
    readiness,
    readinessLevel,
    driftAlerts: Number(raw?.driftAlerts ?? 0),
    consumers,
    updatedAt: String(raw?.updatedAt ?? ''),
    description: String(raw?.description ?? ''),
    entities: Array.isArray(raw?.entities) ? raw.entities : [],
    relationships: Array.isArray(raw?.relationships) ? raw.relationships.map(normalizeRelationship) : [],
    metrics: metrics.map((metric: any) => ({
      id: String(metric.id),
      name: String(metric.name ?? metric.id),
      businessName: String(metric.businessName ?? metric.name ?? metric.id),
      definition: displayValue(metric.definition),
      kind: metric.kind ?? 'measure',
      formula: displayValue(metric.formula),
      filter: displayValue(metric.filter),
      timeField: displayValue(metric.timeField),
      defaultGrain: metric.defaultGrain ?? 'month',
      dimensions: normalizeStringList(metric.dimensions),
      unit: displayValue(metric.unit),
      owner: displayValue(metric.owner ?? raw?.owner ?? 'Data Team'),
      certification: metric.certification ?? 'draft',
      lineage: normalizeStringList(metric.lineage),
      preview: {
        currentValue: displayValue(metric.preview?.currentValue ?? metric.preview?.current_value ?? 'Run query'),
        trend: displayValue(metric.preview?.trend),
        breakdown: Array.isArray(metric.preview?.breakdown) ? metric.preview.breakdown : [],
        explanation: displayValue(metric.preview?.explanation ?? metric.definition),
        sql: displayValue(metric.preview?.sql ?? metric.compiledSql),
        validation: displayValue(metric.preview?.validation ?? metric.validationStatus),
      },
    })),
    dimensions: dimensions.map(normalizeDimension),
    calculatedFields: Array.isArray(raw?.calculatedFields) ? raw.calculatedFields.map(normalizeCalculatedField) : [],
    suggestions: Array.isArray(raw?.suggestions) ? raw.suggestions.map(normalizeSuggestion) : [],
    readinessDetail,
    explore: {
      ...emptyExplore,
      ...(raw?.explore ?? {}),
      metricId: raw?.explore?.metricId ?? firstMetric,
      dimensionId: raw?.explore?.dimensionId ?? firstDimension,
    },
    review: {
      opened: Boolean(raw?.review?.opened),
      reviewed: Boolean(raw?.review?.reviewed),
      publishNotes: String(raw?.review?.publishNotes ?? ''),
      publishedAt: raw?.review?.publishedAt,
      ...(raw?.review ?? {}),
    },
    mcp: {
      exposedVersion: String(raw?.mcp?.exposedVersion ?? raw?.publishedVersion ?? 'v0'),
      consumerIdentity: String(raw?.mcp?.consumerIdentity ?? 'MCP semantic client'),
      rawSqlFallback: Boolean(raw?.mcp?.rawSqlFallback),
      allowedMetrics: Array.isArray(raw?.mcp?.allowedMetrics) ? normalizeStringList(raw.mcp.allowedMetrics) : metrics.map((item: any) => String(item.id)),
      allowedDimensions: Array.isArray(raw?.mcp?.allowedDimensions) ? normalizeStringList(raw.mcp.allowedDimensions) : dimensions.map((item: any) => String(item.id)),
      lastResult: normalizeMcpResult(raw?.mcp?.lastResult),
    },
    validationLog: normalizeStringList(raw?.validationLog),
    assetType: 'semantic_model',
    publishState,
    gate,
    dataStudioAsset: normalizeDataStudioAsset(raw?.dataStudioAsset ?? raw?.data_studio_asset, {
      id: String(raw?.id ?? ''),
      name: String(raw?.name ?? 'Untitled Semantic Model'),
      description: String(raw?.description ?? ''),
      status,
      publishState,
      gate,
      publishedVersion,
      consumers,
      datasource: String(raw?.datasource ?? raw?.datasourceName ?? 'Unknown datasource'),
      validationLog: normalizeStringList(raw?.validationLog),
    }),
    consumptionEntries: normalizeConsumptionEntries(raw?.consumptionEntries ?? raw?.consumption_entries),
  }
  return model
}

function modelPatch(model: SemanticModel, patch: Partial<SemanticModel>) {
  return {
    expected_revision: model.revision,
    ...patch,
  }
}

export const dataModelingAdapter: DataModelingAdapter = {
  async listModels() {
    const response = await ApiService.listSemanticModels()
    return response.items.map(normalizeModel)
  },

  async getModel(modelId) {
    return normalizeModel(await ApiService.getSemanticModel(modelId))
  },

  async patchModel(model, patch) {
    return normalizeModel(await ApiService.updateSemanticModel(model.id, modelPatch(model, patch)))
  },

  async validateModel(model) {
    return normalizeModel(await ApiService.validateSemanticModel(model.id))
  },

  async publishModel(model) {
    return normalizeModel(await ApiService.publishSemanticModel(model.id))
  },

  async queryMetric(model) {
    const metric = model.metrics.find(item => item.id === model.explore.metricId) ?? model.metrics[0]
    const requestedDimension = model.dimensions.find(item => item.id === model.explore.dimensionId)
    const dimensionId = requestedDimension && (!metric?.dimensions.length || metric.dimensions.includes(requestedDimension.id))
      ? requestedDimension.id
      : metric?.dimensions[0] ?? requestedDimension?.id ?? model.explore.dimensionId
    const result = await ApiService.querySemanticMetric(model.id, {
      metric: metric?.id ?? model.explore.metricId,
      dimension: dimensionId,
      grain: model.explore.grain,
      time_range: model.explore.timeRange,
    })
    if (String(result.status ?? '').toLowerCase() === 'failed' || result.error) {
      throw new Error(displayValue(result.error ?? 'Semantic query failed'))
    }
    return {
      resolvedMetric: displayValue(result.resolvedMetric),
      modelVersion: displayValue(result.modelVersion),
      result: typeof result.result === 'string' ? result.result : JSON.stringify(result.result ?? ''),
      freshness: displayValue(result.freshness),
      lineage: normalizeStringList(result.lineage),
      policyDecision: displayValue(result.policyDecision),
    }
  },

  async listDatasources() {
    try {
      const response = await ApiService.listSourcesOverview()
      return response.items
        .map(sourceOverviewToModelingDatasource)
        .sort(compareModelingDatasources)
    } catch (error) {
      console.warn('Falling back to legacy datasource list for Data Modeling:', error)
      const response = await ApiService.listAllDatasources()
      return response.items
        .filter(item => ['oracle', 'postgres', 'pg', 'mysql', 'sqlite', 'databricks'].includes(String(item.database_type ?? item.db_type ?? item.type)))
        .map(legacyDatasourceToModelingDatasource)
        .sort(compareModelingDatasources)
    }
  },

  async loadProfile(datasourceId) {
    try {
      const understanding = await ApiService.getDatasourceUnderstanding(datasourceId)
      return profileFromUnderstanding(understanding)
    } catch {
      const schema = await ApiService.getDatasourceSchema(datasourceId)
      return profileFromSchema(datasourceId, schema)
    }
  },

  async analyzeDatasource(datasourceId, selectedTables) {
    return ApiService.analyzeDatasourceUnderstanding(datasourceId, { scope: selectedTables })
  },

  async reviewCandidate(datasourceId, candidateId, action) {
    return ApiService.reviewSourceSkillCandidate(datasourceId, candidateId, { action })
  },

  async createDraft(datasourceId, payload) {
    const response = await ApiService.createSemanticModelDraftFromSourceUnderstanding(datasourceId, {
      name: payload.name,
      domain: payload.domain,
      owner: payload.owner,
      candidate_ids: payload.candidateIds,
    })
    return normalizeModel(response.model)
  },
}

export function sourceOverviewToModelingDatasource(item: SourceOverviewItem): DataModelingDatasource {
  const reviewedProjectionTarget = item.modeling_status === 'supported'
    && item.modeling_mode === 'projection'
    && item.projected_dataset_id
  const base = {
    id: reviewedProjectionTarget ? item.projected_dataset_id as string : item.id,
    name: item.name,
    kind: normalizeSourceOverviewKind(item),
    sourceType: reviewedProjectionTarget ? 'dataset' as const : item.source_kind,
    status: item.status,
    sourceFamily: item.family,
    provider: item.provider,
    nextActions: item.next_actions ?? [],
    projectedDatasetId: item.projected_dataset_id,
    sourceResourceId: reviewedProjectionTarget ? item.id : undefined,
    contextIndexStatus: item.context_index_status,
    parseStatus: item.parse_status,
    lastSyncedAt: item.last_synced_at ?? item.updated_at ?? null,
  }
  if (item.modeling_status) {
    return {
      ...base,
      modelingStatus: item.modeling_status,
      modelingMode: item.modeling_mode ?? modeForFamily(item),
      reason: item.modeling_reason ?? undefined,
      evidenceSummary: item.modeling_evidence_summary ?? undefined,
      nextActions: item.modeling_next_action
        ? [item.modeling_next_action, ...base.nextActions.filter(action => action !== item.modeling_next_action)]
        : base.nextActions,
      canLoadProfile: Boolean(item.modeling_can_load_profile),
    }
  }
  const blocked = sourceOverviewBlocker(item)
  if (blocked) {
    return {
      ...base,
      modelingStatus: blocked.status,
      modelingMode: modeForFamily(item),
      reason: blocked.reason,
      evidenceSummary: localEvidenceSummary(item),
      canLoadProfile: false,
    }
  }

  if (item.family === 'databases') {
    return {
      ...base,
      modelingStatus: 'supported',
      modelingMode: 'relational',
      reason: 'Schema/profile evidence can be used to generate a production semantic model.',
      evidenceSummary: localEvidenceSummary(item),
      canLoadProfile: true,
    }
  }

  if (item.family === 'nosql') {
    return {
      ...base,
      modelingStatus: 'needs_projection',
      modelingMode: 'document_projection',
      reason: `${nosqlProviderLabel(item)} needs projection review before production semantic modeling. Sampled document/key-value schema evidence is not enough for publish.`,
      evidenceSummary: localEvidenceSummary(item),
      canLoadProfile: true,
    }
  }

  if (item.family === 'warehouses') {
    return {
      ...base,
      modelingStatus: 'supported',
      modelingMode: 'warehouse',
      reason: 'Warehouse catalog/profile evidence can be used to generate a production semantic model.',
      evidenceSummary: localEvidenceSummary(item),
      canLoadProfile: true,
    }
  }

  if (isProjectionSource(item)) {
    return {
      ...base,
      modelingStatus: 'needs_projection',
      modelingMode: 'projection',
      reason: item.projected_dataset_id
        ? 'Review and confirm the projected dataset before production semantic modeling.'
        : 'Detect and confirm a tabular projection before production semantic modeling.',
      evidenceSummary: localEvidenceSummary(item),
      canLoadProfile: false,
    }
  }

  if (isContextSource(item)) {
    return {
      ...base,
      modelingStatus: 'context_only',
      modelingMode: 'context_assisted',
      reason: contextOnlyReason(item),
      evidenceSummary: localEvidenceSummary(item),
      canLoadProfile: false,
    }
  }

  return {
    ...base,
    modelingStatus: 'unsupported',
    modelingMode: modeForFamily(item),
    reason: unsupportedReasonForFamily(item),
    evidenceSummary: localEvidenceSummary(item),
    canLoadProfile: false,
  }
}

function legacyDatasourceToModelingDatasource(item: Datasource): DataModelingDatasource {
  const kind = normalizeKind(item.database_type ?? item.db_type ?? item.type)
  const isWarehouse = kind === 'databricks'
  return {
    id: item.id,
    name: item.name,
    kind,
    sourceType: item.source_type,
    status: item.status,
    modelingStatus: 'supported',
    modelingMode: isWarehouse ? 'warehouse' : 'relational',
    reason: 'Legacy datasource is supported for relational semantic generation.',
    nextActions: ['Generate semantic model'],
    sourceFamily: isWarehouse ? 'warehouses' : 'databases',
    provider: String(item.database_type ?? item.db_type ?? item.type ?? ''),
    canLoadProfile: true,
    projectedDatasetId: item.projected_dataset_id,
    lastSyncedAt: item.updated_at ?? item.created_at ?? null,
  }
}

function compareModelingDatasources(left: DataModelingDatasource, right: DataModelingDatasource): number {
  const priority: Record<DataModelingStatus, number> = {
    supported: 0,
    needs_projection: 1,
    context_only: 2,
    reauthorization_required: 3,
    permission_required: 4,
    blocked: 5,
    processing: 6,
    source_unavailable: 7,
    failed: 8,
    planned: 9,
    unsupported: 10,
  }
  const statusDelta = priority[left.modelingStatus] - priority[right.modelingStatus]
  if (statusDelta !== 0) return statusDelta
  return left.name.localeCompare(right.name)
}

function sourceOverviewBlocker(item: SourceOverviewItem): { status: DataModelingStatus; reason: string } | null {
  const status = normalizeStatusText(item.status)
  if (status === 'authorization required') {
    return {
      status: 'reauthorization_required',
      reason: 'Connect or reauthorize this source before it can feed semantic modeling.',
    }
  }
  if (status === 'reauthorization required') {
    return {
      status: 'reauthorization_required',
      reason: 'Reauthorize this source before it can feed semantic modeling.',
    }
  }
  if (status === 'permission lost') {
    return {
      status: 'permission_required',
      reason: 'Restore upstream permissions before this source can feed semantic modeling.',
    }
  }
  if (status === 'source unavailable') {
    return {
      status: 'source_unavailable',
      reason: 'The upstream source is unavailable. Retry sync or check the upstream resource.',
    }
  }
  if (status === 'blocked') {
    return {
      status: 'blocked',
      reason: 'Source capture is blocked by policy or upstream safety controls.',
    }
  }
  if (status === 'failed') {
    return {
      status: 'failed',
      reason: item.parse_status === 'failed'
        ? 'Parser failed. Review parser warnings and retry sync before modeling.'
        : 'Source processing failed. Retry sync before modeling.',
    }
  }
  if (status === 'needs confirmation') {
    return {
      status: 'needs_projection',
      reason: needsConfirmationReason(item),
    }
  }
  if (item.context_index_status === 'failed' && isContextSource(item)) {
    return {
      status: 'failed',
      reason: 'Context indexing failed. Retry indexing before using this source as modeling evidence.',
    }
  }
  if (item.parse_status === 'failed') {
    return {
      status: 'failed',
      reason: 'Parsing failed. Review parser warnings and retry sync before modeling.',
    }
  }
  if (['pending', 'syncing', 'analyzing'].includes(status)) {
    return {
      status: 'processing',
      reason: pendingSourceReason(item),
    }
  }
  if (status === 'planned') {
    return {
      status: 'planned',
      reason: 'This connector is not production-ready yet. Request access or use an available Source family.',
    }
  }
  if (item.next_actions.some(action => normalizeStatusText(action).includes('request access'))) {
    return {
      status: 'planned',
      reason: 'This connector is not production-ready yet. Request access or use an available Source family.',
    }
  }
  return null
}

function normalizeStatusText(value: unknown): string {
  return String(value ?? '').trim().toLowerCase()
}

function pendingSourceReason(item: SourceOverviewItem): string {
  const actions = (item.next_actions ?? []).map(normalizeStatusText)
  if (item.family === 'nosql') {
    if (actions.some(action => action.includes('refresh document profile'))) {
      return 'Refresh the document profile before projection review.'
    }
    return 'NoSQL document/key-value profile is not ready yet. Refresh the profile before projection review.'
  }
  if (item.family === 'databases' || item.family === 'warehouses') {
    if (actions.some(action => action.includes('refresh schema profile'))) {
      return 'Refresh the schema/profile before this source can feed production semantic modeling.'
    }
    return 'Database schema/profile is not ready yet. Refresh the profile before modeling.'
  }
  return 'Source processing is still running. Wait until processing finishes before modeling.'
}

function nosqlProviderLabel(item: SourceOverviewItem): string {
  const provider = String(item.provider || item.resource_type || '').toLowerCase()
  if (provider.includes('dynamo')) return 'DynamoDB'
  if (provider.includes('mongo')) return 'MongoDB'
  return 'NoSQL source'
}

function isProjectionSource(item: SourceOverviewItem): boolean {
  const resourceType = String(item.resource_type ?? '')
  if (item.family === 'nosql') return true
  return Boolean(item.projected_dataset_id)
    || hasParsedTables(item)
    || isProjectionResourceType(resourceType)
}

function isProjectionResourceType(resourceType: string): boolean {
  return [
    'csv',
    'excel',
    'xlsx',
    'xlsm',
    'feishu_sheet',
    'feishu_base',
    'extracted_table',
  ].includes(resourceType)
}

function hasParsedTables(item: SourceOverviewItem): boolean {
  return Number(item.parsed_asset_counts?.tables ?? 0) > 0
}

function localEvidenceSummary(item: SourceOverviewItem): string {
  const counts = item.parsed_asset_counts ?? { blocks: 0, tables: 0, files: 0, evidence: 0 }
  const parts: string[] = []
  if (counts.tables) parts.push(`${counts.tables} table${counts.tables === 1 ? '' : 's'}`)
  if (counts.files) parts.push(`${counts.files} file${counts.files === 1 ? '' : 's'}`)
  if (counts.evidence) parts.push(`${counts.evidence} evidence fragment${counts.evidence === 1 ? '' : 's'}`)
  if (parts.length === 0) parts.push('no profile or evidence yet')
  parts.push(`parse ${item.parse_status}`)
  parts.push(`context ${item.context_index_status}`)
  return parts.join('; ')
}

function hasIndexedEvidence(item: SourceOverviewItem): boolean {
  return item.context_index_status === 'indexed' && Number(item.parsed_asset_counts?.evidence ?? 0) > 0
}

function isContextResourceType(resourceType: string): boolean {
  return [
    'file',
    'pdf',
    'web',
    'feishu_doc',
    'feishu_wiki',
    'tos_bucket',
    'tos_prefix',
    'tos_object',
  ].includes(resourceType)
}

function isContextSource(item: SourceOverviewItem): boolean {
  const resourceType = String(item.resource_type ?? '')
  if (item.family === 'documents' || item.family === 'web') return true
  if (isContextResourceType(resourceType) && hasIndexedEvidence(item)) return true
  return hasIndexedEvidence(item)
}

function modeForFamily(item: SourceOverviewItem): DataModelingMode | undefined {
  if (item.family === 'databases') return 'relational'
  if (item.family === 'nosql') return 'document_projection'
  if (item.family === 'warehouses') return 'warehouse'
  if (isProjectionSource(item)) return 'projection'
  if (isContextSource(item)) return 'context_assisted'
  if (item.family === 'saas' || item.family === 'api') return 'business_object'
  return undefined
}

function unsupportedReasonForFamily(item: SourceOverviewItem): string {
  if (item.family === 'saas' || item.family === 'api') {
    return 'SaaS/API sources need a business object contract before production semantic modeling.'
  }
  return 'This source family does not yet expose a production modeling handoff contract.'
}

function contextOnlyReason(item: SourceOverviewItem): string {
  if (item.context_index_status === 'pending') {
    return 'Context indexing is pending. Once indexed, this source can support definitions, policies, and evidence, but not production metric facts.'
  }
  if (item.context_index_status === 'indexing') {
    return 'Context indexing is still running. This source can support modeling evidence after indexing, but not production metric facts.'
  }
  if (item.context_index_status === 'unavailable') {
    return 'No context index is available yet. Add context indexing before using this source as modeling evidence.'
  }
  return 'Indexed context can support definitions, policies, and evidence, but cannot be the production fact source for metrics.'
}

function needsConfirmationReason(item: SourceOverviewItem): string {
  const actions = (item.next_actions ?? []).map(normalizeStatusText)
  if (item.family === 'object_storage' && actions.some(action => action.includes('confirm large object sync'))) {
    return 'Confirm large object sync before Data Modeling can profile, project, or index this object.'
  }
  if (isProjectionSource(item)) {
    return 'Confirm the projected dataset before production semantic modeling.'
  }
  if (isContextSource(item)) {
    return 'Confirm the selected resource before using it as modeling evidence.'
  }
  return 'Confirm the selected resource before modeling.'
}

function normalizeSourceOverviewKind(item: SourceOverviewItem): DataSourceKind {
  if (item.family === 'warehouses' || item.provider === 'databricks') return 'databricks'
  if (item.family === 'files') return 'file'
  if (item.family === 'documents') return 'document'
  if (item.family === 'web') return 'web'
  if (item.family === 'object_storage') return 'object_storage'
  if (item.family === 'nosql') return normalizeKind(item.provider || item.resource_type)
  if (item.family === 'api' || item.family === 'saas') return 'api'
  return normalizeKind(item.provider || item.resource_type)
}

export function suggestionsFromUnderstanding(understanding: SourceUnderstanding): AgentSuggestion[] {
  return understanding.candidates.map(candidateToSuggestion)
}

export function profileFromUnderstanding(understanding: SourceUnderstanding): DataSourceProfile {
  const tables = understanding.resources
    .filter(resource => resource.resource_type === 'database_table')
    .map(resource => tableFromCandidate(resource.name.split('.').pop() ?? resource.name, understanding.candidates))
  return {
    id: understanding.datasource_id,
    name: understanding.datasource_name,
    kind: normalizeKind(understanding.datasource_type),
    schema: String(understanding.profile?.schema ?? understanding.overview?.schema ?? 'default'),
    status: understanding.latest_run?.status === 'completed' ? 'ready' : 'partial',
    profileCoverage: Number(understanding.profile?.profile_coverage ?? 80),
    tables,
  }
}

function profileFromSchema(datasourceId: string, schemaResponse: any): DataSourceProfile {
  const raw = schemaResponse?.schema && typeof schemaResponse.schema === 'object' ? schemaResponse.schema : schemaResponse
  const tables = Object.entries(raw?.schema ?? raw ?? {}).map(([name, info]) => profileTableFromSchema(String(name), info as any))
  return {
    id: datasourceId,
    name: String(schemaResponse?.datasource_name ?? schemaResponse?.database_name ?? 'Datasource'),
    kind: normalizeKind(schemaResponse?.datasource_type ?? schemaResponse?.database_type),
    schema: String(schemaResponse?.selected_schema ?? 'default'),
    status: tables.length ? 'ready' : 'partial',
    profileCoverage: tables.length ? 70 : 0,
    tables,
  }
}

function tableFromCandidate(tableName: string, candidates: SourceSkillCandidate[]): ProfileTable {
  const schema = candidates.find(candidate => candidate.candidate_type === 'schema_map' && candidate.structured_payload_json?.table === tableName)
  const profile = candidates.find(candidate => candidate.candidate_type === 'data_profile' && candidate.structured_payload_json?.table === tableName)
  return profileTableFromSchema(tableName, {
    category: schema?.structured_payload_json?.category,
    columns: schema?.structured_payload_json?.fields ?? profile?.structured_payload_json?.columns ?? [],
    primary_key: schema?.structured_payload_json?.primary_key ?? [],
    row_count: profile?.structured_payload_json?.row_count,
    sample_rows: profile?.structured_payload_json?.sample_rows ?? [],
  })
}

function profileTableFromSchema(name: string, info: any): ProfileTable {
  const columns = Array.isArray(info?.columns) ? info.columns : []
  const sampleRows = Array.isArray(info?.sample_rows ?? info?.sample_data) ? (info.sample_rows ?? info.sample_data) : []
  return {
    name,
    label: name,
    category: normalizeCategory(info?.category ?? (hasMeasure(columns) ? 'fact' : 'dimension')),
    rowCount: Number(info?.row_count ?? info?.rowCount ?? info?.profile?.row_count ?? sampleRows.length ?? 0),
    timeRange: timeRange(columns),
    fields: columns.map((column: any) => profileField(column, sampleRows)),
    sampleRows,
  }
}

function profileField(column: any, sampleRows: Array<Record<string, any>>): ProfileField {
  const name = String(column.name ?? column.source_field ?? '')
  const observed = sampleRows.map(row => row[name]).filter(value => value !== undefined && value !== null)
  const topValues = Array.from(new Set(observed.map(String))).slice(0, 5).map(value => ({
    value,
    count: observed.filter(item => String(item) === value).length,
  }))
  return {
    name,
    type: String(column.type ?? column.data_type ?? 'unknown'),
    role: normalizeRole(column.role ?? name),
    nullable: Boolean(column.nullable ?? true),
    nullRate: Number(column.profile?.null_rate ?? column.null_rate ?? 0),
    distinctCount: Number(column.profile?.distinct_count ?? column.distinct_count ?? new Set(observed.map(String)).size),
    min: column.profile?.min ?? column.min,
    max: column.profile?.max ?? column.max,
    topValues,
    pii: normalizeRole(column.role ?? name) === 'pii',
  }
}

function candidateToSuggestion(candidate: SourceSkillCandidate): AgentSuggestion {
  return {
    id: candidate.id,
    type: candidate.candidate_type === 'data_truth' ? 'metric' : candidate.candidate_type === 'quality_gotcha' ? 'policy' : candidate.candidate_type as AgentSuggestion['type'],
    title: displayValue(candidate.title),
    recommendation: displayValue(candidate.statement),
    confidence: candidate.confidence > 1 ? candidate.confidence / 100 : candidate.confidence,
    evidence: candidate.evidence.map(item => ({ label: displayValue(item.fragment_type), detail: displayValue(item.text) })),
    validation: displayValue(candidate.validation_json ?? candidate.validation_status),
    status: candidate.review_status === 'verified' ? 'accepted' : candidate.review_status === 'rejected' ? 'rejected' : 'pending',
  }
}

function normalizeRelationship(relationship: any) {
  return {
    ...relationship,
    id: String(relationship?.id ?? ''),
    fromEntity: String(relationship?.fromEntity ?? relationship?.from_entity ?? ''),
    toEntity: String(relationship?.toEntity ?? relationship?.to_entity ?? ''),
    label: displayValue(relationship?.label),
    joinFields: Array.isArray(relationship?.joinFields ?? relationship?.join_fields) ? (relationship.joinFields ?? relationship.join_fields) : [],
    fkEvidence: displayValue(relationship?.fkEvidence ?? relationship?.fk_evidence),
    uniqueRate: Number(relationship?.uniqueRate ?? relationship?.unique_rate ?? 0),
    orphanRate: Number(relationship?.orphanRate ?? relationship?.orphan_rate ?? 0),
    fanoutRisk: relationship?.fanoutRisk ?? relationship?.fanout_risk ?? 'low',
    validationStatus: relationship?.validationStatus ?? relationship?.validation_status ?? 'warning',
    validationMessage: displayValue(relationship?.validationMessage ?? relationship?.validation_message ?? relationship?.validation),
  }
}

function normalizeDimension(dimension: any) {
  return {
    ...dimension,
    id: String(dimension?.id ?? ''),
    name: displayValue(dimension?.name ?? dimension?.id),
    entityId: String(dimension?.entityId ?? dimension?.entity_id ?? ''),
    field: displayValue(dimension?.field),
    description: displayValue(dimension?.description),
  }
}

function normalizeCalculatedField(calculated: any) {
  return {
    ...calculated,
    id: String(calculated?.id ?? ''),
    name: displayValue(calculated?.name ?? calculated?.id),
    entityId: String(calculated?.entityId ?? calculated?.entity_id ?? ''),
    expression: displayValue(calculated?.expression),
    description: displayValue(calculated?.description),
  }
}

function normalizeSuggestion(suggestion: any): AgentSuggestion {
  return {
    id: String(suggestion?.id ?? ''),
    type: suggestion?.type ?? 'metric',
    title: displayValue(suggestion?.title ?? suggestion?.id),
    recommendation: displayValue(suggestion?.recommendation ?? suggestion?.statement),
    confidence: Number(suggestion?.confidence ?? 0),
    evidence: Array.isArray(suggestion?.evidence)
      ? suggestion.evidence.map((item: any) => ({
          label: displayValue(item?.label ?? item?.fragment_type),
          detail: displayValue(item?.detail ?? item?.text ?? item),
        }))
      : [],
    validation: displayValue(suggestion?.validation),
    status: suggestion?.status ?? 'pending',
    editedNote: suggestion?.editedNote ? displayValue(suggestion.editedNote) : undefined,
  }
}

function normalizeReadiness(readiness: any) {
  if (!readiness || typeof readiness !== 'object') return emptyReadiness
  return {
    ...emptyReadiness,
    ...readiness,
    reliableQuestions: normalizeStringList(readiness.reliableQuestions),
    unreliableQuestions: normalizeStringList(readiness.unreliableQuestions),
    blockers: normalizeStringList(readiness.blockers),
    warnings: normalizeStringList(readiness.warnings),
  }
}

function normalizeGate(gate: any, readiness: number, blockers: string[]): DataStudioAssetGate {
  const total = Number(gate?.total ?? 4)
  const passed = Number(gate?.passed ?? Math.max(0, Math.min(total, Math.round((readiness / 100) * total))))
  const normalizedBlockers = normalizeStringList(gate?.blockers).length ? normalizeStringList(gate.blockers) : blockers
  return {
    score: Number(gate?.score ?? readiness),
    passed,
    total,
    blockers: normalizedBlockers,
  }
}

function normalizePublishState(value: unknown, status: unknown, blockerCount: number) {
  const publishState = String(value ?? '').toLowerCase()
  if (['draft', 'validating', 'blocked', 'published', 'archived'].includes(publishState)) {
    return publishState as SemanticModel['publishState']
  }
  const modelStatus = String(status ?? '').toLowerCase()
  if (modelStatus === 'published') return 'published'
  if (modelStatus === 'validating') return 'validating'
  if (blockerCount > 0) return 'blocked'
  return 'draft'
}

function normalizeDataStudioAsset(raw: any, fallback: {
  id: string
  name: string
  description: string
  status: SemanticModel['status']
  publishState: SemanticModel['publishState']
  gate: DataStudioAssetGate
  publishedVersion: string
  consumers: SemanticModel['consumers']
  datasource: string
  validationLog: string[]
}): DataStudioAsset {
  return {
    asset_type: raw?.asset_type === 'dashboard' ? 'dashboard' : 'semantic_model',
    asset_id: String(raw?.asset_id ?? fallback.id),
    name: String(raw?.name ?? fallback.name),
    description: String(raw?.description ?? fallback.description),
    status: raw?.status ?? fallback.status,
    publish_state: normalizePublishState(raw?.publish_state, fallback.status, fallback.gate.blockers.length),
    gate: normalizeGate(raw?.gate, fallback.gate.score, fallback.gate.blockers),
    version: String(raw?.version ?? fallback.publishedVersion),
    consumers: {
      agents: Number(raw?.consumers?.agents ?? fallback.consumers.agents),
      mcp: Number(raw?.consumers?.mcp ?? fallback.consumers.mcp),
      skills: Number(raw?.consumers?.skills ?? fallback.consumers.skills),
      dashboards: Number(raw?.consumers?.dashboards ?? fallback.consumers.dashboards),
      savedQueries: Number(raw?.consumers?.savedQueries ?? fallback.consumers.savedQueries),
    },
    capabilities: normalizeDisplayList(raw?.capabilities, ['semantic query', 'dashboard binding', 'policy evidence']),
    freshness: displayFreshness(raw?.freshness ?? 'Profile refreshed 2h ago'),
    provenance: normalizeDisplayList(raw?.provenance, [fallback.datasource, ...fallback.validationLog.slice(0, 2)]),
    usage_policy: normalizeDisplayList(raw?.usage_policy, ['Certified metrics only', 'PII excluded from semantic consumers']),
    sample_evidence: normalizeDisplayList(raw?.sample_evidence, fallback.validationLog.slice(0, 3)),
  }
}

function normalizeConsumptionEntries(value: unknown): ConsumptionEntry[] {
  if (!Array.isArray(value)) return defaultConsumptionEntries
  const entries = value
    .map(item => ({
      id: item?.id,
      label: displayValue(item?.label),
      before: displayValue(item?.before),
      after: displayValue(item?.after),
    }))
    .filter(item => ['agent', 'dashboard', 'mcp_api', 'share_link'].includes(String(item.id)))
  return entries.length ? entries as ConsumptionEntry[] : defaultConsumptionEntries
}

function normalizeMcpResult(result: any) {
  if (!result || typeof result !== 'object') return undefined
  return {
    resolvedMetric: displayValue(result.resolvedMetric ?? result.resolved_metric),
    modelVersion: displayValue(result.modelVersion ?? result.model_version),
    result: typeof result.result === 'string' ? result.result : JSON.stringify(result.result ?? ''),
    freshness: displayValue(result.freshness),
    lineage: normalizeStringList(result.lineage),
    policyDecision: displayValue(result.policyDecision ?? result.policy_decision),
  }
}

function normalizeStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.map(displayValue).filter(Boolean)
}

function normalizeDisplayList(value: unknown, fallback: string[]): string[] {
  const items = toDisplayList(value)
  return items.length ? items : fallback
}

function toDisplayList(value: unknown): string[] {
  if (value === null || value === undefined) return []
  if (Array.isArray(value)) return value.map(displayValue).filter(Boolean)
  if (typeof value !== 'object') return [displayValue(value)].filter(Boolean)
  const record = value as Record<string, unknown>
  const entries: string[] = []
  const executionModes = normalizeStringList(record.execution_modes)
  entries.push(...executionModes.map(mode => mode.replace(/_/g, ' ')))
  if (record.slug) entries.push(`slug: ${displayValue(record.slug)}`)
  if (record.domain) entries.push(`domain: ${displayValue(record.domain)}`)
  if (record.published_version) entries.push(`version: ${displayValue(record.published_version)}`)
  if (Array.isArray(record.metrics)) entries.push(`${record.metrics.length} metrics`)
  if (Array.isArray(record.dimensions)) entries.push(`${record.dimensions.length} dimensions`)
  if (record.status) entries.push(`status: ${displayValue(record.status)}`)
  if (record.external !== undefined) entries.push(`external: ${displayValue(record.external)}`)
  if (record.rawSqlFallback !== undefined) entries.push(`raw SQL fallback: ${displayValue(record.rawSqlFallback)}`)
  if (record.datasource_id) entries.push(`source: ${displayValue(record.datasource_id)}`)
  if (record.datasource_kind) entries.push(`kind: ${displayValue(record.datasource_kind)}`)
  if (Array.isArray(record.allowedMetrics)) entries.push(`${record.allowedMetrics.length} allowed metrics`)
  if (Array.isArray(record.allowedDimensions)) entries.push(`${record.allowedDimensions.length} allowed dimensions`)
  if (record.kind || record.title || record.definition || record.formula) entries.push(displayValue(record))
  return entries.length ? entries : [displayValue(value)].filter(Boolean)
}

function displayFreshness(value: unknown): string {
  if (!value || typeof value !== 'object') return displayValue(value || 'Profile refreshed 2h ago')
  const record = value as Record<string, unknown>
  const parts = [
    displayValue(record.status),
    record.drift_alerts !== undefined ? `${displayValue(record.drift_alerts)} drift alerts` : '',
    record.updated_at ? `updated ${displayValue(record.updated_at)}` : '',
    record.schema_updated_at ? `schema ${displayValue(record.schema_updated_at)}` : '',
  ].filter(Boolean)
  return parts.length ? parts.join(' · ') : displayValue(value)
}

function displayValue(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) return value.map(displayValue).filter(Boolean).join(', ')
  if (typeof value === 'object') {
    const record = value as Record<string, any>
    if (record.kind && record.title) return `${displayValue(record.kind)}: ${displayValue(record.title)}`
    if (record.status && record.reason) return `${displayValue(record.status)}: ${displayValue(record.reason)}`
    if (record.candidate_type && record.confidence !== undefined) {
      return `${displayValue(record.candidate_type)} evidence (${Math.round(Number(record.confidence) * 100)}% confidence)`
    }
    if (record.table && record.field) return `${displayValue(record.table)}.${displayValue(record.field)}`
    if (record.name) return displayValue(record.name)
    if (record.id) return displayValue(record.id)
    return JSON.stringify(value)
  }
  return String(value)
}

function normalizeKind(value: unknown): DataSourceKind {
  const kind = String(value ?? 'pg')
  if (kind === 'postgres') return 'pg'
  if (['oracle', 'pg', 'mysql', 'sqlite', 'mongo', 'dynamodb', 'databricks'].includes(kind)) return kind as DataSourceKind
  return 'pg'
}

function normalizeCategory(value: unknown): TableCategory {
  const category = String(value ?? 'dimension')
  if (['fact', 'dimension', 'bridge', 'log'].includes(category)) return category as TableCategory
  return 'dimension'
}

function normalizeRole(value: unknown): FieldRole {
  const role = String(value ?? '').toLowerCase()
  if (['id', 'amount', 'time', 'status', 'pii', 'attribute', 'measure'].includes(role)) return role as FieldRole
  if (role.includes('email') || role.includes('phone')) return 'pii'
  if (role.endsWith('_id') || role === 'id') return 'id'
  if (role.includes('date') || role.includes('time')) return 'time'
  if (role.includes('amount') || role.includes('price') || role.includes('revenue')) return 'amount'
  return 'attribute'
}

function hasMeasure(columns: any[]) {
  return columns.some(column => ['amount', 'measure'].includes(normalizeRole(column.role ?? column.name)))
}

function timeRange(columns: any[]) {
  const timeColumn = columns.find(column => normalizeRole(column.role ?? column.name) === 'time')
  if (!timeColumn) return undefined
  return [timeColumn.profile?.min ?? timeColumn.min, timeColumn.profile?.max ?? timeColumn.max].filter(Boolean).join(' - ')
}
