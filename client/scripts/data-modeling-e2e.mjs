import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'

const baseURL = process.env.BASE_URL || 'http://127.0.0.1:8080'
const screenDir = process.env.SCREEN_DIR || './tmp-data-modeling-screens'
const loginEmail = process.env.E2E_EMAIL || process.env.MASTER_USER_EMAIL || 'admin@byaan.dev'
const loginPassword = process.env.E2E_PASSWORD || process.env.MASTER_USER_PASSWORD || ''
mkdirSync(screenDir, { recursive: true })

const stats = {
  pageerror: 0,
  consoleError: 0,
  requestfailed: 0,
  http5xx: 0,
}

const expectedHttpStatuses = [
  { method: 'GET', path: '/api/slack/config', status: 404 },
]

const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
})

function isExpectedResponse(response) {
  const url = new URL(response.url())
  return expectedHttpStatuses.some(expected => (
    response.request().method() === expected.method
    && url.pathname === expected.path
    && response.status() === expected.status
  ))
}

async function attachStats(page) {
  page.on('pageerror', error => {
    stats.pageerror += 1
    console.error('pageerror:', error.message)
  })
  page.on('console', msg => {
    if (msg.type() === 'error') {
      stats.consoleError += 1
      console.error('console.error:', msg.text())
    }
  })
  page.on('requestfailed', request => {
    stats.requestfailed += 1
    console.error('requestfailed:', request.url(), request.failure()?.errorText)
  })
  page.on('response', response => {
    if (response.status() >= 500 && !isExpectedResponse(response)) {
      stats.http5xx += 1
      console.error('http5xx:', response.status(), response.url())
    }
  })
}

async function makePage(viewport) {
  const page = await browser.newPage({ viewport })
  await page.route('https://accounts.google.com/**', route => {
    route.fulfill({ status: 204, body: '' })
  })
  return page
}

async function noHorizontalOverflow(page) {
  return page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 2)
}

async function isVisible(locator, timeout = 500) {
  try {
    await locator.waitFor({ state: 'visible', timeout })
    return true
  } catch {
    return false
  }
}

async function requiresLogin(page) {
  const configResponse = await page.request.get(`${baseURL}/api/app/config`)
  if (!configResponse.ok()) {
    return false
  }
  const config = await configResponse.json()
  return Boolean(config?.data?.features?.enterprise_licensed)
}

async function ensureAuthenticated(page, targetPath = '/data-models') {
  if (!(await requiresLogin(page))) {
    attachStats(page)
    return
  }

  if (!loginPassword) {
    throw new Error('E2E_PASSWORD or MASTER_USER_PASSWORD is required for self-hosted Team Version login')
  }

  const loginResponse = await page.request.post(`${baseURL}/api/auth/login`, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    form: { username: loginEmail, password: loginPassword },
  })
  if (!loginResponse.ok()) {
    throw new Error(`Self-hosted login failed with ${loginResponse.status()}`)
  }
  const loginPayload = await loginResponse.json()
  const accessToken = (loginPayload.data ?? loginPayload).access_token
  if (!accessToken) {
    throw new Error('Self-hosted login did not return an access token')
  }

  const tenantsResponse = await page.request.get(`${baseURL}/api/scopes/all`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  })
  if (!tenantsResponse.ok()) {
    throw new Error(`Tenant lookup failed with ${tenantsResponse.status()}`)
  }
  const tenantsPayload = await tenantsResponse.json()
  const tenantId = tenantsPayload?.data?.tenants?.[0]?.tenant_id

  await page.addInitScript(({ token, tenant }) => {
    window.localStorage.setItem('byaan_auth_token', token)
    if (tenant) {
      window.localStorage.setItem('byaan_active_tenant', tenant)
    }
  }, { token: accessToken, tenant: tenantId })
  attachStats(page)
  await page.goto(`${baseURL}${targetPath}`, { waitUntil: 'networkidle' })
}

async function completeGeneration(page) {
  for (let index = 0; index < 12; index += 1) {
    const startExploringButton = page.getByRole('button', { name: /Start exploring/i })
    if (await isVisible(startExploringButton)) {
      return
    }

    const continueButton = page.getByRole('button', { name: /Continue to Explore/i })
    if (await isVisible(continueButton)) {
      return
    }

    const startButton = page.getByRole('button', { name: /Start AI generation/i })
    if (await isVisible(startButton)) {
      await startButton.click()
      continue
    }

    const advanceButton = page.getByRole('button', { name: /Advance generation/i })
    if (await isVisible(advanceButton)) {
      await advanceButton.click()
      continue
    }

    await page.waitForTimeout(250)
  }

  throw new Error('AI generation did not reach completed state')
}

async function runDesktopJourney() {
  const page = await makePage({ width: 1440, height: 900 })
  await ensureAuthenticated(page, '/data-models')
  await page.getByRole('heading', { name: 'Data Models' }).waitFor()

  await page.getByRole('button', { name: /Generate from Data/i }).click()
  await page.getByRole('button', { name: /Oracle SALES/i }).click()
  await page.screenshot({ path: `${screenDir}/01-oracle-sales-data-selection-1440.png`, fullPage: true })

  await page.getByRole('button', { name: /AI Generate Semantic Model/i }).click()
  await page.getByText('Orders Profile').waitFor()
  await page.getByRole('button', { name: /NET_AMOUNT/i }).click()
  await page.screenshot({ path: `${screenDir}/02-data-preview-field-profile-1440.png`, fullPage: true })

  await page.getByRole('button', { name: /AI Generate Semantic Model/i }).click()
  await page.getByRole('button', { name: /Start AI generation/i }).click()
  await page.getByRole('button', { name: /Advance generation/i }).click()
  await page.getByRole('button', { name: /Advance generation/i }).click()
  await page.screenshot({ path: `${screenDir}/03-ai-semantic-generation-process-1440.png`, fullPage: true })
  await completeGeneration(page)
  if (await isVisible(page.getByRole('button', { name: /Continue to Explore/i }))) {
    await page.getByRole('button', { name: /Continue to Explore/i }).click()
  }
  await page.getByRole('button', { name: /Start exploring/i }).click()

  await page.waitForURL('**/data-models/sales-growth')
  await page.getByRole('button', { name: 'Explore' }).waitFor()
  await page.getByText('Paid Revenue by Region').waitFor()
  await page.screenshot({ path: `${screenDir}/04-generated-explore-default-1440.png`, fullPage: true })

  await page.locator('select').first().selectOption('avg_order_value')
  await page.locator('select').nth(1).selectOption('customer_tier')
  await page.locator('select').nth(2).selectOption('quarter')
  await page.getByRole('button', { name: /Table/i }).click()
  await page.getByRole('button', { name: /Saved Query/i }).click()
  await page.getByRole('button', { name: /Add Dashboard/i }).click()
  await page.getByRole('button', { name: /Create Data Skill/i }).click()
  await page.getByRole('button', { name: /Confirmed Example/i }).click()
  await page.getByRole('button', { name: /Review model/i }).first().click()

  await page.getByText('Advanced Relationship Canvas').waitFor()
  await page.getByRole('button', { name: /Refunds -> Orders candidate/i }).first().click()
  await page.screenshot({ path: `${screenDir}/05-advanced-relationship-canvas-1440.png`, fullPage: true })
  await page.getByRole('button', { name: /^Fix$|Fix fanout/i }).first().click()
  await page.getByText('Fixed by modeling refunds').first().waitFor()

  await page.getByRole('button', { name: /Paid Revenue/i }).first().click()
  await page.locator('label:has-text("Formula") input').fill('SUM(orders.net_amount) * 1.01')
  await page.getByRole('button', { name: 'certified', exact: true }).click()
  await page.screenshot({ path: `${screenDir}/06-metric-editor-instant-preview-1440.png`, fullPage: true })

  await page.getByRole('button', { name: /Validation Drawer/i }).click()
  await page.getByRole('button', { name: /Validate/i }).click()
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'Publish' }).first().click()
  await page.getByRole('button', { name: /Open Review/i }).click()
  await page.getByRole('button', { name: /Mark Reviewed/i }).click()
  await page.getByRole('button', { name: /Publish v3/i }).click()
  await page.getByText('Published at').waitFor()
  await page.getByRole('button', { name: /Run query_metric/i }).click()
  await page.getByText('policy decision').waitFor()
  await page.screenshot({ path: `${screenDir}/07-publish-readiness-mcp-exposure-1440.png`, fullPage: true })

  for (const route of ['/databases', '/notebook/new', '/llm-connections']) {
    await page.goto(`${baseURL}${route}`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(500)
  }

  await page.reload({ waitUntil: 'networkidle' })
  await page.goto(`${baseURL}/data-models/sales-growth`, { waitUntil: 'networkidle' })
  await page.getByText('Sales Growth Model').waitFor()
  await page.getByText('v3').first().waitFor()

  await page.close()
}

async function runMobileSmoke() {
  const page = await makePage({ width: 390, height: 844 })
  await ensureAuthenticated(page, '/data-models')
  await page.getByRole('heading', { name: 'Data Models' }).waitFor()
  const homeOk = await noHorizontalOverflow(page)
  await page.screenshot({ path: `${screenDir}/08-data-models-mobile-390.png`, fullPage: true })

  await page.goto(`${baseURL}/data-models/sales-growth`, { waitUntil: 'networkidle' })
  await page.getByText('Sales Growth Model').waitFor()
  await page.getByRole('button', { name: 'Explore' }).waitFor()
  const exploreOk = await noHorizontalOverflow(page)
  await page.getByRole('button', { name: /Review model/i }).first().click()
  await page.getByRole('button', { name: /Objects/i }).waitFor()
  await page.getByRole('button', { name: /Inspector/i }).waitFor()
  const modelOk = await noHorizontalOverflow(page)
  await page.screenshot({ path: `${screenDir}/09-builder-mobile-390.png`, fullPage: true })
  await page.close()

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

console.log(JSON.stringify({
  ok: stats.pageerror === 0 && stats.consoleError === 0 && stats.requestfailed === 0 && stats.http5xx === 0,
  baseURL,
  screenshots: screenDir,
  stats,
}, null, 2))

if (stats.pageerror || stats.consoleError || stats.requestfailed || stats.http5xx) {
  process.exit(1)
}
