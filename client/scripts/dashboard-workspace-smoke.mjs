import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'

const baseURL = process.env.BASE_URL || 'http://127.0.0.1:5173'
const apiURL = process.env.API_URL || 'http://127.0.0.1:8000'
const screenDir = process.env.SCREEN_DIR || './tmp-dashboard-screens'
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

function manifest({ dashboardId, queryId, title, policyRefs = false, migrationState = 'new_structured' }) {
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
    data_views: [
      {
        id: 'dv-revenue',
        kind: 'saved_query',
        question: 'What revenue did the governed query return?',
        output_schema: [
          { name: 'revenue', data_type: 'number', unit: 'USD', sensitivity: 'internal' },
          { name: 'region', data_type: 'string', sensitivity: 'internal' },
        ],
        filter_fields: ['region'],
        sensitivity: 'internal',
        saved_query: {
          query_id: queryId,
          compatibility_reason: 'browser acceptance fixture',
          filter_contract: {},
          lineage: [
            {
              id: 'query-lineage',
              kind: 'saved_query',
              name: 'Revenue query',
              ref: queryId,
            },
          ],
        },
        evidence: [
          {
            id: 'evidence-1',
            kind: 'source_understanding',
            title: 'Reviewed source profile',
            locator: { path: 'browser-fixture' },
            confidence: 0.9,
          },
        ],
      },
    ],
    filters: [
      {
        id: 'region',
        label: 'Region',
        source: 'saved_query_contract',
        field: 'region',
        filter_type: 'enum',
        operators: ['eq'],
        affected_data_view_ids: ['dv-revenue'],
        domain: ['AMER', 'EMEA'],
      },
    ],
    layout: { sections: [{ id: 'main', title: 'Revenue Overview', tile_ids: ['tile-revenue', 'tile-table'] }] },
    tiles: [
      {
        id: 'tile-revenue',
        title: 'Revenue',
        tile_type: 'kpi',
        business_question: 'What is revenue?',
        data_view_id: 'dv-revenue',
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
    ],
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
    migration: { state: migrationState, blockers: [] },
  }
}

async function seedDashboardFixtures() {
  const config = await api('/api/app/config')
  const bootstrap = config.local_bootstrap || config.community_bootstrap
  if (!bootstrap?.tenant_id) {
    throw new Error('Local bootstrap tenant was not available')
  }
  const headers = { 'X-Tenant-ID': bootstrap.tenant_id }
  const notebook = await api('/api/notebooks', {
    method: 'POST',
    headers,
    body: JSON.stringify({
      notebook_name: `Dashboard Browser ${Date.now()}`,
      description: 'Browser acceptance fixture notebook',
    }),
  })
  const queryId = crypto.randomUUID()

  const draftAsset = await api('/api/dashboard-assets', {
    method: 'POST',
    headers,
    body: JSON.stringify({
      slug: stableSlug('dashboard-browser-structured'),
      notebook_id: notebook.id,
      manifest: manifest({
        dashboardId: 'browser-structured',
        queryId,
        title: 'Browser Structured Revenue',
      }),
      tags: ['browser'],
      change_summary: 'browser fixture structured draft',
    }),
  })
  const publishedVersion = await api(`/api/dashboard-assets/${draftAsset.id}/publish`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ base_etag: draftAsset.etag, change_summary: 'browser fixture publish' }),
  })

  const policyAsset = await api('/api/dashboard-assets', {
    method: 'POST',
    headers,
    body: JSON.stringify({
      slug: stableSlug('dashboard-browser-policy'),
      notebook_id: notebook.id,
      manifest: manifest({
        dashboardId: 'browser-policy',
        queryId,
        title: 'Browser Policy Guard',
        policyRefs: true,
      }),
      tags: ['browser'],
      change_summary: 'browser fixture policy guard',
    }),
  })
  await api(`/api/dashboard-assets/${policyAsset.id}/publish`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ base_etag: policyAsset.etag, change_summary: 'browser fixture policy publish' }),
  })

  const legacyAsset = await api('/api/dashboard-assets', {
    method: 'POST',
    headers,
    body: JSON.stringify({
      slug: stableSlug('dashboard-browser-legacy'),
      notebook_id: notebook.id,
      manifest: manifest({
        dashboardId: 'browser-legacy',
        queryId,
        title: 'Browser Legacy Review',
        migrationState: 'legacy_unstructured',
      }),
      tags: ['browser'],
      change_summary: 'browser fixture legacy fallback',
    }),
  })

  return {
    tenantId: bootstrap.tenant_id,
    structuredAssetId: draftAsset.id,
    structuredVersionNum: publishedVersion.version_num,
    policyAssetId: policyAsset.id,
    legacyAssetId: legacyAsset.id,
  }
}

const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
})

async function makePage(viewport, tenantId) {
  const page = await browser.newPage({ viewport })
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
  await page.addInitScript(id => {
    localStorage.setItem('byaan_active_tenant', id)
  }, tenantId)
  return page
}

async function assertNoHorizontalOverflow(page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  if (overflow > 2) {
    throw new Error(`Horizontal overflow detected: ${overflow}px`)
  }
}

async function assertNoOverlaps(page) {
  const overlaps = await page.evaluate(() => {
    const selectors = ['button', 'input', 'select', 'a', '[role="tab"]']
    const elements = selectors.flatMap(selector => Array.from(document.querySelectorAll(selector)))
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

async function runDashboardJourney(fixtures) {
  const desktop = await makePage({ width: 1440, height: 900 }, fixtures.tenantId)
  await desktop.goto(`${baseURL}/dashboard-assets/${fixtures.structuredAssetId}`, { waitUntil: 'networkidle' })
  await desktop.getByRole('heading', { name: /Browser Structured Revenue/i }).waitFor()
  await desktop.getByRole('button', { name: /Data/i }).click()
  await desktop.getByRole('heading', { name: 'dv-revenue' }).waitFor()
  await assertNoHorizontalOverflow(desktop)
  await assertNoOverlaps(desktop)
  await desktop.screenshot({ path: `${screenDir}/dashboard-data-1440.png`, fullPage: true })

  await desktop.getByRole('button', { name: /Lineage/i }).click()
  await desktop.getByText('Reviewed source profile').waitFor()
  await desktop.screenshot({ path: `${screenDir}/dashboard-lineage-1440.png`, fullPage: true })

  await desktop.goto(`${baseURL}/dashboard-assets/${fixtures.policyAssetId}`, { waitUntil: 'networkidle' })
  await desktop.getByText('Dashboard data view execution is blocked by unresolved access policy refs').first().waitFor()
  await desktop.screenshot({ path: `${screenDir}/dashboard-permission-denied-1440.png`, fullPage: true })

  await desktop.goto(`${baseURL}/dashboard-assets/${fixtures.legacyAssetId}`, { waitUntil: 'networkidle' })
  await desktop.getByText('Legacy HTML fallback').waitFor()
  await desktop.getByText('not agent-ready').waitFor()
  await desktop.screenshot({ path: `${screenDir}/dashboard-legacy-1440.png`, fullPage: true })
  await desktop.close()

  const mobile = await makePage({ width: 390, height: 844 }, fixtures.tenantId)
  await mobile.goto(`${baseURL}/dashboard-assets/${fixtures.structuredAssetId}`, { waitUntil: 'networkidle' })
  await mobile.getByRole('heading', { name: /Browser Structured Revenue/i }).waitFor()
  await assertNoHorizontalOverflow(mobile)
  await mobile.screenshot({ path: `${screenDir}/dashboard-mobile-390.png`, fullPage: true })
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
