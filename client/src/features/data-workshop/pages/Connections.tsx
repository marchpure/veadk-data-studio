import { AlertTriangle, ArrowRight, CircleDot, Database, ExternalLink, Search, Server, ShieldCheck } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { workshopApi } from '../api'
import { AsyncState } from '../components/AsyncState'
import type { Connection, LoadState, Provider } from '../types'

export function ProviderMarket() {
  const [state, setState] = useState<LoadState>('loading')
  const [providers, setProviders] = useState<Provider[]>([])
  const [query, setQuery] = useState('')
  const load = useCallback(async () => {
    setState('loading')
    try {
      const result = await workshopApi.listProviders()
      setProviders(result)
      setState(result.length ? 'ready' : 'empty')
    } catch {
      setState('error')
    }
  }, [])
  useEffect(() => { void load() }, [load])
  const visibleProviders = providers.filter(provider =>
    `${provider.name} ${provider.category} ${provider.description}`.toLowerCase().includes(query.trim().toLowerCase()),
  )

  return (
    <div className="dw-page">
      <div className="dw-page-heading dw-heading-row">
        <div><span className="dw-eyebrow">连接器</span><h1>连接市场</h1><p>选择一个真实 Provider，完成配置、验证和能力发现。</p></div>
        <label className="dw-search"><Search size={17} /><input aria-label="搜索连接器" placeholder="搜索连接器" value={query} onChange={event => setQuery(event.target.value)} /></label>
      </div>
      {state !== 'ready' ? <AsyncState state={state} message={state === 'error' ? '无法读取连接器目录，请检查 OpenConnector。' : undefined} onRetry={load} /> : visibleProviders.length === 0 ? <AsyncState state="empty" title="没有匹配的连接器" message="尝试搜索其他名称、类型或描述。" /> : <div className="dw-provider-grid">
        {visibleProviders.map(provider => (
          <Link
            className={`dw-provider-card ${provider.available ? '' : 'disabled'}`}
            to={`/connections/providers/${provider.id}`}
            key={provider.id}
            aria-disabled={!provider.available}
            tabIndex={provider.available ? 0 : -1}
            onClick={event => {
              if (!provider.available) event.preventDefault()
            }}
          >
            <div className="dw-provider-logo" style={{ background: provider.color || '#2f6b52' }}>{provider.name.slice(0, 1)}</div>
            <div><span>{provider.category}</span><h2>{provider.name}</h2><p>{provider.description}</p></div>
            <ArrowRight size={18} />
          </Link>
        ))}
      </div>}
    </div>
  )
}

export function ConnectionOverview() {
  const [state, setState] = useState<LoadState>('loading')
  const [connections, setConnections] = useState<Connection[]>([])
  const load = useCallback(async () => {
    setState('loading')
    try {
      const result = await workshopApi.listConnections()
      setConnections(result)
      setState(result.length ? 'ready' : 'empty')
    } catch {
      setState('error')
    }
  }, [])
  useEffect(() => { void load() }, [load])

  return (
    <div className="dw-page">
      <div className="dw-page-heading dw-heading-row">
        <div><span className="dw-eyebrow">连接</span><h1>连接总览</h1><p>查看连接状态、能力数量与最近变更。</p></div>
        <Link className="dw-button dw-button-primary" to="/connections/providers/market">添加连接</Link>
      </div>
      {state !== 'ready' ? (
        <AsyncState state={state} onRetry={load} message={state === 'error' ? '请检查 OpenConnector 配置和网络状态。' : undefined} />
      ) : (
        <div className="dw-table-wrap"><table className="dw-table"><thead><tr><th>连接</th><th>Provider</th><th>状态</th><th>Actions</th><th>更新时间</th></tr></thead>
          <tbody>{connections.map(connection => <tr key={connection.id}><td><Link to={`/connections/providers/${connection.id}`}>{connection.name}</Link></td><td>{connection.provider}</td><td><span className={`dw-status ${connection.status}`}><CircleDot size={12} />{connection.status}</span></td><td>{connection.action_count ?? '-'}</td><td>{connection.updated_at || '-'}</td></tr>)}</tbody>
        </table></div>
      )}
    </div>
  )
}

export function ConnectionDetail() {
  const { id = '' } = useParams()
  const [connection, setConnection] = useState<Connection | null>(null)
  const [state, setState] = useState<LoadState>('loading')
  const [launching, setLaunching] = useState(false)
  const [launchError, setLaunchError] = useState('')
  const load = useCallback(async () => {
    setState('loading')
    try {
      setConnection(await workshopApi.getConnection(id))
      setState('ready')
    } catch { setState('error') }
  }, [id])
  useEffect(() => { void load() }, [load])
  const launchConsole = async () => {
    setLaunching(true)
    setLaunchError('')
    try {
      const session = await workshopApi.createLaunchSession()
      window.location.assign(session.launch_url)
    } catch {
      setLaunchError('无法创建短期 Console 会话，请检查 OpenConnector 配置。')
      setLaunching(false)
    }
  }

  if (state !== 'ready' || !connection) return <div className="dw-page"><AsyncState state={state === 'ready' ? 'empty' : state} onRetry={load} /></div>
  return (
    <div className="dw-page">
      <div className="dw-detail-head">
        <div className="dw-provider-logo oracle">O</div>
        <div><span className="dw-eyebrow">{connection.provider} 连接</span><h1>{connection.name}</h1><p>{connection.description}</p></div>
        <span className={`dw-status ${connection.status}`}><CircleDot size={12} />{connection.status === 'ready' ? 'Ready' : '待配置'}</span>
      </div>
      <div className="dw-detail-actions">
        <Link className="dw-button dw-button-primary" to={`/connections/providers/${connection.id}/access`}><ShieldCheck size={16} />访问权限</Link>
        <button className="dw-button dw-button-secondary" disabled={launching} onClick={() => void launchConsole()}><ExternalLink size={16} />{launching ? '正在启动…' : '打开连接控制台'}</button>
      </div>
      {launchError && <div className="dw-notice"><AlertTriangle size={16} />{launchError}</div>}
      <section className="dw-detail-section"><h2>连接生命周期</h2>
        <div className="dw-timeline">
          <div className="done"><span>1</span><strong>选择 Provider</strong><small>Oracle</small></div>
          <div><span>2</span><strong>配置并验证</strong><small>凭据由服务端托管</small></div>
          <div><span>3</span><strong>发现 Actions</strong><small>确认只读与风险分类</small></div>
          <div><span>4</span><strong>配置访问权限</strong><small>用户或用户组 + 角色</small></div>
        </div>
      </section>
      <section className="dw-detail-section"><h2>安全边界</h2><div className="dw-info-rows">
        <div><Server size={18} /><span><strong>Secret 不回显</strong>数据库凭据只保存在 OpenConnector。</span></div>
        <div><Database size={18} /><span><strong>默认私有</strong>没有 AccessGrant 的连接不会出现在 tools/list。</span></div>
      </div></section>
    </div>
  )
}

export function ConnectionPlaceholder({ title, body }: { title: string; body: string }) {
  return <div className="dw-page"><div className="dw-page-heading"><span className="dw-eyebrow">连接</span><h1>{title}</h1><p>{body}</p></div><div className="dw-placeholder"><Database size={24} /><strong>{title}</strong><span>数据由 OpenConnector V3 接口提供。</span></div></div>
}
