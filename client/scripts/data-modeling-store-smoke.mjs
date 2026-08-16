import { build } from 'esbuild'
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'

globalThis.window = globalThis.window || { __RUNTIME_CONFIG__: {} }
globalThis.localStorage = globalThis.localStorage || {
  getItem: () => null,
  setItem: () => {},
  removeItem: () => {},
}
globalThis.fetch = async () => {
  throw new Error('Store smoke runs without an API server')
}
console.error = () => {}

const cacheDir = join(process.cwd(), 'node_modules', '.cache')
mkdirSync(cacheDir, { recursive: true })
const outfile = join(cacheDir, 'data-modeling-store-smoke.mjs')

await build({
  entryPoints: ['./src/features/data-modeling/store/useDataModelingStore.ts'],
  outfile,
  bundle: true,
  platform: 'node',
  format: 'esm',
  jsx: 'automatic',
  define: {
    'import.meta.env.VITE_IS_HOSTED': '"false"',
    'import.meta.env.VITE_IS_SELF_HOSTED': '"false"',
    'import.meta.env.VITE_GOOGLE_CLIENT_ID': '""',
  },
  external: ['react', 'react-dom'],
  logLevel: 'silent',
})

const { useDataModelingStore, selectActiveModel } = await import(pathToFileURL(outfile).href)

const store = useDataModelingStore.getState()
store.resetDemo()
store.acceptSuggestion('sug-policy-pii')
store.fixFanoutRelationship('rel-orders-refunds-risk')
store.updateMetric('paid_revenue', { formula: 'SUM(orders.net_amount) * 1.01' })
store.setMetricCertification('paid_revenue', 'certified')
store.saveExploreArtifact('query')
await store.publishModel()
await store.runMcpQuery()

const finalState = useDataModelingStore.getState()
const model = selectActiveModel(finalState)

const assertions = [
  ['model published v3', model.status === 'Published' && model.publishedVersion === 'v3'],
  ['fanout blocker cleared', model.readinessDetail.blockers.length === 0],
  ['MCP result generated', Boolean(model.mcp.lastResult?.resolvedMetric)],
  ['saved query count changed', model.explore.savedQueryCount > 8],
]

const failed = assertions.filter(([, ok]) => !ok)
if (failed.length) {
  console.error(JSON.stringify({ ok: false, failed: failed.map(([name]) => name), model }, null, 2))
  process.exit(1)
}

console.log(JSON.stringify({
  ok: true,
  model: model.name,
  status: model.status,
  version: model.publishedVersion,
  readiness: model.readiness,
  mcpResult: model.mcp.lastResult,
}, null, 2))
