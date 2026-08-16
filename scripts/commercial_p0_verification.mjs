#!/usr/bin/env node
import { execFileSync } from 'node:child_process'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const __dirname = dirname(fileURLToPath(import.meta.url))
const root = resolve(__dirname, '..')
const matrix = JSON.parse(readFileSync(join(__dirname, 'commercial_p0_matrix.json'), 'utf8'))

function parseArgs(argv) {
  const args = {}
  for (let index = 2; index < argv.length; index += 1) {
    const item = argv[index]
    if (!item.startsWith('--')) continue
    const key = item.slice(2)
    const next = argv[index + 1]
    if (!next || next.startsWith('--')) {
      args[key] = true
    } else {
      args[key] = next
      index += 1
    }
  }
  return args
}

const args = parseArgs(process.argv)
const timestamp = new Date().toISOString().replace(/[:.]/g, '-')
const baseURL = args['base-url'] || process.env.BASE_URL || `http://127.0.0.1:${matrix.ports.frontend}`
const apiURL = args['api-url'] || process.env.API_URL || baseURL
const evidenceDir = resolve(
  args['evidence-dir']
    || process.env.EVIDENCE_DIR
    || join(process.env.HOME || root, '.codex', 'data-studio-commercial-p0-evidence', `run-${timestamp}`),
)
const selectedAssetPath = process.env.COMMERCIAL_P0_ASSET_PATH || '/dashboard-assets/commercial-verification-asset'
const authEmail = process.env.E2E_EMAIL || process.env.MASTER_USER_EMAIL || ''
const authPassword = process.env.E2E_PASSWORD || process.env.MASTER_USER_PASSWORD || ''

mkdirSync(evidenceDir, { recursive: true })
mkdirSync(join(evidenceDir, 'screenshots'), { recursive: true })

function command(name, commandArgs, options = {}) {
  try {
    return {
      ok: true,
      stdout: execFileSync(name, commandArgs, {
        cwd: root,
        encoding: 'utf8',
        stdio: ['ignore', 'pipe', 'pipe'],
        ...options,
      }).trim(),
      stderr: '',
    }
  } catch (error) {
    return {
      ok: false,
      stdout: error.stdout?.toString().trim() || '',
      stderr: error.stderr?.toString().trim() || error.message,
      status: error.status ?? null,
    }
  }
}

function git(commandArgs) {
  return command('git', ['-C', root, ...commandArgs])
}

function redact(value) {
  if (value == null) return value
  const text = typeof value === 'string' ? value : JSON.stringify(value)
  return text
    .replace(/(password|secret|token|api[_-]?key|access[_-]?key)(["'\s:=]+)([^"',\s}]+)/gi, '$1$2[REDACTED]')
    .slice(0, 4000)
}

function toURL(origin, path) {
  return new URL(path, origin.endsWith('/') ? origin : `${origin}/`).toString()
}

function summarizeBody(contentType, text) {
  const redacted = redact(text)
  if (!contentType.includes('application/json')) return redacted.slice(0, 1000)
  try {
    const parsed = JSON.parse(text)
    return redact(parsed)
  } catch {
    return redacted.slice(0, 1000)
  }
}

function slug(input) {
  return input.replace(/^\/+/, '').replace(/[^a-zA-Z0-9]+/g, '-').replace(/^-|-$/g, '') || 'root'
}

async function probeApi(probe) {
  const startedAt = Date.now()
  const url = toURL(apiURL, probe.path)
  const headers = authState.accessToken ? { authorization: `Bearer ${authState.accessToken}` } : {}
  const options = { method: probe.method || 'GET', headers }
  if (probe.body) {
    headers['content-type'] = 'application/json'
    options.body = JSON.stringify(probe.body)
  }

  try {
    const response = await fetch(url, options)
    const contentType = response.headers.get('content-type') || ''
    const text = await response.text()
    const expected = probe.expected_status || [200]
    return {
      id: probe.id,
      method: options.method,
      path: probe.path,
      url,
      status: response.status,
      ok: expected.includes(response.status),
      expected_status: expected,
      elapsed_ms: Date.now() - startedAt,
      content_type: contentType,
      body_summary: summarizeBody(contentType, text),
    }
  } catch (error) {
    return {
      id: probe.id,
      method: options.method,
      path: probe.path,
      url,
      status: null,
      ok: false,
      expected_status: probe.expected_status || [200],
      elapsed_ms: Date.now() - startedAt,
      error: error.message,
    }
  }
}

const authState = {
  attempted: false,
  ok: false,
  accessToken: '',
  status: null,
  error: null,
}

async function authenticateApiIfConfigured() {
  if (!authEmail || !authPassword) {
    authState.error = 'E2E_EMAIL/E2E_PASSWORD or MASTER_USER_EMAIL/MASTER_USER_PASSWORD not set'
    return
  }
  authState.attempted = true
  const body = new URLSearchParams()
  body.set('username', authEmail)
  body.set('password', authPassword)
  try {
    const response = await fetch(toURL(apiURL, '/api/auth/login'), {
      method: 'POST',
      headers: { 'content-type': 'application/x-www-form-urlencoded' },
      body,
    })
    authState.status = response.status
    const text = await response.text()
    if (!response.ok) {
      authState.error = redact(text)
      return
    }
    const json = JSON.parse(text)
    authState.accessToken = json?.data?.access_token || json?.access_token || ''
    authState.ok = Boolean(authState.accessToken)
    if (!authState.ok) {
      authState.error = 'login response did not contain access_token'
    }
  } catch (error) {
    authState.error = error.message
  }
}

async function launchBrowser() {
  const chromePath = process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
  const options = { headless: true }
  if (existsSync(chromePath)) {
    options.executablePath = chromePath
  }
  return chromium.launch(options)
}

async function routeProbe(browser, route, viewport) {
  const context = await browser.newContext({ viewport, baseURL })
  const page = await context.newPage()
  const events = {
    pageerror: [],
    consoleError: [],
    requestfailed: [],
    http5xx: [],
  }

  page.on('pageerror', error => {
    events.pageerror.push(error.message)
  })
  page.on('console', message => {
    if (message.type() === 'error') {
      events.consoleError.push(message.text())
    }
  })
  page.on('requestfailed', request => {
    events.requestfailed.push({
      url: request.url(),
      errorText: request.failure()?.errorText || null,
    })
  })
  page.on('response', response => {
    if (response.status() >= 500) {
      events.http5xx.push({ status: response.status(), url: response.url() })
    }
  })

  const requestedPath = route.id === 'specified_dashboard_asset' ? selectedAssetPath : route.path
  let gotoStatus = null
  let gotoError = null
  try {
    const response = await page.goto(toURL(baseURL, requestedPath), { waitUntil: 'domcontentloaded', timeout: 45000 })
    gotoStatus = response?.status() ?? null
    await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {})
    await page.waitForTimeout(500)
  } catch (error) {
    gotoError = error.message
  }

  const screenshot = join(
    evidenceDir,
    'screenshots',
    `${slug(requestedPath)}-${viewport.width}x${viewport.height}.png`,
  )
  await page.screenshot({ path: screenshot, fullPage: true }).catch(() => {})

  const dom = await page.evaluate(() => {
    const headings = Array.from(document.querySelectorAll('h1,h2')).slice(0, 8).map(item => item.textContent?.trim())
    const bodyText = document.body?.innerText?.replace(/\s+/g, ' ').trim() || ''
    return {
      title: document.title,
      location: window.location.href,
      path: window.location.pathname,
      headings,
      body_excerpt: bodyText.slice(0, 1200),
      horizontal_overflow: document.documentElement.scrollWidth > window.innerWidth + 2,
    }
  }).catch(error => ({ error: error.message }))

  await context.close()

  const markerText = `${dom.title || ''} ${(dom.headings || []).join(' ')} ${dom.body_excerpt || ''}`
  const markerMatches = (route.expected_markers || []).filter(marker => markerText.includes(marker))
  const routeMatched = dom.path === requestedPath
  const counters = Object.fromEntries(Object.entries(events).map(([key, value]) => [key, value.length]))
  const noErrors = Object.values(counters).every(count => count === 0) && !gotoError
  const ok = noErrors && routeMatched && markerMatches.length > 0 && !dom.horizontal_overflow
  const status = ok
    ? 'passed'
    : !routeMatched
      ? 'failed_route_missing_or_redirected'
      : markerMatches.length === 0
        ? 'failed_marker_missing'
        : dom.horizontal_overflow
          ? 'failed_horizontal_overflow'
          : 'failed_runtime_error'

  return {
    id: route.id,
    requested_path: requestedPath,
    viewport,
    goto_status: gotoStatus,
    goto_error: gotoError,
    final_path: dom.path || null,
    final_url: dom.location || null,
    route_matched: routeMatched,
    expected_markers: route.expected_markers || [],
    marker_matches: markerMatches,
    status,
    ok,
    counters,
    events,
    screenshot,
    dom,
  }
}

function connectorEvidence(apiResults) {
  const definitions = apiResults.find(item => item.id === 'connector_definitions')
  const sources = apiResults.find(item => item.id === 'sources_overview')
  return matrix.connectors.map(connector => ({
    ...connector,
    evidence: {
      connector_definitions_probe: definitions?.ok ? 'available' : 'not_verified',
      sources_overview_probe: sources?.ok ? 'available' : 'not_verified',
      commercial_ready: connector.status === 'ready',
    },
  }))
}

function staticSurfaceEvidence() {
  const app = readFileSync(join(root, 'client', 'src', 'App.tsx'), 'utf8')
  const main = readFileSync(join(root, 'server', 'main.py'), 'utf8')
  return {
    ui_route_presence: Object.fromEntries(
      matrix.ui_routes.map(route => {
        const path = route.id === 'specified_dashboard_asset' ? selectedAssetPath : route.path
        return [route.id, app.includes(`path="${path}"`) || app.includes(`path='${path}'`)]
      }),
    ),
    backend_router_presence: {
      dashboard_router: main.includes('dashboard_router'),
      evaluation_router: main.includes('evaluation_router'),
      assets_router: main.includes('assets_router'),
      source_resources_router: main.includes('source_resources_router'),
      semantic_models_router: main.includes('semantic_models_router'),
      folders_router: main.includes('folders_router'),
    },
  }
}

function provenance() {
  const head = git(['rev-parse', 'HEAD'])
  const branch = git(['branch', '--show-current'])
  const upstream = git(['rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{upstream}'])
  const status = git(['status', '--short'])
  const remotes = git(['remote', '-v'])
  const base = git(['show', '--quiet', '--format=%H %P %s', matrix.base_sha])
  const headShow = git(['show', '--quiet', '--format=%H %P %s', 'HEAD'])
  const dockerPs = command('docker', ['ps', '--format', '{{.Names}} {{.Image}} {{.Ports}}'])
  const dockerImage = process.env.COMMERCIAL_P0_IMAGE
    ? command('docker', ['image', 'inspect', process.env.COMMERCIAL_P0_IMAGE, '--format', '{{json .RepoDigests}} {{json .Labels}}'])
    : { ok: false, stdout: '', stderr: 'COMMERCIAL_P0_IMAGE not set' }
  const lsof8080 = command('lsof', ['-nP', '-iTCP:8080', '-sTCP:LISTEN'])
  const lsofBackend = command('lsof', ['-nP', `-iTCP:${matrix.ports.backend}`, '-sTCP:LISTEN'])
  const lsofFrontend = command('lsof', ['-nP', `-iTCP:${matrix.ports.frontend}`, '-sTCP:LISTEN'])

  return {
    expected_base_sha: matrix.base_sha,
    expected_branch: matrix.branch,
    head: head.stdout,
    branch: branch.stdout,
    upstream: upstream.ok ? upstream.stdout : null,
    clean: status.ok && status.stdout.length === 0,
    status_short: status.stdout,
    remotes: remotes.stdout,
    base: base.stdout,
    head_show: headShow.stdout,
    docker: {
      ps: dockerPs.stdout,
      image_revision: dockerImage.ok ? dockerImage.stdout : null,
      image_revision_note: dockerImage.ok ? null : dockerImage.stderr,
    },
    ports: {
      backend_18123: lsofBackend.stdout,
      frontend_15179: lsofFrontend.stdout,
      do_not_touch_8080: lsof8080.stdout,
    },
  }
}

async function main() {
  const apiResults = []
  if (!args['skip-api']) {
    await authenticateApiIfConfigured()
    for (const probe of matrix.api_probes) {
      apiResults.push(await probeApi(probe))
    }
  }

  const routeResults = []
  if (!args['skip-browser']) {
    const browser = await launchBrowser()
    try {
      for (const viewport of matrix.viewports) {
        for (const route of matrix.ui_routes) {
          routeResults.push(await routeProbe(browser, route, viewport))
        }
      }
    } finally {
      await browser.close()
    }
  }

  const stats = routeResults.reduce(
    (acc, item) => {
      for (const key of Object.keys(acc.browser_counters)) {
        acc.browser_counters[key] += item.counters?.[key] || 0
      }
      if (!item.ok) acc.failed_routes += 1
      return acc
    },
    { failed_routes: 0, browser_counters: { pageerror: 0, consoleError: 0, requestfailed: 0, http5xx: 0 } },
  )

  const result = {
    generated_at: new Date().toISOString(),
    status: routeResults.length && stats.failed_routes === 0 && apiResults.every(item => item.ok)
      ? 'verified'
      : 'partial',
    base_url: baseURL,
    api_url: apiURL,
    evidence_dir: evidenceDir,
    auth: {
      attempted: authState.attempted,
      ok: authState.ok,
      status: authState.status,
      error: authState.error,
      email: authEmail ? authEmail.replace(/^(.).+(@.+)$/, '$1***$2') : null,
    },
    matrix,
    provenance: provenance(),
    static_surface: staticSurfaceEvidence(),
    api: apiResults,
    browser: routeResults,
    connectors: connectorEvidence(apiResults),
    stats,
  }

  writeFileSync(join(evidenceDir, 'result.json'), JSON.stringify(result, null, 2))
  writeFileSync(join(evidenceDir, 'summary.md'), renderSummary(result))
  console.log(JSON.stringify({
    status: result.status,
    evidence_dir: evidenceDir,
    result_json: join(evidenceDir, 'result.json'),
    failed_routes: stats.failed_routes,
    browser_counters: stats.browser_counters,
    failed_api: apiResults.filter(item => !item.ok).map(item => item.id),
  }, null, 2))

  if (args['fail-on-partial'] && result.status !== 'verified') {
    process.exit(1)
  }
}

function renderSummary(result) {
  const routeRows = result.browser.map(item =>
    `| ${item.id} | ${item.viewport.width}x${item.viewport.height} | ${item.requested_path} | ${item.final_path || 'n/a'} | ${item.status} | ${item.screenshot} |`,
  ).join('\n')
  const apiRows = result.api.map(item =>
    `| ${item.id} | ${item.method} ${item.path} | ${item.status ?? 'n/a'} | ${item.ok ? 'pass' : 'fail'} |`,
  ).join('\n')
  return `# Commercial P0 Verification Summary

- Status: \`${result.status}\`
- Generated: \`${result.generated_at}\`
- Base URL: \`${result.base_url}\`
- API URL: \`${result.api_url}\`
- Evidence dir: \`${result.evidence_dir}\`
- Branch: \`${result.provenance.branch}\`
- HEAD: \`${result.provenance.head}\`
- Clean: \`${result.provenance.clean}\`

## Browser Routes

| id | viewport | requested | final | status | screenshot |
|---|---:|---|---|---|---|
${routeRows || '| n/a | n/a | n/a | n/a | skipped | n/a |'}

## API Probes

| id | request | status | result |
|---|---|---:|---|
${apiRows || '| n/a | n/a | n/a | skipped |'}

## Counters

\`\`\`json
${JSON.stringify(result.stats, null, 2)}
\`\`\`
`
}

main().catch(error => {
  console.error(error)
  process.exit(1)
})
