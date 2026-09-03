import { chromium } from 'playwright'
import fs from 'node:fs/promises'
import path from 'node:path'

const baseUrl = process.env.DATA_WORKSHOP_PREVIEW_URL || 'http://127.0.0.1:4173'
const outputDir = path.resolve('artifacts/data-workshop')
await fs.mkdir(outputDir, { recursive: true })

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const consoleErrors = []
page.on('console', message => {
  if (message.type() === 'error') consoleErrors.push(message.text())
})

await page.goto(`${baseUrl}/connections/providers/market`)
await page.getByRole('link', { name: /Oracle/ }).click()
await page.getByRole('link', { name: '访问权限' }).first().click()
await page.getByRole('button', { name: '新增授权' }).click()
await page.getByRole('button', { name: /用户组/ }).click()
await page.getByRole('button', { name: /财务分析组/ }).click()
await page.getByRole('button', { name: /下一步/ }).click()
await page.getByRole('button', { name: /只读者/ }).click()
await page.getByRole('button', { name: /下一步/ }).click()
await page.getByRole('button', { name: '保存授权' }).click()
await page.getByText('财务分析组').first().waitFor()
await page.getByText('AccessGrant 创建').waitFor()
await page.getByRole('button', { name: '权限预览' }).click()
await page.getByPlaceholder('选择要预览的用户').fill('Alice')
await page.getByRole('button', { name: '搜索' }).click()
await page.getByRole('button', { name: /Alice Chen/ }).click()
await page.getByText('最终 Actions 由直接授权').waitFor()
await page.getByRole('button', { name: '关闭权限预览' }).click()
await page.getByRole('link', { name: 'Actions', exact: true }).click()
await page.getByRole('heading', { name: 'Actions' }).waitFor()
await page.locator('iframe[title="OpenConnector Actions"]').waitFor()
await page.getByRole('link', { name: '文档', exact: true }).click()
await page.getByRole('tab', { name: 'MCP' }).click()
await page.getByText('list_connections', { exact: true }).first().waitFor()
await page.getByRole('tab', { name: 'HTTP API' }).click()
await page.getByText('版本化 HTTP API').waitFor()
await page.getByRole('tab', { name: 'SDK' }).click()
await page.getByText('Python SDK').waitFor()
await page.getByRole('button', { name: '运行测试' }).click()
await page.getByText('测试完成').waitFor()

await page.goto(`${baseUrl}/connections/docs`)
await page.screenshot({ path: path.join(outputDir, 'connection-docs-1440x900.png') })
await page.setViewportSize({ width: 1280, height: 800 })
await page.screenshot({ path: path.join(outputDir, 'connection-docs-1280x800.png') })
await page.setViewportSize({ width: 390, height: 844 })
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

if (consoleErrors.length) {
  throw new Error(`Browser console errors:\n${consoleErrors.join('\n')}`)
}
console.log(JSON.stringify({ ok: true, preview_url: baseUrl, screenshots: outputDir }, null, 2))
await browser.close()
