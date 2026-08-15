import { ApiService, type Datasource, type SourceSkillCandidate, type SourceUnderstanding } from '../../../services/api'
import type {
  AgentSuggestion,
  DataModelingDatasource,
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
  return {
    id: String(raw?.id ?? ''),
    name: String(raw?.name ?? 'Untitled Semantic Model'),
    domain: String(raw?.domain ?? 'Unassigned'),
    owner: String(raw?.owner ?? 'Data Team'),
    datasource: String(raw?.datasource ?? raw?.datasourceName ?? 'Unknown datasource'),
    datasourceId: String(raw?.datasourceId ?? ''),
    status: raw?.status ?? 'Draft',
    revision: Number(raw?.revision ?? 1),
    draftRevision: String(raw?.draftRevision ?? 'draft-1'),
    publishedVersion: String(raw?.publishedVersion ?? 'v0'),
    readiness: Number(raw?.readiness ?? 0),
    readinessLevel: raw?.readinessLevel ?? 'blocked',
    driftAlerts: Number(raw?.driftAlerts ?? 0),
    consumers: {
      agents: Number(raw?.consumers?.agents ?? 0),
      mcp: Number(raw?.consumers?.mcp ?? 0),
      skills: Number(raw?.consumers?.skills ?? 0),
      dashboards: Number(raw?.consumers?.dashboards ?? 0),
      savedQueries: Number(raw?.consumers?.savedQueries ?? 0),
    },
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
    readinessDetail: normalizeReadiness(raw?.readinessDetail),
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
  }
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
    const response = await ApiService.listAllDatasources()
    return response.items
      .filter(item => ['oracle', 'postgres', 'pg', 'mysql', 'sqlite'].includes(String(item.database_type ?? item.db_type ?? item.type)))
      .map(item => ({
        id: item.id,
        name: item.name,
        kind: normalizeKind(item.database_type ?? item.db_type ?? item.type),
        sourceType: item.source_type,
        status: item.status,
      }))
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

function displayValue(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) return value.map(displayValue).filter(Boolean).join(', ')
  if (typeof value === 'object') {
    const record = value as Record<string, any>
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
  if (['oracle', 'pg', 'mysql', 'sqlite'].includes(kind)) return kind as DataSourceKind
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
