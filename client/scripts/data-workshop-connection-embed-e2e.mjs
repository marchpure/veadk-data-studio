import { chromium } from 'playwright'
import fs from 'node:fs/promises'
import path from 'node:path'

const baseUrl = process.env.DATA_WORKSHOP_PREVIEW_URL
if (!baseUrl) {
  throw new Error('DATA_WORKSHOP_PREVIEW_URL must point to a real Data Studio preview')
}
const outputDir = path.resolve('artifacts/data-workshop/postrc-connection-embed')
await fs.mkdir(outputDir, { recursive: true })

const routes = [
  ['overview', '/connections/overview', '.overview-page'],
  ['providers', '/connections/providers', '.provider-browser-panel'],
  ['marketplace', '/connections/marketplace', '.marketplace-page'],
  ['actions', '/connections/actions', '.actions-page'],
  ['runs', '/connections/runs', '.runs-page'],
  ['access', '/connections/access', '.access-panel'],
]

const browser = await chromium.launch()
const contextOptions = { viewport: { width: 1440, height: 900 } }
if (process.env.DATA_WORKSHOP_STORAGE_STATE) {
  contextOptions.storageState = process.env.DATA_WORKSHOP_STORAGE_STATE
}
const context = await browser.newContext(contextOptions)
const page = await context.newPage()
const consoleErrors = []
const failedNetwork = []
const browserRequests = []
let currentPageUrl = ''
let launchSessionRequests = 0
let abortedRequests = 0

page.on('console', message => {
  if (message.type() === 'error') consoleErrors.push(message.text())
})
page.on('request', request => {
  if (new URL(request.url()).pathname === '/api/v1/openconnector/launch-sessions') {
    launchSessionRequests += 1
  }
  browserRequests.push({
    url: request.url(),
    authorization: request.headers().authorization || '',
  })
})
page.on('requestfailed', request => {
  const failure = request.failure()?.errorText
  if (failure === 'net::ERR_ABORTED' && new URL(request.url()).pathname.startsWith('/oc/')) {
    abortedRequests += 1
  }
  if (
    failure === 'net::ERR_ABORTED'
    && (
      request.isNavigationRequest()
      || new URL(request.url()).hostname === 'static.oomol.com'
      || (currentPageUrl && request.frame().url() !== currentPageUrl)
    )
  ) return
  failedNetwork.push({ page: currentPageUrl, url: request.url(), reason: failure })
})

await page.goto(new URL('/connections/overview', baseUrl).toString())
const persistentFrame = page.locator('iframe').first()
await persistentFrame.waitFor()
await persistentFrame.evaluate(element => { element.dataset.e2eFrameIdentity = 'persistent' })
const launchBeforeTabs = launchSessionRequests
const abortedBeforeTabs = abortedRequests
for (const label of ['提供商', '操作', '运行记录', '访问权限']) {
  await page.getByRole('navigation', { name: '连接二级导航' }).getByRole('link', { name: label, exact: true }).click()
}
await page.waitForURL('**/connections/access')
await page.locator('.dw-openconnector-loading').waitFor({ state: 'hidden' })
if (await page.locator('iframe[data-e2e-frame-identity="persistent"]').count() !== 1) {
  throw new Error('Connection tab navigation replaced the OpenConnector iframe')
}
if (launchSessionRequests - launchBeforeTabs > 2) {
  throw new Error(`Rapid navigation issued too many launch sessions: ${launchSessionRequests - launchBeforeTabs}`)
}
if (abortedRequests !== abortedBeforeTabs) {
  throw new Error(`Rapid navigation aborted ${abortedRequests - abortedBeforeTabs} OpenConnector requests`)
}
page.on('response', response => {
  if (response.status() >= 400) failedNetwork.push({
    page: currentPageUrl,
    url: response.url(),
    status: response.status(),
  })
})

for (const [surface, parentPath, pageMarker] of routes) {
  currentPageUrl = new URL(parentPath, baseUrl).toString()
  const failedBefore = failedNetwork.length
  await page.goto(new URL(parentPath, baseUrl).toString())
  const iframe = page.locator(`iframe[src^="/oc/${surface}"]`)
  await iframe.waitFor()
  const iframeElement = await iframe.elementHandle()
  const frame = await iframeElement?.contentFrame()
  if (!frame) throw new Error(`OpenConnector ${surface} frame did not load its canonical route`)
  await frame.waitForURL(url => url.pathname === `/oc/${surface}`)
  await frame.locator(pageMarker).waitFor()
  if (await frame.locator('.sidebar, .shell-header').count()) {
    throw new Error(`Embedded OpenConnector ${surface} rendered its standalone shell`)
  }
  if (await frame.getByText('404', { exact: true }).count()) {
    throw new Error(`Embedded OpenConnector ${surface} rendered a 404`)
  }
  await page.screenshot({ path: path.join(outputDir, `${surface}-1440x900.png`) })
  if (failedNetwork.length !== failedBefore) {
    throw new Error(
      `Failed network requests for ${surface}:\n${JSON.stringify(
        failedNetwork.slice(failedBefore),
        null,
        2,
      )}`,
    )
  }
}

// Action detail uses the same persistent iframe and a validated one-segment
// resource id, while the marketplace remains reachable only as a compatibility
// route (it is intentionally absent from the secondary nav).
if (await page.getByRole('navigation', { name: '连接二级导航' }).getByRole('link', { name: '市场', exact: true }).count()) {
  throw new Error('Marketplace must not be present in the connection secondary navigation')
}
currentPageUrl = new URL('/connections/actions/query_rows', baseUrl).toString()
await page.goto(currentPageUrl)
const actionFrame = page.locator('iframe[src^="/oc/actions/query_rows"]')
await actionFrame.waitFor()
const actionFrameElement = await actionFrame.elementHandle()
const actionContentFrame = await actionFrameElement?.contentFrame()
if (!actionContentFrame) throw new Error('OpenConnector action detail frame did not load')
await actionContentFrame.waitForURL(url => url.pathname === '/oc/actions/query_rows')

currentPageUrl = new URL('/connections/overview', baseUrl).toString()
await page.goto(new URL('/connections/overview', baseUrl).toString())
const overviewElement = await page.locator('iframe[src^="/oc/overview"]').elementHandle()
const overviewFrame = await overviewElement?.contentFrame()
if (!overviewFrame) throw new Error('OpenConnector overview frame did not load')
await overviewFrame.waitForURL(url => url.pathname === '/oc/overview')
await overviewFrame.evaluate(() => {
  history.pushState({}, '', '/oc/runs?service=gmail&embed=studio')
  dispatchEvent(new PopStateEvent('popstate'))
})
await page.waitForURL('**/connections/runs?service=gmail')

currentPageUrl = new URL('/connections/trace', baseUrl).toString()
await page.goto(new URL('/connections/trace', baseUrl).toString())
await page.waitForURL('**/connections/runs')

for (const [width, height] of [[1280, 800], [390, 844]]) {
  currentPageUrl = new URL('/connections/overview', baseUrl).toString()
  await page.setViewportSize({ width, height })
  await page.goto(new URL('/connections/overview', baseUrl).toString())
  await page.locator('iframe[src^="/oc/overview"]').waitFor()
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  if (overflow) throw new Error(`Connection surface overflowed at ${width}x${height}`)
  await page.screenshot({ path: path.join(outputDir, `overview-${width}x${height}.png`) })
}

const browserEvidence = JSON.stringify({
  requests: browserRequests,
  localStorage: await page.evaluate(() => ({ ...localStorage })),
  sessionStorage: await page.evaluate(() => ({ ...sessionStorage })),
})
for (const credentialMarker of [
  'OPENCONNECTOR_ADMIN_TOKEN',
  'admin_token',
  'test-admin-token',
]) {
  if (browserEvidence.includes(credentialMarker)) {
    throw new Error(`OpenConnector admin credential leaked into browser-visible state: ${credentialMarker}`)
  }
}
if (consoleErrors.length) throw new Error(`Browser console errors:\n${consoleErrors.join('\n')}`)
if (failedNetwork.length) throw new Error(`Failed network requests:\n${JSON.stringify(failedNetwork, null, 2)}`)

console.log(JSON.stringify({
  ok: true,
  preview_url: baseUrl,
  routes: Object.fromEntries(routes.map(([surface, parentPath]) => [surface, parentPath])),
  screenshots: outputDir,
  console_errors: consoleErrors,
  failed_network: failedNetwork,
  launch_session_requests: launchSessionRequests,
  aborted_requests: abortedRequests,
}, null, 2))
await context.close()
await browser.close()
