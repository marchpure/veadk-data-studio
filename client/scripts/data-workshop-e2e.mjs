import { chromium } from 'playwright'
import fs from 'node:fs/promises'
import path from 'node:path'

const baseUrl = process.env.DATA_WORKSHOP_PREVIEW_URL || 'http://127.0.0.1:4173'
const mcpEndpoint = process.env.DATA_WORKSHOP_MCP_ENDPOINT ||
  'https://s4j054gh1e125mqsipi2e.apigateway-cn-beijing.volceapi.com/mcp'
const groupName = process.env.DATA_WORKSHOP_E2E_GROUP_NAME || '财务分析组'
const userQuery = process.env.DATA_WORKSHOP_E2E_USER_QUERY || 'Alice'
const userMatch = process.env.DATA_WORKSHOP_E2E_USER_MATCH || 'user-alice'
const oracleProviderId = process.env.DATA_WORKSHOP_E2E_ORACLE_PROVIDER_ID || 'oracle'
const outputDir = path.resolve('artifacts/data-workshop')
await fs.mkdir(outputDir, { recursive: true })

async function assertViewportGeometry(page, viewport) {
  const geometry = await page.evaluate(() => {
    const main = document.querySelector('.dw-main')
    const controls = [...document.querySelectorAll('button,a,input,select')].filter(element => {
      const style = getComputedStyle(element)
      const rect = element.getBoundingClientRect()
      return style.display !== 'none' &&
        style.visibility !== 'hidden' &&
        rect.width > 0 &&
        rect.height > 0 &&
        !element.closest('.dw-sidebar:not(.is-open)')
    })
    const clippedControls = controls.filter(element => {
      const rect = element.getBoundingClientRect()
      return rect.left < -0.5 || rect.right > window.innerWidth + 0.5
    })
    return {
      documentOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      mainOverflow: main ? main.scrollWidth - main.clientWidth : 0,
      clippedControls: clippedControls.map(element =>
        (element.textContent || element.getAttribute('aria-label') || element.tagName).trim(),
      ),
    }
  })
  if (geometry.documentOverflow || geometry.mainOverflow || geometry.clippedControls.length) {
    throw new Error(`Invalid ${viewport} geometry: ${JSON.stringify(geometry)}`)
  }
}

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const consoleErrors = []
const browserRequests = []
const networkFailures = []
const upstreamScopes = []
page.on('console', message => {
  if (message.type() === 'error') consoleErrors.push(message.text())
})
page.on('request', request => {
  browserRequests.push({ url: request.url(), authorization: request.headers().authorization || '' })
})
page.on('response', response => {
  if (response.status() >= 400) networkFailures.push({ url: response.url(), status: response.status() })
  const scope = response.headers()['x-data-workshop-upstream-scope']
  if (scope) upstreamScopes.push({ path: new URL(response.url()).pathname, scope })
})

const bootstrapResponse = page.waitForResponse(response =>
  new URL(response.url()).pathname === '/api/v1/bootstrap' && response.ok(),
)
await page.goto(baseUrl)
await page.waitForURL('**/home')
const bootstrapPayload = await (await bootstrapResponse).json()
const backendMode = bootstrapPayload.data.backend_mode
if (process.env.DATA_WORKSHOP_EXPECT_MODE && backendMode !== process.env.DATA_WORKSHOP_EXPECT_MODE) {
  throw new Error(`Expected backend mode ${process.env.DATA_WORKSHOP_EXPECT_MODE}, received ${backendMode}`)
}
if (backendMode === 'TEST') {
  await page.getByText('TEST BACKEND', { exact: true }).waitFor()
} else if (await page.getByText('TEST BACKEND', { exact: true }).count()) {
  throw new Error('REAL preview must not display the TEST BACKEND banner')
}
for (const step of ['准备数据', '配置访问权限', '查看接入文档', '生成 Skill']) {
  await page.getByText(step, { exact: true }).waitFor()
}
await page.getByRole('navigation', { name: '一级导航' }).getByRole('link').allTextContents().then(labels => {
  const expected = ['首页', '连接', '知识库', 'Skill', '最近会话']
  if (JSON.stringify(labels) !== JSON.stringify(expected)) {
    throw new Error(`Unexpected primary navigation: ${JSON.stringify(labels)}`)
  }
})
await page.goto(`${baseUrl}/connections/providers/market`)
const connectionNavigation = page.getByRole('navigation', { name: '连接二级导航' })
await connectionNavigation.waitFor()
await connectionNavigation.getByRole('link').allTextContents().then(labels => {
  const expected = ['总览', '连接器', 'Actions', 'Trace', '访问权限', '文档']
  if (JSON.stringify(labels) !== JSON.stringify(expected)) {
    throw new Error(`Unexpected connection navigation: ${JSON.stringify(labels)}`)
  }
})
await page.getByText('当前用户', { exact: true }).waitFor()
await page.getByRole('link', { name: /Oracle/ }).click()
await page.getByRole('link', { name: '访问权限' }).first().click()
await page.getByRole('button', { name: '新增授权' }).click()
await page.getByRole('button', { name: '用户组', exact: true }).click()
await page.getByRole('button', { name: new RegExp(groupName) }).click()
await page.getByRole('button', { name: /下一步/ }).click()
await page.getByRole('button', { name: /只读者/ }).click()
await page.getByRole('button', { name: /下一步/ }).click()
await page.getByRole('button', { name: '保存授权' }).click()
await page.getByText(groupName).first().waitFor()
await page.getByText('Access allowed').first().waitFor()
await page.getByRole('button', { name: '权限预览' }).click()
await page.getByPlaceholder('选择要预览的用户').fill(userQuery)
await page.getByRole('button', { name: '搜索' }).click()
await page.getByRole('button', { name: new RegExp(userMatch) }).click()
await page.getByText('最终 Actions 由直接授权').waitFor()
await page.getByRole('button', { name: '关闭权限预览' }).click()
const grantRow = page.locator('.dw-table tbody tr').filter({ hasText: groupName }).last()
await grantRow.getByTitle('编辑授权').click()
await page.getByRole('button', { name: /自定义/ }).click()
const highRiskAction = page.locator('.dw-action-picker label').filter({ hasText: 'refresh_snapshot' })
await highRiskAction.getByText('高风险', { exact: true }).waitFor()
await highRiskAction.click()
await page.getByRole('button', { name: /下一步/ }).click()
await page.getByRole('button', { name: '保存授权' }).click()
await grantRow.getByText('自定义', { exact: true }).waitFor()
page.once('dialog', dialog => dialog.accept())
await grantRow.getByTitle('撤销授权').click()
await grantRow.getByText('已撤销', { exact: true }).waitFor()
await page.getByRole('link', { name: 'Actions', exact: true }).click()
await page.getByRole('heading', { name: 'Actions' }).waitFor()
const consoleFrame = page.frameLocator('iframe[title="OpenConnector Actions"]')
await consoleFrame.getByText('"console":"actions"').waitFor()
await page.getByRole('link', { name: '文档', exact: true }).click()
await page.getByRole('tab', { name: 'MCP' }).click()
for (const tool of ['list_apps', 'list_connections', 'search_actions', 'get_action_guide', 'execute_action']) {
  await page.getByText(tool, { exact: true }).first().waitFor()
}
await page.getByRole('tab', { name: 'HTTP API' }).click()
await page.getByText('版本化 HTTP API').waitFor()
await page.getByRole('tab', { name: 'SDK' }).click()
await page.getByText('Python SDK').waitFor()
await page.locator('.dw-tester select').selectOption('tools_list')
await page.getByRole('button', { name: '运行测试' }).click()
await page.getByText('测试完成').waitFor()

await page.goto(`${baseUrl}/connections/docs`)
await page.getByText(mcpEndpoint, { exact: true }).waitFor()
const expectedHealthLabel = backendMode === 'TEST' ? '测试后端' : '服务正常'
await page.getByText(expectedHealthLabel, { exact: true }).waitFor()
if (backendMode === 'TEST' && await page.getByText('服务正常', { exact: true }).count()) {
  throw new Error('Test-backed preview must not claim normal service health')
}
await assertViewportGeometry(page, '1440x900')
await page.screenshot({ path: path.join(outputDir, 'connection-docs-1440x900.png') })
await page.setViewportSize({ width: 1280, height: 800 })
await page.getByText(expectedHealthLabel, { exact: true }).waitFor()
await assertViewportGeometry(page, '1280x800')
await page.screenshot({ path: path.join(outputDir, 'connection-docs-1280x800.png') })
await page.setViewportSize({ width: 390, height: 844 })
await page.getByText(expectedHealthLabel, { exact: true }).waitFor()
await assertViewportGeometry(page, '390x844')
await page.screenshot({ path: path.join(outputDir, 'connection-docs-390x844.png') })

for (const route of ['/mcp', '/mcp/new', '/mcp/example', '/mcp/not-found']) {
  await page.goto(`${baseUrl}${route}`)
  await page.waitForURL('**/connections/docs')
  await page.getByRole('heading', { name: '使用连接能力' }).waitFor()
}

await page.goBack()
await page.goForward()
await page.reload()
await page.getByRole('heading', { name: '使用连接能力' }).waitFor()
await page.goto(`${baseUrl}/connections/providers/new/${oracleProviderId}`)
await page.getByRole('heading', { name: '新建 Oracle 连接' }).waitFor()
await page.frameLocator('iframe[title="OpenConnector 新建 Oracle 连接"]').getByText('"console":"connections/new"').waitFor()

if (consoleErrors.length) {
  throw new Error(`Browser console errors:\n${consoleErrors.join('\n')}`)
}
const storage = await page.evaluate(() => ({
  local: { ...localStorage },
  session: { ...sessionStorage },
}))
const browserEvidence = JSON.stringify({ browserRequests, storage })
for (const credentialMarker of [
  'test-admin-token',
  'test-runtime-token',
  'OPENCONNECTOR_ADMIN_TOKEN',
  'OPENCONNECTOR_TEST_RUNTIME_TOKEN',
]) {
  if (browserEvidence.includes(credentialMarker)) {
    throw new Error(`OpenConnector credential leaked into browser-visible state: ${credentialMarker}`)
  }
}
const managementEvidence = upstreamScopes.filter(item =>
  /\/api\/v1\/(?:providers|connections|identity|access|connection-docs\/config)/.test(item.path),
)
if (managementEvidence.some(item => item.scope !== 'admin')) {
  throw new Error(`Management request escaped Admin API: ${JSON.stringify(managementEvidence)}`)
}
const mcpTestEvidence = upstreamScopes.filter(item => item.path.endsWith('/connection-docs/read-only-tests'))
if (!mcpTestEvidence.some(item => item.scope === 'runtime')) {
  throw new Error(`Missing controlled-user MCP evidence: ${JSON.stringify(mcpTestEvidence)}`)
}
const upstreamScopeSummary = Object.entries(upstreamScopes.reduce((summary, item) => {
  const key = `${item.scope} ${item.path}`
  summary[key] = (summary[key] || 0) + 1
  return summary
}, {})).map(([route, count]) => ({ route, count }))
console.log(JSON.stringify({
  ok: true,
  backend_mode: backendMode,
  preview_url: baseUrl,
  screenshots: outputDir,
  console_errors: consoleErrors,
  network_failures: networkFailures,
  upstream_scopes: upstreamScopeSummary,
  browser_request_paths: [...new Set(browserRequests
    .map(request => new URL(request.url).pathname)
    .filter(pathname => pathname.startsWith('/api/') || pathname.startsWith('/oc/')))],
}, null, 2))
await browser.close()
