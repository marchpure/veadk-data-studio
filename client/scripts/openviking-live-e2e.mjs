import fs from 'node:fs/promises'
import path from 'node:path'
import { chromium } from 'playwright'

const previewUrl = process.env.OPENVIKING_PREVIEW_URL || 'http://127.0.0.1:5184/kb'
const profileId = process.env.OPENVIKING_PROFILE_ID || ''
const profileName = process.env.OPENVIKING_PROFILE_NAME || 'W6.1 Hosted Validation Updated'
const outputDir = path.resolve(
  process.cwd(),
  '../docs/openviking/screenshots/w61',
)
const failedResponses = []
const observedOperations = new Set()

await fs.mkdir(outputDir, { recursive: true })

const browser = await chromium.launch({
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: true,
})
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
if (profileId) {
  await page.addInitScript(
    ({ profileId }) => {
      localStorage.setItem('openviking.activeProfileId', profileId)
      localStorage.setItem('byaan_active_tenant', '00000000-0000-0000-0000-000000000001')
    },
    { profileId },
  )
}

page.on('response', (response) => {
  const url = response.url()
  if (!url.includes('/api/knowledge/openviking/')) return
  const operation = url.match(/operations\/([^/?]+)/)?.[1]
  if (operation) observedOperations.add(operation)
  if (response.status() >= 400) {
    failedResponses.push({ status: response.status(), url: new URL(url).pathname })
  }
})

await page.goto(previewUrl, { waitUntil: 'networkidle' })
await page.getByText(profileName).first().waitFor()
const resourceTreeVisible = await page
  .locator('[aria-label="OpenViking context tree"]')
  .isVisible()
await page.getByRole('treeitem', { name: /^skill_prompt$/ }).click()
const importedLeaf = page
  .locator('.ov-context-tree-scroll [role="group"] [role="treeitem"]')
  .first()
await importedLeaf.waitFor()
await importedLeaf.click()
const previewContent = page
  .locator('.ov-resource-preview')
  .getByText(/AI analyst|skill|prompt/i)
  .first()
await previewContent.waitFor()
const filePreviewVisible = await previewContent.isVisible()
await page.screenshot({
  path: path.join(outputDir, 'openviking-w61-resource-1440x900.png'),
})
const desktopOverflow = await page.evaluate(
  () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
)

await page.setViewportSize({ width: 1280, height: 800 })
await page.getByRole('button', { name: 'Retrieval' }).click()
const searchInput = page.locator('input[type="text"]').first()
await searchInput.fill('W61HOSTEDV3')
await searchInput.press('Enter')
const retrievalResponse = await page.waitForResponse(
  (response) =>
    response.url().includes('/operations/find') && response.status() === 200,
)
await page.waitForTimeout(500)
await page.screenshot({
  path: path.join(outputDir, 'openviking-w61-retrieval-1280x800.png'),
})
const tabletOverflow = await page.evaluate(
  () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
)

const tasksResponse = page.waitForResponse(
  (response) =>
    response.url().includes('/operations/tasks') && response.status() === 200,
)
await page.getByRole('button', { name: 'Tasks' }).click()
await tasksResponse
const tasksRendered = await page.locator('.ov-page-content').isVisible()
const watchesResponse = page.waitForResponse(
  (response) =>
    response.url().includes('/operations/watches') && response.status() === 200,
)
await page.getByRole('button', { name: 'Watches' }).click()
await watchesResponse
const watchesRendered = await page.locator('.ov-page-content').isVisible()
const skillContextResponse = page.waitForResponse(
  (response) =>
    response.url().includes('/skill-context') && response.status() === 200,
)
await page.getByRole('button', { name: '加入 Skill 上下文' }).click()
const skillContextStatus = (await skillContextResponse).status()

await page.reload({ waitUntil: 'networkidle' })
await page.getByText(profileName).first().waitFor()
const refreshRecovered = await page.getByRole('button', { name: 'Retrieval' }).isVisible()

await page.setViewportSize({ width: 390, height: 844 })
await page.locator('.openviking-module-nav nav button').nth(4).click()
await page.getByRole('button', { name: 'Health check' }).waitFor()
const healthResponse = page.waitForResponse(
  (response) =>
    response.url().endsWith('/validate') && response.status() === 200,
)
await page.getByRole('button', { name: 'Health check' }).click()
await healthResponse
const readyState = page
  .locator('.ov-active-connection .ov-connection-state.is-ready')
  .first()
await readyState.waitFor()
const profileReadyVisible = await readyState.isVisible()
await page.screenshot({
  path: path.join(outputDir, 'openviking-w61-profile-390x844.png'),
})
const mobileOverflow = await page.evaluate(
  () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
)
const storage = await page.evaluate(() => ({
  local: Object.keys(localStorage).sort(),
  session: Object.keys(sessionStorage).sort(),
  values: [...Object.values(localStorage), ...Object.values(sessionStorage)],
}))

const evidence = {
  preview_url: previewUrl,
  profile_ready_visible: profileReadyVisible,
  resource_tree_visible: resourceTreeVisible,
  file_preview_marker_visible: filePreviewVisible,
  retrieval_result_visible: retrievalResponse.status() === 200,
  tasks_rendered: tasksRendered,
  watches_rendered: watchesRendered,
  skill_context_http_status: skillContextStatus,
  refresh_recovery: refreshRecovered,
  observed_operations: [...observedOperations].sort(),
  failed_responses: failedResponses,
  browser_storage_keys: {
    local: storage.local,
    session: storage.session,
  },
  browser_storage_contains_api_key_pattern: storage.values.some((value) =>
    /OPENVIKING_E2E_API_KEY|volc-[A-Za-z0-9_-]{16,}/i.test(value),
  ),
  horizontal_overflow: {
    '1440x900': desktopOverflow,
    '1280x800': tabletOverflow,
    '390x844': mobileOverflow,
  },
}

await fs.writeFile(
  path.resolve(process.cwd(), '../docs/openviking/w61-browser-evidence.json'),
  `${JSON.stringify(evidence, null, 2)}\n`,
)
await browser.close()
console.log(JSON.stringify(evidence, null, 2))
