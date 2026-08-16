import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { mockDataModelingAdapter } from '../adapters/dataModelingAdapter'
import { cloneDemoData } from '../mock/fixtures'
import type {
  CertificationStatus,
  CreateModelDraft,
  DataModelingDemoData,
  ExploreState,
  HomeDemoMode,
  McpState,
  Metric,
  Relationship,
  SemanticModel,
  TimeGrain,
  WorkspaceMode,
} from '../types'

interface DataModelingStore extends DataModelingDemoData {
  homeMode: HomeDemoMode
  homeLoading: boolean
  homeError: string | null
  visibleModels: SemanticModel[]
  loadModels: (mode?: HomeDemoMode) => Promise<void>
  loadModel: (modelId: string) => Promise<void>
  setHomeMode: (mode: HomeDemoMode) => void
  resetDemo: () => void
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

const demo = cloneDemoData()

function levelForScore(score: number) {
  if (score >= 85) return 'ready' as const
  if (score >= 65) return 'warning' as const
  return 'blocked' as const
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

function recalculateReadiness(model: SemanticModel): SemanticModel {
  const fanoutBlocked = model.relationships.some(rel => rel.validationStatus === 'blocked' && rel.status !== 'rejected')
  const piiAccepted = model.suggestions.some(suggestion => suggestion.id === 'sug-policy-pii' && suggestion.status !== 'pending')
  const certifiedCore = model.metrics.some(metric => metric.id === 'paid_revenue' && metric.certification === 'certified')
  const acceptedSuggestions = model.suggestions.filter(suggestion => suggestion.status === 'accepted' || suggestion.status === 'edited').length

  const structural = Math.min(96, 84 + acceptedSuggestions * 2)
  const semantic = Math.min(94, 74 + acceptedSuggestions * 3)
  const query = fanoutBlocked ? 66 : 88
  const governance = Math.min(92, 62 + (piiAccepted ? 16 : 0) + (certifiedCore ? 10 : 0))
  const evidence = Math.min(95, 79 + acceptedSuggestions * 2)
  const score = Math.round(structural * 0.2 + semantic * 0.25 + query * 0.25 + governance * 0.15 + evidence * 0.15)
  const blockers = fanoutBlocked ? ['Orders -> Refunds fanout candidate is unresolved.'] : []
  const warnings = [
    ...(!piiAccepted ? ['Customer contact fields need a confirmed PII policy.'] : []),
    ...(!certifiedCore ? ['Paid Revenue should be certified before broad MCP exposure.'] : []),
    ...model.metrics.some(metric => metric.id === 'refund_rate' && metric.certification === 'draft') ? ['Refund Rate is still draft certified.'] : [],
  ]
  const level = blockers.length > 0 ? 'blocked' : levelForScore(score)
  const reliableQuestions = fanoutBlocked
    ? model.readinessDetail.reliableQuestions
    : [...model.readinessDetail.reliableQuestions, 'What is refund rate by region and product category?']

  return {
    ...model,
    readiness: score,
    readinessLevel: level,
    readinessDetail: {
      ...model.readinessDetail,
      score,
      level,
      components: [
        { id: 'structural', name: 'Structural completeness', score: structural, status: levelForScore(structural) },
        { id: 'semantic', name: 'Semantic completeness', score: semantic, status: levelForScore(semantic) },
        { id: 'query', name: 'Query correctness', score: query, status: fanoutBlocked ? 'blocked' : levelForScore(query) },
        { id: 'governance', name: 'Governance', score: governance, status: levelForScore(governance) },
        { id: 'evidence', name: 'Evidence coverage', score: evidence, status: levelForScore(evidence) },
      ],
      reliableQuestions: Array.from(new Set(reliableQuestions)),
      unreliableQuestions: fanoutBlocked
        ? model.readinessDetail.unreliableQuestions
        : ['Which individual customers should be contacted?'],
      blockers,
      warnings,
    },
  }
}

function updateMetricPreview(metric: Metric, patch: Partial<Metric>): Metric {
  const changedFormula = typeof patch.formula === 'string' && patch.formula !== metric.formula
  const changedFilter = typeof patch.filter === 'string' && patch.filter !== metric.filter
  const changedTimeField = typeof patch.timeField === 'string' && patch.timeField !== metric.timeField
  const changedGrain = typeof patch.defaultGrain === 'string' && patch.defaultGrain !== metric.defaultGrain
  const previewChanged = changedFormula || changedFilter || changedTimeField || changedGrain
  const signature = `${patch.formula ?? metric.formula}|${patch.filter ?? metric.filter}|${patch.timeField ?? metric.timeField}|${patch.defaultGrain ?? metric.defaultGrain}`
  const deterministicDelta = signature.length % 7
  const currentValue = previewChanged && metric.id === 'paid_revenue'
    ? `$${(8.48 + deterministicDelta * 0.03).toFixed(2)}M`
    : previewChanged && metric.id === 'avg_order_value'
      ? `$${(73.24 + deterministicDelta * 0.41).toFixed(2)}`
      : previewChanged && metric.unit === '%'
        ? `${(4.8 + deterministicDelta * 0.2).toFixed(1)}%`
        : metric.preview.currentValue
  const validation = patch.certification === 'certified'
    ? 'Certified by owner and ready for semantic MCP exposure.'
    : previewChanged
      ? 'Recompiled successfully; preview refreshed from deterministic demo data.'
      : metric.preview.validation

  return {
    ...metric,
    ...patch,
    preview: {
      ...metric.preview,
      currentValue,
      trend: previewChanged ? `+${(10.8 + deterministicDelta * 0.7).toFixed(1)}% vs prior period` : metric.preview.trend,
      validation,
      sql: previewChanged ? `-- Demo SQL preview\nSELECT ${patch.formula ?? metric.formula} AS ${metric.name}\nFROM semantic_model.sales_growth\nWHERE ${patch.filter ?? metric.filter}\n-- time: ${patch.timeField ?? metric.timeField}; grain: ${patch.defaultGrain ?? metric.defaultGrain}` : metric.preview.sql,
      breakdown: previewChanged
        ? metric.preview.breakdown.map((row, index) => ({
            ...row,
            delta: `${index === 2 ? '-' : '+'}${(deterministicDelta + index + 1).toFixed(1)}%`,
          }))
        : metric.preview.breakdown,
    },
  }
}

function generationProgressFor(index: number, total: number) {
  return Math.min(96, Math.round(((index + 1) / total) * 100))
}

export const useDataModelingStore = create<DataModelingStore>()(
  persist(
    (set, get) => ({
      ...demo,
      homeMode: 'ready',
      homeLoading: false,
      homeError: null,
      visibleModels: demo.models,

      async loadModels(mode = get().homeMode) {
        set({ homeMode: mode, homeLoading: true, homeError: null })
        try {
          const visibleModels = await mockDataModelingAdapter.listModels(get().models, mode)
          const mergedModels = mergeModels(get().models, visibleModels)
          const activeModelId = mergedModels.some(model => model.id === get().activeModelId)
            ? get().activeModelId
            : mergedModels[0]?.id || get().activeModelId
          set({ models: mergedModels, visibleModels, activeModelId, homeLoading: false, homeError: null })
        } catch (error) {
          const message = error instanceof Error ? error.message : 'Unable to load Data Models'
          set({ visibleModels: [], homeLoading: false, homeError: message })
        }
      },

      async loadModel(modelId) {
        try {
          const model = await mockDataModelingAdapter.getModel(get().models, modelId)
          if (!model) return
          set(state => {
            const models = mergeModels(state.models, [model])
            return {
              models,
              visibleModels: mergeModels(state.visibleModels, [model]),
              activeModelId: model.id,
            }
          })
        } catch {
          // Keep existing mock model if the backend is unavailable or the model was deleted.
        }
      },

      setHomeMode(mode) {
        void get().loadModels(mode)
      },

      resetDemo() {
        const next = cloneDemoData()
        set({ ...next, homeMode: 'ready', homeLoading: false, homeError: null, visibleModels: next.models })
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

          if (current !== 'completed') {
            const nextModels = state.models.map(model => model.id === 'sales-growth' ? recalculateReadiness({ ...model, draftRevision: 'draft-8' }) : model)
            return {
              createDraft: { ...state.createDraft, generated: true },
              models: nextModels,
              visibleModels: state.visibleModels.map(model => nextModels.find(item => item.id === model.id) ?? model),
              generation: {
                ...state.generation,
                phase: 'completed',
                progress: 100,
                steps: state.generation.steps.map(step => ({ ...step, status: 'done' })),
                summary: [
                  'Generated 5 metrics.',
                  'Generated 7 dimensions.',
                  'Validated 3 relationships.',
                  '2 suggestions remain for review.',
                ],
              },
            }
          }

          return {}
        })
      },

      generateDraft() {
        set(state => ({
          createDraft: { ...state.createDraft, generated: true },
          models: state.models.map(model => model.id === 'sales-growth' ? recalculateReadiness({ ...model, draftRevision: 'draft-8' }) : model),
          generation: {
            ...state.generation,
            phase: 'completed',
            progress: 100,
            steps: state.generation.steps.map(step => ({ ...step, status: 'done' })),
            summary: state.generation.summary.length ? state.generation.summary : [
              'Generated 5 metrics.',
              'Generated 7 dimensions.',
              'Validated 3 relationships.',
              '2 suggestions remain for review.',
            ],
          },
        }))
      },

      acceptSuggestion(suggestionId) {
        set(state => updateModel(state, model => recalculateReadiness({
          ...model,
          suggestions: model.suggestions.map(suggestion => suggestion.id === suggestionId ? { ...suggestion, status: 'accepted' } : suggestion),
          validationLog: [`Accepted suggestion ${suggestionId}.`, ...model.validationLog],
        })))
      },

      editAcceptSuggestion(suggestionId) {
        set(state => updateModel(state, model => recalculateReadiness({
          ...model,
          suggestions: model.suggestions.map(suggestion => suggestion.id === suggestionId ? { ...suggestion, status: 'edited', editedNote: 'Business wording adjusted before accepting.' } : suggestion),
          validationLog: [`Edited and accepted suggestion ${suggestionId}.`, ...model.validationLog],
        })))
      },

      rejectSuggestion(suggestionId) {
        set(state => updateModel(state, model => recalculateReadiness({
          ...model,
          suggestions: model.suggestions.map(suggestion => suggestion.id === suggestionId ? { ...suggestion, status: 'rejected' } : suggestion),
          validationLog: [`Rejected suggestion ${suggestionId}.`, ...model.validationLog],
        })))
      },

      updateRelationship(relationshipId, patch) {
        set(state => updateModel(state, model => recalculateReadiness({
          ...model,
          relationships: model.relationships.map(rel => rel.id === relationshipId ? { ...rel, ...patch } : rel),
          validationLog: [`Relationship ${relationshipId} updated.`, ...model.validationLog],
        })))
      },

      fixFanoutRelationship(relationshipId) {
        set(state => updateModel(state, model => recalculateReadiness({
          ...model,
          relationships: model.relationships.map(rel => rel.id === relationshipId ? {
            ...rel,
            cardinality: 'one-to-many',
            uniqueRate: 99.1,
            orphanRate: 0.9,
            fanoutRisk: 'medium',
            validationStatus: 'valid',
            status: 'confirmed',
            validationMessage: 'Fixed by modeling refunds as a pre-aggregated order-level subquery.',
          } : rel),
          validationLog: ['Fixed refund fanout by introducing order-level refund aggregation.', ...model.validationLog],
        })))
      },

      rejectRelationship(relationshipId) {
        set(state => updateModel(state, model => recalculateReadiness({
          ...model,
          relationships: model.relationships.map(rel => rel.id === relationshipId ? {
            ...rel,
            status: 'rejected',
            validationStatus: 'warning',
            validationMessage: 'Rejected for this model version; refund metrics must use explicit aggregate SQL.',
          } : rel),
          validationLog: ['Rejected fanout-prone relationship candidate.', ...model.validationLog],
        })))
      },

      updateMetric(metricId, patch) {
        set(state => updateModel(state, model => recalculateReadiness({
          ...model,
          metrics: model.metrics.map(metric => metric.id === metricId ? updateMetricPreview(metric, patch) : metric),
          validationLog: [`Metric ${metricId} preview refreshed.`, ...model.validationLog],
        })))
      },

      setMetricCertification(metricId, certification) {
        get().updateMetric(metricId, { certification })
      },

      updateExplore(patch) {
        set(state => updateModel(state, model => ({
          ...model,
          explore: { ...model.explore, ...patch },
        })))
      },

      saveExploreArtifact(kind) {
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
      },

      async validateModel() {
        const model = currentModel(get())
        try {
          const validated = await mockDataModelingAdapter.validateModel(model)
          set(state => ({
            models: mergeModels(state.models, [validated]),
            visibleModels: mergeModels(state.visibleModels, [validated]),
          }))
        } catch {
          set(state => updateModel(state, current => recalculateReadiness({
            ...current,
            validationLog: [
              'Validation run completed locally because the Semantic Model API was unavailable.',
              ...current.validationLog,
            ],
          })))
        }
      },

      openReview() {
        set(state => updateModel(state, model => ({ ...model, review: { ...model.review, opened: true } })))
      },

      updatePublishNotes(notes) {
        set(state => updateModel(state, model => ({ ...model, review: { ...model.review, publishNotes: notes } })))
      },

      markReviewed() {
        set(state => updateModel(state, model => ({ ...model, review: { ...model.review, reviewed: true, opened: true } })))
      },

      async publishModel() {
        const model = currentModel(get())
        try {
          const published = await mockDataModelingAdapter.publishModel(model)
          set(state => ({
            models: mergeModels(state.models, [published]),
            visibleModels: mergeModels(state.visibleModels, [published]),
          }))
        } catch {
          set(state => updateModel(state, current => {
            const nextMcp: McpState = { ...current.mcp, exposedVersion: 'v3' }
            return recalculateReadiness({
              ...current,
              status: 'Published',
              publishedVersion: 'v3',
              draftRevision: 'clean',
              driftAlerts: 0,
              mcp: nextMcp,
              review: { ...current.review, reviewed: true, opened: false, publishedAt: '2026-08-14 12:45' },
              validationLog: [
                'Published Semantic Model v3 locally because the Semantic Model API was unavailable.',
                ...current.validationLog,
              ],
            })
          }))
        }
      },

      setRawSqlFallback(enabled) {
        set(state => updateModel(state, model => ({ ...model, mcp: { ...model.mcp, rawSqlFallback: enabled } })))
      },

      async runMcpQuery() {
        const model = currentModel(get())
        const metric = model.metrics.find(item => item.id === model.explore.metricId) ?? model.metrics[0]
        try {
          const lastResult = await mockDataModelingAdapter.queryMetric(model)
          set(state => updateModel(state, current => ({
            ...current,
            mcp: { ...current.mcp, lastResult },
            validationLog: [`MCP query_metric resolved ${lastResult?.resolvedMetric ?? metric.businessName}.`, ...current.validationLog],
          })))
        } catch {
          set(state => updateModel(state, current => ({
            ...current,
            mcp: {
              ...current.mcp,
              lastResult: {
                resolvedMetric: metric.businessName,
                modelVersion: current.mcp.exposedVersion,
                result: metric.preview.currentValue,
                freshness: 'Profile refreshed 2h ago; semantic version immutable.',
                lineage: metric.lineage,
                policyDecision: current.mcp.rawSqlFallback ? 'Allowed semantic tool; raw SQL fallback remains separately audited.' : 'Allowed semantic tool; raw SQL fallback denied by default.',
              },
            },
            validationLog: [
              `MCP query_metric resolved ${metric.businessName} locally because the Semantic Model API was unavailable.`,
              ...current.validationLog,
            ],
          })))
        }
      },
    }),
    {
      name: 'byaan-data-modeling-demo-v1',
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

export function selectExploreResult(model: SemanticModel) {
  const metric = model.metrics.find(item => item.id === model.explore.metricId) ?? model.metrics[0]
  const dimension = model.dimensions.find(item => item.id === model.explore.dimensionId) ?? model.dimensions[0]
  const grainMultiplier: Record<TimeGrain, number> = { day: 0.12, week: 0.42, month: 1, quarter: 2.7 }
  const metricSeed = metric.id.length + dimension.id.length + model.explore.filter.length
  const multiplier = grainMultiplier[model.explore.grain]
  const base = Math.round((metricSeed * 137) * multiplier)
  return {
    kpi: metric.preview.currentValue,
    delta: metric.preview.trend,
    trend: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'].map((period, index) => ({ period, value: base + index * Math.round(base * 0.12) })),
    rows: metric.preview.breakdown.map((row, index) => ({
      [dimension.name]: row.label,
      [metric.businessName]: row.value,
      Delta: row.delta,
      Rank: index + 1,
    })),
  }
}
