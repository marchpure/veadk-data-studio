import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { dataModelingAdapter } from '../adapters/dataModelingAdapter'
import type {
  CertificationStatus,
  CreateModelDraft,
  DataModelingDatasource,
  DataModelingWorkspaceData,
  ExploreState,
  ExploreResult,
  HomeViewMode,
  Metric,
  Relationship,
  SemanticModel,
  WorkspaceMode,
} from '../types'

interface DataModelingStore extends DataModelingWorkspaceData {
  homeMode: HomeViewMode
  homeLoading: boolean
  homeError: string | null
  datasourceOptions: DataModelingDatasource[]
  datasourceLoading: boolean
  datasourceError: string | null
  visibleModels: SemanticModel[]
  loadModels: (mode?: HomeViewMode) => Promise<void>
  loadModel: (modelId: string) => Promise<void>
  setHomeMode: (mode: HomeViewMode) => void
  reloadWorkspace: () => void
  loadDatasources: () => Promise<void>
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
  validateModel: () => Promise<void>
  openReview: () => void
  updatePublishNotes: (notes: string) => void
  markReviewed: () => void
  publishModel: () => Promise<void>
  setRawSqlFallback: (enabled: boolean) => void
  runMcpQuery: () => Promise<void>
}

const emptyData: DataModelingWorkspaceData = {
  models: [],
  profiles: [],
  createDraft: {
    datasourceId: '',
    domain: '',
    selectedTables: [],
    businessQuestions: '',
    generated: false,
  },
  activeModelId: '',
  selectedObjectId: '',
  workspaceMode: 'explore',
  selectedProfileTable: '',
  selectedProfileField: '',
  generation: {
    phase: 'idle',
    progress: 0,
    steps: [
      { id: 'profile', title: 'Read schema and profile', detail: 'Load live datasource schema and table profile evidence.', status: 'pending' },
      { id: 'candidates', title: 'Generate candidates', detail: 'Create entity, relationship, metric, and dimension suggestions from Source Understanding.', status: 'pending' },
      { id: 'review', title: 'Require human review', detail: 'Agent output remains draft suggestions until source candidates are explicitly verified.', status: 'pending' },
      { id: 'draft', title: 'Create semantic draft', detail: 'Persist a draft from already verified Source Understanding candidates.', status: 'pending' },
    ],
    summary: [],
  },
}

function currentModel(state: DataModelingStore) {
  return state.models.find(model => model.id === state.activeModelId) ?? state.models[0]
}

function updateModel(state: DataModelingStore, updater: (model: SemanticModel) => SemanticModel): Partial<DataModelingStore> {
  const activeId = state.activeModelId

  return {
    models: state.models.map(model => model.id === activeId ? updater(model) : model),
    visibleModels: state.visibleModels.map(model => model.id === activeId ? updater(model) : model),
  }
}

function replaceModel(state: DataModelingStore, incoming: SemanticModel): Partial<DataModelingStore> {
  return {
    models: mergeModels(state.models, [incoming]),
    visibleModels: mergeModels(state.visibleModels, [incoming]),
    activeModelId: incoming.id,
  }
}

function rollbackModel(state: DataModelingStore, previous: SemanticModel): Partial<DataModelingStore> {
  return {
    models: state.models.map(model => model.id === previous.id ? previous : model),
    visibleModels: state.visibleModels.map(model => model.id === previous.id ? previous : model),
  }
}

let modelPatchQueue: Promise<void> = Promise.resolve()

function saveModelPatch(
  set: (partial: Partial<DataModelingStore> | ((state: DataModelingStore) => Partial<DataModelingStore>)) => void,
  get: () => DataModelingStore,
  before: SemanticModel,
  patch: Partial<SemanticModel>,
  errorMessage: string,
) {
  const modelId = before.id
  const task = modelPatchQueue.then(async () => {
    const latest = await dataModelingAdapter.getModel(modelId)
    const saved = await dataModelingAdapter.patchModel(latest, patch)
    set(state => ({
      ...replaceModel(state, saved),
      homeError: null,
    }))
  }).catch(error => {
    const activeModel = currentModel(get())
    set(state => ({
      ...(activeModel?.id === modelId ? rollbackModel(state, before) : {}),
      homeError: error instanceof Error ? error.message : errorMessage,
    }))
  })
  modelPatchQueue = task.then(() => undefined, () => undefined)
  return task
}

async function flushModelPatches() {
  await modelPatchQueue
}

function generationProgressFor(index: number, total: number) {
  return Math.min(96, Math.round(((index + 1) / total) * 100))
}

export const useDataModelingStore = create<DataModelingStore>()(
  persist(
    (set, get) => ({
      ...emptyData,
      homeMode: 'ready',
      homeLoading: false,
      homeError: null,
      datasourceOptions: [],
      datasourceLoading: false,
      datasourceError: null,
      visibleModels: [],

      async loadModels(mode = get().homeMode) {
        set({ homeMode: mode, homeLoading: true, homeError: null })
        try {
          if (mode === 'loading') await new Promise(resolve => setTimeout(resolve, 500))
          if (mode === 'error') throw new Error('Unable to load Data Models')
          if (mode === 'permission') throw new Error('Permission required to view Data Models')
          const visibleModels = mode === 'empty' ? [] : await dataModelingAdapter.listModels()
          const mergedModels = visibleModels
          const activeModelId = mergedModels.some(model => model.id === get().activeModelId)
            ? get().activeModelId
            : mergedModels[0]?.id || ''
          set({ models: mergedModels, visibleModels, activeModelId, homeLoading: false, homeError: null })
        } catch (error) {
          const message = error instanceof Error ? error.message : 'Unable to load Data Models'
          set({ visibleModels: [], homeLoading: false, homeError: message })
        }
      },

      async loadModel(modelId) {
        try {
          const model = await dataModelingAdapter.getModel(modelId)
          if (!model) return
          set(state => {
            const models = mergeModels(state.models, [model])
            return {
              models,
              visibleModels: mergeModels(state.visibleModels, [model]),
              activeModelId: model.id,
            }
          })
        } catch (error) {
          const message = error instanceof Error ? error.message : 'Unable to load Data Model'
          set({ homeError: message })
        }
      },

      setHomeMode(mode) {
        void get().loadModels(mode)
      },

      reloadWorkspace() {
        set({ ...emptyData, homeMode: 'ready', homeLoading: false, homeError: null, visibleModels: [] })
        void get().loadModels('ready')
        void get().loadDatasources()
      },

      async loadDatasources() {
        set({ datasourceLoading: true, datasourceError: null })
        try {
          const datasourceOptions = await dataModelingAdapter.listDatasources()
          const selected = get().createDraft.datasourceId
          const nextDatasourceId = selected && datasourceOptions.some(item => item.id === selected)
            ? selected
            : datasourceOptions[0]?.id ?? ''
          set(state => ({
            datasourceOptions,
            datasourceLoading: false,
            datasourceError: null,
            createDraft: { ...state.createDraft, datasourceId: nextDatasourceId },
          }))
          if (nextDatasourceId) {
            get().updateCreateDraft({ datasourceId: nextDatasourceId })
          }
        } catch (error) {
          set({
            datasourceOptions: [],
            datasourceLoading: false,
            datasourceError: error instanceof Error ? error.message : 'Unable to load datasources',
          })
        }
      },

      setActiveModel(modelId) {
        set({ activeModelId: modelId, selectedObjectId: '', workspaceMode: 'explore' })
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
        set(state => {
          const profile = state.profiles.find(item => item.id === state.createDraft.datasourceId) ?? state.profiles[0]
          const table = profile?.tables.find(item => item.name === tableName)
          return {
            selectedProfileTable: tableName,
            selectedProfileField: table?.fields[0]?.name ?? state.selectedProfileField,
          }
        })
      },

      selectProfileField(fieldName) {
        set({ selectedProfileField: fieldName })
      },

      updateCreateDraft(patch) {
        set(state => ({ createDraft: { ...state.createDraft, ...patch } }))
        if (patch.datasourceId) {
          void dataModelingAdapter.loadProfile(patch.datasourceId).then(profile => {
            set(state => ({
              profiles: mergeProfiles(state.profiles, [profile]),
              selectedProfileTable: profile.tables[0]?.name ?? '',
              selectedProfileField: profile.tables[0]?.fields[0]?.name ?? '',
              createDraft: {
                ...state.createDraft,
                selectedTables: state.createDraft.selectedTables.length ? state.createDraft.selectedTables : profile.tables.slice(0, 5).map(table => table.name),
              },
            }))
          }).catch(error => {
            set({ homeError: error instanceof Error ? error.message : 'Unable to load datasource profile' })
          })
        }
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
        set(state => ({
          generation: {
            ...state.generation,
            phase: 'profile',
            progress: generationProgressFor(0, state.generation.steps.length),
            steps: state.generation.steps.map((step, index) => ({
              ...step,
              status: index === 0 ? 'running' : 'pending',
            })),
            summary: [],
          },
        }))
        const draft = get().createDraft
        if (!draft.datasourceId) {
          set(state => ({
            homeError: 'Choose a datasource before generating a Semantic Model.',
            generation: { ...state.generation, phase: 'idle', progress: 0 },
          }))
          return
        }
        void (async () => {
          try {
            const understanding = await dataModelingAdapter.analyzeDatasource(draft.datasourceId, draft.selectedTables)
            const relevantCandidates = understanding.candidates.filter(candidate => ['schema_map', 'relationship', 'data_truth'].includes(candidate.candidate_type))
            const verifiedIds = relevantCandidates.filter(candidate => candidate.review_status === 'verified').map(candidate => candidate.id)
            if (verifiedIds.length === 0) {
              throw new Error('No verified Source Understanding candidates are available. Review source suggestions before creating a Semantic Model draft.')
            }
            const model = await dataModelingAdapter.createDraft(draft.datasourceId, {
              domain: draft.domain || 'Unassigned',
              owner: 'Data Team',
              name: draft.businessQuestions.trim() ? draft.businessQuestions.trim().slice(0, 80) : undefined,
              candidateIds: verifiedIds,
            })
            set(state => ({
              models: mergeModels(state.models, [model]),
              visibleModels: mergeModels(state.visibleModels, [model]),
              activeModelId: model.id,
              createDraft: { ...state.createDraft, generated: true },
              generation: {
                ...state.generation,
                phase: 'completed',
                progress: 100,
                steps: state.generation.steps.map(step => ({ ...step, status: 'done' })),
                summary: [
                  `Analyzed ${understanding.candidates.length} source candidates.`,
                  `Used ${verifiedIds.length} already verified suggestions.`,
                  `Created draft Semantic Model ${model.name}. Validate and approve review before publishing.`,
                ],
              },
              homeError: null,
            }))
          } catch (error) {
            set(state => ({
              homeError: error instanceof Error ? error.message : 'Semantic generation failed',
              generation: {
                ...state.generation,
                phase: 'idle',
                steps: state.generation.steps.map(step => step.status === 'running' ? { ...step, status: 'pending' } : step),
              },
            }))
          }
        })()
      },

      advanceSemanticGeneration() {
        set(state => {
          const current = state.generation.phase
          const runningIndex = state.generation.steps.findIndex(step => step.status === 'running')
          const nextIndex = runningIndex < 0 ? 0 : runningIndex + 1
          if (current === 'idle') {
            return {
              generation: {
                ...state.generation,
                phase: 'profile',
                progress: generationProgressFor(0, state.generation.steps.length),
                steps: state.generation.steps.map((step, index) => ({ ...step, status: index === 0 ? 'running' : 'pending' })),
                summary: [],
              },
            }
          }

          if (nextIndex < state.generation.steps.length) {
            const phase = nextIndex < 3 ? 'profile' : nextIndex < 7 ? 'semantic' : 'validation'
            return {
              generation: {
                ...state.generation,
                phase,
                progress: generationProgressFor(nextIndex, state.generation.steps.length),
                steps: state.generation.steps.map((step, index) => ({
                  ...step,
                  status: index < nextIndex ? 'done' : index === nextIndex ? 'running' : 'pending',
                })),
              },
            }
          }

          if (current !== 'completed') return {}

          return {}
        })
      },

      generateDraft() {
        get().startSemanticGeneration()
      },

      acceptSuggestion(suggestionId) {
        set({ homeError: `Suggestion review for ${suggestionId} requires the Source Understanding review API. Reload the datasource profile and generate a new model draft after reviewing source candidates.` })
      },

      editAcceptSuggestion(suggestionId) {
        set({ homeError: `Edited suggestion acceptance for ${suggestionId} is not persisted on Semantic Models yet. Use source candidate review before creating the draft.` })
      },

      rejectSuggestion(suggestionId) {
        set({ homeError: `Suggestion rejection for ${suggestionId} requires the Source Understanding review API. The current Semantic Model was not changed.` })
      },

      updateRelationship(relationshipId, patch) {
        const before = currentModel(get())
        set(state => updateModel(state, model => ({
          ...model,
          relationships: model.relationships.map(rel => rel.id === relationshipId ? { ...rel, ...patch } : rel),
        })))
        const after = currentModel(get())
        saveModelPatch(set, get, before, { relationships: after.relationships }, 'Unable to save relationship')
      },

      fixFanoutRelationship(relationshipId) {
        const before = currentModel(get())
        set(state => updateModel(state, model => ({
          ...model,
          relationships: model.relationships.map(rel => rel.id === relationshipId ? {
            ...rel,
            cardinality: 'one-to-many',
            fanoutRisk: 'medium',
            validationStatus: 'valid',
            status: 'confirmed',
            validationMessage: 'Relationship marked confirmed after modeler review. Run Validate to refresh readiness.',
          } : rel),
        })))
        const after = currentModel(get())
        saveModelPatch(set, get, before, { relationships: after.relationships }, 'Unable to save relationship fix')
      },

      rejectRelationship(relationshipId) {
        const before = currentModel(get())
        set(state => updateModel(state, model => ({
          ...model,
          relationships: model.relationships.map(rel => rel.id === relationshipId ? {
            ...rel,
            status: 'rejected',
            validationStatus: 'warning',
            validationMessage: 'Rejected for this model version. Run Validate to refresh readiness.',
          } : rel),
        })))
        const after = currentModel(get())
        saveModelPatch(set, get, before, { relationships: after.relationships }, 'Unable to reject relationship')
      },

      updateMetric(metricId, patch) {
        const before = currentModel(get())
        set(state => updateModel(state, model => ({
          ...model,
          metrics: model.metrics.map(metric => metric.id === metricId ? { ...metric, ...patch } : metric),
        })))
        const after = currentModel(get())
        saveModelPatch(set, get, before, { metrics: after.metrics }, 'Unable to save metric')
      },

      setMetricCertification(metricId, certification) {
        if (certification === 'certified') {
          set({ homeError: 'Certification is assigned by the publish workflow after validation and human review. Draft editing can only mark metrics as draft or reviewed.' })
          return
        }
        get().updateMetric(metricId, { certification })
      },

      updateExplore(patch) {
        const before = currentModel(get())
        set(state => updateModel(state, model => ({
          ...model,
          explore: { ...model.explore, ...patch },
        })))
        const after = currentModel(get())
        saveModelPatch(set, get, before, { explore: after.explore }, 'Unable to save explore state')
      },

      saveExploreArtifact(kind) {
        const before = currentModel(get())
        set(state => updateModel(state, model => {
          const explore = { ...model.explore }
          const consumers = { ...model.consumers }
          if (kind === 'query') {
            explore.savedQueryCount += 1
            consumers.savedQueries += 1
          }
          if (kind === 'dashboard') {
            explore.dashboardAdds += 1
            consumers.dashboards += 1
          }
          if (kind === 'skill') {
            explore.skillDrafts += 1
            consumers.skills += 1
          }
          if (kind === 'example') {
            explore.confirmedExamples += 1
          }
          return {
            ...model,
            explore,
            consumers,
            validationLog: [`Saved Explore result as ${kind}.`, ...model.validationLog],
          }
        }))
        const after = currentModel(get())
        saveModelPatch(set, get, before, { explore: after.explore, consumers: after.consumers }, 'Unable to save Explore artifact')
      },

      async validateModel() {
        await flushModelPatches()
        const model = currentModel(get())
        try {
          const validated = await dataModelingAdapter.validateModel(model)
          set(state => ({
            models: mergeModels(state.models, [validated]),
            visibleModels: mergeModels(state.visibleModels, [validated]),
          }))
        } catch (error) {
          set({ homeError: error instanceof Error ? error.message : 'Validation failed' })
        }
      },

      openReview() {
        const before = currentModel(get())
        set(state => updateModel(state, model => ({ ...model, review: { ...model.review, opened: true } })))
        const after = currentModel(get())
        saveModelPatch(set, get, before, { review: after.review }, 'Unable to open review')
      },

      updatePublishNotes(notes) {
        set(state => updateModel(state, model => ({ ...model, review: { ...model.review, publishNotes: notes } })))
      },

      markReviewed() {
        const before = currentModel(get())
        set(state => updateModel(state, model => ({ ...model, review: { ...model.review, reviewed: true, opened: true } })))
        const after = currentModel(get())
        saveModelPatch(set, get, before, { review: after.review }, 'Unable to mark review complete')
      },

      async publishModel() {
        await flushModelPatches()
        const model = currentModel(get())
        try {
          const latest = await dataModelingAdapter.getModel(model.id)
          const reviewSaved = await dataModelingAdapter.patchModel(latest, { review: model.review })
          const published = await dataModelingAdapter.publishModel(reviewSaved)
          set(state => ({
            models: mergeModels(state.models, [published]),
            visibleModels: mergeModels(state.visibleModels, [published]),
          }))
        } catch (error) {
          set({ homeError: error instanceof Error ? error.message : 'Publish failed' })
        }
      },

      setRawSqlFallback(enabled) {
        const before = currentModel(get())
        set(state => updateModel(state, model => ({ ...model, mcp: { ...model.mcp, rawSqlFallback: enabled } })))
        const after = currentModel(get())
        saveModelPatch(set, get, before, { mcp: after.mcp }, 'Unable to update MCP policy')
      },

      async runMcpQuery() {
        await flushModelPatches()
        const model = currentModel(get())
        try {
          const lastResult = await dataModelingAdapter.queryMetric(model)
          await get().loadModel(model.id)
          set({ homeError: null })
          if (lastResult) {
            set(state => updateModel(state, current => ({
              ...current,
              mcp: { ...current.mcp, lastResult },
            })))
          }
        } catch (error) {
          set({ homeError: error instanceof Error ? error.message : 'MCP query failed' })
        }
      },
    }),
    {
      name: 'byaan-data-modeling-production-v1',
      partialize: state => ({
        models: state.models,
        profiles: state.profiles,
        createDraft: state.createDraft,
        activeModelId: state.activeModelId,
        selectedObjectId: state.selectedObjectId,
        workspaceMode: state.workspaceMode,
        selectedProfileTable: state.selectedProfileTable,
        selectedProfileField: state.selectedProfileField,
        generation: state.generation,
      }),
    },
  ),
)

export function selectActiveModel(state: DataModelingStore) {
  return state.models.find(model => model.id === state.activeModelId) ?? state.models[0]
}

function mergeModels(current: SemanticModel[], incoming: SemanticModel[]) {
  const byId = new Map(current.map(model => [model.id, model]))
  for (const model of incoming) {
    byId.set(model.id, model)
  }
  return Array.from(byId.values())
}

function mergeProfiles(current: DataModelingWorkspaceData['profiles'], incoming: DataModelingWorkspaceData['profiles']) {
  const byId = new Map(current.map(profile => [profile.id, profile]))
  for (const profile of incoming) {
    byId.set(profile.id, profile)
  }
  return Array.from(byId.values())
}

export function selectExploreResult(model: SemanticModel) {
  const metric = model.metrics.find(item => item.id === model.explore.metricId) ?? model.metrics[0]
  const dimension = model.dimensions.find(item => item.id === model.explore.dimensionId) ?? model.dimensions[0]
  const lastResult = model.mcp.lastResult
  if (lastResult) {
    const parsed = parseResultRows(lastResult.result)
    if (parsed.length) {
      return {
        kpi: String(parsed[0]?.[metric?.id] ?? parsed[0]?.[metric?.businessName] ?? lastResult.result),
        delta: lastResult.freshness,
        trend: parsed.slice(0, 8).map((row, index) => ({ period: String(row[dimension?.id] ?? row[dimension?.name] ?? index + 1), value: Number(row[metric?.id] ?? Object.values(row).find(value => typeof value === 'number') ?? 0) })),
        rows: parsed,
      }
    }
  }
  if (!metric || !dimension) {
    return { kpi: 'No result', delta: '', trend: [], rows: [] }
  }
  return {
    kpi: 'Run query_metric',
    delta: model.publishedVersion === 'v0' ? 'Publish the model before MCP queries.' : 'No semantic query result yet.',
    trend: [],
    rows: [],
  }
}

function parseResultRows(value: string): ExploreResult['rows'] {
  try {
    const parsed = JSON.parse(value)
    if (Array.isArray(parsed)) return parsed as ExploreResult['rows']
    if (parsed && typeof parsed === 'object') return [parsed as Record<string, string | number>]
    return []
  } catch {
    return []
  }
}
