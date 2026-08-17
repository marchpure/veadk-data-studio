import { chromium } from 'playwright'
import { mkdirSync, writeFileSync } from 'node:fs'

const baseURL = process.env.BASE_URL || 'http://127.0.0.1:15174'
const screenDir = process.env.SCREEN_DIR || `./tmp-data-studio-p0-honest-states-${new Date().toISOString().replace(/[:.]/g, '-')}`
const runId = process.env.RUN_ID || String(Date.now())

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
  apiRequests: [],
  expectedConsoleErrors: [],
}

const evidence = {
  baseURL,
  screenDir,
  runId,
  steps: [],
}

const ownerScopes = [
  'connection.create',
  'connection.read',
  'connection.update',
  'connection.delete',
  'dataset.create',
  'dataset.read',
  'dataset.update',
  'dataset.delete',
  'notebook.create',
  'notebook.read',
  'llm_connection.read',
]

function record(step, data = {}) {
  evidence.steps.push({ step, at: new Date().toISOString(), ...data })
}

function ok(data) {
  return { success: true, message: 'ok', data }
}

function routeJson(route, status, payload) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(payload),
  })
}

function emptyPageResponse(path) {
  if (path === '/api/connections' || path === '/api/datasources') return ok({ items: [], total: 0 })
  if (path === '/api/notebooks') return ok({ items: [], total: 0 })
  if (path === '/api/llm-connections') return ok({ items: [], total: 0 })
  if (path === '/api/mcp/keys') return ok([])
  if (path === '/api/schedules') return ok([])
  if (path === '/api/skill-suggestions/pending-count') return ok(0)
  if (path === '/api/user-preferences') return ok({})
  return null
}

const blockedSource = {
  id: 'blocked-web-source',
  source_kind: 'source_resource',
  connection_id: null,
  family: 'web',
  provider: 'web',
  resource_type: 'web',
  name: 'Blocked local admin page',
  status: 'Blocked',
  attention_state: 'policy',
  freshness_status: 'unknown',
  last_synced_at: null,
  latest_snapshot_id: null,
  raw_artifact_uri: null,
  projected_dataset_id: null,
  projection_review: null,
  context_index_status: 'unavailable',
  parse_status: 'pending',
  parsed_asset_counts: { blocks: 0, tables: 0, files: 0, evidence: 0 },
  consumer_counts: { semantic_models: 0, dashboards: 0, notebooks: 0, mcp_tools: 0 },
  owner: { id: '00000000-0000-0000-0000-000000000001', name: 'Demo User' },
  visibility: 'workspace',
  next_actions: ['Review source settings', 'Choose an allowed source'],
  modeling_status: 'blocked',
  modeling_mode: 'context_assisted',
  modeling_reason: 'Source capture is blocked by policy or upstream safety controls.',
  modeling_next_action: 'Review source settings',
  modeling_evidence_summary: 'no profile or evidence yet',
  modeling_can_load_profile: false,
  created_at: '2026-08-16T00:00:00Z',
  updated_at: '2026-08-16T00:00:00Z',
  counts_partial: true,
}

const connectorDefinitions = {
  items: [
    {
      id: 'feishu',
      provider: 'feishu',
      category: 'documents',
      family: 'documents',
      display_name: 'Feishu / Lark',
      icon: 'file-text',
      auth_mode: 'oauth',
      capabilities: ['resource_picker', 'quick_locate'],
      limitations: ['OAuth must be authorized by the current user.'],
      required_scopes: ['docx:document:readonly', 'drive:drive:readonly'],
      config_schema: {},
      resource_picker_schema: {},
      resource_picker_type: 'hierarchical',
      supported_resource_types: ['feishu_doc', 'feishu_wiki', 'feishu_sheet', 'feishu_base'],
      availability: 'beta',
      status: 'beta',
      readiness_gates: [{ key: 'authorization', label: 'User OAuth authorization', status: 'partial' }],
      modeling_modes: ['context_assisted', 'document_projection'],
      description: 'Import selected Feishu documents, wikis, sheets, and bases.',
      entry_kind: 'connector_backed',
    },
    {
      id: 'volcengine_tos',
      provider: 'volcengine_tos',
      category: 'object_storage',
      family: 'object_storage',
      display_name: 'Volcengine TOS',
      icon: 'hard-drive',
      auth_mode: 'access_key',
      capabilities: ['resource_picker'],
      limitations: ['Requires bucket permissions.'],
      required_scopes: [],
      config_schema: {},
      resource_picker_schema: {},
      resource_picker_type: 'hierarchical',
      supported_resource_types: ['tos_prefix', 'tos_object'],
      availability: 'beta',
      status: 'beta',
      readiness_gates: [{ key: 'authorization', label: 'Access key authorization', status: 'partial' }],
      modeling_modes: ['projection', 'context_assisted'],
      description: 'Import selected TOS objects and prefixes.',
      entry_kind: 'connector_backed',
    },
  ],
  total: 2,
}

const feishuConnection = {
  id: 'feishu-revoked-connection',
  provider: 'feishu',
  auth_mode: 'oauth',
  external_account_id: 'redacted',
  display_name: 'Revoked Feishu workspace',
  status: 'connected',
  capabilities: {},
  token_expires_at: null,
  created_by: '00000000-0000-0000-0000-000000000001',
  created_at: '2026-08-16T00:00:00Z',
  updated_at: '2026-08-16T00:00:00Z',
}

async function installApiRoutes(page) {
  await page.route('**/api/**', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    const method = request.method()
    observed.apiRequests.push({ method, path, query: url.search })

    if (path === '/api/app/config') {
      return routeJson(route, 200, ok({
        features: {
          worker_features_enabled: false,
          external_sharing_enabled: false,
          notebook_import_enabled: false,
          public_registration_enabled: false,
          local_auth_enabled: true,
          invitation_only: false,
          google_oauth_enabled: false,
          team_sharing_enabled: false,
          enterprise_licensed: false,
        },
        local_bootstrap: {
          user_id: '00000000-0000-0000-0000-000000000001',
          email: 'demo@local',
          full_name: 'Demo User',
          tenant_id: '00000000-0000-0000-0000-000000000001',
        },
      }))
    }
    if (path === '/api/scopes/all') {
      return routeJson(route, 200, ok({
        tenants: [{
          tenant_id: '00000000-0000-0000-0000-000000000001',
          tenant_name: 'Local Demo',
          role: 'owner',
          scopes: ownerScopes,
          features: {
            local_auth_enabled: true,
            team_sharing_enabled: false,
          },
        }],
      }))
    }
    if (path === '/api/tenants') {
      return routeJson(route, 200, ok([{
        tenant_id: '00000000-0000-0000-0000-000000000001',
        tenant_name: 'Local Demo',
        role: 'owner',
        scopes: ownerScopes,
      }]))
    }
    if (path === '/api/sources/overview') {
      return routeJson(route, 200, ok({ items: [blockedSource], total: 1, counts_partial: true }))
    }
    if (path === '/api/connector-definitions') {
      return routeJson(route, 200, ok(connectorDefinitions))
    }
    if (path === '/api/source-connections/feishu/status') {
      return routeJson(route, 200, ok({
        configured: true,
        connected: true,
        status: 'connected',
        connection: feishuConnection,
        admin_config: {
          configured: true,
          required_scopes: ['docx:document:readonly', 'drive:drive:readonly'],
          missing_scopes: [],
        },
      }))
    }
    if (path === '/api/source-connections' && method === 'GET') {
      return routeJson(route, 200, ok({ items: [feishuConnection], total: 1 }))
    }
    if (path === '/api/source-connections/feishu/oauth/start' && method === 'POST') {
      return routeJson(route, 200, ok({
        authorization_url: 'https://example.feishu.cn/oauth/mock',
        state: 'state-mock',
      }))
    }
    if (path === `/api/source-connections/${feishuConnection.id}/resources`) {
      return routeJson(route, 403, {
        success: false,
        message: 'Source authorization expired or was revoked. Reauthorize source before browsing resources.',
        data: {
          code: 'needs_authorization',
          message: 'Source authorization expired or was revoked. Reauthorize source before browsing resources.',
        },
      })
    }
    if (path === `/api/source-connections/${feishuConnection.id}/resources/locate`) {
      return routeJson(route, 403, {
        success: false,
        message: 'Source authorization expired or was revoked. Reauthorize source before locating resources.',
        data: {
          code: 'needs_authorization',
          message: 'Source authorization expired or was revoked. Reauthorize source before locating resources.',
        },
      })
    }

    const empty = emptyPageResponse(path)
    if (empty) return routeJson(route, 200, empty)
    return routeJson(route, 200, ok([]))
  })
}

async function makePage(browser, viewport) {
  const context = await browser.newContext({ viewport, baseURL })
  const page = await context.newPage()
  await installApiRoutes(page)
  page.on('pageerror', error => {
    stats.pageerror += 1
    observed.pageErrors.push(error.message)
  })
  page.on('console', msg => {
    if (msg.type() !== 'error') return
    const text = msg.text()
    if (text.includes('PostHog API key not found')) return
    if (text.includes('Failed to load resource: the server responded with a status of 403')) {
      observed.expectedConsoleErrors.push({
        errorText: text,
        reason: 'expected-needs-authorization-api-403',
      })
      return
    }
    stats.consoleError += 1
    observed.consoleErrors.push(text)
  })
  page.on('requestfailed', request => {
    stats.requestfailed += 1
    observed.failedRequests.push({ url: request.url(), errorText: request.failure()?.errorText })
  })
  page.on('response', response => {
    if (response.status() >= 500) {
      stats.http5xx += 1
      observed.http5xx.push({ status: response.status(), url: response.url() })
    }
  })
  return { context, page }
}

async function assertVisible(page, text, timeout = 30000) {
  const deadline = Date.now() + timeout
  const locator = page.getByText(text, { exact: false })
  while (Date.now() < deadline) {
    const count = await locator.count()
    for (let index = 0; index < count; index += 1) {
      const item = locator.nth(index)
      const box = await item.boundingBox().catch(() => null)
      if (box && box.width > 0 && box.height > 0) return
    }
    await page.waitForTimeout(100)
  }
  throw new Error(`Timed out waiting for visible text: ${text}`)
}

async function noHorizontalOverflow(page) {
  return page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 2)
}

async function assertNoInfiniteLoading(page) {
  const stuck = await page.getByText(/Loading sources|Loading resources|Preparing your workspace/i).count()
  if (stuck > 0) {
    throw new Error('Page still shows a loading state after honest-state assertions')
  }
}

async function runDesktop(browser) {
  const { context, page } = await makePage(browser, { width: 1440, height: 900 })
  await page.goto('/sources', { waitUntil: 'domcontentloaded' })
  await page.getByRole('heading', { name: 'Sources' }).waitFor({ timeout: 30000 })
  await assertVisible(page, 'Blocked local admin page')
  await assertVisible(page, 'Blocked')
  await assertVisible(page, 'Review source settings')
  await page.screenshot({ path: `${screenDir}/01-blocked-source-overview-1440.png`, fullPage: true })
  record('blocked_source_overview_1440', {
    screenshot: `${screenDir}/01-blocked-source-overview-1440.png`,
  })

  await page.getByRole('button', { name: 'Add source' }).click()
  await page.getByRole('button', { name: /Business docs/i }).click()
  await page.getByRole('button', { name: /Feishu \/ Lark/i }).click()
  await assertVisible(page, 'Authorization required')
  await assertVisible(page, 'does not treat missing credentials as an empty result')
  await assertVisible(page, 'Reauthorize Feishu')
  await page.screenshot({ path: `${screenDir}/02-needs-authorization-picker-1440.png`, fullPage: true })
  record('needs_authorization_picker_1440', {
    screenshot: `${screenDir}/02-needs-authorization-picker-1440.png`,
  })

  const overflowOk = await noHorizontalOverflow(page)
  await assertNoInfiniteLoading(page)
  await context.close()
  if (!overflowOk) {
    throw new Error('Desktop horizontal overflow detected')
  }
}

async function runMobile(browser) {
  const { context, page } = await makePage(browser, { width: 390, height: 844 })
  await page.goto('/sources', { waitUntil: 'domcontentloaded' })
  await page.getByRole('heading', { name: 'Sources' }).waitFor({ timeout: 30000 })
  await assertVisible(page, 'Blocked')
  await assertVisible(page, 'Review source settings')
  await page.screenshot({ path: `${screenDir}/03-blocked-source-overview-390.png`, fullPage: true })
  record('blocked_source_overview_390', {
    screenshot: `${screenDir}/03-blocked-source-overview-390.png`,
  })

  await page.getByRole('button', { name: 'Add source' }).click()
  await page.getByRole('button', { name: /Business docs/i }).click()
  await page.getByRole('button', { name: /Feishu \/ Lark/i }).click()
  await assertVisible(page, 'Authorization required')
  await assertVisible(page, 'Reauthorize Feishu')
  await page.screenshot({ path: `${screenDir}/04-needs-authorization-picker-390.png`, fullPage: true })
  record('needs_authorization_picker_390', {
    screenshot: `${screenDir}/04-needs-authorization-picker-390.png`,
  })

  const overflowOk = await noHorizontalOverflow(page)
  await assertNoInfiniteLoading(page)
  await context.close()
  if (!overflowOk) {
    throw new Error('Mobile horizontal overflow detected')
  }
}

async function main() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  })
  try {
    await runDesktop(browser)
    await runMobile(browser)
  } finally {
    await browser.close()
  }

  const result = {
    ok: stats.pageerror === 0 && stats.consoleError === 0 && stats.requestfailed === 0 && stats.http5xx === 0,
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
