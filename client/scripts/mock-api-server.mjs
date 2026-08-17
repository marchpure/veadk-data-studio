import http from 'node:http'

const port = Number(process.env.MOCK_API_PORT || 5174)

const json = (res, status, payload) => {
  res.writeHead(status, {
    'content-type': 'application/json',
    'access-control-allow-origin': '*',
    'access-control-allow-methods': 'GET,POST,PATCH,OPTIONS',
    'access-control-allow-headers': 'content-type,authorization,x-active-tenant',
  })
  res.end(JSON.stringify(payload))
}

const ok = data => ({ success: true, message: 'ok', data })

const modelId = 'integration-sales-pg-1786717080'
let semanticModel = createSemanticModel()
let dashboardVersion = createDashboardVersion()
let dashboardAsset = createDashboardAsset()

const server = http.createServer((req, res) => {
  if (req.method === 'OPTIONS') {
    res.writeHead(204, {
      'access-control-allow-origin': '*',
      'access-control-allow-methods': 'GET,POST,PATCH,OPTIONS',
      'access-control-allow-headers': 'content-type,authorization,x-active-tenant',
    })
    res.end()
    return
  }

  const url = new URL(req.url ?? '/', `http://127.0.0.1:${port}`)
  if (url.pathname === '/api/app/config') {
    json(res, 200, ok({
      features: {
        worker_features_enabled: false,
        external_sharing_enabled: false,
        notebook_import_enabled: false,
        public_registration_enabled: false,
        local_auth_enabled: true,
        invitation_only: false,
        google_oauth_enabled: false,
        enterprise_licensed: false,
        team_sharing_enabled: false,
      },
      local_bootstrap: {
        user_id: '00000000-0000-0000-0000-000000000001',
        email: 'demo@local',
        full_name: 'Demo User',
        tenant_id: '00000000-0000-0000-0000-000000000001',
      },
    }))
    return
  }

  if (url.pathname === '/api/auth/login') {
    semanticModel = createSemanticModel()
    dashboardVersion = createDashboardVersion()
    dashboardAsset = createDashboardAsset()
    json(res, 200, ok({ access_token: 'mock-token', token_type: 'bearer' }))
    return
  }

  if (url.pathname === '/api/schedules') {
    json(res, 200, ok([]))
    return
  }

  if (url.pathname === '/api/scopes/all') {
    json(res, 200, ok({
      tenants: [{
        tenant_id: '00000000-0000-0000-0000-000000000001',
        tenant_name: 'Local Demo',
        role: 'owner',
        scopes: ['*'],
      }],
    }))
    return
  }

  if (url.pathname === '/api/tenants') {
    json(res, 200, ok([{ tenant_id: '00000000-0000-0000-0000-000000000001', tenant_name: 'Local Demo', role: 'owner', scopes: ['*'] }]))
    return
  }

  if (url.pathname === '/api/user-preferences') {
    json(res, 200, ok({}))
    return
  }

  if (url.pathname === '/api/connections' || url.pathname === '/api/datasources') {
    json(res, 200, ok({ items: [], total: 0 }))
    return
  }

  if (url.pathname === '/api/sources/overview') {
    json(res, 200, ok({
      items: [
        {
          id: 'datasource-sales-pg',
          name: 'Modeling Sales Postgres E2E',
          family: 'databases',
          provider: 'postgres',
          source_kind: 'connection',
          status: 'Ready',
          resource_type: 'postgres',
          modeling_status: 'supported',
          modeling_mode: 'relational',
          modeling_reason: 'Schema/profile evidence can be used to generate a production semantic model.',
          modeling_can_load_profile: true,
          modeling_next_action: 'Generate semantic model',
          modeling_evidence_summary: '4 tables; parse completed; context indexed',
          parsed_asset_counts: { blocks: 0, tables: 4, files: 0, evidence: 8 },
          parse_status: 'completed',
          context_index_status: 'indexed',
          consumer_counts: { semantic_models: 1, dashboards: 1, notebooks: 0, mcp_tools: 1 },
          next_actions: ['Generate semantic model'],
          updated_at: '2026-08-17T09:00:00Z',
        },
        {
          id: 'source-policy-docs',
          name: 'Revenue Policy Docs',
          family: 'documents',
          provider: 'feishu_doc',
          source_kind: 'source_resource',
          status: 'Ready',
          resource_type: 'feishu_doc',
          modeling_status: 'context_only',
          modeling_mode: 'context_assisted',
          modeling_reason: 'Indexed context can support definitions, policies, and evidence, but cannot be the production fact source for metrics.',
          modeling_can_load_profile: false,
          modeling_next_action: 'Use as evidence only',
          parsed_asset_counts: { blocks: 12, tables: 0, files: 1, evidence: 10 },
          parse_status: 'completed',
          context_index_status: 'indexed',
          consumer_counts: { semantic_models: 0, dashboards: 0, notebooks: 0, mcp_tools: 0 },
          next_actions: ['Use as evidence'],
          updated_at: '2026-08-16T12:00:00Z',
        },
      ],
      total: 2,
    }))
    return
  }

  if (url.pathname === '/api/datasources/datasource-sales-pg/understanding') {
    json(res, 200, ok(createUnderstanding()))
    return
  }

  if (url.pathname === '/api/datasources/datasource-sales-pg/understanding/analyze') {
    json(res, 200, ok(createUnderstanding()))
    return
  }

  if (url.pathname.includes('/api/datasources/datasource-sales-pg/understanding/candidates/') && url.pathname.endsWith('/review')) {
    json(res, 200, ok(createUnderstanding('verified')))
    return
  }

  if (url.pathname === '/api/datasources/datasource-sales-pg/understanding/semantic-model-draft') {
    json(res, 200, ok({ model: semanticModel }))
    return
  }

  if (url.pathname === '/api/semantic-models') {
    json(res, 200, ok({ items: [semanticModel], total: 1 }))
    return
  }

  if (url.pathname === `/api/semantic-models/${modelId}`) {
    json(res, 200, ok(semanticModel))
    return
  }

  if (url.pathname === `/api/data-models/${modelId}` && req.method === 'PATCH') {
    readBody(req).then(body => {
      semanticModel = {
        ...semanticModel,
        ...body,
        revision: semanticModel.revision + 1,
      }
      json(res, 200, ok(semanticModel))
    })
    return
  }

  if (url.pathname === `/api/data-models/${modelId}/validate`) {
    semanticModel = {
      ...semanticModel,
      readiness: 92,
      readinessLevel: 'ready',
      readinessDetail: { ...semanticModel.readinessDetail, score: 92, level: 'ready', blockers: [], warnings: [] },
      gate: { score: 100, passed: 4, total: 4, blockers: [] },
      publishState: 'draft',
    }
    json(res, 200, ok(semanticModel))
    return
  }

  if (url.pathname === `/api/data-models/${modelId}/publish`) {
    semanticModel = {
      ...semanticModel,
      status: 'Published',
      publishedVersion: 'v3',
      publishState: 'published',
      review: { ...semanticModel.review, publishedAt: '2026-08-17T10:00:00Z' },
      mcp: { ...semanticModel.mcp, exposedVersion: 'v3' },
    }
    json(res, 200, ok(semanticModel))
    return
  }

  if (url.pathname === `/api/data-models/${modelId}/mcp/query_metric`) {
    json(res, 200, ok({
      status: 'success',
      resolvedMetric: 'paid_revenue',
      modelVersion: semanticModel.publishedVersion,
      result: [{ region: 'North', paid_revenue: 3200 }, { region: 'West', paid_revenue: 2400 }],
      freshness: 'fresh 2h ago',
      lineage: ['orders.paid_amount', 'stores.region'],
      policyDecision: 'allowed',
    }))
    return
  }

  if (url.pathname === '/api/dashboard-assets') {
    json(res, 200, ok({ items: [dashboardAsset], total: 1 }))
    return
  }

  if (url.pathname === '/api/dashboard-assets/dashboard-sales') {
    json(res, 200, ok({ ...dashboardAsset, versions: [dashboardVersionSummary()] }))
    return
  }

  if (url.pathname === '/api/dashboard-assets/dashboard-sales/versions/1') {
    json(res, 200, ok(dashboardVersion))
    return
  }

  if (url.pathname === '/api/dashboard-assets/dashboard-sales/query' || url.pathname === '/api/dashboard-assets/dashboard-sales/preview') {
    json(res, 200, ok(createDashboardRun(url.pathname.endsWith('/preview'))))
    return
  }

  if (url.pathname === '/api/dashboard-assets/dashboard-sales/audit') {
    json(res, 200, ok({ items: [] }))
    return
  }

  if (url.pathname === '/api/llm-connections') {
    json(res, 200, ok({ items: [], total: 0 }))
    return
  }

  if (url.pathname === '/api/llm-connections/models') {
    json(res, 200, { models_by_provider: { openai: ['gpt-4o-mini'] } })
    return
  }

  if (url.pathname === '/api/notebooks') {
    json(res, 200, ok({ items: [], total: 0 }))
    return
  }

  if (url.pathname === '/api/mcp/keys') {
    json(res, 200, ok([]))
    return
  }

  if (url.pathname === '/api/skill-suggestions/pending-count') {
    json(res, 200, ok(0))
    return
  }

  if (url.pathname.startsWith('/api/')) {
    json(res, 200, ok([]))
    return
  }

  json(res, 404, { success: false, message: 'not found' })
})

server.listen(port, '127.0.0.1', () => {
  console.log(`mock api listening on http://127.0.0.1:${port}`)
})

process.on('SIGTERM', () => server.close(() => process.exit(0)))
process.on('SIGINT', () => server.close(() => process.exit(0)))

function readBody(req) {
  return new Promise(resolve => {
    let body = ''
    req.on('data', chunk => { body += chunk })
    req.on('end', () => {
      try {
        resolve(body ? JSON.parse(body) : {})
      } catch {
        resolve({})
      }
    })
  })
}

function createUnderstanding(reviewStatus = 'pending') {
  return {
    datasource_id: 'datasource-sales-pg',
    datasource_name: 'Modeling Sales Postgres E2E',
    datasource_type: 'postgres',
    profile: { schema: 'sales', profile_coverage: 94 },
    overview: { schema: 'sales' },
    latest_run: { status: 'completed' },
    resources: [
      { id: 'orders', name: 'sales.orders', resource_type: 'database_table' },
      { id: 'refunds', name: 'sales.refunds', resource_type: 'database_table' },
      { id: 'stores', name: 'sales.stores', resource_type: 'database_table' },
      { id: 'customers', name: 'sales.customers', resource_type: 'database_table' },
    ],
    candidates: [
      {
        id: 'schema-orders',
        candidate_type: 'schema_map',
        title: 'Orders fact table',
        statement: 'Orders is the main fact table for paid revenue.',
        confidence: 0.94,
        evidence: [{ fragment_type: 'schema', text: 'orders.order_id primary key with paid_amount and paid_at.' }],
        structured_payload_json: {
          table: 'orders',
          category: 'fact',
          primary_key: ['order_id'],
          fields: [
            { name: 'order_id', type: 'text', role: 'id' },
            { name: 'paid_amount', type: 'numeric', role: 'amount' },
            { name: 'paid_at', type: 'timestamp', role: 'time' },
            { name: 'store_id', type: 'text', role: 'id' },
          ],
        },
        review_status: reviewStatus,
      },
      {
        id: 'profile-orders',
        candidate_type: 'data_profile',
        title: 'Orders profile',
        statement: 'Orders profile has paid revenue evidence.',
        confidence: 0.9,
        evidence: [],
        structured_payload_json: {
          table: 'orders',
          row_count: 240000,
          sample_rows: [{ order_id: 'o1', paid_amount: 120, paid_at: '2026-08-16', store_id: 's1' }],
          columns: [
            { name: 'order_id', type: 'text', role: 'id' },
            { name: 'paid_amount', type: 'numeric', role: 'amount' },
            { name: 'paid_at', type: 'timestamp', role: 'time' },
            { name: 'store_id', type: 'text', role: 'id' },
          ],
        },
        review_status: reviewStatus,
      },
      {
        id: 'schema-refunds',
        candidate_type: 'schema_map',
        title: 'Refunds table',
        statement: 'Refunds must be aggregated before joining orders.',
        confidence: 0.88,
        evidence: [{ fragment_type: 'schema', text: 'refunds.order_id can repeat.' }],
        structured_payload_json: {
          table: 'refunds',
          category: 'fact',
          primary_key: ['refund_id'],
          fields: [
            { name: 'refund_id', type: 'text', role: 'id' },
            { name: 'order_id', type: 'text', role: 'id' },
            { name: 'amount', type: 'numeric', role: 'amount' },
          ],
        },
        review_status: reviewStatus,
      },
      {
        id: 'profile-refunds',
        candidate_type: 'data_profile',
        title: 'Refunds profile',
        statement: 'Refund rows fan out by order.',
        confidence: 0.86,
        evidence: [],
        structured_payload_json: {
          table: 'refunds',
          row_count: 4200,
          sample_rows: [{ refund_id: 'r1', order_id: 'o1', amount: 12 }],
          columns: [
            { name: 'refund_id', type: 'text', role: 'id' },
            { name: 'order_id', type: 'text', role: 'id' },
            { name: 'amount', type: 'numeric', role: 'amount' },
          ],
        },
        review_status: reviewStatus,
      },
      {
        id: 'metric-paid-revenue',
        candidate_type: 'data_truth',
        title: 'Paid Revenue',
        statement: 'Paid Revenue should use paid order amount net of refunds.',
        confidence: 0.9,
        evidence: [{ fragment_type: 'doc', text: 'Revenue Playbook defines paid revenue net of refunds.' }],
        structured_payload_json: { metric_slug: 'paid_revenue' },
        review_status: reviewStatus,
      },
    ],
  }
}

function createSemanticModel() {
  return {
    id: modelId,
    name: 'Integration Sales Postgres Model',
    domain: 'Sales / Orders',
    owner: 'Data Team',
    datasource: 'Modeling Sales Postgres E2E',
    datasourceId: 'datasource-sales-pg',
    status: 'Draft',
    revision: 1,
    draftRevision: 'draft-7',
    publishedVersion: 'v2',
    readiness: 72,
    readinessLevel: 'blocked',
    driftAlerts: 0,
    consumers: { agents: 2, mcp: 1, skills: 1, dashboards: 1, savedQueries: 3 },
    updatedAt: '2026-08-17T09:00:00Z',
    description: 'Business semantic model for orders, revenue, refunds, and store performance.',
    entities: [
      { id: 'orders', name: 'orders', businessName: 'Orders', table: 'orders', description: 'Orders fact', primaryKey: 'order_id', fields: [{ name: 'order_id', sourceField: 'order_id', type: 'text', role: 'id' }, { name: 'paid_at', sourceField: 'paid_at', type: 'timestamp', role: 'time' }] },
      { id: 'refunds', name: 'refunds', businessName: 'Refunds', table: 'refunds', description: 'Refund fact', primaryKey: 'refund_id', fields: [{ name: 'refund_id', sourceField: 'refund_id', type: 'text', role: 'id' }, { name: 'order_id', sourceField: 'order_id', type: 'text', role: 'id' }] },
      { id: 'stores', name: 'stores', businessName: 'Stores', table: 'stores', description: 'Store dimension', primaryKey: 'store_id', fields: [{ name: 'store_id', sourceField: 'store_id', type: 'text', role: 'id' }, { name: 'region', sourceField: 'region', type: 'text', role: 'attribute' }] },
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
        validationMessage: 'High fanout risk: aggregate refunds by order_id before joining.',
      },
      {
        id: 'rel-orders-stores',
        fromEntity: 'orders',
        toEntity: 'stores',
        label: 'Orders -> Stores',
        joinFields: [{ from: 'store_id', to: 'store_id' }],
        cardinality: 'many-to-one',
        fkEvidence: 'Every paid order maps to one store.',
        uniqueRate: 99.8,
        orphanRate: 0.1,
        fanoutRisk: 'low',
        validationStatus: 'valid',
        status: 'confirmed',
        validationMessage: 'Store dimension join is safe.',
      },
    ],
    metrics: [
      {
        id: 'paid_revenue',
        name: 'paid_revenue',
        businessName: 'Paid Revenue',
        definition: 'Paid order amount net of refunds.',
        kind: 'measure',
        formula: 'SUM(orders.paid_amount - refunds.amount)',
        filter: "orders.status = 'PAID'",
        timeField: 'orders.paid_at',
        defaultGrain: 'month',
        dimensions: ['region'],
        unit: '$',
        owner: 'Data Team',
        certification: 'draft',
        lineage: ['orders.paid_amount', 'refunds.amount', 'stores.region'],
        preview: {
          currentValue: '$320K',
          trend: '+8.4%',
          breakdown: [{ label: 'North', value: '$160K', delta: '+6%' }, { label: 'West', value: '$120K', delta: '+9%' }],
          explanation: 'Aggregates paid order amount net of refunds.',
          sql: 'select sum(paid_amount - refund_amount) from orders',
          validation: 'Fanout guard required.',
        },
      },
    ],
    dimensions: [{ id: 'region', name: 'Region', entityId: 'stores', field: 'region', description: 'Store operating region.' }],
    calculatedFields: [],
    suggestions: [
      { id: 'sug-paid-revenue', type: 'metric', title: 'Confirm Paid Revenue', recommendation: 'Use paid order amount net of refunds.', confidence: 0.9, evidence: [{ label: 'doc', detail: 'Revenue Playbook' }], validation: 'Needs fanout guard', status: 'pending' },
      { id: 'sug-pii', type: 'policy', title: 'Mask PII fields', recommendation: 'Exclude customer contact fields from semantic consumers.', confidence: 0.95, evidence: [{ label: 'policy', detail: 'Privacy Rules' }], validation: 'Policy match', status: 'accepted' },
    ],
    readinessDetail: {
      score: 72,
      level: 'blocked',
      components: [
        { id: 'structure', name: 'Structural completeness', score: 85, status: 'ready' },
        { id: 'semantic', name: 'Semantic completeness', score: 72, status: 'warning' },
        { id: 'query', name: 'Query correctness', score: 58, status: 'blocked' },
      ],
      reliableQuestions: ['What is paid revenue by region?'],
      unreliableQuestions: ['What is refund-adjusted revenue by segment?'],
      blockers: ['Refund fanout risk blocks publish.'],
      warnings: ['Paid Revenue certification is draft.'],
    },
    gate: {
      score: 50,
      passed: 2,
      total: 4,
      blockers: [
        'Failed: Dashboard KPI still references gross_amount while the semantic model exposes paid_revenue after refunds.',
        'Failed: Refunds can duplicate order lines unless refunds are pre-aggregated by order_id.',
      ],
    },
    publishState: 'blocked',
    explore: { metricId: 'paid_revenue', dimensionId: 'region', grain: 'month', timeRange: '90d', filter: '', viewMode: 'trend', savedQueryCount: 3, dashboardAdds: 1, skillDrafts: 0, confirmedExamples: 2 },
    review: { opened: false, reviewed: false, publishNotes: 'Ready after gate pass.' },
    mcp: { exposedVersion: 'v2', consumerIdentity: 'MCP semantic client', rawSqlFallback: false, allowedMetrics: ['paid_revenue'], allowedDimensions: ['region'] },
    validationLog: ['Draft loaded from v2 semantic contract.', 'Profile refreshed at 2026-08-17 09:00.'],
  }
}

function dashboardVersionSummary() {
  return {
    id: 'dashboard-sales-v1',
    asset_id: 'dashboard-sales',
    notebook_id: 'notebook-sales',
    version_num: 1,
    manifest_schema_version: 'dashboard.manifest.v1',
    content_hash: 'hash-dashboard-sales-v1',
    status: 'published',
    created_by: 'data-team',
    actor_type: 'user',
    change_summary: 'Initial governed dashboard',
    pinned_model_versions: { [modelId]: 'v2' },
    pinned_source_snapshots: [],
    validation_result: { valid: true, blockers: [], warnings: [], validated_at: '2026-08-17T09:00:00Z', semantic_diff: { warnings: [], blockers: [] } },
    renderer_version: 'mock',
    migration_state: 'structured',
    is_published_immutable: true,
    created_at: '2026-08-17T09:00:00Z',
  }
}

function createDashboardAsset() {
  return {
    id: 'dashboard-sales',
    tenant_id: 'tenant-demo',
    notebook_id: 'notebook-sales',
    slug: 'sales-performance',
    name: 'Sales Performance Dashboard',
    description: 'Revenue dashboard bound to the sales semantic model.',
    owner_id: 'data-team',
    tags: ['sales'],
    lifecycle: 'published',
    current_draft_version_id: 'dashboard-sales-v1',
    published_version_id: 'dashboard-sales-v1',
    access_policy: {},
    freshness_policy: { max_age_hours: 4 },
    consumer_summary: { dashboards: 1 },
    health_summary: { freshness: 'fresh 2h ago', semantic_diff: { warnings: [], blockers: [] } },
    etag: 'dashboard-etag-1',
    created_at: '2026-08-17T09:00:00Z',
    updated_at: '2026-08-17T09:00:00Z',
  }
}

function createDashboardVersion() {
  return {
    ...dashboardVersionSummary(),
    manifest: {
      schema_version: 'dashboard.manifest.v1',
      dashboard_id: 'dashboard-sales',
      title: 'Sales Performance Dashboard',
      description: 'Revenue by region with governed semantic bindings.',
      audience: ['Revenue Operations'],
      semantic_bindings: [{ id: 'sales-model', model_slug: modelId, model_version: 'v2', readiness: 'blocked', allowed_metrics: ['paid_revenue'], allowed_dimensions: ['region'] }],
      data_views: [{
        id: 'paid-revenue-by-region',
        kind: 'semantic_metric',
        question: 'Paid revenue by region',
        output_schema: [{ name: 'region', data_type: 'string' }, { name: 'paid_revenue', data_type: 'number', unit: '$' }],
        semantic_metric: { semantic_binding_id: 'sales-model', metric: 'paid_revenue', dimensions: ['region'], grain: 'month' },
        evidence: [{ id: 'doc-1', kind: 'doc', title: 'Revenue Playbook' }],
        lineage: [{ id: 'lin-1', kind: 'table', name: 'orders', ref: 'orders' }],
      }],
      filters: [{ id: 'region-filter', label: 'Region', source: 'semantic_field', field: 'region', filter_type: 'enum', operators: ['eq'], affected_data_view_ids: ['paid-revenue-by-region'], default_value: '', required: false, domain: ['North', 'West'], timezone: null }],
      layout: { sections: [{ id: 'main', title: 'Overview', tile_ids: ['kpi-paid-revenue', 'table-region'] }] },
      tiles: [
        { id: 'kpi-paid-revenue', title: 'Paid Revenue', tile_type: 'kpi', business_question: 'How much paid revenue did we book?', data_view_id: 'paid-revenue-by-region', accessible_fallback: { summary: 'Paid revenue KPI' } },
        { id: 'table-region', title: 'Paid Revenue by Region', tile_type: 'table', business_question: 'Which regions drive revenue?', data_view_id: 'paid-revenue-by-region', accessible_fallback: { table_fields: ['region', 'paid_revenue'] } },
      ],
      actions: [],
      freshness_policy: { max_age_hours: 4 },
      access_policy: { pii: 'excluded' },
      provenance: { source: 'semantic model' },
      migration: { state: 'structured', blockers: [] },
    },
  }
}

function createDashboardRun(preview) {
  return {
    contract_version: 'dashboard.run.v1',
    run_id: 'run-dashboard-sales',
    dashboard_id: 'dashboard-sales',
    dashboard_version_id: 'dashboard-sales-v1',
    actor_type: 'user',
    actor_id: 'data-team',
    correlation_id: 'mock',
    mode: 'live',
    normalized_filters: {},
    filter_digest: 'filter-digest',
    pinned_versions: { semantic_models: { [modelId]: 'v2' }, source_snapshots: [] },
    execution_plan_digest: 'plan-digest',
    started_at: '2026-08-17T09:00:00Z',
    completed_at: '2026-08-17T09:00:01Z',
    overall_freshness: 'fresh 2h ago',
    preview,
    views: [{
      data_view_id: 'paid-revenue-by-region',
      status: 'success',
      result: [{ region: 'North', paid_revenue: 3200 }, { region: 'West', paid_revenue: 2400 }],
      schema: [{ name: 'region', data_type: 'string' }, { name: 'paid_revenue', data_type: 'number' }],
      row_count: 2,
      cached: false,
      stale: false,
      as_of: '2026-08-17T09:00:00Z',
      warnings: [],
      error: null,
      evidence: [{ id: 'doc-1', kind: 'doc', title: 'Revenue Playbook' }],
      lineage: [{ id: 'lin-1', kind: 'table', name: 'orders', ref: 'orders' }],
    }],
    warnings: [],
    errors: [],
  }
}
