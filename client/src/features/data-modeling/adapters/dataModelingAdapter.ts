import type { HomeDemoMode, SemanticModel } from '../types'
import { ApiService } from '../../../services/api'
import { cloneDemoData } from '../mock/fixtures'

export interface DataModelingAdapter {
  listModels(models: SemanticModel[], mode: HomeDemoMode): Promise<SemanticModel[]>
  getModel(models: SemanticModel[], modelId: string): Promise<SemanticModel | undefined>
  validateModel(model: SemanticModel): Promise<SemanticModel>
  publishModel(model: SemanticModel): Promise<SemanticModel>
  queryMetric(model: SemanticModel): Promise<SemanticModel['mcp']['lastResult']>
}

const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))
const demoDefaults = cloneDemoData().models[0]

function normalizeModel(raw: any, fallback: SemanticModel = demoDefaults): SemanticModel {
  const model = { ...fallback, ...raw } as SemanticModel
  const metrics = Array.isArray(raw?.metrics) && raw.metrics.length ? raw.metrics : fallback.metrics
  const dimensions = Array.isArray(raw?.dimensions) && raw.dimensions.length ? raw.dimensions : fallback.dimensions
  const relationships = Array.isArray(raw?.relationships) ? raw.relationships : fallback.relationships
  const entities = Array.isArray(raw?.entities) && raw.entities.length ? raw.entities : fallback.entities

  return {
    ...model,
    consumers: { ...fallback.consumers, ...(raw?.consumers ?? {}) },
    entities,
    relationships,
    metrics,
    dimensions,
    calculatedFields: Array.isArray(raw?.calculatedFields) ? raw.calculatedFields : fallback.calculatedFields,
    suggestions: Array.isArray(raw?.suggestions) ? raw.suggestions : fallback.suggestions,
    readinessDetail: { ...fallback.readinessDetail, ...(raw?.readinessDetail ?? {}) },
    explore: {
      ...fallback.explore,
      ...(raw?.explore ?? {}),
      metricId: raw?.explore?.metricId ?? metrics[0]?.id ?? fallback.explore.metricId,
      dimensionId: raw?.explore?.dimensionId ?? dimensions[0]?.id ?? fallback.explore.dimensionId,
    },
    review: { ...fallback.review, ...(raw?.review ?? {}) },
    mcp: { ...fallback.mcp, ...(raw?.mcp ?? {}) },
    validationLog: Array.isArray(raw?.validationLog) ? raw.validationLog : fallback.validationLog,
  }
}

export const mockDataModelingAdapter: DataModelingAdapter = {
  async listModels(models, mode) {
    await delay(mode === 'loading' ? 650 : 180)
    if (mode === 'error') {
      throw new Error('Demo adapter failed to load semantic models')
    }
    if (mode === 'permission') {
      throw new Error('Permission required to view Data Models')
    }
    if (mode === 'empty') {
      return []
    }
    try {
      const response = await ApiService.listSemanticModels()
      return response.items.length > 0 ? response.items.map(item => normalizeModel(item)) : models
    } catch {
      return models
    }
  },

  async getModel(models, modelId) {
    await delay(120)
    try {
      const fallback = models.find(model => model.id === modelId) ?? demoDefaults
      return normalizeModel(await ApiService.getSemanticModel(modelId), fallback)
    } catch {
      return models.find(model => model.id === modelId)
    }
  },

  async validateModel(model) {
    const response = await ApiService.validateSemanticModel(model.id)
    return normalizeModel(response, model)
  },

  async publishModel(model) {
    const response = await ApiService.publishSemanticModel(model.id)
    return normalizeModel(response, model)
  },

  async queryMetric(model) {
    const metric = model.metrics.find(item => item.id === model.explore.metricId) ?? model.metrics[0]
    const result = await ApiService.querySemanticMetric(model.id, {
      metric: metric?.id ?? model.explore.metricId,
      dimension: model.explore.dimensionId,
      grain: model.explore.grain,
      time_range: model.explore.timeRange,
    })
    return {
      resolvedMetric: result.resolvedMetric,
      modelVersion: result.modelVersion,
      result: typeof result.result === 'string' ? result.result : JSON.stringify(result.result),
      freshness: result.freshness,
      lineage: result.lineage,
      policyDecision: result.policyDecision,
    }
  },
}
