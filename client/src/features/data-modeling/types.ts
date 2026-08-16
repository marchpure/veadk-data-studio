import type { SourceOverviewFamily } from '../../services/api'

export type DataSourceKind = 'oracle' | 'postgres' | 'pg' | 'mysql' | 'sqlite' | 'mongo' | 'dynamodb' | 'databricks' | 'file' | 'document' | 'web' | 'object_storage' | 'api' | 'unknown'
export type ModelStatus = 'Draft' | 'Validating' | 'Validation Failed' | 'Ready for Review' | 'Published' | 'Rejected'
export type ReadinessLevel = 'ready' | 'warning' | 'blocked'
export type TableCategory = 'fact' | 'dimension' | 'bridge' | 'log'
export type FieldRole = 'id' | 'amount' | 'time' | 'status' | 'pii' | 'attribute' | 'measure'
export type SuggestionStatus = 'pending' | 'accepted' | 'edited' | 'rejected'
export type ValidationStatus = 'valid' | 'warning' | 'blocked'
export type RelationshipStatus = 'confirmed' | 'candidate' | 'rejected'
export type Cardinality = 'many-to-one' | 'one-to-many' | 'one-to-one' | 'many-to-many'
export type MetricKind = 'measure' | 'derived_metric'
export type CertificationStatus = 'draft' | 'reviewed' | 'certified'
export type WorkspaceMode = 'explore' | 'model' | 'publish'
export type ExploreViewMode = 'trend' | 'table' | 'pivot'
export type TimeGrain = 'day' | 'week' | 'month' | 'quarter'
export type HomeViewMode = 'ready' | 'loading' | 'error' | 'empty' | 'permission'
export type GenerationPhase = 'idle' | 'profile' | 'semantic' | 'validation' | 'completed'
export type GenerationStepStatus = 'pending' | 'running' | 'done'
export type DataModelingStatus =
  | 'supported'
  | 'needs_projection'
  | 'context_only'
  | 'permission_required'
  | 'reauthorization_required'
  | 'source_unavailable'
  | 'processing'
  | 'failed'
  | 'planned'
  | 'unsupported'
export type DataModelingMode = 'relational' | 'warehouse' | 'projection' | 'document_projection' | 'context_assisted' | 'business_object' | 'event' | 'semantic_import'

export interface DataModelingDatasource {
  id: string
  name: string
  kind: DataSourceKind
  sourceType: 'connection' | 'dataset' | 'source_resource'
  status?: string
  modelingStatus: DataModelingStatus
  modelingMode?: DataModelingMode
  reason?: string
  evidenceSummary?: string
  nextActions: string[]
  sourceFamily: SourceOverviewFamily
  provider?: string
  canLoadProfile: boolean
  projectedDatasetId?: string | null
  sourceResourceId?: string | null
  contextIndexStatus?: string
  parseStatus?: string
}

export interface ModelConsumers {
  agents: number
  mcp: number
  skills: number
  dashboards: number
  savedQueries: number
}

export interface SemanticModelSummary {
  id: string
  name: string
  domain: string
  owner: string
  datasource: string
  status: ModelStatus
  revision: number
  draftRevision: string
  publishedVersion: string
  readiness: number
  readinessLevel: ReadinessLevel
  driftAlerts: number
  consumers: ModelConsumers
  updatedAt: string
}

export interface ProfileField {
  name: string
  type: string
  role: FieldRole
  nullable: boolean
  nullRate: number
  distinctCount: number
  min?: string | number
  max?: string | number
  topValues: Array<{ value: string; count: number }>
  pii: boolean
}

export interface ProfileTable {
  name: string
  label: string
  category: TableCategory
  rowCount: number
  timeRange?: string
  fields: ProfileField[]
  sampleRows: Array<Record<string, string | number>>
}

export interface DataSourceProfile {
  id: string
  name: string
  kind: DataSourceKind
  schema: string
  status: 'ready' | 'partial' | 'stale' | 'error'
  profileCoverage: number
  tables: ProfileTable[]
}

export interface EvidenceItem {
  label: string
  detail: string
}

export interface AgentSuggestion {
  id: string
  type: 'entity' | 'relationship' | 'metric' | 'dimension' | 'policy'
  title: string
  recommendation: string
  confidence: number
  evidence: EvidenceItem[]
  validation: string
  status: SuggestionStatus
  editedNote?: string
}

export interface EntityField {
  name: string
  sourceField: string
  type: string
  role: FieldRole
}

export interface Entity {
  id: string
  name: string
  businessName: string
  table: string
  description: string
  primaryKey: string
  fields: EntityField[]
}

export interface Relationship {
  id: string
  fromEntity: string
  toEntity: string
  label: string
  joinFields: Array<{ from: string; to: string }>
  cardinality: Cardinality
  fkEvidence: string
  uniqueRate: number
  orphanRate: number
  fanoutRisk: 'low' | 'medium' | 'high'
  validationStatus: ValidationStatus
  status: RelationshipStatus
  validationMessage: string
}

export interface Dimension {
  id: string
  name: string
  entityId: string
  field: string
  description: string
}

export interface CalculatedField {
  id: string
  name: string
  entityId: string
  expression: string
  description: string
}

export interface MetricPreview {
  currentValue: string
  trend: string
  breakdown: Array<{ label: string; value: string; delta: string }>
  explanation: string
  sql: string
  validation: string
}

export interface Metric {
  id: string
  name: string
  businessName: string
  definition: string
  kind: MetricKind
  formula: string
  filter: string
  timeField: string
  defaultGrain: TimeGrain
  dimensions: string[]
  unit: string
  owner: string
  certification: CertificationStatus
  lineage: string[]
  preview: MetricPreview
}

export interface ReadinessComponent {
  id: string
  name: string
  score: number
  status: ReadinessLevel
}

export interface Readiness {
  score: number
  level: ReadinessLevel
  components: ReadinessComponent[]
  reliableQuestions: string[]
  unreliableQuestions: string[]
  blockers: string[]
  warnings: string[]
}

export interface ExploreState {
  metricId: string
  dimensionId: string
  grain: TimeGrain
  timeRange: '30d' | '90d' | 'ytd' | '12m'
  filter: string
  viewMode: ExploreViewMode
  savedQueryCount: number
  dashboardAdds: number
  skillDrafts: number
  confirmedExamples: number
}

export interface ExploreResult {
  kpi: string
  delta: string
  trend: Array<{ period: string; value: number }>
  rows: Array<Record<string, string | number>>
}

export interface ReviewState {
  opened: boolean
  reviewed: boolean
  publishNotes: string
  publishedAt?: string
}

export interface McpState {
  exposedVersion: string
  consumerIdentity: string
  rawSqlFallback: boolean
  allowedMetrics: string[]
  allowedDimensions: string[]
  lastResult?: {
    resolvedMetric: string
    modelVersion: string
    result: string
    freshness: string
    lineage: string[]
    policyDecision: string
  }
}

export interface SemanticModel extends SemanticModelSummary {
  description: string
  datasourceId: string
  entities: Entity[]
  relationships: Relationship[]
  metrics: Metric[]
  dimensions: Dimension[]
  calculatedFields: CalculatedField[]
  suggestions: AgentSuggestion[]
  readinessDetail: Readiness
  explore: ExploreState
  review: ReviewState
  mcp: McpState
  validationLog: string[]
}

export interface CreateModelDraft {
  datasourceId: string
  domain: string
  selectedTables: string[]
  businessQuestions: string
  generated: boolean
}

export interface GenerationStep {
  id: string
  title: string
  detail: string
  status: GenerationStepStatus
}

export interface SemanticGenerationState {
  phase: GenerationPhase
  progress: number
  steps: GenerationStep[]
  summary: string[]
  error: string | null
}

export interface DataModelingWorkspaceData {
  models: SemanticModel[]
  profiles: DataSourceProfile[]
  createDraft: CreateModelDraft
  activeModelId: string
  selectedObjectId: string
  workspaceMode: WorkspaceMode
  selectedProfileTable: string
  selectedProfileField: string
  generation: SemanticGenerationState
}
