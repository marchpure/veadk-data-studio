import { chromium } from 'playwright'
import { mkdirSync, readFileSync } from 'node:fs'

const baseURL = process.env.BASE_URL || 'http://127.0.0.1:5173'
const apiURL = process.env.API_URL || 'http://127.0.0.1:8000'
const screenDir = process.env.SCREEN_DIR || './tmp-evaluation-screens'
const adminEmail = process.env.BYAAN_ADMIN_EMAIL || 'admin@example.com'
const adminPassword = process.env.BYAAN_ADMIN_PASSWORD || 'password'
mkdirSync(screenDir, { recursive: true })

const fixture = loadFixture()
const stats = {
  pageerror: 0,
  consoleError: 0,
  requestfailed: 0,
  http5xx: 0,
}
let authHeaders = { 'X-Tenant-ID': fixture.tenant_id }

function loadFixture() {
  if (process.env.EVALUATION_SMOKE_FIXTURE_JSON) {
    return JSON.parse(process.env.EVALUATION_SMOKE_FIXTURE_JSON)
  }
  if (process.env.EVALUATION_SMOKE_FIXTURE_FILE) {
    return JSON.parse(readFileSync(process.env.EVALUATION_SMOKE_FIXTURE_FILE, 'utf8'))
  }
  throw new Error('Set EVALUATION_SMOKE_FIXTURE_JSON or EVALUATION_SMOKE_FIXTURE_FILE')
}

async function api(path, options = {}) {
  const response = await fetch(`${apiURL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders,
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
    throw new Error(`Evaluation smoke login failed ${response.status}: ${JSON.stringify(payload)}`)
  }
  const token = payload?.data?.access_token
  if (!token) {
    throw new Error(`Evaluation smoke login did not return an access token: ${JSON.stringify(payload)}`)
  }
  authHeaders = { Authorization: `Bearer ${token}`, 'X-Tenant-ID': fixture.tenant_id }
}

async function assertRestParity() {
  const suites = await api('/api/evaluation/suites?query=Browser%20Evaluation%20Governance&target_kind=agent_answer&status=published')
  if (!suites.items.some(item => item.id === fixture.suite_id)) {
    throw new Error('Seeded Evaluation suite was not listed through REST')
  }
  const suite = await api(`/api/evaluation/suites/${fixture.suite_id}?include_manifests=true`)
  if (suite.suite.versions[0].id !== fixture.suite_version_id) {
    throw new Error('Suite detail did not expose the seeded version')
  }
  const cases = await api(`/api/evaluation/suite-versions/${fixture.suite_version_id}/cases`)
  if (cases.total < 3) throw new Error(`Expected at least 3 cases, got ${cases.total}`)
  const failures = await api(`/api/evaluation/runs/${fixture.candidate_run_id}/failures`)
  if (failures.total < 1) throw new Error('Expected at least one candidate failure')
  const comparison = await api(`/api/evaluation/runs/compare?baseline_run_id=${fixture.baseline_run_id}&candidate_run_id=${fixture.candidate_run_id}`)
  if (comparison.comparison.summary.regression_count < 1) {
    throw new Error('Expected at least one run regression')
  }
  const serialized = JSON.stringify({ suites, suite, cases, failures, comparison })
  for (const forbidden of ['raw-token', 'plain-password', 'restricted_table', 'secret_table']) {
    if (serialized.includes(forbidden)) throw new Error(`REST payload leaked ${forbidden}`)
  }
}

async function makePage(viewport) {
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
  const loginResponse = await page.request.post(`${apiURL}/api/auth/login`, {
    form: { username: adminEmail, password: adminPassword },
  })
  if (!loginResponse.ok()) {
    throw new Error(`Browser login failed ${loginResponse.status()}: ${await loginResponse.text()}`)
  }
  await page.addInitScript(id => {
    localStorage.setItem('byaan_active_tenant', id)
  }, fixture.tenant_id)
  return page
}

async function assertNoHorizontalOverflow(page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  if (overflow > 2) {
    throw new Error(`Horizontal overflow detected: ${overflow}px`)
  }
}

async function runEvaluationJourney() {
  const desktop = await makePage({ width: 1440, height: 920 })
  await desktop.goto(`${baseURL}/evaluation/${fixture.suite_id}`, { waitUntil: 'networkidle' })
  await desktop.getByRole('heading', { name: /Browser Evaluation Governance/i }).waitFor()
  await desktop.getByText('Security hard-fail case').waitFor()
  await assertNoHorizontalOverflow(desktop)
  await desktop.screenshot({ path: `${screenDir}/evaluation-cases-1440.png`, fullPage: true })

  await desktop.getByRole('button', { name: /^Runs$/i }).click()
  await desktop.getByText('Failures').waitFor()
  await desktop.getByText('security').waitFor()
  await desktop.getByRole('button', { name: /Compare/i }).click()
  await desktop.getByText('Baseline compare').waitFor()
  await desktop.getByText('Regressions first').waitFor()
  await desktop.screenshot({ path: `${screenDir}/evaluation-runs-compare-1440.png`, fullPage: true })

  await desktop.getByRole('button', { name: /^Advisor$/i }).click()
  await desktop.getByRole('button', { name: /custom_skill:refund-rule-ready.*custom_skill:refund-rule:v1/i }).click()
  await desktop.getByText('Advisor staged patch').waitFor()
  await desktop.getByText('Verification', { exact: true }).waitFor()
  await desktop.getByText('Regression', { exact: true }).waitFor()
  await desktop.getByText('Ready', { exact: true }).waitFor()
  await desktop.getByRole('button', { name: /Apply/i }).click()
  await desktop.getByText(/Apply decision/i).last().waitFor()
  await desktop.screenshot({ path: `${screenDir}/evaluation-advisor-apply-1440.png`, fullPage: true })

  await desktop.getByRole('button', { name: /custom_skill:refund-rule-draft.*custom_skill:refund-rule:v1/i }).click()
  await desktop.getByRole('button', { name: /Verify/i }).click()
  await desktop.getByText(/verification run queued/i).last().waitFor()
  await desktop.getByRole('button', { name: /custom_skill:refund-rule-draft.*custom_skill:refund-rule:v1/i }).click()
  await desktop.getByRole('button', { name: /Regress/i }).click()
  await desktop.getByText(/regression run queued/i).last().waitFor()
  await desktop.screenshot({ path: `${screenDir}/evaluation-advisor-queued-1440.png`, fullPage: true })

  await desktop.getByRole('button', { name: /^Feedback$/i }).click()
  await desktop.getByText('Feedback review').waitFor()
  await desktop.getByText('Feedback promoted regression case').waitFor()
  await desktop.getByRole('button', { name: /^Settings$/i }).click()
  await desktop.getByText('Gate policy').waitFor()
  await desktop.getByText('Manifest', { exact: true }).waitFor()
  await assertNoHorizontalOverflow(desktop)
  await desktop.screenshot({ path: `${screenDir}/evaluation-settings-1440.png`, fullPage: true })
  await desktop.close()

  const mobile = await makePage({ width: 390, height: 844 })
  await mobile.goto(`${baseURL}/evaluation/${fixture.suite_id}`, { waitUntil: 'networkidle' })
  await mobile.getByRole('heading', { name: /Browser Evaluation Governance/i }).waitFor()
  await assertNoHorizontalOverflow(mobile)
  await mobile.screenshot({ path: `${screenDir}/evaluation-mobile-390.png`, fullPage: true })
  await mobile.close()
}

const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
})

try {
  await loginForSelfHostedAuth()
  await assertRestParity()
  await runEvaluationJourney()
} finally {
  await browser.close()
}

console.log(JSON.stringify({
  ok: stats.pageerror === 0 && stats.consoleError === 0 && stats.requestfailed === 0 && stats.http5xx === 0,
  baseURL,
  apiURL,
  suiteId: fixture.suite_id,
  screenshots: screenDir,
  stats,
}, null, 2))

if (stats.pageerror || stats.consoleError || stats.requestfailed || stats.http5xx) {
  process.exit(1)
}
