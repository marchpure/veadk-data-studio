import { writeFileSync, mkdirSync } from 'node:fs'

const baseURL = process.env.BASE_URL || 'http://127.0.0.1:18084'
const email = process.env.E2E_EMAIL || 'admin@example.com'
const password = process.env.E2E_PASSWORD || 'Passw0rd123!'
const commit = process.env.COMMIT || 'local'
const datasourceName = process.env.DATASOURCE_NAME || `DM Journey External Postgres ${commit}`
const modelId = process.env.MODEL_ID || `dm-journey-${commit}`
const modelName = process.env.MODEL_NAME || `DM Journey Sales Model ${commit}`
const evidenceDir = process.env.EVIDENCE_DIR || `./tmp-data-modeling-api-${commit}`
const pgHost = process.env.PG_HOST || '172.17.0.5'
const pgPort = Number(process.env.PG_PORT || 5432)
const pgUser = process.env.PG_USER || 'journey_user'
const pgPassword = process.env.PG_PASSWORD || 'journey_pass'
const pgDatabase = process.env.PG_DATABASE || 'journey_db'
const pgSchema = process.env.PG_SCHEMA || 'sales'

mkdirSync(evidenceDir, { recursive: true })

let token = ''
const evidence = {
  baseURL,
  commit,
  datasourceName,
  modelId,
  steps: [],
}

function record(step, data = {}) {
  evidence.steps.push({ step, at: new Date().toISOString(), ...data })
}

async function api(path, options = {}) {
  const response = await fetch(`${baseURL}${path}`, {
    ...options,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(options.headers || {}),
    },
  })
  const text = await response.text()
  let body
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    body = { raw: text }
  }
  if (!response.ok) {
    throw new Error(`${options.method || 'GET'} ${path} failed: ${response.status} ${JSON.stringify(body)}`)
  }
  return body?.data ?? body
}

async function main() {
  const login = await fetch(`${baseURL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ username: email, password }),
  })
  const loginBody = await login.json()
  if (!login.ok || !loginBody?.success) {
    throw new Error(`Login failed: ${login.status} ${JSON.stringify(loginBody)}`)
  }
  token = loginBody.data.access_token
  record('login', { ok: true })

  const connection = await api('/api/connections', {
    method: 'POST',
    body: JSON.stringify({
      type: 'pg',
      name: datasourceName,
      connection_obj: {
        host: pgHost,
        port: pgPort,
        database: pgDatabase,
        user: pgUser,
        password: pgPassword,
        schema: pgSchema,
      },
    }),
  })
  const connectionId = connection.id
  record('create_connection', {
    connectionId,
    schemaTables: Object.keys(connection.database_schema?.schema || {}),
  })

  const datasources = await api('/api/datasources')
  const datasource = datasources.items.find(item => item.connection_id === connectionId || item.name === datasourceName)
  if (!datasource) {
    throw new Error(`Created connection ${connectionId} did not appear in /api/datasources`)
  }
  record('datasource_listed', { datasourceId: datasource.id, sourceType: datasource.source_type, type: datasource.type })

  const schema = await api(`/api/datasources/${datasource.id}/schema`)
  record('schema_loaded', { tables: Object.keys(schema.schema || schema || {}).slice(0, 12) })

  const understanding = await api(`/api/datasources/${datasource.id}/understanding/analyze`, {
    method: 'POST',
    body: JSON.stringify({ refresh_schema: false, scope: ['orders', 'order_items', 'customers', 'products', 'stores'] }),
  })
  const candidates = understanding.candidates || []
  const selected = candidates.filter(candidate => ['schema_map', 'relationship', 'data_truth'].includes(candidate.candidate_type))
  if (selected.length < 8) {
    throw new Error(`Expected schema/relationship/metric candidates, got ${selected.length}`)
  }
  record('analyze', {
    runStatus: understanding.latest_run?.status,
    candidateCount: candidates.length,
    selectedCount: selected.length,
    candidateTypes: [...new Set(candidates.map(item => item.candidate_type))],
  })

  const acceptedIds = []
  const rejected = selected.find(item => item.candidate_type === 'data_truth' && /products_price/.test(String(item.structured_payload_json?.metric_slug)))
  for (const candidate of selected) {
    if (rejected && candidate.id === rejected.id) {
      await api(`/api/datasources/${datasource.id}/understanding/candidates/${candidate.id}/review`, {
        method: 'POST',
        body: JSON.stringify({ action: 'reject', note: 'Reject product price as a sales KPI for this journey.' }),
      })
      continue
    }
    const action = candidate.candidate_type === 'data_truth' && /orders_paid_amount/.test(String(candidate.structured_payload_json?.metric_slug))
      ? {
          action: 'edit',
          structured_payload: {
            ...candidate.structured_payload_json,
            business_name: 'Paid Revenue',
            definition: 'Total paid order amount from the live Postgres sales schema.',
            unit: 'USD',
          },
          note: 'Edited metric definition during production journey.',
        }
      : { action: 'accept' }
    await api(`/api/datasources/${datasource.id}/understanding/candidates/${candidate.id}/review`, {
      method: 'POST',
      body: JSON.stringify(action),
    })
    acceptedIds.push(candidate.id)
  }
  record('review_candidates', { accepted: acceptedIds.length, rejected: rejected?.id || null })

  const draftPayload = await api(`/api/datasources/${datasource.id}/understanding/semantic-model-draft`, {
    method: 'POST',
    body: JSON.stringify({
      model_id: modelId,
      name: modelName,
      domain: 'Sales / Orders',
      owner: 'Data Team',
      candidate_ids: acceptedIds,
    }),
  })
  let model = draftPayload.model
  const paidRevenue = model.metrics.find(item => item.id === 'orders_paid_amount')
  if (!paidRevenue?.dimensions?.length) {
    throw new Error('Generated orders_paid_amount metric has no queryable dimensions')
  }
  record('create_semantic_draft', {
    metricCount: model.metrics.length,
    dimensionCount: model.dimensions.length,
    relationshipCount: model.relationships.length,
    paidRevenueDimensions: paidRevenue.dimensions,
  })

  const dimensionPatch = model.dimensions.some(item => item.id === 'orders_paid_flag')
    ? model.dimensions
    : [
        ...model.dimensions,
        {
          id: 'orders_paid_flag',
          name: 'Orders Paid Flag',
          entityId: 'orders',
          field: 'status',
          description: 'Calculated field placeholder for paid order filtering in this journey.',
        },
      ]
  model = await api(`/api/data-models/${modelId}`, {
    method: 'PATCH',
    body: JSON.stringify({
      expected_revision: model.revision,
      metrics: model.metrics.map(metric => metric.id === 'orders_paid_amount'
        ? {
            ...metric,
            businessName: 'Paid Revenue',
            definition: 'Total paid amount for orders in the live Postgres sales schema.',
            unit: 'USD',
            certification: 'certified',
          }
        : metric),
      dimensions: dimensionPatch,
      calculatedFields: [
        ...(model.calculatedFields || []),
        {
          id: 'orders_paid_flag_calc',
          name: 'Orders Paid Flag Calc',
          entityId: 'orders',
          expression: "orders.status = 'paid'",
          description: 'Calculated field added during production journey to verify persistence and published snapshots.',
        },
      ],
    }),
  })
  const calculatedField = model.calculatedFields?.find(item => item.id === 'orders_paid_flag_calc')
  if (!calculatedField || calculatedField.expression !== "orders.status = 'paid'") {
    throw new Error('Calculated field was not returned after PATCH')
  }
  record('edit_metric_dimension_calculated_field', {
    revision: model.revision,
    status: model.status,
    calculatedField: calculatedField.id,
  })

  const conflict = await fetch(`${baseURL}/api/data-models/${modelId}`, {
    method: 'PATCH',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ expected_revision: 1, name: 'Stale overwrite attempt' }),
  })
  if (conflict.status !== 409) {
    throw new Error(`Expected stale revision conflict, got ${conflict.status}`)
  }
  record('revision_conflict', { status: conflict.status })

  model = await api(`/api/data-models/${modelId}/validate`, { method: 'POST' })
  if (model.status === 'Validated' && model.readinessDetail?.blockers?.length) {
    throw new Error('Validation reported success with blockers')
  }
  if (!['Ready for Review', 'Published'].includes(model.status)) {
    throw new Error(`Validation did not reach reviewable state: ${model.status}`)
  }
  record('validate', { status: model.status, readiness: model.readiness, blockers: model.readinessDetail?.blockers || [] })

  model = await api(`/api/data-models/${modelId}/publish`, { method: 'POST' })
  if (model.status !== 'Published' || model.publishedVersion === 'v0') {
    throw new Error(`Publish failed to create immutable version: ${model.status} ${model.publishedVersion}`)
  }
  record('publish', { status: model.status, version: model.publishedVersion })

  const query = await api(`/api/data-models/${modelId}/mcp/query_metric`, {
    method: 'POST',
    body: JSON.stringify({ metric: 'orders_paid_amount', dimension: paidRevenue.dimensions[0], limit: 20 }),
  })
  if (query.status !== 'completed' || !Array.isArray(query.result) || query.result.length === 0) {
    throw new Error(`query_metric did not return live rows: ${JSON.stringify(query)}`)
  }
  record('query_metric', {
    status: query.status,
    modelVersion: query.modelVersion,
    rowCount: query.result.length,
    firstRow: query.result[0],
    sql: query.sql,
  })

  const reloaded = await api(`/api/semantic-models/${modelId}`)
  if (reloaded.publishedVersion !== model.publishedVersion || !reloaded.mcp?.lastResult) {
    throw new Error('Reloaded model did not retain publish/query state')
  }
  const reloadedCalculatedField = reloaded.calculatedFields?.find(item => item.id === 'orders_paid_flag_calc')
  if (!reloadedCalculatedField || reloadedCalculatedField.expression !== "orders.status = 'paid'") {
    throw new Error('Reloaded model did not retain calculated field state')
  }
  record('reload', {
    version: reloaded.publishedVersion,
    hasLastResult: Boolean(reloaded.mcp.lastResult),
    calculatedField: reloadedCalculatedField.id,
  })

  const unpublished = await api(`/api/datasources/${datasource.id}/understanding/semantic-model-draft`, {
    method: 'POST',
    body: JSON.stringify({
      model_id: `${modelId}-draft-only`,
      name: `${modelName} Draft Only`,
      domain: 'Sales / Orders',
      owner: 'Data Team',
      candidate_ids: acceptedIds,
    }),
  })
  const draftOnlyQuery = await fetch(`${baseURL}/api/data-models/${unpublished.model.id}/mcp/query_metric`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ metric: 'orders_paid_amount', dimension: paidRevenue.dimensions[0] }),
  })
  if (draftOnlyQuery.status !== 409) {
    throw new Error(`Draft-only model should not be exposed to MCP, got ${draftOnlyQuery.status}`)
  }
  record('draft_not_exposed_to_mcp', { status: draftOnlyQuery.status })

  writeFileSync(`${evidenceDir}/result.json`, `${JSON.stringify({ ok: true, ...evidence }, null, 2)}\n`)
  console.log(JSON.stringify({ ok: true, ...evidence }, null, 2))
}

main().catch(error => {
  const failed = { ok: false, error: error.message, ...evidence }
  writeFileSync(`${evidenceDir}/result.json`, `${JSON.stringify(failed, null, 2)}\n`)
  console.error(JSON.stringify(failed, null, 2))
  process.exit(1)
})
