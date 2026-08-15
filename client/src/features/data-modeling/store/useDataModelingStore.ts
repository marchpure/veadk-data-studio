import { create } from 'zustand'
import { dataModelingAdapter, type GenerationJob } from '../adapters/dataModelingAdapter'
import type {
  CertificationStatus,
  CreateModelDraft,
  DataSourceProfile,
  ExploreResult,
  ExploreState,
  HomeStateMode,
  Metric,
  Relationship,
  SemanticGenerationState,
  SemanticModel,
  WorkspaceMode,
} from '../types'

interface DataModelingStore {
  models: SemanticModel[]
  profiles: DataSourceProfile[]
  createDraft: CreateModelDraft
  activeModelId: string
  selectedObjectId: string
  workspaceMode: WorkspaceMode
  selectedProfileTable: string
  selectedProfileField: string
  generation: SemanticGenerationState
  generationJobId: string
  homeMode: HomeStateMode
  homeLoading: boolean
  homeError: string | null
  visibleModels: SemanticModel[]
  operationError: string | null
  loadModels: (mode?: HomeStateMode) => Promise<void>
  loadModel: (modelId: string) => Promise<void>
  setHomeMode: (mode: HomeStateMode) => void
  refreshWorkspace: () => void
  setActiveModel: (modelId: string) => void
  selectObject: (objectId: string) => void
  setWorkspaceMode: (mode: WorkspaceMode) => void
  selectProfileTable: (tableName: string) => void
  selectProfileField: (fieldName: string) => void
  updateCreateDraft: (patch: Partial<CreateModelDraft>) => void
  toggleCreateTable: (tableName: string) => void
  startSemanticGeneration: () => void
  advanceSemanticGeneration: () => void
  generateDraft: () => void
  acceptSuggestion: (suggestionId: string) => void
  editAcceptSuggestion: (suggestionId: string) => void
  rejectSuggestion: (suggestionId: string) => void
  updateRelationship: (relationshipId: string, patch: Partial<Relationship>) => void
  fixFanoutRelationship: (relationshipId: string) => void
  rejectRelationship: (relationshipId: string) => void
  updateMetric: (metricId: string, patch: Partial<Metric>) => void
  setMetricCertification: (metricId: string, certification: CertificationStatus) => void
  updateExplore: (patch: Partial<ExploreState>) => void
  saveExploreArtifact: (kind: 'query' | 'dashboard' | 'skill' | 'example') => void
  validateModel: () => void
  openReview: () => void
  updatePublishNotes: (notes: string) => void
  markReviewed: () => void
  publishModel: () => void
  setRawSqlFallback: (enabled: boolean) => void
  runMcpQuery: () => void
}

const emptyGeneration: SemanticGenerationState = {
  phase: 'idle',
  progress: 0,
  steps: [],
  summary: [],
}

const initialDraft: CreateModelDraft = {
  datasourceId: 'oracle-sales',
  domain: 'Sales / Orders',
  selectedTables: ['ORDERS', 'ORDER_ITEMS', 'CUSTOMERS', 'PRODUCTS', 'STORES'],
  businessQuestions: 'How did paid revenue, order volume, refund rate, and store attainment change by region and product category?',
  generated: false,
}

function activeModel(state: DataModelingStore) {
  return state.models.find(model => model.id === state.activeModelId) ?? state.models[0]
}

function modelPatch(model: SemanticModel) {
  return (state: DataModelingStore) => ({
    models: state.models.some(item => item.id === model.id)
      ? state.models.map(item => item.id === model.id ? model : item)
      : [model, ...state.models],
    visibleModels: state.visibleModels.some(item => item.id === model.id)
      ? state.visibleModels.map(item => item.id === model.id ? model : item)
      : [model, ...state.visibleModels],
    activeModelId: model.id,
    operationError: null,
  })
}

function generationFromJob(job: GenerationJob): SemanticGenerationState {
  const summary = job.status === 'completed'
    ? ['Generated 5 metrics.', 'Generated 7 dimensions.', 'Validated relationships.', 'Prepared Explore defaults.']
    : []
  return {
    phase: job.phase,
    progress: job.progress,
    steps: job.steps,
    summary,
  }
}

function runAction(get: () => DataModelingStore, set: (patch: Partial<DataModelingStore> | ((state: DataModelingStore) => Partial<DataModelingStore>)) => void, action: () => Promise<void>) {
  void action().catch(error => {
    const message = error instanceof Error ? error.message : 'Data Model operation failed'
    set({ operationError: message, homeError: message })
  })
}

export const useDataModelingStore = create<DataModelingStore>()((set, get) => ({
  models: [],
  profiles: [],
  createDraft: initialDraft,
  activeModelId: 'sales-growth',
  selectedObjectId: '',
  workspaceMode: 'explore',
  selectedProfileTable: 'ORDERS',
  selectedProfileField: 'NET_AMOUNT',
  generation: emptyGeneration,
  generationJobId: '',
  homeMode: 'ready',
  homeLoading: false,
  homeError: null,
  visibleModels: [],
  operationError: null,

  async loadModels(mode = get().homeMode) {
    set({ homeMode: mode, homeLoading: true, homeError: null, operationError: null })
    try {
      const [models, profiles] = await Promise.all([
        dataModelingAdapter.listModels(),
        dataModelingAdapter.listProfiles(),
      ])
      const visibleModels = mode === 'empty' ? [] : models
      if (mode === 'error') {
        throw new Error('Unable to load Data Models')
      }
      if (mode === 'permission') {
        throw new Error('Permission required to view Data Models')
      }
      const defaultProfile = profiles[0]
      set(state => ({
        models,
        profiles,
        visibleModels,
        activeModelId: state.activeModelId || models[0]?.id || 'sales-growth',
        createDraft: {
          ...state.createDraft,
          datasourceId: state.createDraft.datasourceId || defaultProfile?.id || 'oracle-sales',
          selectedTables: state.createDraft.selectedTables.length ? state.createDraft.selectedTables : defaultProfile?.tables.slice(0, 5).map(table => table.name) ?? [],
        },
        selectedProfileTable: state.selectedProfileTable || defaultProfile?.tables[0]?.name || 'ORDERS',
        selectedProfileField: state.selectedProfileField || defaultProfile?.tables[0]?.fields[0]?.name || 'NET_AMOUNT',
        homeLoading: false,
        homeError: null,
      }))
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to load Data Models'
      set({ visibleModels: [], homeLoading: false, homeError: message })
    }
  },

  async loadModel(modelId) {
    const model = await dataModelingAdapter.getModel(modelId)
    set(modelPatch(model))
  },

  setHomeMode(mode) {
    void get().loadModels(mode)
  },

  refreshWorkspace() {
    set({ generation: emptyGeneration, generationJobId: '', operationError: null })
    void get().loadModels('ready')
  },

  setActiveModel(modelId) {
    set({ activeModelId: modelId, selectedObjectId: '', workspaceMode: 'explore' })
    void get().loadModel(modelId)
  },

  selectObject(objectId) {
    set({ selectedObjectId: objectId })
  },

  setWorkspaceMode(mode) {
    set(state => ({
      workspaceMode: mode,
      selectedObjectId: mode === 'explore' ? '' : state.selectedObjectId,
    }))
  },

  selectProfileTable(tableName) {
    const profile = get().profiles.find(item => item.id === get().createDraft.datasourceId) ?? get().profiles[0]
    const table = profile?.tables.find(item => item.name === tableName)
    set({
      selectedProfileTable: tableName,
      selectedProfileField: table?.fields[0]?.name ?? get().selectedProfileField,
    })
  },

  selectProfileField(fieldName) {
    set({ selectedProfileField: fieldName })
  },

  updateCreateDraft(patch) {
    set(state => ({ createDraft: { ...state.createDraft, ...patch } }))
  },

  toggleCreateTable(tableName) {
    set(state => {
      const selected = state.createDraft.selectedTables.includes(tableName)
        ? state.createDraft.selectedTables.filter(name => name !== tableName)
        : [...state.createDraft.selectedTables, tableName]
      return { createDraft: { ...state.createDraft, selectedTables: selected } }
    })
  },

  startSemanticGeneration() {
    runAction(get, set, async () => {
      const job = await dataModelingAdapter.createGenerationJob(get().createDraft)
      set({ generationJobId: job.id, generation: generationFromJob(job), operationError: null })
    })
  },

  advanceSemanticGeneration() {
    runAction(get, set, async () => {
      const jobId = get().generationJobId
      const job = jobId ? await dataModelingAdapter.advanceGenerationJob(jobId) : await dataModelingAdapter.createGenerationJob(get().createDraft)
      const generation = generationFromJob(job)
      if (job.status === 'completed' && job.result_model_id) {
        const model = await dataModelingAdapter.getModel(job.result_model_id)
        set(state => ({
          ...modelPatch(model)(state),
          generationJobId: job.id,
          generation,
          createDraft: { ...state.createDraft, generated: true },
          operationError: null,
        }))
        return
      }
      set(state => ({
        generationJobId: job.id,
        generation,
        createDraft: { ...state.createDraft, generated: job.status === 'completed' },
        operationError: null,
      }))
    })
  },

  generateDraft() {
    get().advanceSemanticGeneration()
  },

  acceptSuggestion(suggestionId) {
    runAction(get, set, async () => {
      const model = await dataModelingAdapter.updateSuggestion(activeModel(get()).id, suggestionId, 'accepted')
      set(modelPatch(model))
    })
  },

  editAcceptSuggestion(suggestionId) {
    runAction(get, set, async () => {
      const model = await dataModelingAdapter.updateSuggestion(activeModel(get()).id, suggestionId, 'edited')
      set(modelPatch(model))
    })
  },

  rejectSuggestion(suggestionId) {
    runAction(get, set, async () => {
      const model = await dataModelingAdapter.updateSuggestion(activeModel(get()).id, suggestionId, 'rejected')
      set(modelPatch(model))
    })
  },

  updateRelationship(relationshipId, patch) {
    runAction(get, set, async () => {
      const model = await dataModelingAdapter.updateRelationship(activeModel(get()).id, relationshipId, patch)
      set(modelPatch(model))
    })
  },

  fixFanoutRelationship(relationshipId) {
    runAction(get, set, async () => {
      const model = await dataModelingAdapter.fixFanoutRelationship(activeModel(get()).id, relationshipId)
      set(modelPatch(model))
    })
  },

  rejectRelationship(relationshipId) {
    runAction(get, set, async () => {
      const model = await dataModelingAdapter.rejectRelationship(activeModel(get()).id, relationshipId)
      set(modelPatch(model))
    })
  },

  updateMetric(metricId, patch) {
    runAction(get, set, async () => {
      const model = await dataModelingAdapter.updateMetric(activeModel(get()).id, metricId, patch)
      set(modelPatch(model))
    })
  },

  setMetricCertification(metricId, certification) {
    get().updateMetric(metricId, { certification })
  },

  updateExplore(patch) {
    runAction(get, set, async () => {
      const model = await dataModelingAdapter.updateExplore(activeModel(get()).id, patch)
      set(modelPatch(model))
    })
  },

  saveExploreArtifact(kind) {
    runAction(get, set, async () => {
      const model = await dataModelingAdapter.saveExploreArtifact(activeModel(get()).id, kind)
      set(modelPatch(model))
    })
  },

  validateModel() {
    runAction(get, set, async () => {
      const model = await dataModelingAdapter.validateModel(activeModel(get()).id)
      set(modelPatch(model))
    })
  },

  openReview() {
    runAction(get, set, async () => {
      const model = await dataModelingAdapter.openReview(activeModel(get()).id)
      set(modelPatch(model))
    })
  },

  updatePublishNotes(notes) {
    runAction(get, set, async () => {
      const model = await dataModelingAdapter.updatePublishNotes(activeModel(get()).id, notes)
      set(modelPatch(model))
    })
  },

  markReviewed() {
    runAction(get, set, async () => {
      const model = await dataModelingAdapter.markReviewed(activeModel(get()).id)
      set(modelPatch(model))
    })
  },

  publishModel() {
    runAction(get, set, async () => {
      const model = await dataModelingAdapter.publishModel(activeModel(get()).id)
      set(modelPatch(model))
    })
  },

  setRawSqlFallback(enabled) {
    runAction(get, set, async () => {
      const model = await dataModelingAdapter.setRawSqlFallback(activeModel(get()).id, enabled)
      set(modelPatch(model))
    })
  },

  runMcpQuery() {
    runAction(get, set, async () => {
      const model = activeModel(get())
      const next = await dataModelingAdapter.runMcpQuery(model.id, {
        metric: model.explore.metricId,
        dimension: model.explore.dimensionId,
        grain: model.explore.grain,
        time_range: model.explore.timeRange,
      })
      set(modelPatch(next))
    })
  },
}))

export function selectActiveModel(state: DataModelingStore) {
  return state.models.find(model => model.id === state.activeModelId) ?? state.models[0]
}

export function selectExploreResult(model: SemanticModel): ExploreResult {
  const metric = model.metrics.find(item => item.id === model.explore.metricId) ?? model.metrics[0]
  const dimension = model.dimensions.find(item => item.id === model.explore.dimensionId) ?? model.dimensions[0]
  const base = metric?.id.length ?? 8
  const dim = dimension?.id.length ?? 6
  const rangeFactor = model.explore.timeRange === '30d' ? 0.86 : model.explore.timeRange === 'ytd' ? 1.18 : model.explore.timeRange === '12m' ? 1.32 : 1
  const trend = Array.from({ length: 8 }, (_, index) => ({
    period: `${model.explore.grain.slice(0, 1).toUpperCase()}${index + 1}`,
    value: Math.round((68 + base * 3 + dim * 2 + index * (4 + (base % 5))) * rangeFactor),
  }))
  const rows = (metric?.preview.breakdown ?? []).map((row, index) => ({
    [dimension?.name ?? 'Dimension']: row.label,
    [metric?.businessName ?? 'Metric']: row.value,
    delta: row.delta,
    rank: index + 1,
  }))
  return {
    kpi: metric?.preview.currentValue ?? '-',
    delta: metric?.preview.trend ?? '-',
    trend,
    rows,
  }
}
