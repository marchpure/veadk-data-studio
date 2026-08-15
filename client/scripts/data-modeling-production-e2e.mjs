import { chromium } from 'playwright'
import { mkdirSync, writeFileSync } from 'node:fs'

const baseURL = process.env.BASE_URL || 'http://localhost:8080'
const modelId = process.env.MODEL_ID || 'integration-sales-pg-1786717080'
const modelName = process.env.MODEL_NAME || 'Integration Sales Postgres Model'
const datasourceName = process.env.DATASOURCE_NAME || 'Modeling Sales Postgres E2E'
const directMetric = process.env.DIRECT_METRIC || 'orders_paid_amount'
const directDimension = process.env.DIRECT_DIMENSION || 'customers_segment'
const email = process.env.E2E_EMAIL || 'admin@example.com'
const password = process.env.E2E_PASSWORD || 'password'
const screenDir = process.env.SCREEN_DIR || `./tmp-data-modeling-production-${new Date().toISOString().replace(/[:.]/g, '-')}`

mkdirSync(screenDir, { recursive: true })

const stats = {
  pageerror: 0,
  consoleError: 0,
  requestfailed: 0,
  http5xx: 0,
}

const observed = {
  failedRequests: [],
  consoleErrors: [],
  http5xx: [],
  pageErrors: [],
  ignoredAborts: [],
  ignoredConsoleErrors: [],
}

let accessToken = ''

const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
})

async function makePage(viewport) {
  const context = await browser.newContext({ viewport, baseURL })
  const login = await context.request.post('/api/auth/login', {
    form: { username: email, password },
  })
  if (!login.ok()) {
    throw new Error(`Pre-authentication failed: ${login.status()} ${await login.text()}`)
  }
  const loginBody = await login.json()
  accessToken = loginBody?.data?.access_token ?? loginBody?.access_token ?? accessToken
  const page = await context.newPage()
  await context.route('https://accounts.google.com/**', route => {
    route.fulfill({ status: 204, body: '' })
  })
  page.on('pageerror', error => {
    stats.pageerror += 1
    observed.pageErrors.push(error.message)
    console.error('pageerror:', error.message)
  })
  page.on('console', msg => {
    if (msg.type() === 'error') {
      const text = msg.text()
      if (text.includes('TypeError: Failed to fetch')) {
        observed.ignoredConsoleErrors.push(text)
        return
      }
      stats.consoleError += 1
      observed.consoleErrors.push(text)
      console.error('console.error:', text)
    }
  })
  page.on('requestfailed', request => {
    const url = request.url()
    if (url.startsWith('https://accounts.google.com/')) return
    const failure = request.failure()?.errorText
    if (failure === 'net::ERR_ABORTED') {
      observed.ignoredAborts.push({ url, failure })
      return
    }
    stats.requestfailed += 1
    observed.failedRequests.push({ url, failure })
    console.error('requestfailed:', url, failure)
  })
  page.on('response', response => {
    const status = response.status()
    if (status >= 500) {
      stats.http5xx += 1
      observed.http5xx.push({ status, url: response.url() })
      console.error('http5xx:', status, response.url())
    }
  })
  return page
}

async function loginIfNeeded(page) {
  await page.goto(`${baseURL}/data-models`, { waitUntil: 'domcontentloaded' })
  if (page.url().includes('/login')) {
    await page.getByLabel('Email').fill(email)
    await page.getByLabel('Password').fill(password)
    await page.getByRole('button', { name: /^Sign in$/ }).click()
  }
  if (!page.url().includes('/data-models')) {
    await page.goto(`${baseURL}/data-models`, { waitUntil: 'domcontentloaded' })
  }
  await page.getByRole('heading', { name: 'Data Models' }).waitFor({ timeout: 30000 })
  await settlePage(page)
}

async function settlePage(page) {
  await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {})
  await page.waitForTimeout(500)
}

async function noHorizontalOverflow(page) {
  return page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 2)
}

async function waitForAnyText(page, texts, timeout = 15000) {
  const started = Date.now()
  while (Date.now() - started < timeout) {
    for (const text of texts) {
      const locator = typeof text === 'string' ? page.getByText(text, { exact: false }) : page.getByText(text)
      if (await locator.first().isVisible().catch(() => false)) return text
    }
    await page.waitForTimeout(200)
  }
  throw new Error(`Timed out waiting for one of: ${texts.map(String).join(', ')}`)
}

async function clickAndWaitForModelPatch(page, locator) {
  const patchResponse = page.waitForResponse(response =>
    response.url().includes(`/api/data-models/${modelId}`) && response.request().method() === 'PATCH',
  { timeout: 30000 })
  await locator.click()
  const response = await patchResponse
  if (!response.ok()) {
    throw new Error(`Model PATCH failed: ${response.status()} ${await response.text()}`)
  }
}

async function clickAndWaitForMcpQuery(page, locator) {
  const queryResponse = page.waitForResponse(response =>
    response.url().includes(`/api/data-models/${modelId}/mcp/query_metric`) && response.request().method() === 'POST',
  { timeout: 30000 })
  const reloadResponse = page.waitForResponse(response =>
    response.url().includes(`/api/semantic-models/${modelId}`) && response.request().method() === 'GET',
  { timeout: 30000 })
  await locator.click()
  const query = await queryResponse
  if (!query.ok()) {
    throw new Error(`MCP query failed: ${query.status()} ${await query.text()}`)
  }
  const reload = await reloadResponse
  if (!reload.ok()) {
    throw new Error(`Model reload after MCP query failed: ${reload.status()} ${await reload.text()}`)
  }
}

async function clickAndWaitForPublish(page, locator) {
  const reviewPatchResponse = page.waitForResponse(response =>
    response.url().includes(`/api/data-models/${modelId}`) && response.request().method() === 'PATCH',
  { timeout: 30000 })
  const publishResponse = page.waitForResponse(response =>
    response.url().includes(`/api/data-models/${modelId}/publish`) && response.request().method() === 'POST',
  { timeout: 30000 })
  await locator.click()
  const reviewPatch = await reviewPatchResponse
  if (!reviewPatch.ok()) {
    throw new Error(`Review PATCH before publish failed: ${reviewPatch.status()} ${await reviewPatch.text()}`)
  }
  const publish = await publishResponse
  if (!publish.ok()) {
    throw new Error(`Publish failed: ${publish.status()} ${await publish.text()}`)
  }
}

async function runDesktopJourney() {
  const page = await makePage({ width: 1440, height: 900 })
  await loginIfNeeded(page)

  await page.getByRole('link', { name: modelName, exact: true }).waitFor({ timeout: 30000 })
  const modelRow = page.locator('tbody tr', { has: page.getByRole('link', { name: modelName, exact: true }) })
  await modelRow.getByText(/Draft|Validating|Validation Failed|Ready for Review|Published|Rejected/).first().waitFor()
  await page.screenshot({ path: `${screenDir}/01-data-models-home-1440.png`, fullPage: true })

  await page.getByRole('button', { name: /Generate from Data/i }).click()
  await page.getByText('Generate Semantic Model From Data').waitFor()
  await page.getByText(datasourceName).first().waitFor({ timeout: 30000 })
  await page.getByText('Recommended Modeling Scope').waitFor()
  await page.getByRole('button', { name: /^Profile\b/ }).click()
  await page.getByText(/Tables$/).first().waitFor()
  await page.getByText(/Profile$/).first().waitFor()
  await page.screenshot({ path: `${screenDir}/02-create-model-profile-1440.png`, fullPage: true })
  await page.keyboard.press('Escape')

  await page.goto(`${baseURL}/data-models/${modelId}`, { waitUntil: 'domcontentloaded' })
  await page.getByRole('heading', { name: modelName }).waitFor({ timeout: 30000 })
  await page.getByRole('button', { name: 'Explore' }).waitFor()
  await clickAndWaitForMcpQuery(page, page.getByRole('button', { name: /Run query_metric/i }).first())
  await page.getByText('query result', { exact: true }).waitFor({ timeout: 30000 })
  await clickAndWaitForModelPatch(page, page.getByRole('button', { name: /Table/i }))
  await clickAndWaitForModelPatch(page, page.getByRole('button', { name: /Saved Query/i }))
  await clickAndWaitForModelPatch(page, page.getByRole('button', { name: /Add Dashboard/i }))
  await clickAndWaitForModelPatch(page, page.getByRole('button', { name: /Create Data Skill/i }))
  await clickAndWaitForModelPatch(page, page.getByRole('button', { name: /Confirmed Example/i }))
  await page.getByRole('button', { name: /Why this calculation/i }).click()
  await page.getByText('Lineage').waitFor()
  await page.screenshot({ path: `${screenDir}/03-explore-real-query-1440.png`, fullPage: true })

  await clickAndWaitForModelPatch(page, page.getByRole('button', { name: /Review model/i }).first())
  await page.getByText('Advanced Relationship Canvas').waitFor()
  await page.getByText('Objects').first().waitFor()
  await page.getByText('Fields and Profile Evidence').waitFor()
  await page.getByRole('button', { name: /Validation Drawer/i }).click()
  await page.getByText('Agent Readiness').waitFor()
  await page.getByRole('button', { name: /Validate/i }).click()
  await waitForAnyText(page, ['Reliable Questions', 'No hard blockers remain.'])
  await page.keyboard.press('Escape')
  await page.screenshot({ path: `${screenDir}/04-builder-validation-1440.png`, fullPage: true })

  await clickAndWaitForModelPatch(page, page.getByRole('button', { name: 'Publish' }).first())
  await page.getByText('Review / Publish').waitFor()
  await clickAndWaitForModelPatch(page, page.getByRole('button', { name: /Open Review/i }))
  await clickAndWaitForModelPatch(page, page.getByRole('button', { name: /Mark Reviewed/i }))
  await clickAndWaitForPublish(page, page.getByRole('button', { name: /Publish next version/i }))
  await waitForAnyText(page, ['Published at', 'v2', 'v3'], 30000)
  await clickAndWaitForMcpQuery(page, page.getByRole('button', { name: /Run query_metric/i }).last())
  await page.getByText('policy decision').waitFor({ timeout: 30000 })
  await page.screenshot({ path: `${screenDir}/05-publish-mcp-1440.png`, fullPage: true })

  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.getByRole('heading', { name: modelName }).waitFor({ timeout: 30000 })
  await clickAndWaitForModelPatch(page, page.getByRole('button', { name: 'Publish' }).first())
  await page.getByText('policy decision').waitFor({ timeout: 30000 })
  await page.screenshot({ path: `${screenDir}/06-reload-persistence-1440.png`, fullPage: true })

  const direct = await page.context().request.post(`/api/data-models/${modelId}/mcp/query_metric`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: { metric: directMetric, dimension: directDimension, limit: 20 },
  })
  if (!direct.ok()) {
    throw new Error(`Direct MCP API failed: ${direct.status()} ${await direct.text()}`)
  }

  for (const route of ['/databases', '/notebook/new', '/llm-connections']) {
    await page.goto(`${baseURL}${route}`, { waitUntil: 'domcontentloaded' })
    await settlePage(page)
    await page.screenshot({ path: `${screenDir}/regression-${route.replaceAll('/', '-') || 'home'}-1440.png`, fullPage: true })
  }

  await settlePage(page)
  await page.context().close()
}

async function runMobileSmoke() {
  const page = await makePage({ width: 390, height: 844 })
  await loginIfNeeded(page)
  const homeOk = await noHorizontalOverflow(page)
  await page.screenshot({ path: `${screenDir}/07-data-models-mobile-390.png`, fullPage: true })

  await page.goto(`${baseURL}/data-models/${modelId}`, { waitUntil: 'domcontentloaded' })
  await page.getByRole('heading', { name: modelName }).waitFor({ timeout: 30000 })
  const exploreOk = await noHorizontalOverflow(page)
  await clickAndWaitForModelPatch(page, page.getByRole('button', { name: /Review model/i }).first())
  await page.getByRole('button', { name: /Objects/i }).waitFor()
  await page.getByRole('button', { name: /Inspector/i }).waitFor()
  const modelOk = await noHorizontalOverflow(page)
  await page.screenshot({ path: `${screenDir}/08-builder-mobile-390.png`, fullPage: true })
  await settlePage(page)
  await page.context().close()

  if (!homeOk || !exploreOk || !modelOk) {
    throw new Error(`Mobile horizontal overflow detected: home=${homeOk}, explore=${exploreOk}, model=${modelOk}`)
  }
}

try {
  await runDesktopJourney()
  await runMobileSmoke()
} finally {
  await browser.close()
}

const result = {
  ok: stats.pageerror === 0 && stats.consoleError === 0 && stats.requestfailed === 0 && stats.http5xx === 0,
  baseURL,
  modelId,
  screenshots: screenDir,
  stats,
  observed,
}

writeFileSync(`${screenDir}/result.json`, `${JSON.stringify(result, null, 2)}\n`)
console.log(JSON.stringify(result, null, 2))

if (!result.ok) {
  process.exit(1)
}
