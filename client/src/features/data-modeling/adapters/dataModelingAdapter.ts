import { ApiService } from '../../../services/api'
import type {
  CreateModelDraft,
  DataSourceProfile,
  ExploreState,
  GenerationStep,
  SemanticModel,
} from '../types'

export interface GenerationJob {
  id: string
  datasource_id: string
  status: 'running' | 'completed' | 'failed'
  phase: 'idle' | 'profile' | 'semantic' | 'validation' | 'completed'
  progress: number
  steps: GenerationStep[]
  result_model_id?: string | null
  error?: string | null
}

export interface DataModelingAdapter {
  listModels(): Promise<SemanticModel[]>
  listProfiles(): Promise<DataSourceProfile[]>
  getModel(modelId: string): Promise<SemanticModel>
  createGenerationJob(draft: CreateModelDraft): Promise<GenerationJob>
  advanceGenerationJob(jobId: string): Promise<GenerationJob>
  updateRelationship(modelId: string, relationshipId: string, patch: Record<string, unknown>): Promise<SemanticModel>
  fixFanoutRelationship(modelId: string, relationshipId: string): Promise<SemanticModel>
  rejectRelationship(modelId: string, relationshipId: string): Promise<SemanticModel>
  updateMetric(modelId: string, metricId: string, patch: Record<string, unknown>): Promise<SemanticModel>
  updateExplore(modelId: string, patch: Partial<ExploreState>): Promise<SemanticModel>
  saveExploreArtifact(modelId: string, kind: 'query' | 'dashboard' | 'skill' | 'example'): Promise<SemanticModel>
  updateSuggestion(modelId: string, suggestionId: string, action: 'accepted' | 'edited' | 'rejected'): Promise<SemanticModel>
  validateModel(modelId: string): Promise<SemanticModel>
  openReview(modelId: string): Promise<SemanticModel>
  markReviewed(modelId: string): Promise<SemanticModel>
  updatePublishNotes(modelId: string, notes: string): Promise<SemanticModel>
  publishModel(modelId: string): Promise<SemanticModel>
  setRawSqlFallback(modelId: string, enabled: boolean): Promise<SemanticModel>
  runMcpQuery(modelId: string, payload: Record<string, unknown>): Promise<SemanticModel>
}

function normalizeGenerationJob(job: any): GenerationJob {
  return {
    id: String(job.id),
    datasource_id: String(job.datasource_id),
    status: job.status,
    phase: job.phase,
    progress: Number(job.progress ?? 0),
    steps: Array.isArray(job.steps) ? job.steps : [],
    result_model_id: job.result_model_id ?? null,
    error: job.error ?? null,
  }
}

export const dataModelingAdapter: DataModelingAdapter = {
  async listModels() {
    const data = await ApiService.listDataModels()
    return data.items ?? []
  },

  async listProfiles() {
    const data = await ApiService.listDataModelProfiles()
    return data.items ?? []
  },

  async getModel(modelId) {
    return ApiService.getDataModel(modelId)
  },

  async createGenerationJob(draft) {
    const job = await ApiService.createDataModelGenerationJob({
      datasource_id: draft.datasourceId,
      domain: draft.domain,
      selected_tables: draft.selectedTables,
      business_questions: draft.businessQuestions,
    })
    return normalizeGenerationJob(job)
  },

  async advanceGenerationJob(jobId) {
    return normalizeGenerationJob(await ApiService.advanceDataModelGenerationJob(jobId))
  },

  async updateRelationship(modelId, relationshipId, patch) {
    return ApiService.updateDataModelRelationship(modelId, relationshipId, patch)
  },

  async fixFanoutRelationship(modelId, relationshipId) {
    return ApiService.fixDataModelRelationshipFanout(modelId, relationshipId)
  },

  async rejectRelationship(modelId, relationshipId) {
    return ApiService.rejectDataModelRelationship(modelId, relationshipId)
  },

  async updateMetric(modelId, metricId, patch) {
    return ApiService.updateDataModelMetric(modelId, metricId, patch)
  },

  async updateExplore(modelId, patch) {
    return ApiService.updateDataModelExplore(modelId, patch)
  },

  async saveExploreArtifact(modelId, kind) {
    return ApiService.saveDataModelExploreArtifact(modelId, kind)
  },

  async updateSuggestion(modelId, suggestionId, action) {
    return ApiService.updateDataModelSuggestion(modelId, suggestionId, action)
  },

  async validateModel(modelId) {
    return ApiService.validateDataModel(modelId)
  },

  async openReview(modelId) {
    return ApiService.openDataModelReview(modelId)
  },

  async markReviewed(modelId) {
    return ApiService.markDataModelReviewed(modelId)
  },

  async updatePublishNotes(modelId, notes) {
    return ApiService.updateDataModelPublishNotes(modelId, notes)
  },

  async publishModel(modelId) {
    return ApiService.publishDataModel(modelId)
  },

  async setRawSqlFallback(modelId, enabled) {
    return ApiService.setDataModelRawSqlFallback(modelId, enabled)
  },

  async runMcpQuery(modelId, payload) {
    return ApiService.runDataModelMcpQueryMetric(modelId, payload)
  },
}
