import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'

const baseURL = process.env.BASE_URL || 'http://127.0.0.1:5173'
const apiURL = process.env.API_URL || 'http://127.0.0.1:8000'
const screenDir = process.env.SCREEN_DIR || './tmp-dashboard-screens'
const adminEmail = process.env.BYAAN_ADMIN_EMAIL || 'admin@example.com'
const adminPassword = process.env.BYAAN_ADMIN_PASSWORD || 'password'
const explicitLegacyAssetId = process.env.LEGACY_ASSET_ID || ''
mkdirSync(screenDir, { recursive: true })

const stats = {
  pageerror: 0,
  consoleError: 0,
  requestfailed: 0,
  http5xx: 0,
}

function stableSlug(prefix) {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

async function api(path, options = {}) {
  const response = await fetch(`${apiURL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
  })
  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    throw new Error(`API ${path} failed ${response.status}: ${JSON.stringify(payload)}`)
  }
  return payload?.data ?? payload
}

async function loginForSelfHostedAuth() {
  const response = await fetch(`${apiURL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ username: adminEmail, password: adminPassword }),
  })
  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    throw new Error(`Dashboard smoke login failed ${response.status}: ${JSON.stringify(payload)}`)
  }
  const token = payload?.data?.access_token
  if (!token) {
    throw new Error(`Dashboard smoke login did not return an access token: ${JSON.stringify(payload)}`)
  }
  const authHeaders = { Authorization: `Bearer ${token}` }
  const scopes = await api('/api/scopes/all', { headers: authHeaders })
  const tenantId = scopes.tenants?.[0]?.tenant_id
  if (!tenantId) {
    throw new Error(`Dashboard smoke login did not expose a tenant: ${JSON.stringify(scopes)}`)
  }
  return { tenantId, headers: { ...authHeaders, 'X-Tenant-ID': tenantId } }
}

async function resolveDashboardAuth() {
  const config = await api('/api/app/config')
  const bootstrap = config.local_bootstrap || config.community_bootstrap
  if (bootstrap?.tenant_id) {
    return { tenantId: bootstrap.tenant_id, headers: { 'X-Tenant-ID': bootstrap.tenant_id } }
  }
  return loginForSelfHostedAuth()
}

async function uploadCsvDataset(headers, notebookId) {
  const form = new FormData()
  const csv = [
    'region,revenue,failure_reason',
    'AMER,4200,none',
    'EMEA,2700,none',
  ].join('\n')
  form.append('files', new Blob([csv], { type: 'text/csv' }), 'dashboard_browser_fixture.csv')
  form.append('notebook_id', notebookId)
  form.append('name', `Dashboard Browser Dataset ${Date.now()}`)
  form.append('file_type', 'csv')
  const response = await fetch(`${apiURL}/api/datasets/upload-files`, {
    method: 'POST',
    headers,
    body: form,
  })
  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    throw new Error(`Dataset upload failed ${response.status}: ${JSON.stringify(payload)}`)
  }
  return payload?.data ?? payload
}

async function createSavedQuery(headers, notebookId, datasetId, name, query) {
  const response = await fetch(`${apiURL}/api/execute-query`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...headers,
    },
    body: JSON.stringify({
      query,
      connection_id: datasetId,
      notebook_id: notebookId,
      db_type: 'duckdb',
      name,
    }),
  })
  const result = await response.json().catch(() => null)
  if (!response.ok) {
    throw new Error(`Saved query creation failed ${response.status}: ${JSON.stringify(result)}`)
  }
  if (!result?.query_id) {
    throw new Error(`Saved query was not created: ${JSON.stringify(result)}`)
  }
  return String(result.query_id)
}

function savedQueryView({ id, queryId, question, fields, stale = false, failing = false }) {
  return {
    id,
    kind: 'saved_query',
    question,
    output_schema: fields,
    filter_fields: ['region'],
    sensitivity: 'internal',
    freshness_policy: stale
      ? { mode: 'live', max_age_seconds: 0, allow_stale: true, require_as_of: true }
      : { mode: 'live', max_age_seconds: 3600, allow_stale: true, require_as_of: true },
    saved_query: {
      query_id: queryId,
      compatibility_reason: failing ? 'browser acceptance partial failure fixture' : 'browser acceptance fixture',
      filter_contract: {},
      lineage: [
        {
          id: `${id}-lineage`,
          kind: 'saved_query',
          name: failing ? 'Failure query' : 'Revenue query',
          ref: queryId,
        },
      ],
    },
    evidence: [
      {
        id: `${id}-evidence`,
        kind: stale ? 'cache_snapshot' : 'source_understanding',
        title: stale ? 'Stale cache snapshot' : 'Reviewed source profile',
        locator: { path: stale ? 'browser-fixture-stale-cache' : 'browser-fixture' },
        confidence: 0.9,
      },
    ],
  }
}

function manifest({
  dashboardId,
  queryId,
  title,
  policyRefs = false,
  migrationState = 'new_structured',
  blockers = [],
  staleQueryId,
  failureQueryId,
  tileTitle = 'Revenue',
}) {
  const dataViews = [
    savedQueryView({
      id: 'dv-revenue',
      queryId,
      question: 'What revenue did the governed query return?',
      fields: [
        { name: 'revenue', data_type: 'number', unit: 'USD', sensitivity: 'internal' },
        { name: 'region', data_type: 'string', sensitivity: 'internal' },
      ],
    }),
  ]
  const tiles = [
    {
      id: 'tile-revenue',
      title: tileTitle,
      tile_type: 'kpi',
      business_question: 'What is revenue?',
      data_view_id: 'dv-revenue',
      encoding: { value: 'revenue', label: 'region' },
      accessible_fallback: { summary: 'Revenue KPI', table_fields: ['revenue', 'region'] },
    },
    {
      id: 'tile-table',
      title: 'Revenue Table',
      tile_type: 'table',
      business_question: 'Which rows support revenue?',
      data_view_id: 'dv-revenue',
      accessible_fallback: { summary: 'Revenue table', table_fields: ['revenue', 'region'] },
    },
  ]
  let layout = { sections: [{ id: 'main', title: 'Revenue Overview', tile_ids: ['tile-revenue', 'tile-table'] }] }

  if (staleQueryId && failureQueryId) {
    dataViews.push(
      savedQueryView({
        id: 'dv-stale-revenue',
        queryId: staleQueryId,
        question: 'Which revenue snapshot is stale?',
        fields: [
          { name: 'revenue', data_type: 'number', unit: 'USD', sensitivity: 'internal' },
          { name: 'region', data_type: 'string', sensitivity: 'internal' },
        ],
        stale: true,
      }),
      savedQueryView({
        id: 'dv-partial-failure',
        queryId: failureQueryId,
        question: 'Which dashboard data view partially failed?',
        fields: [{ name: 'failure_reason', data_type: 'string', sensitivity: 'internal' }],
        failing: true,
      }),
    )
    tiles.push(
      {
        id: 'tile-stale',
        title: 'Stale Revenue Cache',
        tile_type: 'kpi',
        business_question: 'Which cached value is stale?',
        data_view_id: 'dv-stale-revenue',
        accessible_fallback: { summary: 'Stale cached revenue KPI', table_fields: ['revenue', 'region'] },
      },
      {
        id: 'tile-partial',
        title: 'Partial Failure View',
        tile_type: 'status',
        business_question: 'Which data view failed while the dashboard partially rendered?',
        data_view_id: 'dv-partial-failure',
        accessible_fallback: { summary: 'Partial failure status', table_fields: ['failure_reason'] },
      },
    )
    layout = { sections: [{ id: 'main', title: 'Stale And Partial States', tile_ids: ['tile-stale', 'tile-partial'] }] }
  }

  return {
    schema_version: 'dashboard.manifest.v1',
    dashboard_id: dashboardId,
    title,
    description: `${title} browser acceptance fixture`,
    audience: ['finance'],
    semantic_bindings: [
      {
        id: 'sales-model',
        model_slug: 'sales',
        model_version: 'v1',
        source_snapshot_ids: ['snapshot-browser'],
        allowed_metrics: ['revenue'],
        allowed_dimensions: ['region'],
      },
    ],
    data_views: dataViews,
    filters: [
      {
        id: 'region',
        label: 'Region',
        source: 'saved_query_contract',
        field: 'region',
        filter_type: 'enum',
        operators: ['eq'],
        affected_data_view_ids: dataViews.map(view => view.id),
        domain: ['AMER', 'EMEA'],
        default_value: 'AMER',
      },
    ],
    layout,
    tiles,
    actions: [
      { id: 'export', label: 'Export', action_type: 'export', required_scope: 'dashboard:export' },
    ],
    freshness_policy: { mode: 'live', max_age_seconds: 3600, allow_stale: true, require_as_of: true },
    access_policy: policyRefs
      ? {
          required_scopes: ['dashboard:read', 'dashboard:query'],
          row_policy_refs: ['tenant_rls'],
          column_policy_refs: ['finance_columns'],
          redaction_policy_refs: ['pii_redaction'],
        }
      : { required_scopes: ['dashboard:read', 'dashboard:query'] },
    provenance: { created_by_actor_type: 'human', created_by: 'browser-smoke', source: 'human' },
    migration: { state: migrationState, blockers },
  }
}

async function createDashboard(headers, notebookId, slugPrefix, manifestPayload, publish = true) {
  const draftAsset = await api('/api/dashboard-assets', {
    method: 'POST',
    headers,
    body: JSON.stringify({
      slug: stableSlug(slugPrefix),
      notebook_id: notebookId,
      manifest: manifestPayload,
      tags: ['browser'],
      change_summary: `browser fixture ${slugPrefix}`,
    }),
  })
  let publishedVersion = null
  if (publish) {
    publishedVersion = await api(`/api/dashboard-assets/${draftAsset.id}/publish`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ base_etag: draftAsset.etag, change_summary: `browser fixture publish ${slugPrefix}` }),
    })
  }
  return { asset: draftAsset, publishedVersion }
}

async function seedDashboardFixtures() {
  const { tenantId, headers } = await resolveDashboardAuth()
  const notebook = await api('/api/notebooks', {
    method: 'POST',
    headers,
    body: JSON.stringify({
      notebook_name: `Dashboard Browser ${Date.now()}`,
      description: 'Browser acceptance fixture notebook',
    }),
  })

  const dataset = await uploadCsvDataset(headers, notebook.id)
  const queryId = await createSavedQuery(
    headers,
    notebook.id,
    dataset.dataset_id,
    'Browser revenue query',
    'SELECT region, revenue FROM dashboard_browser_fixture ORDER BY region',
  )
  const secondQueryId = await createSavedQuery(
    headers,
    notebook.id,
    dataset.dataset_id,
    'Browser margin query',
    'SELECT region, revenue AS margin FROM dashboard_browser_fixture ORDER BY region',
  )
  const staleQueryId = await createSavedQuery(
    headers,
    notebook.id,
    dataset.dataset_id,
    'Browser stale revenue query',
    'SELECT region, revenue FROM dashboard_browser_fixture WHERE region = \'AMER\'',
  )
  const failureQueryId = crypto.randomUUID()
  const editQueryId = queryId

  const structured = await createDashboard(
    headers,
    notebook.id,
    'dashboard-browser-structured',
    manifest({
      dashboardId: 'browser-structured',
      queryId,
      title: 'Browser Structured Revenue',
    }),
  )
  const secondary = await createDashboard(
    headers,
    notebook.id,
    'dashboard-browser-secondary',
    manifest({
      dashboardId: 'browser-secondary',
      queryId: secondQueryId,
      title: 'Browser Secondary Margin',
      tileTitle: 'Margin',
    }),
  )
  const policy = await createDashboard(
    headers,
    notebook.id,
    'dashboard-browser-policy',
    manifest({
      dashboardId: 'browser-policy',
      queryId,
      title: 'Browser Policy Guard',
      policyRefs: true,
    }),
  )
  const stalePartial = await createDashboard(
    headers,
    notebook.id,
    'dashboard-browser-stale-partial',
    manifest({
      dashboardId: 'browser-stale-partial',
      queryId,
      staleQueryId,
      failureQueryId,
      title: 'Browser Stale Partial',
    }),
  )
  const edit = await createDashboard(
    headers,
    notebook.id,
    'dashboard-browser-edit-review',
    manifest({
      dashboardId: 'browser-edit-review',
      queryId: editQueryId,
      title: 'Browser Edit Review',
      migrationState: 'legacy_unstructured',
      blockers: ['browser smoke publish blocker'],
    }),
    false,
  )
  const legacy = await createDashboard(
    headers,
    notebook.id,
    'dashboard-browser-legacy',
    manifest({
      dashboardId: 'browser-legacy',
      queryId,
      title: 'Browser Legacy Review',
      migrationState: 'legacy_unstructured',
    }),
    false,
  )

  const structuredDetail = await api(`/api/dashboard-assets/${structured.asset.id}`, { headers })
  const policyDetail = await api(`/api/dashboard-assets/${policy.asset.id}`, { headers })
  const staleDetail = await api(`/api/dashboard-assets/${stalePartial.asset.id}`, { headers })

  return {
    tenantId,
    notebookId: notebook.id,
    headers,
    structuredSlug: structured.asset.slug,
    secondarySlug: secondary.asset.slug,
    structuredAssetId: structured.asset.id,
    structuredVersionNum: structured.publishedVersion.version_num,
    secondaryAssetId: secondary.asset.id,
    policyAssetId: policy.asset.id,
    stalePartialAssetId: stalePartial.asset.id,
    editAssetId: edit.asset.id,
    editEtag: edit.asset.etag,
    legacyAssetId: legacy.asset.id,
    stalePartialVersionNum: stalePartial.publishedVersion.version_num,
    publishedEtags: {
      structured: structuredDetail.etag,
      policy: policyDetail.etag,
      stalePartial: staleDetail.etag,
    },
  }
}

const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
})

async function issueBrowserRefreshToken() {
  const response = await fetch(`${apiURL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ username: adminEmail, password: adminPassword }),
  })
  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    throw new Error(`Browser login failed ${response.status}: ${JSON.stringify(payload)}`)
  }
  const refreshToken = payload?.data?.refresh_token
  if (!refreshToken) {
    throw new Error(`Browser login did not return a refresh token: ${JSON.stringify(payload)}`)
  }
  return refreshToken
}

async function makePage(viewport, tenantId) {
  const refreshToken = await issueBrowserRefreshToken()
  const context = await browser.newContext({ viewport, baseURL })
  await context.addInitScript(({ id, token }) => {
    window.localStorage.setItem('byaan_active_tenant', id)
    window.sessionStorage.setItem('byaan_refresh_token', token)
  }, { id: tenantId, token: refreshToken })
  const page = await context.newPage()
  page.on('pageerror', error => {
    stats.pageerror += 1
    console.error('pageerror:', error.message)
  })
  page.on('console', message => {
    if (message.type() === 'error') {
      stats.consoleError += 1
      console.error('console.error:', message.text())
    }
  })
  page.on('requestfailed', request => {
    const url = request.url()
    if (url.includes('accounts.google.com')) return
    stats.requestfailed += 1
    console.error('requestfailed:', url, request.failure()?.errorText)
  })
  page.on('response', response => {
    if (response.status() >= 500) {
      stats.http5xx += 1
      console.error('http5xx:', response.status(), response.url())
    }
  })
  return page
}

async function assertNoHorizontalOverflow(page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  if (overflow > 2) {
    throw new Error(`Horizontal overflow detected: ${overflow}px`)
  }
}

async function hideDevtoolToggles(page) {
  await page.evaluate(() => {
    for (const element of Array.from(document.querySelectorAll('button, [role="button"]'))) {
      const label = element.getAttribute('aria-label') || element.textContent || ''
      if (/tanstack query devtools/i.test(label)) {
        element.setAttribute('data-dashboard-smoke-hidden', 'true')
        element.setAttribute('style', `${element.getAttribute('style') || ''}; display: none !important;`)
      }
    }
  })
}

async function assertNoOverlaps(page) {
  await hideDevtoolToggles(page)
  const overlaps = await page.evaluate(() => {
    const root = document.querySelector('[data-dashboard-workspace="true"]') || document.querySelector('main') || document.body
    const selectors = ['button', 'input', 'select', 'a', '[role="tab"]']
    const elements = selectors.flatMap(selector => Array.from(root.querySelectorAll(selector)))
    const boxes = elements
      .map((element, index) => {
        const rect = element.getBoundingClientRect()
        return { index, tag: element.tagName, text: element.textContent?.trim() || element.getAttribute('aria-label') || '', rect }
      })
      .filter(item => item.rect.width > 8 && item.rect.height > 8)
    const hits = []
    for (let i = 0; i < boxes.length; i += 1) {
      for (let j = i + 1; j < boxes.length; j += 1) {
        const a = boxes[i].rect
        const b = boxes[j].rect
        const x = Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left))
        const y = Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top))
        const area = x * y
        if (area > 32) {
          hits.push([boxes[i].text, boxes[j].text, Math.round(area)])
        }
      }
    }
    return hits.slice(0, 5)
  })
  if (overlaps.length > 0) {
    throw new Error(`Interactive element overlap detected: ${JSON.stringify(overlaps)}`)
  }
}

async function assertSceneLayout(page) {
  await assertNoHorizontalOverflow(page)
  await assertNoOverlaps(page)
}

async function capture(page, scene, viewport) {
  await assertSceneLayout(page)
  await page.screenshot({ path: `${screenDir}/dashboard-${scene}-${viewport}.png`, fullPage: true })
}

async function runInventoryScene(page, fixtures, viewport) {
  await page.goto(`${baseURL}/dashboard-assets`, { waitUntil: 'networkidle' })
  await page.getByRole('heading', { name: 'Dashboards' }).waitFor()
  const inventoryTable = page.getByRole('table')
  await inventoryTable.getByText(fixtures.structuredSlug).waitFor()
  await inventoryTable.getByText(fixtures.secondarySlug).waitFor()
  await inventoryTable.getByRole('columnheader', { name: 'Owner' }).waitFor()
  await inventoryTable.getByRole('columnheader', { name: 'Published / Draft Version' }).waitFor()
  await inventoryTable.getByRole('columnheader', { name: 'Model / Version' }).waitFor()
  await inventoryTable.getByRole('columnheader', { name: 'Freshness' }).waitFor()
  await inventoryTable.getByRole('columnheader', { name: 'Readiness / Warnings' }).waitFor()
  await inventoryTable.getByRole('columnheader', { name: 'Last Update' }).waitFor()
  await inventoryTable.getByText(/Published/i).first().waitFor()
  await inventoryTable.getByText(/Draft/i).first().waitFor()
  await inventoryTable.getByText(/published|draft|legacy_unstructured/i).first().waitFor()
  if (viewport === '1440') {
    const search = page.getByLabel('Search Dashboards').first()
    await search.fill('Secondary')
    await inventoryTable.getByText(fixtures.secondarySlug).waitFor()
    await inventoryTable.getByText(fixtures.structuredSlug).waitFor({ state: 'detached' })
    await search.fill('')
    await inventoryTable.getByText(fixtures.structuredSlug).waitFor()
  } else {
    await page.goto(`${baseURL}/dashboard-assets/${fixtures.structuredAssetId}`, { waitUntil: 'networkidle' })
    await page.getByRole('heading', { name: /Browser Structured Revenue/i }).waitFor()
  }
  await capture(page, 'inventory', viewport)
}

async function runViewScene(page, fixtures, viewport) {
  await page.goto(`${baseURL}/dashboard-assets/${fixtures.structuredAssetId}`, { waitUntil: 'networkidle' })
  await page.getByRole('heading', { name: /Browser Structured Revenue/i }).waitFor()
  await page.getByText('Filter Digest').waitFor()
  await page.getByText(/as of|No rows returned|No run timestamp/i).first().waitFor()
  await capture(page, 'view', viewport)

  if (viewport === '1440') {
    await page.getByRole('button', { name: /Data/i }).click()
    await page.getByRole('heading', { name: 'dv-revenue' }).waitFor()
    await capture(page, 'data', viewport)

    await page.getByRole('button', { name: /Lineage/i }).click()
    await page.getByText('Reviewed source profile').waitFor()
    await capture(page, 'lineage', viewport)
  }
}

async function runPermissionScene(page, fixtures, viewport) {
  await page.goto(`${baseURL}/dashboard-assets/${fixtures.policyAssetId}`, { waitUntil: 'networkidle' })
  await page.getByText('Dashboard data view execution is blocked by unresolved access policy refs').first().waitFor()
  await page.getByText(/permission_denied|blocked/i).first().waitFor()
  await capture(page, 'permission-denied', viewport)
}

async function runLegacyScene(page, fixtures, viewport) {
  await page.goto(`${baseURL}/dashboard-assets/${fixtures.legacyAssetId}`, { waitUntil: 'networkidle' })
  await page.getByText('Legacy migration review').waitFor()
  await page.getByText('stays read-only').waitFor()
  await page.getByRole('link', { name: /Open legacy preview/i }).waitFor()
  await capture(page, 'legacy', viewport)
}

async function runExplicitLegacyAssetScene(page, assetId) {
  if (!assetId) return
  await page.goto(`${baseURL}/dashboard-assets/${assetId}`, { waitUntil: 'networkidle' })
  await page.getByRole('heading', { name: 'Black Friday Demographic Buying Pattern Analysis', exact: true }).waitFor()
  await page.getByText('legacy_unstructured').first().waitFor()
  await page.getByText('legacy HTML dashboard requires structured manifest review before agent-ready publish').first().waitFor()
  await page.getByText('Legacy migration review').waitFor()
  await page.getByText('stays read-only').first().waitFor()
  await page.getByRole('link', { name: /Open legacy preview/i }).waitFor()
  const bodyText = await page.locator('body').innerText()
  if (/Something went wrong/i.test(bodyText)) {
    throw new Error(`Explicit legacy asset ${assetId} rendered the generic error boundary`)
  }
  await capture(page, 'legacy-explicit-asset', '1440')
}

async function runStalePartialScene(page, fixtures, viewport) {
  await page.goto(`${baseURL}/dashboard-assets/${fixtures.stalePartialAssetId}`, { waitUntil: 'networkidle' })
  await page.getByRole('heading', { name: /Browser Stale Partial/i }).waitFor()
  await page.locator('h3:visible', { hasText: 'Stale Revenue Cache' }).first().waitFor()
  await page.locator('h3:visible', { hasText: 'Partial Failure View' }).first().waitFor()
  await page.getByText('Stale data', { exact: true }).first().waitFor()
  await page.getByText(/as of/i).first().waitFor()
  await page.getByText('Partial failure', { exact: true }).waitFor()
  await page.getByText(/Dashboard data view execution failed|No run timestamp/i).first().waitFor()
  await capture(page, 'stale-partial', viewport)
}

async function runEditReviewScene(page, fixtures, viewport) {
  await page.goto(`${baseURL}/dashboard-assets/${fixtures.editAssetId}`, { waitUntil: 'networkidle' })
  await page.getByRole('heading', { name: /Browser Edit Review/i }).waitFor()
  await page.getByText(/1 blockers/i).waitFor()
  await page.getByRole('button', { name: 'Publish' }).waitFor()
  if (await page.getByRole('button', { name: 'Publish' }).isEnabled()) {
    throw new Error('Publish must be disabled while a draft has unresolved blockers')
  }
  await page.getByLabel('Draft title').fill('Browser Edit Review Patched')
  await page.getByRole('button', { name: 'Patch Title' }).click()
  await page.getByText('Draft title updated').waitFor()
  await page.getByRole('heading', { name: /Browser Edit Review Patched/i }).waitFor()
  await page.getByRole('heading', { name: 'Manifest editor' }).waitFor()

  if (viewport === '1440' && !fixtures.editConflictExercised) {
    fixtures.editConflictExercised = true
    const latestEditAsset = await api(`/api/dashboard-assets/${fixtures.editAssetId}`, { headers: fixtures.headers })
    const parallelDraft = await api(`/api/dashboard-assets/${fixtures.editAssetId}/draft`, {
      method: 'PATCH',
      headers: fixtures.headers,
      body: JSON.stringify({
        base_etag: latestEditAsset.etag,
        json_patch: [{ op: 'replace', path: '/description', value: 'Parallel browser conflict update' }],
        change_summary: 'parallel browser conflict fixture',
      }),
    })
    const conflictedEditAsset = await api(`/api/dashboard-assets/${fixtures.editAssetId}`, { headers: fixtures.headers })
    await page.evaluate(currentEtag => {
      const realFetch = window.fetch.bind(window)
      let returnedConflict = false
      window.fetch = async (input, init) => {
        const url = typeof input === 'string' ? input : input instanceof Request ? input.url : String(input)
        const method = init?.method ?? (input instanceof Request ? input.method : 'GET')
        if (!returnedConflict && method === 'PATCH' && url.includes('/api/dashboard-assets/') && url.endsWith('/draft')) {
          returnedConflict = true
          return new Response(JSON.stringify({
            success: false,
            message: 'etag_conflict',
            data: { code: 'etag_conflict', current_etag: currentEtag },
          }), {
            status: 409,
            headers: { 'Content-Type': 'application/json' },
          })
        }
        return realFetch(input, init)
      }
    }, conflictedEditAsset.etag ?? parallelDraft.etag ?? latestEditAsset.etag)
    await page.getByLabel('Tile title').fill(`Edited Revenue ${viewport}`)
    await page.getByLabel('Tile business question').fill(`What edited revenue does viewport ${viewport} show?`)
    await page.getByLabel('Tile encoding JSON').fill(JSON.stringify({ value: 'revenue', label: 'region', comparison: `viewport-${viewport}` }, null, 2))
    await page.getByRole('button', { name: 'Save Tile' }).click()
    await page.getByText('Draft conflict (409)').waitFor()
    await page.getByText('Current ETag').waitFor()
    await page.getByRole('button', { name: 'Retry Patch' }).click()
    await page.getByText('Tile inspector saved').waitFor()
  } else {
    await page.getByLabel('Tile title').fill(`Edited Revenue ${viewport}`)
    await page.getByLabel('Tile business question').fill(`What edited revenue does viewport ${viewport} show?`)
    await page.getByLabel('Tile encoding JSON').fill(JSON.stringify({ value: 'revenue', label: 'region', comparison: `viewport-${viewport}` }, null, 2))
    await page.getByRole('button', { name: 'Save Tile' }).click()
    await page.getByText('Tile inspector saved').waitFor()
  }

  await page.getByRole('button', { name: `Select tile Edited Revenue ${viewport}` }).waitFor()
  await page.locator('button').filter({ hasText: `What edited revenue does viewport ${viewport} show?` }).first().waitFor()
  await page.getByLabel(`Move Edited Revenue ${viewport} down`).click()
  await page.getByText('Tile order updated').waitFor()
  await page.getByLabel(`Move Edited Revenue ${viewport} up`).click()
  await page.getByText('Tile order updated').waitFor()
  await page.getByRole('button', { name: /Region/ }).click()
  await page.getByLabel('Filter label').fill(`Region ${viewport}`)
  await page.getByLabel('Filter operator').selectOption('in')
  await page.getByLabel('Filter default value').fill('EMEA')
  await page.getByRole('button', { name: 'Save Filter' }).click()
  await page.getByText('Filter inspector saved').waitFor()
  await page.getByRole('button', { name: 'Filter', exact: true }).click()
  await page.getByText('Filter added').waitFor()
  await page.getByLabel('Filter label').fill(`Added Filter ${viewport}`)
  await page.getByRole('button', { name: 'Save Filter' }).click()
  await page.getByText('Filter inspector saved').waitFor()
  await page.getByRole('button', { name: 'Remove Filter' }).click()
  await page.getByText('Filter removed').waitFor()
  await page.getByRole('button', { name: 'Validate' }).click()
  await page.getByText(/1 blockers/i).waitFor()
  const previewResponse = page.waitForResponse(response => (
    response.request().method() === 'POST'
    && response.url().includes(`/api/dashboard-assets/${fixtures.editAssetId}/preview`)
    && response.status() === 200
  ))
  await page.getByRole('button', { name: 'Preview' }).click()
  await previewResponse
  await page.getByText('Preview run').waitFor()
  await page.getByText(/Review diff/i).waitFor()
  await capture(page, 'edit-review', viewport)
}

async function runDashboardJourney(fixtures) {
  const desktop = await makePage({ width: 1440, height: 900 }, fixtures.tenantId)
  await desktop.goto(`${baseURL}/notebook/${fixtures.notebookId}/preview`, { waitUntil: 'networkidle' })
  await desktop.getByTitle('Close preview (Esc)').waitFor()
  await desktop.getByRole('button', { name: /Code/i }).click()
  await desktop.getByText('Dashboard HTML').waitFor()
  await desktop.screenshot({ path: `${screenDir}/notebook-preview-route-1440.png`, fullPage: true })

  await runInventoryScene(desktop, fixtures, '1440')
  await runViewScene(desktop, fixtures, '1440')
  await runEditReviewScene(desktop, fixtures, '1440')
  await runStalePartialScene(desktop, fixtures, '1440')
  await runPermissionScene(desktop, fixtures, '1440')
  await runLegacyScene(desktop, fixtures, '1440')
  await runExplicitLegacyAssetScene(desktop, explicitLegacyAssetId)
  await desktop.close()

  const mobile = await makePage({ width: 390, height: 844 }, fixtures.tenantId)
  await runInventoryScene(mobile, fixtures, '390')
  await runViewScene(mobile, fixtures, '390')
  await runEditReviewScene(mobile, fixtures, '390')
  await runStalePartialScene(mobile, fixtures, '390')
  await runPermissionScene(mobile, fixtures, '390')
  await runLegacyScene(mobile, fixtures, '390')
  await mobile.close()
}

try {
  const fixtures = await seedDashboardFixtures()
  await runDashboardJourney(fixtures)
} finally {
  await browser.close()
}

console.log(JSON.stringify({
  ok: stats.pageerror === 0 && stats.consoleError === 0 && stats.requestfailed === 0 && stats.http5xx === 0,
  baseURL,
  apiURL,
  screenshots: screenDir,
  stats,
}, null, 2))

if (stats.pageerror || stats.consoleError || stats.requestfailed || stats.http5xx) {
  process.exit(1)
}
