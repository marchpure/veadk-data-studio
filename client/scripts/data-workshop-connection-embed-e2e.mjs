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
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const consoleErrors = []
const failedNetwork = []
const browserRequests = []
let currentPageUrl = ''

page.on('console', message => {
  if (message.type() === 'error') consoleErrors.push(message.text())
})
page.on('request', request => {
  browserRequests.push({
    url: request.url(),
    authorization: request.headers().authorization || '',
  })
})
page.on('requestfailed', request => {
  const failure = request.failure()?.errorText
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
}, null, 2))
await browser.close()
