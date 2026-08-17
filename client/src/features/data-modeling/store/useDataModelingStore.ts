import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { dataModelingAdapter } from '../adapters/dataModelingAdapter'
import { knowledgeCenterMockAdapter } from '../adapters/knowledgeCenterMockAdapter'
import type {
  CertificationStatus,
  CreateModelDraft,
  DataModelingDatasource,
  DataModelingWorkspaceData,
  ExploreState,
  ExploreResult,
  KnowledgeCenterGateState,
  ModelingScopeItem,
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
  selectScopeSource: (datasourceId: string) => void
  addScopeTable: (tableName: string) => void
  removeScopeItem: (scopeItemId: string) => void
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
  runKnowledgeGate: () => Promise<void>
  publishKnowledgeAsset: () => Promise<void>
  publishModel: () => Promise<void>
  setRawSqlFallback: (enabled: boolean) => void
  runMcpQuery: () => Promise<void>
}

const initialGate: KnowledgeCenterGateState = {
  score: 50,
  passed: 2,
  total: 4,
  blockers: [
    'Failed: Dashboard KPI still references gross_amount while the semantic model exposes paid_revenue after refunds.',
    'Failed: Refunds can duplicate order lines unless refunds are pre-aggregated by order_id.',
  ],
  evaluated: false,
  checks: [
    {
      id: 'metric-contract',
      title: 'Paid Revenue contract matches dashboard KPI',
      status: 'failed',
      reason: 'Failed: Dashboard KPI still references gross_amount while the semantic model exposes paid_revenue after refunds.',
      passedReason: 'Passed: Dashboard KPI and semantic model both resolve Paid Revenue from paid order lines net of refunds.',
      evidence: {
        sql: 'select sum(paid_amount - refunded_amount) as paid_revenue from marts.order_revenue_daily',
        doc: 'Revenue Playbook / Section 2.1 Paid Revenue',
        policy: 'Metric consumers may use certified revenue only after refund fanout is resolved.',
      },
    },
    {
      id: 'fanout',
      title: 'Refund relationship fanout guard',
      status: 'failed',
      reason: 'Failed: Refunds can duplicate order lines unless refunds are pre-aggregated by order_id.',
      passedReason: 'Passed: Refund evidence is aggregated by order_id before joining to order facts.',
      evidence: {
        sql: 'with refund_by_order as (select order_id, sum(amount) refund_amount from refunds group by 1)',
        doc: 'Modeling Notes / Section 3.4 Refund Join Pattern',
        policy: 'Fanout risk must be medium or lower for published revenue metrics.',
      },
    },
    {
      id: 'pii-policy',
      title: 'PII is masked from semantic consumers',
      status: 'passed',
      reason: 'Passed: Customer email and phone fields are excluded from Agent, dashboard, and MCP exposure.',
      passedReason: 'Passed: Customer email and phone fields are excluded from Agent, dashboard, and MCP exposure.',
      evidence: {
        sql: 'select customer_id, customer_segment from dim_customers',
        doc: 'Privacy Rules / Section 5 Customer Contact Fields',
        policy: 'MCP allowlist excludes customers.email and customers.phone.',
      },
    },
    {
      id: 'freshness',
      title: 'Freshness is inside operational SLA',
      status: 'passed',
      reason: 'Passed: Source profile and dashboard snapshot were refreshed inside the 4 hour SLA.',
      passedReason: 'Passed: Source profile and dashboard snapshot were refreshed inside the 4 hour SLA.',
      evidence: {
        sql: 'select max(updated_at) from marts.order_revenue_daily',
        doc: 'Operations Runbook / Section 1.2 Data Freshness',
        policy: 'Revenue assets require freshness under 4 hours for publish.',
      },
    },
  ],
}

const emptyData: DataModelingWorkspaceData = {
  models: [],
  profiles: [],
  createDraft: {
    datasourceId: '',
    domain: 'Sales / Orders',
    selectedTables: [],
    businessQuestions: '',
    generated: false,
  },
  activeModelId: '',
  selectedObjectId: '',
  workspaceMode: 'connectors',
  scope: {
    selectedSourceId: '',
    items: [],
  },
  gate: initialGate,
  publishState: 'blocked',
  selectedProfileTable: '',
  selectedProfileField: '',
  generation: {
    phase: 'idle',
    progress: 0,
    steps: [
      { id: 'profile', title: 'Read schema and profile', detail: 'Load live datasource schema and table profile evidence.', status: 'pending' },
      { id: 'candidates', title: 'Generate candidates', detail: 'Create entity, relationship, metric, and dimension suggestions from Source Understanding.', status: 'pending' },
      { id: 'review', title: 'Review accepted suggestions', detail: 'Only verified suggestions feed the semantic draft.', status: 'pending' },
      { id: 'draft', title: 'Create semantic draft', detail: 'Persist the draft Semantic Model through the backend API.', status: 'pending' },
    ],
    summary: [],
    error: null,
  },
}

const idleGeneration = emptyData.generation

function resetRunningGeneration(generation: typeof emptyData.generation | undefined) {
  if (!generation || generation.phase === 'idle') return idleGeneration
  if (generation.phase !== 'completed') return idleGeneration
  return {
    ...generation,
    steps: generation.steps.map(step => ({ ...step, status: 'done' as const })),
    error: null,
  }
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
          const activeModel = mergedModels.find(model => model.id === activeModelId)
          set({
            models: mergedModels,
            visibleModels,
            activeModelId,
            gate: activeModel ? gateStateFromModel(activeModel) : get().gate,
            publishState: activeModel?.publishState ?? get().publishState,
            homeLoading: false,
            homeError: null,
          })
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
              gate: gateStateFromModel(model),
              publishState: model.publishState,
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
          const selectedDatasource = datasourceOptions.find(item => item.id === selected)
          const nextDatasourceId = selectedDatasource?.canLoadProfile && selectedDatasource.modelingStatus === 'supported'
            ? selected
            : datasourceOptions.find(item => item.canLoadProfile && item.modelingStatus === 'supported')?.id ?? datasourceOptions[0]?.id ?? ''
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
        set({ activeModelId: modelId, selectedObjectId: '', workspaceMode: 'connectors' })
      },

      selectObject(objectId) {
        set({ selectedObjectId: objectId })
      },

      setWorkspaceMode(mode) {
        set(state => ({
          workspaceMode: mode,
          selectedObjectId: mode === 'dashboard' || mode === 'connectors' ? '' : state.selectedObjectId,
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
          const selectedDatasource = get().datasourceOptions.find(item => item.id === patch.datasourceId)
          if (selectedDatasource && !selectedDatasource.canLoadProfile) {
            set({
              selectedProfileTable: '',
              selectedProfileField: '',
            })
            return
          }
          void dataModelingAdapter.loadProfile(patch.datasourceId).then(profile => {
            set(current => ({
              profiles: mergeProfiles(current.profiles, [profile]),
              selectedProfileTable: profile.tables[0]?.name ?? '',
              selectedProfileField: profile.tables[0]?.fields[0]?.name ?? '',
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

      selectScopeSource(datasourceId) {
        set(state => ({
          scope: { ...state.scope, selectedSourceId: datasourceId },
          createDraft: { ...state.createDraft, datasourceId },
        }))
        get().updateCreateDraft({ datasourceId })
      },

      addScopeTable(tableName) {
        const state = get()
        const sourceId = state.scope.selectedSourceId || state.createDraft.datasourceId
        const profile = state.profiles.find(item => item.id === sourceId)
        const table = profile?.tables.find(item => item.name === tableName)
        if (!sourceId || !profile || !table) return
        const item: ModelingScopeItem = {
          id: `${sourceId}:${table.name}`,
          sourceId,
          tableName: table.name,
          label: `${profile.name}.${table.name}`,
          category: table.category,
          rowCount: table.rowCount,
        }
        set(current => {
          if (current.scope.items.some(scopeItem => scopeItem.id === item.id)) return {}
          return {
            scope: {
              ...current.scope,
              selectedSourceId: sourceId,
              items: [...current.scope.items, item],
            },
            createDraft: {
              ...current.createDraft,
              selectedTables: Array.from(new Set([...current.createDraft.selectedTables, table.name])),
            },
          }
        })
      },

      removeScopeItem(scopeItemId) {
        set(state => {
          const nextItems = state.scope.items.filter(item => item.id !== scopeItemId)
          return {
            scope: { ...state.scope, items: nextItems },
            createDraft: {
              ...state.createDraft,
              selectedTables: nextItems.map(item => item.tableName),
            },
          }
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
            error: null,
          },
          homeError: null,
        }))
        const draft = get().createDraft
        if (!draft.datasourceId) {
          const message = 'Choose a datasource before generating a Semantic Model.'
          set(state => ({
            homeError: message,
            generation: { ...state.generation, phase: 'idle', progress: 0, error: message },
          }))
          return
        }
        const selectedDatasource = get().datasourceOptions.find(item => item.id === draft.datasourceId)
        if (selectedDatasource && (!selectedDatasource.canLoadProfile || selectedDatasource.modelingStatus !== 'supported')) {
          const message = selectedDatasource.reason ?? 'This source is not ready for production semantic generation.'
          set(state => ({
            homeError: message,
            generation: { ...state.generation, phase: 'idle', progress: 0, error: message },
          }))
          return
        }
        void (async () => {
          try {
            const scopedTables = get().scope.items.length
              ? get().scope.items.map(item => item.tableName)
              : draft.selectedTables
            const understanding = await dataModelingAdapter.analyzeDatasource(draft.datasourceId, scopedTables)
            const candidates = understanding.candidates.filter(candidate => ['schema_map', 'relationship', 'data_truth'].includes(candidate.candidate_type))
            set(state => ({
              generation: {
                ...state.generation,
                phase: 'semantic',
                progress: generationProgressFor(1, state.generation.steps.length),
                steps: state.generation.steps.map((step, index) => ({
                  ...step,
                  status: index < 1 ? 'done' : index === 1 ? 'running' : 'pending',
                })),
              },
            }))
            const reviewedIds: string[] = []
            set(state => ({
              generation: {
                ...state.generation,
                progress: generationProgressFor(2, state.generation.steps.length),
                steps: state.generation.steps.map((step, index) => ({
                  ...step,
                  status: index < 2 ? 'done' : index === 2 ? 'running' : 'pending',
                })),
              },
            }))
            for (const candidate of candidates) {
              const reviewed = await dataModelingAdapter.reviewCandidate(draft.datasourceId, candidate.id, 'accept')
              reviewedIds.splice(0, reviewedIds.length, ...reviewed.candidates.filter(item => item.review_status === 'verified').map(item => item.id))
            }
            set(state => ({
              generation: {
                ...state.generation,
                phase: 'validation',
                progress: generationProgressFor(3, state.generation.steps.length),
                steps: state.generation.steps.map((step, index) => ({
                  ...step,
                  status: index < 3 ? 'done' : index === 3 ? 'running' : 'pending',
                })),
              },
            }))
            const model = await dataModelingAdapter.createDraft(draft.datasourceId, {
              domain: draft.domain,
              owner: 'Data Team',
              name: draft.businessQuestions.trim() ? draft.businessQuestions.trim().slice(0, 80) : undefined,
              candidateIds: reviewedIds,
            })
            set(state => ({
              models: mergeModels(state.models, [model]),
              visibleModels: mergeModels(state.visibleModels, [model]),
              activeModelId: model.id,
              createDraft: { ...state.createDraft, generated: true },
              gate: gateStateFromModel(model),
              publishState: model.publishState,
              generation: {
                ...state.generation,
                phase: 'completed',
                progress: 100,
                steps: state.generation.steps.map(step => ({ ...step, status: 'done' })),
                summary: [
                  `Analyzed ${understanding.candidates.length} source candidates.`,
                  `Accepted ${reviewedIds.length} verified suggestions.`,
                  `Created Semantic Model draft ${model.name}.`,
                ],
                error: null,
              },
              homeError: null,
            }))
          } catch (error) {
            const message = error instanceof Error ? error.message : 'Semantic generation failed'
            set(state => ({
              homeError: message,
              generation: {
                ...state.generation,
                phase: 'idle',
                progress: 0,
                steps: state.generation.steps.map(step => step.status === 'running' ? { ...step, status: 'pending' } : step),
                error: message,
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
                error: null,
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
            publishState: validated.publishState,
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

      async runKnowledgeGate() {
        const model = currentModel(get())
        if (!model) return
        set({ publishState: 'validating', homeError: null })
        const gate = await knowledgeCenterMockAdapter.evaluateGate(model)
        set(state => {
          const publishState = gate.blockers.length ? 'blocked' as const : 'draft' as const
          return {
            gate,
            publishState,
            ...updateModel(state, current => ({
              ...current,
              gate: {
                score: gate.score,
                passed: gate.passed,
                total: gate.total,
                blockers: gate.blockers,
              },
              publishState,
              dataStudioAsset: {
                ...current.dataStudioAsset,
                gate: {
                  score: gate.score,
                  passed: gate.passed,
                  total: gate.total,
                  blockers: gate.blockers,
                },
                publish_state: publishState,
              },
              validationLog: [
                `Knowledge gate evaluated: ${gate.passed}/${gate.total} checks passed.`,
                ...current.validationLog,
              ],
            })),
          }
        })
      },

      async publishKnowledgeAsset() {
        const state = get()
        const model = currentModel(state)
        if (!model) return
        const blockers = state.gate.blockers.length ? state.gate.blockers : model.gate.blockers
        if (blockers.length) {
          set({
            publishState: 'blocked',
            homeError: 'Publish blocked by knowledge center gate.',
          })
          return
        }
        try {
          const published = await knowledgeCenterMockAdapter.publishAsset(model)
          set(current => ({
            publishState: 'published',
            homeError: null,
            ...updateModel(current, item => ({
              ...item,
              status: 'Published',
              publishState: 'published',
              publishedVersion: published.publishedVersion,
              consumers: published.consumers,
              review: { ...item.review, publishedAt: published.publishedAt, reviewed: true, opened: true },
              mcp: { ...item.mcp, exposedVersion: published.publishedVersion },
              consumptionEntries: published.entries,
              dataStudioAsset: {
                ...item.dataStudioAsset,
                status: 'Published',
                publish_state: 'published',
                version: published.publishedVersion,
                consumers: published.consumers,
              },
              validationLog: [
                `Published ${published.publishedVersion} to Agent, Dashboard, MCP API, and share link consumers.`,
                ...item.validationLog,
              ],
            })),
          }))
        } catch (error) {
          set({ homeError: error instanceof Error ? error.message : 'Publish failed' })
        }
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
          if (lastResult) {
            set(state => updateModel(state, current => ({
              ...current,
              mcp: { ...current.mcp, lastResult },
            })))
          }
          await get().loadModel(model.id)
          if (lastResult) {
            set(state => updateModel(state, current => ({
              ...current,
              mcp: { ...current.mcp, lastResult },
            })))
          }
          set({ homeError: null })
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
        scope: state.scope,
        gate: state.gate,
        publishState: state.publishState,
        selectedProfileTable: state.selectedProfileTable,
        selectedProfileField: state.selectedProfileField,
        generation: resetRunningGeneration(state.generation),
      }),
      merge: (persisted, current) => {
        const persistedState = persisted as Partial<DataModelingStore> | undefined
        return {
          ...current,
          ...persistedState,
          generation: resetRunningGeneration(persistedState?.generation),
        }
      },
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

function gateStateFromModel(model: SemanticModel): KnowledgeCenterGateState {
  const passed = model.gate.passed
  const total = model.gate.total || Math.max(model.readinessDetail.components.length, 4)
  const blockers = model.gate.blockers.length ? model.gate.blockers : model.readinessDetail.blockers
  const matchedChecks = initialGate.checks.map(check => {
    const blocker = blockers.find(item => item === check.reason || item === check.passedReason || item.includes(check.title))
    return {
      ...check,
      status: blocker ? 'failed' as const : 'passed' as const,
      reason: blocker ?? check.passedReason,
    }
  })
  const unmatchedBlockers = blockers.filter(blocker => !matchedChecks.some(check => check.reason === blocker))
  if (unmatchedBlockers.length) {
    for (let index = 0; index < unmatchedBlockers.length; index += 1) {
      const target = matchedChecks[matchedChecks.length - 1 - index]
      if (!target) break
      target.status = 'failed'
      target.reason = unmatchedBlockers[index]
    }
  }
  return {
    score: model.gate.score,
    passed,
    total,
    blockers,
    evaluated: false,
    checks: matchedChecks,
  }
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
