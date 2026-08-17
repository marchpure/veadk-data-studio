import { chromium } from 'playwright'
import { mkdirSync, writeFileSync } from 'node:fs'

const baseURL = process.env.BASE_URL || 'http://localhost:8080'
const modelId = process.env.MODEL_ID || 'integration-sales-pg-1786717080'
const modelName = process.env.MODEL_NAME || 'Integration Sales Postgres Model'
const datasourceName = process.env.DATASOURCE_NAME || 'Modeling Sales Postgres E2E'
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
    if (msg.type() !== 'error') return
    const text = msg.text()
    if (text.includes('TypeError: Failed to fetch')) {
      observed.ignoredConsoleErrors.push(text)
      return
    }
    stats.consoleError += 1
    observed.consoleErrors.push(text)
    console.error('console.error:', text)
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
  await page.evaluate(() => {
    localStorage.removeItem('byaan-data-modeling-production-v1')
  })
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
  await page.waitForTimeout(400)
}

async function noHorizontalOverflow(page) {
  return page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 2)
}

async function isVisible(locator, timeout = 800) {
  try {
    await locator.first().waitFor({ state: 'visible', timeout })
    return true
  } catch {
    return false
  }
}

async function clickIfVisible(locator, timeout = 800) {
  if (await isVisible(locator, timeout)) {
    await locator.first().click()
    return true
  }
  return false
}

function stepButton(page, stepLabel) {
  return page.getByRole('button', { name: new RegExp(stepLabel, 'i') }).filter({ hasText: stepLabel }).first()
}

async function runDesktopJourney() {
  const page = await makePage({ width: 1440, height: 900 })
  await loginIfNeeded(page)

  await page.getByRole('link', { name: modelName, exact: true }).waitFor({ timeout: 30000 })
  await page.screenshot({ path: `${screenDir}/01-data-models-home-1440.png`, fullPage: true })

  await page.getByRole('button', { name: /Generate from Data/i }).click()
  await page.getByText('Generate Semantic Model From Data').waitFor()
  await page.getByText(datasourceName).first().waitFor({ timeout: 30000 })
  await page.getByText('Recommended Modeling Scope').waitFor()
  await page.screenshot({ path: `${screenDir}/02-create-model-profile-1440.png`, fullPage: true })
  await page.keyboard.press('Escape')

  await page.goto(`${baseURL}/data-models/${modelId}`, { waitUntil: 'domcontentloaded' })
  await page.getByRole('heading', { name: modelName }).waitFor({ timeout: 30000 })
  await page.getByText('Step 1').waitFor()
  await page.getByText('Knowledge asset').waitFor()
  await page.getByRole('button', { name: /Connectors/i }).waitFor()

  await page.getByRole('heading', { name: 'This Modeling Scope' }).waitFor()
  await page.getByText(/0 selected|selected/).first().waitFor()
  await page.screenshot({ path: `${screenDir}/03-step-1-connectors-scope-1440.png`, fullPage: true })

  await page.getByRole('button', { name: datasourceName }).first().click().catch(() => {})
  const firstTableButton = page.locator('button', { has: page.locator('svg') }).filter({ hasText: /rows/i }).first()
  if (await isVisible(firstTableButton, 3000)) {
    await firstTableButton.click()
  }
  await clickIfVisible(page.getByRole('button', { name: /Add source/i }))
  if (await isVisible(page.getByRole('dialog'), 1000)) {
    await page.getByText('Connector setup stays outside the four-step modeling flow.').waitFor()
    await page.keyboard.press('Escape')
  }

  await stepButton(page, 'Step 2').click()
  await page.getByRole('heading', { name: 'Structure Understanding' }).waitFor()
  await page.getByRole('heading', { name: 'Semantic Suggestions' }).waitFor()
  await page.getByRole('heading', { name: 'Conflicts' }).waitFor()
  await page.screenshot({ path: `${screenDir}/04-step-2-modeling-evidence-1440.png`, fullPage: true })

  await stepButton(page, 'Step 3').click()
  await page.getByRole('heading', { name: 'Dashboard Context' }).waitFor()
  await page.getByText('Bound semantic version', { exact: true }).waitFor()
  await page.getByText('Dashboard metrics', { exact: true }).waitFor()
  await page.getByText('Dashboards').first().waitFor({ timeout: 30000 })
  await page.screenshot({ path: `${screenDir}/05-step-3-dashboard-context-1440.png`, fullPage: true })

  await stepButton(page, 'Step 4').click()
  await page.getByRole('heading', { name: 'Gate Results' }).waitFor()
  await page.getByText('Publish blockers').waitFor()
  const publishButton = page.getByRole('button', { name: /Publish knowledge asset/i })
  if (!(await publishButton.isDisabled())) {
    throw new Error('Publish knowledge asset button must be disabled while gate blockers exist')
  }
  const failedReason = page.getByText('Failed: Dashboard KPI still references gross_amount', { exact: false })
  await failedReason.first().waitFor()
  await page.screenshot({ path: `${screenDir}/06-step-4-gate-blocked-1440.png`, fullPage: true })

  await stepButton(page, 'Step 2').click()
  await clickIfVisible(page.getByRole('button', { name: /Open metric editor/i }).first())
  await clickIfVisible(page.getByRole('button', { name: /Fix fanout with order aggregate/i }))
  await clickIfVisible(page.getByRole('button', { name: 'certified', exact: true }))
  await clickIfVisible(page.getByRole('button', { name: /Validation Drawer/i }))
  if (await isVisible(page.getByRole('dialog'), 1000)) {
    await page.getByRole('button', { name: /Validate/i }).click()
    await page.keyboard.press('Escape')
  }
  await stepButton(page, 'Step 4').click()
  await page.getByRole('heading', { name: 'Gate Results' }).waitFor()
  await page.getByRole('button', { name: /Run evaluation/i }).click()
  await page.getByText('Passed: Dashboard KPI and semantic model both resolve Paid Revenue', { exact: false }).waitFor({ timeout: 30000 })
  if (await failedReason.count()) {
    throw new Error('Failed reason text was not replaced after passing gate evaluation')
  }
  await page.getByRole('button', { name: /Publish knowledge asset/i }).click()
  await page.getByText('Serving v', { exact: false }).waitFor({ timeout: 30000 })
  await page.getByText('Share link', { exact: true }).waitFor()
  await page.screenshot({ path: `${screenDir}/07-step-4-published-consumers-1440.png`, fullPage: true })

  const desktopOverflow = await noHorizontalOverflow(page)
  if (!desktopOverflow) {
    throw new Error('Desktop horizontal overflow detected')
  }

  for (const route of ['/databases', '/notebook/new', '/llm-connections']) {
    await page.goto(`${baseURL}${route}`, { waitUntil: 'domcontentloaded' })
    await settlePage(page)
    await page.screenshot({ path: `${screenDir}/regression-${route.replaceAll('/', '-') || 'home'}-1440.png`, fullPage: true })
  }

  await page.context().close()
}

async function runMobileSmoke() {
  const page = await makePage({ width: 390, height: 844 })
  await loginIfNeeded(page)
  const homeOk = await noHorizontalOverflow(page)
  await page.screenshot({ path: `${screenDir}/08-data-models-mobile-390.png`, fullPage: true })

  await page.goto(`${baseURL}/data-models/${modelId}`, { waitUntil: 'domcontentloaded' })
  await page.getByRole('heading', { name: modelName }).waitFor({ timeout: 30000 })
  await page.getByText('Step 1').waitFor()
  const connectorsOk = await noHorizontalOverflow(page)
  await stepButton(page, 'Step 2').click()
  await page.getByRole('heading', { name: 'Structure Understanding' }).waitFor()
  const modelingOk = await noHorizontalOverflow(page)
  await stepButton(page, 'Step 4').click()
  await page.getByRole('heading', { name: 'Gate Results' }).waitFor()
  const publishOk = await noHorizontalOverflow(page)
  await page.screenshot({ path: `${screenDir}/09-builder-mobile-390.png`, fullPage: true })
  await page.context().close()

  if (!homeOk || !connectorsOk || !modelingOk || !publishOk) {
    throw new Error(`Mobile horizontal overflow detected: home=${homeOk}, connectors=${connectorsOk}, modeling=${modelingOk}, publish=${publishOk}`)
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
