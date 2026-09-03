import {
  AlertCircle,
  Check,
  ChevronDown,
  Clipboard,
  Code2,
  ExternalLink,
  FileJson,
  HeartPulse,
  KeyRound,
  LockKeyhole,
  Play,
  RefreshCw,
  ServerCog,
  TerminalSquare,
} from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { workshopApi } from '../api'
import { AsyncState } from '../components/AsyncState'
import type { DocsConfig, DocsStatus, LoadState } from '../types'

type Tab = 'mcp' | 'http' | 'sdk'
type TestOperation = 'health' | 'identity' | 'tools_list' | 'list_connections'

const tools = [
  ['list_apps', '列出当前身份可见的应用空间'],
  ['list_connections', '列出 AccessGrant 允许访问的连接'],
  ['search_actions', '按意图搜索当前身份可用的 Actions'],
  ['get_action_guide', '获取 Action 参数与调用约束'],
  ['execute_action', '执行已授权 Action，并在每次调用时重新鉴权'],
]

function CopyButton({ value, label = '复制' }: { value: string; label?: string }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    await navigator.clipboard.writeText(value)
    setCopied(true)
  }
  return <button className="dw-icon-text" onClick={() => void copy()}>{copied ? <Check size={15} /> : <Clipboard size={15} />}{copied ? '已复制' : label}</button>
}

function CodeBlock({ code }: { code: string }) {
  return <div className="dw-code"><CopyButton value={code} /><pre><code>{code}</code></pre></div>
}

function ReadOnlyTester() {
  const [operation, setOperation] = useState<TestOperation>('health')
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<unknown>(null)
  const [error, setError] = useState('')
  const run = async () => {
    setRunning(true); setError(''); setResult(null)
    try { setResult(await workshopApi.runReadOnlyTest(operation)) }
    catch (requestError) { setError(requestError instanceof Error ? requestError.message : '测试失败') }
    finally { setRunning(false) }
  }
  return <section className="dw-tester">
    <div className="dw-section-heading"><div><span className="dw-eyebrow">安全验证</span><h2>只读测试器</h2><p>服务端仅允许固定的只读操作，不生成或展示用户 Token。</p></div><LockKeyhole size={22} /></div>
    <div className="dw-tester-controls"><select value={operation} onChange={event => setOperation(event.target.value as TestOperation)}>
      <option value="health">服务健康检查</option><option value="identity">身份状态</option><option value="tools_list">tools/list</option><option value="list_connections">list_connections</option>
    </select><button className="dw-button dw-button-primary" disabled={running} onClick={() => void run()}>{running ? <RefreshCw className="dw-spin" size={16} /> : <Play size={16} />}{running ? '运行中' : '运行测试'}</button></div>
    {(result !== null || error) && <div className={`dw-test-output ${error ? 'error' : ''}`}><header>{error ? <AlertCircle size={15} /> : <Check size={15} />}{error ? '测试失败' : '测试完成'}</header><pre>{error || JSON.stringify(result, null, 2)}</pre></div>}
  </section>
}

export function ConnectionDocs() {
  const [tab, setTab] = useState<Tab>('mcp')
  const [config, setConfig] = useState<DocsConfig | null>(null)
  const [status, setStatus] = useState<DocsStatus | null>(null)
  const [state, setState] = useState<LoadState>('loading')
  const load = useCallback(async () => {
    setState('loading')
    try {
      const [nextConfig, nextStatus] = await Promise.all([workshopApi.getDocsConfig(), workshopApi.getDocsStatus()])
      setConfig(nextConfig); setStatus(nextStatus); setState('ready')
    } catch { setState('error') }
  }, [])
  useEffect(() => { void load() }, [load])

  if (state !== 'ready' || !config || !status) return <div className="dw-page"><div className="dw-page-heading"><span className="dw-eyebrow">连接</span><h1>文档</h1><p>MCP、HTTP API 与 SDK 的统一接入说明。</p></div><AsyncState state={state === 'ready' ? 'empty' : state} message="无法读取 OpenConnector 的非敏感接入元数据。请检查服务配置后重试。" onRetry={load} /></div>

  const endpoint = config.mcp.endpoint
  const workBuddy = JSON.stringify(config.mcp.workbuddy_config || { transport: 'streamable-http', url: endpoint, auth: 'oauth' }, null, 2)
  const genericClient = JSON.stringify(config.mcp.generic_config || { mcpServers: { 'data-workshop': { url: endpoint, transport: 'streamable-http', authentication: 'oauth' } } }, null, 2)
  const sdkLanguages = config.mcp.sdk_languages?.length ? config.mcp.sdk_languages : ['Python', 'TypeScript']
  return <div className="dw-page dw-docs-page">
    <div className="dw-page-heading dw-heading-row"><div><span className="dw-eyebrow">连接 / 文档</span><h1>使用连接能力</h1><p>通过 OAuth / JWT，以 MCP、HTTP API 或 SDK 调用当前身份获准的能力。</p></div><span className={`dw-health ${status.status}`}><HeartPulse size={16} />{status.status === 'healthy' ? '服务正常' : status.status === 'degraded' ? '服务降级' : '服务不可用'}</span></div>
    <div className="dw-doc-tabs" role="tablist">
      <button role="tab" aria-selected={tab === 'mcp'} className={tab === 'mcp' ? 'active' : ''} onClick={() => setTab('mcp')}><TerminalSquare size={17} />MCP</button>
      <button role="tab" aria-selected={tab === 'http'} className={tab === 'http' ? 'active' : ''} onClick={() => setTab('http')}><FileJson size={17} />HTTP API</button>
      <button role="tab" aria-selected={tab === 'sdk'} className={tab === 'sdk' ? 'active' : ''} onClick={() => setTab('sdk')}><Code2 size={17} />SDK</button>
    </div>
    {tab === 'mcp' && <div className="dw-doc-layout"><div className="dw-doc-main">
      <section className="dw-endpoint"><div><span>Streamable HTTP Endpoint</span><strong>{endpoint}</strong><small>{config.mcp.protocol || 'MCP Streamable HTTP'} · OAuth/JWT</small></div><CopyButton value={endpoint} label="复制 Endpoint" /></section>
      <section className="dw-doc-section"><div className="dw-section-heading"><div><span className="dw-section-number">01</span><h2>配置 MCP 客户端</h2></div></div><p>添加 MCP Server 后，浏览器将跳转到企业身份登录。Access Token 只通过 HTTPS Authorization Header 传输。</p><h3 className="dw-code-label">WorkBuddy</h3><CodeBlock code={workBuddy} /><h3 className="dw-code-label">通用客户端</h3><CodeBlock code={genericClient} /></section>
      <section className="dw-doc-section"><div className="dw-section-heading"><div><span className="dw-section-number">02</span><h2>完成 OAuth / JWT 登录</h2></div></div><ol className="dw-steps"><li><span>1</span><div><strong>发起登录</strong><p>客户端从 MCP Server 获取 OAuth 元数据并打开企业登录页。</p></div></li><li><span>2</span><div><strong>确认身份</strong><p>Agent Identity 签发带 issuer、audience、expiry 与 tenant 的 Access Token。</p></div></li><li><span>3</span><div><strong>发现能力</strong><p>调用 tools/list；结果按用户与用户组的 AccessGrant 动态过滤。</p></div></li></ol></section>
      <section className="dw-doc-section"><div className="dw-section-heading"><div><span className="dw-section-number">03</span><h2>通用工具</h2></div><span className="dw-doc-note">结果按 AccessGrant 动态过滤</span></div><div className="dw-tool-table">{tools.map(([name, description]) => <div key={name}><code>{name}</code><span>{description}</span></div>)}</div></section>
      <section className="dw-doc-section"><div className="dw-section-heading"><div><span className="dw-section-number">04</span><h2>最小只读调用</h2></div></div><CodeBlock code={`// tools/list\n{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}\n\n// 只读：列出当前身份可见连接\n{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"list_connections","arguments":{}}}`} /></section>
    </div><aside className="dw-doc-aside"><div><strong>身份状态</strong><span className={`dw-status ${config.identity.status === 'ready' ? 'ready' : 'error'}`}>{config.identity.status === 'ready' ? '已配置' : '需处理'}</span></div><dl><dt>UserPool</dt><dd>{config.identity.user_pool_ref || '-'}</dd><dt>Issuer</dt><dd>{config.identity.issuer || '-'}</dd><dt>Audience</dt><dd>{config.identity.audience?.join(', ') || '-'}</dd><dt>JWKS</dt><dd>{config.identity.jwks_status || '-'}</dd></dl><a href="/connections/access">查看访问权限 <ExternalLink size={14} /></a><a href="/connections/trace">查看调用 Trace <ExternalLink size={14} /></a></aside></div>}
    {tab === 'http' && <div className="dw-doc-single">
      <section className="dw-doc-section"><div className="dw-section-heading"><div><span className="dw-section-number">01</span><h2>版本化 HTTP API</h2></div></div><p>所有控制面请求使用 <code>/v1/*</code>。自然人请求默认使用 OAuth Bearer Token，不在 URL 或浏览器存储中保存凭据。</p><CodeBlock code={`curl --request GET \\\n  '${new URL('/v1/connections', endpoint).toString()}' \\\n  --header 'Authorization: Bearer $ACCESS_TOKEN' \\\n  --header 'Accept: application/json'`} /></section>
      <section className="dw-doc-section"><h2>错误包络</h2><CodeBlock code={`{\n  "error": {\n    "code": "ACCESS_DENIED",\n    "message": "Action is not allowed for this identity",\n    "request_id": "req_..."\n  }\n}`} /><div className="dw-link-row">{config.mcp.api_reference_url && <a href={config.mcp.api_reference_url} target="_blank" rel="noreferrer">API Reference <ExternalLink size={14} /></a>}{config.mcp.openapi_url && <a href={config.mcp.openapi_url} target="_blank" rel="noreferrer">OpenAPI <ExternalLink size={14} /></a>}</div></section>
    </div>}
    {tab === 'sdk' && <div className="dw-doc-single">
      {sdkLanguages.includes('Python') && <section className="dw-doc-section"><div className="dw-section-heading"><div><span className="dw-section-number">01</span><h2>Python SDK</h2></div><span className="dw-doc-note">批准语言</span></div><CodeBlock code="pip install openconnector" /><CodeBlock code={`import os\nfrom openconnector import Client\n\nclient = Client(\n    endpoint="${endpoint}",\n    access_token=os.environ["ACCESS_TOKEN"],\n)\nconnections = client.connections.list()\nprint([item.name for item in connections])`} /></section>}
      {sdkLanguages.includes('TypeScript') && <section className="dw-doc-section"><h2>TypeScript SDK</h2><CodeBlock code="pnpm add @openconnector/sdk" /><CodeBlock code={`import { OpenConnector } from "@openconnector/sdk";\n\nconst client = new OpenConnector({\n  endpoint: "${endpoint}",\n  getAccessToken: () => authSession.accessToken(),\n});\nconst connections = await client.connections.list();`} /></section>}
    </div>}
    <ReadOnlyTester />
    <details className="dw-advanced"><summary><ServerCog size={17} /><span><strong>高级：服务账号与兼容接入</strong><small>仅用于 M2M、CI、后台任务和旧客户端</small></span><ChevronDown size={17} /></summary><div><KeyRound size={18} /><p>Runtime API Key 不是自然人主流程，也不与用户 AccessGrant 混算。密钥创建和吊销应在受保护的管理端完成，文档页不会生成或显示用户 Token。</p></div></details>
  </div>
}
