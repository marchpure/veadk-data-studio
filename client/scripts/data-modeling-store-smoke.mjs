import { build } from 'esbuild'
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'

const modelId = 'store-smoke-sales'
let serverModel = createModel()
const patchBodies = []
let sourceDraftCounter = 0
let analyzeShouldFail = false
let createDraftShouldFail = false
let patchShouldFail = false
let validateShouldFail = false
let publishShouldFail = false
let semanticQueryShouldFail = false
let validateCalls = 0
let publishCalls = 0

globalThis.window = globalThis.window || { __RUNTIME_CONFIG__: {} }
globalThis.document = globalThis.document || { cookie: '' }
globalThis.localStorage = globalThis.localStorage || {
  getItem: () => null,
  setItem: () => {},
  removeItem: () => {},
}
globalThis.sessionStorage = globalThis.sessionStorage || {
  getItem: () => null,
  setItem: () => {},
  removeItem: () => {},
}

const originalConsoleError = console.error
console.error = () => {}

globalThis.fetch = async (url, init = {}) => {
  const path = String(url)
  const method = String(init.method || 'GET').toUpperCase()

  if (path.endsWith('/api/semantic-models') && method === 'GET') {
    return jsonResponse({ items: [serverModel], total: 1 })
  }
  if (path.endsWith(`/api/semantic-models/${modelId}`) && method === 'GET') {
    return jsonResponse(serverModel)
  }
  if (path.endsWith('/api/datasources/datasource-store-smoke/understanding/analyze') && method === 'POST') {
    if (analyzeShouldFail) {
      return errorResponse(500, 'Analyze failed at source')
    }
    return jsonResponse(createSourceUnderstanding())
  }
  if (path.includes('/api/datasources/datasource-store-smoke/understanding/candidates/') && path.endsWith('/review') && method === 'POST') {
    return jsonResponse(createSourceUnderstanding('verified'))
  }
  if (path.endsWith('/api/datasources/datasource-store-smoke/understanding/semantic-model-draft') && method === 'POST') {
    if (createDraftShouldFail) {
      return errorResponse(500, 'Create semantic draft failed')
    }
    sourceDraftCounter += 1
    return jsonResponse({ model: normalizeServerModel({ ...createModel(), id: `${modelId}-generated-${sourceDraftCounter}` }) })
  }
  if (path.endsWith(`/api/data-models/${modelId}`) && method === 'PATCH') {
    if (patchShouldFail) {
      return errorResponse(500, 'Patch failed at API')
    }
    const patch = JSON.parse(String(init.body || '{}'))
    patchBodies.push(patch)
    serverModel = normalizeServerModel({ ...serverModel, ...patch, revision: serverModel.revision + 1 })
    return jsonResponse(serverModel)
  }
  if (path.endsWith(`/api/data-models/${modelId}/validate`) && method === 'POST') {
    validateCalls += 1
    if (validateShouldFail) {
      return errorResponse(500, 'Validation failed at API')
    }
    serverModel = normalizeServerModel({
      ...serverModel,
      status: 'Ready for Review',
      readiness: 92,
      readinessLevel: 'ready',
      readinessDetail: {
        ...serverModel.readinessDetail,
        blockers: [],
        components: serverModel.readinessDetail.components.map(component => ({ ...component, score: 90, status: 'ready' })),
      },
    })
    return jsonResponse(serverModel)
  }
  if (path.endsWith(`/api/data-models/${modelId}/publish`) && method === 'POST') {
    publishCalls += 1
    if (publishShouldFail) {
      return errorResponse(409, 'Publish blocked by validation')
    }
    serverModel = normalizeServerModel({
      ...serverModel,
      status: 'Published',
      publishedVersion: 'v3',
      draftRevision: `draft-${serverModel.revision + 1}`,
      revision: serverModel.revision + 1,
      review: { ...serverModel.review, publishedAt: '2026-08-14T14:49:20Z' },
      mcp: { ...serverModel.mcp, exposedVersion: 'v3' },
    })
    return jsonResponse(serverModel)
  }
  if (path.endsWith(`/api/data-models/${modelId}/mcp/query_metric`) && method === 'POST') {
    if (semanticQueryShouldFail) {
      return jsonResponse({
        resolvedMetric: 'paid_revenue',
        modelVersion: 'v3',
        status: 'failed',
        result: null,
        error: 'Semantic query failed at datasource',
        freshness: 'fresh 2h ago',
        lineage: ['orders.paid_amount'],
        policyDecision: 'allowed',
      })
    }
    serverModel = normalizeServerModel({
      ...serverModel,
      mcp: {
        ...serverModel.mcp,
        lastResult: {
          resolvedMetric: 'paid_revenue',
          modelVersion: 'v3',
          result: JSON.stringify([{ region: 'North', paid_revenue: 3200 }]),
          freshness: 'fresh 2h ago',
          lineage: ['orders.paid_amount', 'stores.region'],
          policyDecision: 'allowed',
        },
      },
    })
    return jsonResponse({
      resolvedMetric: 'paid_revenue',
      modelVersion: 'v3',
      result: [{ region: 'North', paid_revenue: 3200 }, { region: 'West', paid_revenue: 2400 }],
      freshness: 'fresh 2h ago',
      lineage: ['orders.paid_amount', 'stores.region'],
      policyDecision: 'allowed',
    })
  }

  return new Response(JSON.stringify({ success: false, message: `Unhandled ${method} ${path}`, data: null }), {
    status: 404,
    headers: { 'Content-Type': 'application/json' },
  })
}

const cacheDir = join(process.cwd(), 'node_modules', '.cache')
mkdirSync(cacheDir, { recursive: true })
const outfile = join(cacheDir, 'data-modeling-store-smoke.mjs')

await build({
  entryPoints: ['./src/features/data-modeling/store/useDataModelingStore.ts'],
  outfile,
  bundle: true,
  platform: 'node',
  format: 'esm',
  jsx: 'automatic',
  define: {
    'import.meta.env.VITE_IS_HOSTED': '"false"',
    'import.meta.env.VITE_IS_SELF_HOSTED': '"false"',
    'import.meta.env.VITE_GOOGLE_CLIENT_ID': '""',
  },
  external: ['react', 'react-dom'],
  logLevel: 'silent',
})

const { useDataModelingStore, selectActiveModel } = await import(pathToFileURL(outfile).href)

const store = useDataModelingStore.getState()
await store.loadModels('ready')
store.setActiveModel(modelId)

useDataModelingStore.setState(state => ({
  createDraft: {
    ...state.createDraft,
    datasourceId: 'datasource-store-smoke',
    domain: 'Sales',
    selectedTables: ['orders'],
    businessQuestions: 'Paid revenue by region',
    generated: false,
  },
  homeError: null,
}))
analyzeShouldFail = true
store.startSemanticGeneration()
await waitForHomeError('Analyze failed at source')
const analyzeFailureState = useDataModelingStore.getState()
const analyzeFailureDidNotCreate = analyzeFailureState.models.length === 1 && !analyzeFailureState.createDraft.generated
const analyzeFailureVisibleInGeneration = analyzeFailureState.generation.phase === 'idle'
  && analyzeFailureState.generation.progress === 0
  && analyzeFailureState.generation.error === 'Analyze failed at source'
analyzeShouldFail = false
useDataModelingStore.setState({ homeError: null })

createDraftShouldFail = true
store.startSemanticGeneration()
await waitForHomeError('Create semantic draft failed')
const createFailureState = useDataModelingStore.getState()
const createFailureDidNotCreate = createFailureState.models.length === 1 && !createFailureState.createDraft.generated
const createFailureVisibleInGeneration = createFailureState.generation.phase === 'idle'
  && createFailureState.generation.progress === 0
  && createFailureState.generation.error === 'Create semantic draft failed'
createDraftShouldFail = false
useDataModelingStore.setState({ homeError: null })

const persistedRunning = useDataModelingStore.persist.getOptions().partialize({
  ...useDataModelingStore.getState(),
  generation: {
    ...useDataModelingStore.getState().generation,
    phase: 'profile',
    progress: 24,
    steps: useDataModelingStore.getState().generation.steps.map((step, index) => ({
      ...step,
      status: index === 0 ? 'running' : 'pending',
    })),
    error: null,
  },
})
const persistedGenerationDoesNotRestoreRunning = persistedRunning.generation.phase === 'idle'
  && persistedRunning.generation.progress === 0
  && persistedRunning.generation.steps.every(step => step.status === 'pending')

const formulaBeforePatchFailure = selectActiveModel(useDataModelingStore.getState()).metrics[0].formula
patchShouldFail = true
store.updateMetric('paid_revenue', { formula: 'SUM(orders.paid_amount) * 999' })
await waitForHomeError('Patch failed at API')
const patchFailureModel = selectActiveModel(useDataModelingStore.getState())
const patchFailureRolledBack = patchFailureModel.metrics[0].formula === formulaBeforePatchFailure
patchShouldFail = false
useDataModelingStore.setState({ homeError: null })

const statusBeforeValidateFailure = selectActiveModel(useDataModelingStore.getState()).status
validateShouldFail = true
await store.validateModel()
const validateFailureState = useDataModelingStore.getState()
const validateFailureDidNotSucceed = validateFailureState.homeError === 'Validation failed at API'
  && selectActiveModel(validateFailureState).status === statusBeforeValidateFailure
validateShouldFail = false
useDataModelingStore.setState({ homeError: null })

const versionBeforePublishFailure = selectActiveModel(useDataModelingStore.getState()).publishedVersion
publishShouldFail = true
await store.publishModel()
const publishFailureState = useDataModelingStore.getState()
const publishFailureDidNotSucceed = publishFailureState.homeError === 'Publish blocked by validation'
  && selectActiveModel(publishFailureState).publishedVersion === versionBeforePublishFailure
publishShouldFail = false
useDataModelingStore.setState({ homeError: null })

store.updateRelationship('rel-orders-refunds-risk', {
  cardinality: 'one-to-many',
  uniqueRate: 99.1,
  orphanRate: 0.9,
  fanoutRisk: 'medium',
  validationStatus: 'valid',
  status: 'confirmed',
  validationMessage: 'Fixed by modeling refunds as a pre-aggregated order-level subquery.',
})
await flushAsync()
store.updateMetric('paid_revenue', { formula: 'SUM(orders.paid_amount) * 1.01' })
await flushAsync()
store.setMetricCertification('paid_revenue', 'certified')
await flushAsync()
store.saveExploreArtifact('query')
await flushAsync()
store.openReview()
await flushAsync()
store.updatePublishNotes('Reviewed in store smoke.')
store.markReviewed()
await flushAsync()
const savedQueryChanged = selectActiveModel(useDataModelingStore.getState()).explore.savedQueryCount > 8
const validateCallsBeforeGate = validateCalls
await store.runKnowledgeGate()
const gateStateAfterBackendRun = useDataModelingStore.getState()
const knowledgeGateUsesBackend = validateCalls === validateCallsBeforeGate + 1
  && gateStateAfterBackendRun.gate.evaluated === true
  && gateStateAfterBackendRun.homeError === null
  && !selectActiveModel(gateStateAfterBackendRun).validationLog.some(entry => entry.includes('Mock knowledge gate'))
const publishCallsBeforeKnowledgeAsset = publishCalls
await store.publishKnowledgeAsset()
const publishStateAfterBackendRun = useDataModelingStore.getState()
const knowledgePublishUsesBackend = publishCalls === publishCallsBeforeKnowledgeAsset + 1
  && publishStateAfterBackendRun.publishState === 'published'
  && !selectActiveModel(publishStateAfterBackendRun).validationLog.some(entry => entry.includes('Mock-published'))
await store.runMcpQuery()
semanticQueryShouldFail = true
await store.runMcpQuery()

const finalState = useDataModelingStore.getState()
const model = selectActiveModel(finalState)

const assertions = [
  ['analyze failure did not create model', analyzeFailureDidNotCreate],
  ['analyze failure visible in generation state', analyzeFailureVisibleInGeneration],
  ['create failure did not create model', createFailureDidNotCreate],
  ['create failure visible in generation state', createFailureVisibleInGeneration],
  ['persisted generation does not restore running state', persistedGenerationDoesNotRestoreRunning],
  ['patch failure rolled back optimistic edit', patchFailureRolledBack],
  ['validate failure did not mark model ready', validateFailureDidNotSucceed],
  ['publish failure did not advance version', publishFailureDidNotSucceed],
  ['knowledge gate used backend validate', knowledgeGateUsesBackend],
  ['knowledge asset publish used backend publish', knowledgePublishUsesBackend],
  ['model published v3', model.status === 'Published' && model.publishedVersion === 'v3'],
  ['fanout blocker cleared', model.readinessDetail.blockers.length === 0],
  ['MCP result generated', Boolean(model.mcp.lastResult?.resolvedMetric)],
  ['saved query count changed', savedQueryChanged],
  ['relationship fix persisted', patchBodies.some(body => body.relationships?.[0]?.validationStatus === 'valid')],
  ['explore artifact persisted', patchBodies.some(body => body.explore?.savedQueryCount > 8 && body.consumers?.savedQueries > 8)],
  ['review state persisted', patchBodies.some(body => body.review?.reviewed === true && body.review?.publishNotes === 'Reviewed in store smoke.')],
  ['failed query reported as error', finalState.homeError === 'Semantic query failed at datasource'],
]

const failed = assertions.filter(([, ok]) => !ok)
if (failed.length) {
  originalConsoleError(JSON.stringify({ ok: false, failed: failed.map(([name]) => name), model }, null, 2))
  process.exit(1)
}

console.log(JSON.stringify({
  ok: true,
  model: model.name,
  status: model.status,
  version: model.publishedVersion,
  readiness: model.readiness,
  mcpResult: model.mcp.lastResult,
}, null, 2))

function jsonResponse(data) {
  return new Response(JSON.stringify({ success: true, message: 'ok', data }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

function errorResponse(status, message) {
  return new Response(JSON.stringify({ success: false, message, data: null }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function flushAsync() {
  return new Promise(resolve => setTimeout(resolve, 25))
}

async function waitForHomeError(message) {
  for (let attempt = 0; attempt < 80; attempt += 1) {
    if (useDataModelingStore.getState().homeError === message) return
    await flushAsync()
  }
  throw new Error(`Timed out waiting for homeError=${message}; got ${useDataModelingStore.getState().homeError}`)
}

function normalizeServerModel(model) {
  const hasBlockedRelationship = model.relationships.some(rel => rel.validationStatus === 'blocked' && rel.status !== 'rejected')
  return {
    ...model,
    revision: Number(model.revision || 1),
    readiness: hasBlockedRelationship ? 78 : model.readiness,
    readinessLevel: hasBlockedRelationship ? 'blocked' : model.readinessLevel,
    readinessDetail: {
      ...model.readinessDetail,
      blockers: hasBlockedRelationship ? ['Orders -> Refunds fanout candidate is unresolved.'] : model.readinessDetail.blockers,
    },
  }
}

function createSourceUnderstanding(reviewStatus = 'pending') {
  return {
    datasource_id: 'datasource-store-smoke',
    datasource_name: 'Postgres sales',
    datasource_type: 'pg',
    latest_run: { status: 'completed' },
    candidates: [
      {
        id: 'schema-orders',
        candidate_type: 'schema_map',
        title: 'Orders entity',
        statement: 'Orders table can be modeled as an entity.',
        confidence: 0.9,
        evidence: [],
        structured_payload_json: { table: 'orders' },
        review_status: reviewStatus,
      },
      {
        id: 'metric-paid-revenue',
        candidate_type: 'data_truth',
        title: 'Paid revenue',
        statement: 'Paid revenue can be computed from orders.paid_amount.',
        confidence: 0.86,
        evidence: [],
        structured_payload_json: { metric_slug: 'paid_revenue' },
        review_status: reviewStatus,
      },
    ],
  }
}

function createModel() {
  return {
    id: modelId,
    name: 'Store Smoke Sales Model',
    domain: 'Sales',
    owner: 'Analytics',
    datasource: 'Postgres sales',
    datasourceId: 'datasource-store-smoke',
    status: 'Draft',
    revision: 1,
    draftRevision: 'draft-1',
    publishedVersion: 'v2',
    readiness: 78,
    readinessLevel: 'blocked',
    driftAlerts: 0,
    consumers: { agents: 1, mcp: 1, skills: 0, dashboards: 1, savedQueries: 8 },
    updatedAt: '2026-08-14T14:00:00Z',
    description: 'Store smoke fixture',
    entities: [
      { id: 'orders', name: 'orders', businessName: 'Orders', table: 'orders', description: 'Orders', primaryKey: 'order_id', fields: [] },
      { id: 'refunds', name: 'refunds', businessName: 'Refunds', table: 'refunds', description: 'Refunds', primaryKey: 'refund_id', fields: [] },
    ],
    relationships: [
      {
        id: 'rel-orders-refunds-risk',
        fromEntity: 'orders',
        toEntity: 'refunds',
        label: 'Orders -> Refunds candidate',
        joinFields: [{ from: 'order_id', to: 'order_id' }],
        cardinality: 'one-to-many',
        fkEvidence: 'Refund rows map to orders but can duplicate order-level metrics.',
        uniqueRate: 72,
        orphanRate: 1.8,
        fanoutRisk: 'high',
        validationStatus: 'blocked',
        status: 'candidate',
        validationMessage: 'High fanout risk.',
      },
    ],
    metrics: [
      {
        id: 'paid_revenue',
        name: 'paid_revenue',
        businessName: 'Paid Revenue',
        definition: 'Paid order amount.',
        kind: 'measure',
        formula: 'SUM(orders.paid_amount)',
        filter: "orders.status = 'PAID'",
        timeField: 'orders.paid_at',
        defaultGrain: 'month',
        dimensions: ['region'],
        unit: '$',
        owner: 'Analytics',
        certification: 'draft',
        lineage: ['orders.paid_amount'],
        preview: {
          currentValue: 'Run query',
          trend: '',
          breakdown: [],
          explanation: 'Sums paid order amount.',
          sql: 'SELECT SUM(orders.paid_amount) FROM orders',
          validation: 'Draft validation.',
        },
      },
    ],
    dimensions: [{ id: 'region', name: 'Region', entityId: 'stores', field: 'region', description: 'Store region' }],
    calculatedFields: [],
    suggestions: [],
    readinessDetail: {
      score: 78,
      level: 'blocked',
      components: [
        { id: 'structural', name: 'Structural completeness', score: 88, status: 'ready' },
        { id: 'semantic', name: 'Semantic completeness', score: 80, status: 'warning' },
        { id: 'query', name: 'Query correctness', score: 55, status: 'blocked' },
      ],
      reliableQuestions: ['What is paid revenue by region?'],
      unreliableQuestions: ['What is refund rate by order?'],
      blockers: ['Orders -> Refunds fanout candidate is unresolved.'],
      warnings: [],
    },
    explore: {
      metricId: 'paid_revenue',
      dimensionId: 'region',
      grain: 'month',
      timeRange: '90d',
      filter: '',
      viewMode: 'trend',
      savedQueryCount: 8,
      dashboardAdds: 0,
      skillDrafts: 0,
      confirmedExamples: 0,
    },
    review: { opened: false, reviewed: false, publishNotes: 'Smoke publish' },
    mcp: {
      exposedVersion: 'v2',
      consumerIdentity: 'smoke-client',
      rawSqlFallback: false,
      allowedMetrics: ['paid_revenue'],
      allowedDimensions: ['region'],
    },
    validationLog: [],
  }
}
