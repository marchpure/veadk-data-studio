import { chromium } from 'playwright'
import fs from 'node:fs/promises'
import path from 'node:path'

const baseUrl = process.env.DATA_WORKSHOP_PREVIEW_URL || 'http://127.0.0.1:4176'
const outputDir = path.resolve('artifacts/data-workshop')
await fs.mkdir(outputDir, { recursive: true })

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const consoleErrors = []
const networkFailures = []
const browserRequests = []
page.on('console', message => {
  if (message.type() === 'error') consoleErrors.push(message.text())
})
page.on('response', response => {
  if (response.status() >= 400) {
    networkFailures.push({ path: new URL(response.url()).pathname, status: response.status() })
  }
})
page.on('request', request => {
  browserRequests.push({ url: request.url(), authorization: request.headers().authorization || '' })
})

await page.goto(`${baseUrl}/skill`, { waitUntil: 'networkidle' })
await page.locator('[data-workshop-skill-mount]').waitFor()
const suffix = Date.now().toString(36)
const firstTitle = `周度营收复盘 ${suffix}`
await page.getByRole('button', { name: /新建 Skill/ }).first().click()
await page.getByPlaceholder('例如：周度营收复盘').fill(firstTitle)
await page.getByPlaceholder('weekly-revenue-review').fill(`weekly-revenue-${suffix}`)
await page.getByPlaceholder('这个 Skill 将帮助团队…').fill('汇总数据、核对口径并生成可复用的营收复盘。')
await page.getByRole('button', { name: /创建并进入工作台/ }).click()
await page.getByRole('heading', { name: firstTitle }).waitFor()

const sessionUrl = page.url()
const selected = new URL(sessionUrl)
const skillId = selected.searchParams.get('skillId')
const sessionId = selected.searchParams.get('sessionId')
if (!skillId || !sessionId) throw new Error(`Selected Skill URL is incomplete: ${sessionUrl}`)
await page.reload({ waitUntil: 'networkidle' })
await page.getByRole('heading', { name: firstTitle }).waitFor()
if (page.url() !== sessionUrl) throw new Error('Reload did not restore the selected Skill and Session')
const firstSkillId = skillId
await page.locator('.dw-session-control select').selectOption('__new__')
await page.waitForURL(url => url.pathname === '/skill' && url.searchParams.get('sessionId') !== sessionId)
await page.locator('.dw-session-control select').selectOption(sessionId)
await page.waitForURL(url => url.searchParams.get('sessionId') === sessionId)
await page.getByPlaceholder('搜索 Skill').fill('不存在的 Skill')
await page.getByRole('heading', { name: firstTitle }).waitFor()
await page.getByPlaceholder('搜索 Skill').fill('')
await page.getByRole('button', { name: /新建 Skill/ }).first().click()
await page.getByPlaceholder('例如：周度营收复盘').fill('客户留存分析')
await page.getByPlaceholder('weekly-revenue-review').fill(`retention-${Date.now().toString(36)}`)
await page.getByPlaceholder('这个 Skill 将帮助团队…').fill('分析客户留存趋势。')
await page.getByRole('button', { name: /创建并进入工作台/ }).click()
await page.getByRole('heading', { name: '客户留存分析' }).waitFor()
await page.locator('.dw-skill-list > button').filter({ hasText: firstTitle }).click()
await page.waitForURL(url => url.searchParams.get('skillId') === firstSkillId && Boolean(url.searchParams.get('sessionId')))
const activeSessionId = new URL(page.url()).searchParams.get('sessionId')
if (!activeSessionId) throw new Error(`Selected Skill did not restore a Session: ${page.url()}`)
await page.getByLabel('Skill 消息').fill('继续修改这个 Skill，并保留原有 Revision。')
await page.getByRole('button', { name: '发送' }).click()
await page.locator('.dw-skill-status-notice').waitFor({ timeout: 120000 })
if (await page.locator('.dw-artifact-panel').count()) {
  throw new Error('Failed W5 invocation mounted a fabricated Artifact')
}
if (!browserRequests.some(request => new URL(request.url).pathname.endsWith(`/sessions/${activeSessionId}/events`))) {
  throw new Error('Incremental events endpoint was not consumed')
}

for (const [width, height] of [[1440, 900], [1280, 800]]) {
  await page.setViewportSize({ width, height })
  const geometry = await page.evaluate(() => ({
    overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    shell: document.querySelectorAll('.dw-app > .dw-sidebar').length,
    rail: document.querySelectorAll('.dw-skill-rail').length,
    artifact: document.querySelectorAll('.dw-artifact-panel').length,
  }))
  if (geometry.overflow || geometry.shell !== 1 || geometry.rail !== 1) {
    throw new Error(`Invalid ${width}x${height} layout: ${JSON.stringify(geometry)}`)
  }
  await page.screenshot({ path: path.join(outputDir, `skill-workbench-${width}x${height}.png`) })
}

await page.setViewportSize({ width: 390, height: 844 })
await page.getByRole('button', { name: 'Skill', exact: true }).click()
const mobileGeometry = await page.evaluate(() => ({
  overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  shell: Boolean(document.querySelector('.dw-mobile-header')),
  rail: Boolean(document.querySelector('.dw-skill-rail')),
}))
if (mobileGeometry.overflow || !mobileGeometry.shell || !mobileGeometry.rail) {
  throw new Error(`Invalid mobile layout: ${JSON.stringify(mobileGeometry)}`)
}
await page.screenshot({ path: path.join(outputDir, 'skill-workbench-390x844.png') })

for (const route of ['/skill/new', `/skill/${skillId}`, '/sessions', `/sessions/${sessionId}`]) {
  await page.goto(`${baseUrl}${route}`, { waitUntil: 'networkidle' })
  if (new URL(page.url()).pathname !== '/skill') throw new Error(`Legacy URL did not redirect: ${route}`)
  await page.locator('[data-workshop-skill-mount]').waitFor()
}

await page.setViewportSize({ width: 1440, height: 900 })
await page.goto(sessionUrl, { waitUntil: 'networkidle' })
await page.getByRole('link', { name: '首页', exact: true }).click()
await page.goBack()
await page.waitForURL(sessionUrl)

const storage = await page.evaluate(() => JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }))
if (consoleErrors.length) throw new Error(`Browser console errors: ${JSON.stringify(consoleErrors)}`)
if (networkFailures.length) throw new Error(`Browser network failures: ${JSON.stringify(networkFailures)}`)
if (browserRequests.some(request => request.authorization)) throw new Error('Browser sent an unexpected Authorization header')
if (browserRequests.some(request => /\/revisions\/[^/]+\/(preview|download)$/.test(new URL(request.url).pathname))) {
  throw new Error('Artifact preview/download was requested before an Artifact existed')
}
for (const marker of ['W5_SKILL_AGENT_API_KEY', 'OPENCONNECTOR_ADMIN_TOKEN', 'OPENVIKING_API_KEY']) {
  if (storage.includes(marker)) throw new Error(`Credential marker leaked: ${marker}`)
}

console.log(JSON.stringify({
  ok: true,
  preview_url: baseUrl,
  screenshots: [
    path.join(outputDir, 'skill-workbench-1440x900.png'),
    path.join(outputDir, 'skill-workbench-1280x800.png'),
    path.join(outputDir, 'skill-workbench-390x844.png'),
  ],
}, null, 2))
await browser.close()
