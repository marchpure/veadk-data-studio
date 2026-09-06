import fs from 'node:fs/promises'
import path from 'node:path'
import { chromium } from 'playwright'

const baseUrl = process.env.DATA_WORKSHOP_PREVIEW_URL || 'http://127.0.0.1:4184'
const profileId = process.env.OPENVIKING_PROFILE_ID || ''
const profileName = process.env.OPENVIKING_PROFILE_NAME || 'W6.1 Hosted Validation Updated'
const outputDir = path.resolve(process.cwd(), '../docs/handoffs/screenshots/dwv1-i4a-w61-w71-v3')
const tenantId = '00000000-0000-0000-0000-000000000001'

if (!profileId) {
  throw new Error('OPENVIKING_PROFILE_ID is required for the integrated journey')
}

await fs.mkdir(outputDir, { recursive: true })

const browser = await chromium.launch({
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: true,
})
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const consoleErrors = []
const networkFailures = []
const browserRequests = []

page.on('console', message => {
  if (message.type() === 'error') consoleErrors.push(message.text())
})
page.on('response', response => {
  if (response.status() >= 400) {
    networkFailures.push({ status: response.status(), path: new URL(response.url()).pathname })
  }
})
page.on('request', request => {
  browserRequests.push({ method: request.method(), path: new URL(request.url()).pathname })
})

await page.addInitScript(
  ({ profileId, tenantId }) => {
    localStorage.setItem('openviking.activeProfileId', profileId)
    localStorage.setItem('byaan_active_tenant', tenantId)
  },
  { profileId, tenantId },
)

const screenshot = async name => {
  const target = path.join(outputDir, name)
  await page.screenshot({ path: target })
  return target
}

const unsafeUrlMarkers = ['viking://', 'OPENVIKING_E2E_API_KEY', 'volc-', 'skill_prompt', 'Build_a_Data-Agent']

await page.goto(`${baseUrl}/kb`, { waitUntil: 'networkidle' })
await page.getByText(profileName).first().waitFor()
const primaryNavLabels = await page.locator('.dw-primary-nav a').allTextContents()
if (primaryNavLabels.join('|') !== '首页|连接|知识库|Skill') {
  throw new Error(`Unexpected primary navigation: ${primaryNavLabels.join('|')}`)
}
await page.getByRole('treeitem', { name: /^skill_prompt$/ }).click()
const importedLeaf = page.locator('.ov-context-tree-scroll [role="group"] [role="treeitem"]').first()
await importedLeaf.waitFor()
const leafName = (await importedLeaf.innerText()).trim()
await importedLeaf.click()
await page.locator('.ov-resource-preview').getByText(/AI analyst|skill|prompt/i).first().waitFor()

const kbScreenshots = {
  '1440x900': await screenshot('kb-resource-1440x900.png'),
}
await page.setViewportSize({ width: 1280, height: 800 })
kbScreenshots['1280x800'] = await screenshot('kb-resource-1280x800.png')
await page.setViewportSize({ width: 390, height: 844 })
kbScreenshots['390x844'] = await screenshot('kb-resource-390x844.png')

await page.setViewportSize({ width: 1440, height: 900 })
await page.locator('.ov-resource-preview').getByRole('button', { name: '加入 Skill 上下文' }).click()
await page.waitForURL(url => url.pathname === '/skill' && url.searchParams.get('mode') === 'new')

const handoffUrl = page.url()
const resourceRef = new URL(handoffUrl).searchParams.get('resource_ref') || ''
if (!/^ovr_[A-Za-z0-9_-]+\.[0-9a-f]{64}$/.test(resourceRef)) {
  throw new Error(`Handoff ResourceRef is not opaque: ${resourceRef}`)
}
if (unsafeUrlMarkers.some(marker => handoffUrl.includes(marker))) {
  throw new Error(`Sensitive data appeared in handoff URL: ${handoffUrl}`)
}
if (handoffUrl.includes(leafName)) {
  throw new Error(`Resource filename appeared in handoff URL: ${handoffUrl}`)
}

await page.getByText('Knowledge ResourceRefs 1', { exact: true }).waitFor()
const knowledgeDetails = page.locator('details').nth(1)
await knowledgeDetails.locator('summary').click()
const importedText = await knowledgeDetails.innerText()
for (const marker of [leafName, profileName, resourceRef]) {
  if (!importedText.includes(marker)) throw new Error(`Imported ResourceRef metadata missing: ${marker}`)
}

const skillScreenshots = {
  '1440x900': await screenshot('skill-imported-1440x900.png'),
}
await page.setViewportSize({ width: 1280, height: 800 })
skillScreenshots['1280x800'] = await screenshot('skill-imported-1280x800.png')
await page.setViewportSize({ width: 390, height: 844 })
skillScreenshots['390x844'] = await screenshot('skill-imported-390x844.png')

await page.setViewportSize({ width: 1440, height: 900 })
const suffix = Date.now().toString(36)
const title = `OpenViking integrated journey ${suffix}`
await page.getByPlaceholder('例如：周度营收复盘').fill(title)
await page.getByPlaceholder('weekly-revenue-review').fill(`openviking-integrated-${suffix}`)
await page.getByPlaceholder('这个 Skill 将帮助团队…').fill('验证托管知识资源进入 Skill 上下文的完整生命周期。')
await page.getByRole('button', { name: /创建并进入工作台/ }).click()
await page.getByRole('heading', { name: title }).waitFor()
await page.getByText('1 个 ResourceRef').waitFor()
const sessionUrl = page.url()
await page.getByLabel('Skill 消息').fill('验证未配置 W5 时保持阻断。')
await page.getByRole('button', { name: '发送' }).click()
await page.getByText('W5 production transport 尚未配置。', { exact: true }).first().waitFor({ timeout: 120000 })
const blockedConfigVisible = true
if (await page.locator('.dw-artifact-panel').count()) {
  throw new Error('A fabricated Artifact appeared for BLOCKED_CONFIG')
}
await page.reload({ waitUntil: 'networkidle' })
await page.getByRole('heading', { name: title }).waitFor()
await page.getByText('1 个 ResourceRef').waitFor()
const restored = (await page.locator('body').innerText()).includes(leafName)
if (!restored) throw new Error('ResourceRef was not restored after reload')

const patchResponse = page.waitForResponse(
  response =>
    response.request().method() === 'PATCH' &&
    response.url().includes('/context') &&
    response.status() === 200,
)
await page.getByRole('button', { name: /移除/ }).first().click()
const patchStatus = (await patchResponse).status()
await page.getByText('未选择知识').waitFor()
if (await page.locator('.dw-artifact-panel').count()) throw new Error('A fabricated Artifact appeared during the unconfigured W5 journey')
const artifactRequests = browserRequests.filter(request =>
  /\/revisions\/[^/]+\/(preview|download)$/.test(request.path),
)
if (artifactRequests.length) throw new Error(`Artifact preview/download was requested without an Artifact: ${JSON.stringify(artifactRequests)}`)

const storage = await page.evaluate(() => ({
  local: Object.values(localStorage),
  session: Object.values(sessionStorage),
}))
const serializedStorage = JSON.stringify(storage)
if (/OPENVIKING_E2E_API_KEY|volc-[A-Za-z0-9_-]{16,}|W5_SKILL_AGENT_API_KEY|OPENCONNECTOR_ADMIN_TOKEN/i.test(serializedStorage)) {
  throw new Error('Credential marker appeared in browser storage')
}
if (consoleErrors.length) throw new Error(`Browser console errors: ${JSON.stringify(consoleErrors)}`)
if (networkFailures.length) throw new Error(`Browser network failures: ${JSON.stringify(networkFailures)}`)

const evidence = {
  ok: true,
  preview_url: baseUrl,
  profile_id: profileId,
  display_name_visible: true,
  handoff_url_safe: true,
  resource_ref_opaque: true,
  imported_metadata_visible: true,
  screenshots: {
    kb: kbScreenshots,
    skill_imported: skillScreenshots,
  },
  created_session_url: sessionUrl,
  restored_after_reload: restored,
  primary_navigation: primaryNavLabels,
  blocked_config_visible: blockedConfigVisible,
  context_patch_status: patchStatus,
  removed_resource_ref: true,
  empty_state_visible: true,
  artifact_absent: true,
  artifact_preview_download_requests: artifactRequests,
  browser_storage_secret_free: true,
  console_errors: consoleErrors,
  network_failures: networkFailures,
}

await fs.writeFile(
  path.resolve(process.cwd(), '../docs/handoffs/dwv1-i4a-w61-w71-v3-browser-evidence.json'),
  `${JSON.stringify(evidence, null, 2)}\n`,
)
await browser.close()
console.log(JSON.stringify(evidence, null, 2))
