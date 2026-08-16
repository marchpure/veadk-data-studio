import { chromium } from 'playwright'
import { mkdirSync, writeFileSync } from 'node:fs'

const apiURL = process.env.API_URL || 'http://127.0.0.1:18000'
const baseURL = process.env.BASE_URL || 'http://127.0.0.1:15173'
const screenDir = process.env.SCREEN_DIR || `./tmp-data-studio-p0-${new Date().toISOString().replace(/[:.]/g, '-')}`
const runId = process.env.RUN_ID || String(Date.now())
const sourceName = `P0 projected revenue ${runId}`
const modelId = `p0-projected-revenue-${runId}`
const modelName = `P0 Projected Revenue ${runId}`
const email = process.env.E2E_EMAIL
const password = process.env.E2E_PASSWORD
const MAX_NAVIGATION_EXEMPTIONS = 3
const allowedNavigationAbortPath = `/api/semantic-models/${modelId}`

let accessToken = ''
let refreshToken = ''
let browserContext
const navigationStateByPage = new WeakMap()

if ((email && !password) || (!email && password)) {
  throw new Error('Set both E2E_EMAIL and E2E_PASSWORD, or leave both unset for local no-auth mode.')
}

mkdirSync(screenDir, { recursive: true })

const stats = {
  pageerror: 0,
  consoleError: 0,
  requestfailed: 0,
  http5xx: 0,
}

const observed = {
  pageErrors: [],
  consoleErrors: [],
  failedRequests: [],
  http5xx: [],
  ignoredAborts: [],
  ignoredConsoleErrors: [],
  navigationExemptionLimitExceeded: false,
}

const evidence = {
  apiURL,
  baseURL,
  screenDir,
  runId,
  sourceName,
  modelId,
  authMode: email && password ? 'password' : 'local',
  steps: [],
}

function record(step, data = {}) {
  evidence.steps.push({ step, at: new Date().toISOString(), ...data })
}

function getNavigationState(page) {
  const state = navigationStateByPage.get(page)
  if (!state) {
    throw new Error('Missing navigation state for page')
  }
  return state
}

async function duringNavigation(page, screen, action) {
  const state = getNavigationState(page)
  state.navigating = true
  state.screen = screen
  try {
    return await action()
  } finally {
    state.navigating = false
  }
}

function trackedSettlingRequest(request) {
  try {
    const parsed = new URL(request.url())
    const method = request.method()
    if (parsed.pathname === allowedNavigationAbortPath && method === 'GET') return 'semantic-model-load'
    if (parsed.pathname === `/api/data-models/${modelId}` && method === 'PATCH') return 'semantic-model-autosave'
    if (parsed.pathname === '/api/knowledge/search' && method === 'POST') return 'source-evidence-search'
  } catch {
    return null
  }
  return null
}

async function waitForTrackedRequests(page, screen, timeoutMs = 10000) {
  const state = getNavigationState(page)
  const start = Date.now()
  while (state.pendingRequests.size > 0) {
    if (Date.now() - start > timeoutMs) {
      const pending = [...state.pendingRequests.values()]
      throw new Error(`Timed out waiting for ${screen} tracked requests: ${JSON.stringify(pending)}`)
    }
    await page.waitForTimeout(100)
  }
  await page.waitForTimeout(250)
  if (state.pendingRequests.size > 0) {
    return waitForTrackedRequests(page, screen, timeoutMs - (Date.now() - start))
  }
}

function isAllowedSemanticModelNavigationAbort(url, errorText, screen, reason) {
  if (!screen) return false
  try {
    const parsed = new URL(url)
    return parsed.pathname === allowedNavigationAbortPath && errorText === 'net::ERR_ABORTED' && reason === 'navigation-cancelled-semantic-model-fetch'
  } catch {
    return false
  }
}

function semanticModelUrlFromConsoleText(text) {
  const expectedPrefix = `Error fetching semantic model ${modelId}: TypeError: Failed to fetch`
  if (!text.startsWith(expectedPrefix)) return null
  return new URL(allowedNavigationAbortPath, baseURL).toString()
}

function recordNavigationExemption(collection, entry) {
  collection.push(entry)
  const count = observed.ignoredAborts.length + observed.ignoredConsoleErrors.length
  if (count > MAX_NAVIGATION_EXEMPTIONS) {
    observed.navigationExemptionLimitExceeded = true
  }
}

async function api(path, options = {}) {
  const headers = {
    ...(options.body && !(options.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}),
    ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    ...(options.headers || {}),
  }
  const response = await fetch(`${apiURL}${path}`, {
    ...options,
    headers,
  })
  const text = await response.text()
  let body
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    body = { raw: text }
  }
  if (!response.ok || body?.success === false) {
    throw new Error(`${options.method || 'GET'} ${path} failed: ${response.status} ${JSON.stringify(body)}`)
  }
  return body?.data ?? body
}

async function authenticate() {
  if (!email || !password) return
  const form = new URLSearchParams()
  form.set('username', email)
  form.set('password', password)
  const response = await fetch(`${apiURL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: form,
  })
  const text = await response.text()
  let body
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    body = { raw: text }
  }
  if (!response.ok || body?.success === false) {
    throw new Error(`POST /api/auth/login failed: ${response.status} ${JSON.stringify(body)}`)
  }
  accessToken = body?.data?.access_token ?? body?.access_token ?? ''
  refreshToken = body?.data?.refresh_token ?? body?.refresh_token ?? ''
  if (!accessToken) {
    throw new Error(`Login response did not include an access token: ${JSON.stringify(body)}`)
  }
  if (!refreshToken) {
    throw new Error(`Login response did not include a refresh token: ${JSON.stringify(body)}`)
  }
  record('authenticate', { email })
}

async function uploadProjectedSource() {
  const form = new FormData()
  form.append(
    'file',
    new Blob(
      [
        [
          'order_id,region,revenue,paid_at',
          '1,East,120,2026-08-01',
          '2,West,80,2026-08-02',
          '3,East,30,2026-08-03',
        ].join('\n'),
      ],
      { type: 'text/csv' },
    ),
    'revenue.csv',
  )
  form.append('name', sourceName)
  const resource = await api('/api/source-resources/files', { method: 'POST', body: form })
  if (!resource.projected_dataset_id) {
    throw new Error(`Uploaded source did not create a projected dataset: ${JSON.stringify(resource)}`)
  }
  record('upload_projected_source', {
    sourceResourceId: resource.id,
    projectedDatasetId: resource.projected_dataset_id,
    snapshotId: resource.latest_snapshot_id,
  })
  return resource
}

async function reviewProjection(resource) {
  const review = await api(`/api/source-resources/${resource.id}/projection/review`, {
    method: 'POST',
    body: JSON.stringify({
      status: 'verified',
      reviewed_by: 'data-studio-p0-e2e',
      note: 'Verified by local projected-source acceptance journey.',
    }),
  })
  record('review_projection', { status: review.status, current: review.current })
  return review
}

async function createSemanticModel(projectedDatasetId) {
  const understanding = await api(`/api/datasources/${projectedDatasetId}/understanding/analyze`, {
    method: 'POST',
    body: JSON.stringify({}),
  })
  const selected = (understanding.candidates || []).filter(candidate =>
    ['schema_map', 'relationship', 'data_truth'].includes(candidate.candidate_type),
  )
  if (!selected.some(candidate => candidate.candidate_type === 'schema_map')) {
    throw new Error('Projected dataset did not produce a schema_map candidate')
  }
  if (!selected.some(candidate => candidate.candidate_type === 'data_truth')) {
    throw new Error('Projected dataset did not produce a data_truth candidate')
  }
  const acceptedIds = []
  for (const candidate of selected) {
    await api(`/api/datasources/${projectedDatasetId}/understanding/candidates/${candidate.id}/review`, {
      method: 'POST',
      body: JSON.stringify({ action: 'accept', note: 'Accepted by projected-source E2E.' }),
    })
    acceptedIds.push(candidate.id)
  }
  const draft = await api(`/api/datasources/${projectedDatasetId}/understanding/semantic-model-draft`, {
    method: 'POST',
    body: JSON.stringify({
      model_id: modelId,
      name: modelName,
      domain: 'Sales / Orders',
      owner: 'Data Studio P0',
      candidate_ids: acceptedIds,
    }),
  })
  record('create_semantic_draft', {
    runStatus: understanding.latest_run?.status,
    candidateCount: understanding.candidates?.length || 0,
    acceptedCount: acceptedIds.length,
    modelStatus: draft.model.status,
    metricIds: draft.model.metrics.map(metric => metric.id),
  })
  return draft.model
}

async function publishAndQueryModel(model) {
  const validated = await api(`/api/data-models/${model.id}/validate`, { method: 'POST' })
  if (validated.readinessDetail?.blockers?.length) {
    throw new Error(`Projected model still has readiness blockers: ${JSON.stringify(validated.readinessDetail.blockers)}`)
  }
  const published = await api(`/api/data-models/${model.id}/publish`, { method: 'POST' })
  if (published.status !== 'Published') {
    throw new Error(`Projected model did not publish: ${JSON.stringify(published)}`)
  }
  const query = await api(`/api/data-models/${model.id}/mcp/query_metric`, {
    method: 'POST',
    body: JSON.stringify({ metric: 'revenue_revenue', dimension: 'revenue_region', limit: 20 }),
  })
  if (query.status !== 'completed' || !Array.isArray(query.result) || query.result.length === 0) {
    throw new Error(`Projected MCP query did not return rows: ${JSON.stringify(query)}`)
  }
  const reloaded = await api(`/api/semantic-models/${model.id}`)
  if (reloaded.status !== 'Published' || !reloaded.mcp?.lastResult) {
    throw new Error(`Reloaded model did not retain publish/query state: ${JSON.stringify(reloaded)}`)
  }
  record('publish_reload_mcp_query', {
    status: published.status,
    version: published.publishedVersion,
    rowCount: query.result.length,
    firstRow: query.result[0],
    sql: query.sql,
    hasReloadedLastResult: Boolean(reloaded.mcp.lastResult),
  })
  return reloaded
}

async function makePage(browser, viewport) {
  if (!browserContext) {
    browserContext = await browser.newContext({ viewport, baseURL })
    if (refreshToken) {
      await browserContext.addInitScript(token => {
        window.sessionStorage.setItem('byaan_refresh_token', token)
      }, refreshToken)
    }
  }
  const page = await browserContext.newPage()
  navigationStateByPage.set(page, { navigating: false, screen: '', pendingRequests: new Map() })
  await page.setViewportSize(viewport)
  await browserContext.route('https://accounts.google.com/**', route => {
    route.fulfill({ status: 204, body: '' })
  })
  page.on('pageerror', error => {
    stats.pageerror += 1
    observed.pageErrors.push(error.message)
    console.error('pageerror:', error.message)
  })
  page.on('request', request => {
    const reason = trackedSettlingRequest(request)
    if (!reason) return
    const state = getNavigationState(page)
    state.pendingRequests.set(request, { url: request.url(), method: request.method(), reason })
  })
  page.on('requestfinished', request => {
    const state = getNavigationState(page)
    state.pendingRequests.delete(request)
  })
  page.on('console', msg => {
    if (msg.type() !== 'error') return
    const text = msg.text()
    const state = getNavigationState(page)
    const url = semanticModelUrlFromConsoleText(text)
    if (state.navigating && url) {
      recordNavigationExemption(observed.ignoredConsoleErrors, {
        url,
        errorText: text,
        reason: 'navigation-cancelled-semantic-model-fetch',
        screen: state.screen,
      })
      return
    }
    stats.consoleError += 1
    observed.consoleErrors.push(text)
    console.error('console.error:', text)
  })
  page.on('requestfailed', request => {
    const url = request.url()
    if (url.startsWith('https://accounts.google.com/')) return
    const errorText = request.failure()?.errorText
    const state = getNavigationState(page)
    const reason = 'navigation-cancelled-semantic-model-fetch'
    if (state.navigating && isAllowedSemanticModelNavigationAbort(url, errorText, state.screen, reason)) {
      state.pendingRequests.delete(request)
      recordNavigationExemption(observed.ignoredAborts, {
        url,
        errorText,
        reason,
        screen: state.screen,
      })
      return
    }
    state.pendingRequests.delete(request)
    stats.requestfailed += 1
    observed.failedRequests.push({ url, errorText })
    console.error('requestfailed:', url, errorText)
  })
  page.on('response', response => {
    if (response.status() >= 500) {
      stats.http5xx += 1
      observed.http5xx.push({ status: response.status(), url: response.url() })
      console.error('http5xx:', response.status(), response.url())
    }
  })
  return page
}

async function noHorizontalOverflow(page) {
  return page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 2)
}

async function runDesktopJourney(browser, resource) {
  const page = await makePage(browser, { width: 1440, height: 900 })
  await duringNavigation(page, '01-source-detail-projection-1440', () =>
    page.goto(`${baseURL}/sources/${resource.id}`, { waitUntil: 'domcontentloaded' }),
  )
  await page.getByRole('heading', { name: sourceName }).waitFor({ timeout: 30000 })
  await page.getByText('Projection review').first().waitFor()
  await page.getByText('Verified').first().waitFor()
  await page.getByText('Projected dataset').first().waitFor()
  await page.screenshot({ path: `${screenDir}/01-source-detail-projection-1440.png`, fullPage: true })
  await waitForTrackedRequests(page, '01-source-detail-projection-1440')

  await duringNavigation(page, '02-data-models-home-1440', () =>
    page.goto(`${baseURL}/data-models`, { waitUntil: 'domcontentloaded' }),
  )
  await page.getByRole('heading', { name: 'Data Models' }).waitFor({ timeout: 30000 })
  await page.getByRole('link', { name: modelName, exact: true }).waitFor({ timeout: 30000 })
  await page.screenshot({ path: `${screenDir}/02-data-models-home-1440.png`, fullPage: true })
  await waitForTrackedRequests(page, '02-data-models-home-1440')

  await duringNavigation(page, '03-explore-mcp-result-1440', () =>
    page.goto(`${baseURL}/data-models/${modelId}`, { waitUntil: 'domcontentloaded' }),
  )
  await page.getByRole('heading', { name: modelName }).waitFor({ timeout: 30000 })
  await page.getByRole('button', { name: 'Explore' }).click()
  await page.getByText('query result', { exact: true }).waitFor({ timeout: 30000 })
  await page.getByRole('button', { name: 'Table' }).click()
  await page.getByRole('cell', { name: 'East', exact: true }).waitFor()
  await page.getByRole('cell', { name: 'West', exact: true }).waitFor()
  await page.getByRole('cell', { name: '150', exact: true }).waitFor()
  await page.getByRole('cell', { name: '80', exact: true }).waitFor()
  await page.screenshot({ path: `${screenDir}/03-explore-mcp-result-1440.png`, fullPage: true })
  await waitForTrackedRequests(page, '03-explore-mcp-result-1440')

  await page.getByRole('button', { name: 'Publish' }).first().click()
  await page.getByText('Review / Publish').waitFor({ timeout: 30000 })
  await page.getByText('MCP Test Console').waitFor()
  await page.getByText('policy decision').waitFor()
  await page.screenshot({ path: `${screenDir}/04-publish-mcp-console-1440.png`, fullPage: true })
  await waitForTrackedRequests(page, '04-publish-mcp-console-1440')

  await duringNavigation(page, '05-reload-persistence-1440', () =>
    page.reload({ waitUntil: 'domcontentloaded' }),
  )
  await page.getByRole('heading', { name: modelName }).waitFor({ timeout: 30000 })
  await page.getByRole('button', { name: 'Publish' }).first().click()
  await page.getByText('policy decision').waitFor({ timeout: 30000 })
  await page.screenshot({ path: `${screenDir}/05-reload-persistence-1440.png`, fullPage: true })
  await waitForTrackedRequests(page, '05-reload-persistence-1440')

  const overflowOk = await noHorizontalOverflow(page)
  await page.close()
  if (!overflowOk) {
    throw new Error('Desktop horizontal overflow detected')
  }
}

async function runMobileJourney(browser, resource) {
  const page = await makePage(browser, { width: 390, height: 844 })
  await duringNavigation(page, '06-source-detail-mobile-390', () =>
    page.goto(`${baseURL}/sources/${resource.id}`, { waitUntil: 'domcontentloaded' }),
  )
  await page.getByRole('heading', { name: sourceName }).waitFor({ timeout: 30000 })
  await page.getByText('Verified').first().waitFor()
  const sourceOk = await noHorizontalOverflow(page)
  await page.screenshot({ path: `${screenDir}/06-source-detail-mobile-390.png`, fullPage: true })
  await waitForTrackedRequests(page, '06-source-detail-mobile-390')

  await duringNavigation(page, '07-data-model-mobile-390', () =>
    page.goto(`${baseURL}/data-models/${modelId}`, { waitUntil: 'domcontentloaded' }),
  )
  await page.getByRole('heading', { name: modelName }).waitFor({ timeout: 30000 })
  await page.getByRole('button', { name: 'Explore' }).waitFor()
  const modelOk = await noHorizontalOverflow(page)
  await page.screenshot({ path: `${screenDir}/07-data-model-mobile-390.png`, fullPage: true })
  await waitForTrackedRequests(page, '07-data-model-mobile-390')
  await page.close()

  if (!sourceOk || !modelOk) {
    throw new Error(`Mobile horizontal overflow detected: source=${sourceOk}, model=${modelOk}`)
  }
}

async function main() {
  await authenticate()
  await api('/api/app/config')
  const resource = await uploadProjectedSource()
  await reviewProjection(resource)
  const model = await createSemanticModel(resource.projected_dataset_id)
  await publishAndQueryModel(model)

  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  })
  try {
    await runDesktopJourney(browser, resource)
    await runMobileJourney(browser, resource)
  } finally {
    await browserContext?.close()
    await browser.close()
  }

  const result = {
    ok:
      stats.pageerror === 0 &&
      stats.consoleError === 0 &&
      stats.requestfailed === 0 &&
      stats.http5xx === 0 &&
      !observed.navigationExemptionLimitExceeded,
    ...evidence,
    stats,
    observed,
  }
  writeFileSync(`${screenDir}/result.json`, `${JSON.stringify(result, null, 2)}\n`)
  console.log(JSON.stringify(result, null, 2))
  if (!result.ok) process.exit(1)
}

main().catch(error => {
  const failed = { ok: false, error: error.stack || error.message, ...evidence, stats, observed }
  writeFileSync(`${screenDir}/result.json`, `${JSON.stringify(failed, null, 2)}\n`)
  console.error(JSON.stringify(failed, null, 2))
  process.exit(1)
})
