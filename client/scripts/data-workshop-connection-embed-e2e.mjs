import { chromium } from 'playwright'

const baseUrl = process.env.DATA_WORKSHOP_PREVIEW_URL
if (!baseUrl) {
  throw new Error('DATA_WORKSHOP_PREVIEW_URL must point to a real Data Studio preview')
}

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

page.on('console', message => {
  if (message.type() === 'error') consoleErrors.push(message.text())
})
page.on('request', request => {
  browserRequests.push({
    url: request.url(),
    authorization: request.headers().authorization || '',
  })
})
page.on('requestfailed', request => failedNetwork.push({
  url: request.url(),
  reason: request.failure()?.errorText,
}))
page.on('response', response => {
  if (response.status() >= 400) failedNetwork.push({
    url: response.url(),
    status: response.status(),
  })
})

for (const [surface, parentPath, pageMarker] of routes) {
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
}

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

await page.goto(new URL('/connections/trace', baseUrl).toString())
await page.waitForURL('**/connections/runs')

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
  console_errors: consoleErrors,
  failed_network: failedNetwork,
}, null, 2))
await browser.close()
