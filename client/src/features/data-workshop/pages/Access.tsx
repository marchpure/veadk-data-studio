import {
  AlertTriangle,
  Check,
  ChevronRight,
  Eye,
  Pencil,
  Plus,
  Search,
  Shield,
  Trash2,
  UserRound,
  UsersRound,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { WorkshopApiError, workshopApi } from '../api'
import { AsyncState } from '../components/AsyncState'
import type { AccessGrant, AccessPreview, Action, AuditEvent, Connection, LoadState, Subject } from '../types'

type Role = AccessGrant['role_id']

const roleLabels: Record<Role, string> = {
  reader: '只读者',
  operator: '操作员',
  custom: '自定义',
}

function RiskBadge({ risk }: { risk: Action['risk'] }) {
  return <span className={`dw-risk ${risk}`}>{risk === 'low' ? '低风险' : risk === 'medium' ? '中风险' : '高风险'}</span>
}

interface GrantEditorProps {
  connection: Connection
  actions: Action[]
  editing?: AccessGrant | null
  onClose: () => void
  onSaved: () => void
}

function GrantEditor({ connection, actions, editing, onClose, onSaved }: GrantEditorProps) {
  const [step, setStep] = useState(editing ? 2 : 1)
  const [subjectType, setSubjectType] = useState<'user' | 'group'>(editing?.subject_type || 'group')
  const [query, setQuery] = useState('')
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [selected, setSelected] = useState<Subject | null>(
    editing
      ? { id: editing.subject_id, type: editing.subject_type, display_name: editing.subject_display_snapshot }
      : null,
  )
  const [role, setRole] = useState<Role>(editing?.role_id || 'reader')
  const [selectedActions, setSelectedActions] = useState<string[]>(editing?.action_scope || [])
  const [searchState, setSearchState] = useState<LoadState>('empty')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const search = useCallback(async () => {
    setSearchState('loading')
    setError('')
    try {
      const result = await workshopApi.searchSubjects(query, subjectType)
      setSubjects(result)
      setSearchState(result.length ? 'ready' : 'empty')
    } catch (requestError) {
      setSearchState('error')
      setError(
        requestError instanceof WorkshopApiError && requestError.status === 503
          ? 'Identity 未配置或 UserPool 当前不可用，请先检查身份提供方。'
          : '无法搜索用户目录，请稍后重试。',
      )
    }
  }, [query, subjectType])

  useEffect(() => {
    if (!editing) void search()
  }, [editing, search])

  const toggleAction = (actionId: string) => {
    setSelectedActions(current =>
      current.includes(actionId) ? current.filter(id => id !== actionId) : [...current, actionId],
    )
  }

  const save = async () => {
    if (!selected) return
    setSaving(true)
    setError('')
    const actionScope =
      role === 'custom'
        ? selectedActions
        : actions.filter(action => role === 'operator' || action.read_only).map(action => action.id)
    const payload = {
      connection_id: connection.id,
      subject_type: selected.type,
      subject_id: selected.id,
      subject_display_snapshot: selected.display_name,
      role_id: role,
      effect: 'allow' as const,
      action_scope: actionScope,
      version: editing?.version,
    }
    try {
      if (editing) await workshopApi.updateGrant(editing.id, payload)
      else await workshopApi.createGrant(payload)
      onSaved()
    } catch (requestError) {
      setError(
        requestError instanceof WorkshopApiError && requestError.status === 409
          ? '授权已被其他管理员修改。请关闭后刷新，再重新提交。'
          : '保存失败，现有授权未改变。请重试。',
      )
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="dw-drawer-layer">
      <button className="dw-drawer-backdrop" aria-label="关闭授权抽屉" onClick={onClose} />
      <aside className="dw-drawer" aria-label={editing ? '编辑授权' : '新增授权'}>
        <header><div><span className="dw-eyebrow">{connection.name}</span><h2>{editing ? '编辑授权' : '新增授权'}</h2></div><button className="dw-icon-button" aria-label="关闭" onClick={onClose}><X /></button></header>
        <div className="dw-drawer-steps">
          {['选择主体', '选择角色', '确认生效'].map((label, index) => (
            <div className={step >= index + 1 ? 'active' : ''} key={label}><span>{step > index + 1 ? <Check size={13} /> : index + 1}</span>{label}</div>
          ))}
        </div>
        <div className="dw-drawer-body">
          {step === 1 && (
            <>
              <div className="dw-segmented">
                <button className={subjectType === 'user' ? 'active' : ''} onClick={() => setSubjectType('user')}><UserRound size={16} />用户</button>
                <button className={subjectType === 'group' ? 'active' : ''} onClick={() => setSubjectType('group')}><UsersRound size={16} />用户组</button>
              </div>
              <form className="dw-search dw-search-wide" onSubmit={event => { event.preventDefault(); void search() }}>
                <Search size={17} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder={`搜索${subjectType === 'user' ? '用户姓名或邮箱' : '用户组'}`} /><button type="submit">搜索</button>
              </form>
              {searchState === 'ready' ? <div className="dw-subject-list">{subjects.map(subject => (
                <button className={selected?.id === subject.id ? 'selected' : ''} key={subject.id} onClick={() => setSelected(subject)}>
                  <span className="dw-avatar small">{subject.type === 'group' ? <UsersRound size={15} /> : subject.display_name.slice(0, 1)}</span>
                  <span><strong>{subject.display_name}</strong><small>{subject.secondary_text || subject.id}</small></span>
                  {selected?.id === subject.id && <Check size={17} />}
                </button>
              ))}</div> : <AsyncState state={searchState === 'loading' ? 'loading' : searchState === 'error' ? 'error' : 'empty'} message={error || '输入关键词搜索 UserPool 主体'} onRetry={search} />}
            </>
          )}
          {step === 2 && (
            <>
              <div className="dw-role-list">
                {(['reader', 'operator', 'custom'] as Role[]).map(roleId => (
                  <button className={role === roleId ? 'selected' : ''} key={roleId} onClick={() => setRole(roleId)}>
                    <span className="dw-radio">{role === roleId && <span />}</span>
                    <span><strong>{roleLabels[roleId]}</strong><small>{roleId === 'reader' ? '仅发现、Schema、查询和预览等只读 Actions' : roleId === 'operator' ? '只读能力与平台批准的业务写操作' : '逐项选择 Actions，高风险能力明确标记'}</small></span>
                  </button>
                ))}
              </div>
              {role === 'custom' && <div className="dw-action-picker"><h3>选择 Actions <span>{selectedActions.length} 项</span></h3>{actions.map(action => (
                <label key={action.id}><input type="checkbox" checked={selectedActions.includes(action.id)} onChange={() => toggleAction(action.id)} /><span><strong>{action.name}</strong><small>{action.description || action.id}</small></span><RiskBadge risk={action.risk} /></label>
              ))}</div>}
            </>
          )}
          {step === 3 && selected && (
            <div className="dw-review">
              <div><span>连接</span><strong>{connection.name}</strong></div>
              <div><span>授权主体</span><strong>{selected.display_name} · {selected.type === 'group' ? '用户组' : '用户'}</strong></div>
              <div><span>角色</span><strong>{roleLabels[role]}</strong></div>
              <div><span>Action 范围</span><strong>{role === 'custom' ? `${selectedActions.length} 项显式选择` : role === 'reader' ? '全部只读 Actions' : '批准的操作员 Actions'}</strong></div>
              <p><Shield size={17} />保存后，新请求立即按最新授权计算；不会为用户生成 Token。</p>
            </div>
          )}
          {error && step !== 1 && <div className="dw-inline-error"><AlertTriangle size={16} />{error}</div>}
        </div>
        <footer>
          <button className="dw-button dw-button-secondary" onClick={step === 1 ? onClose : () => setStep(step - 1)}>{step === 1 ? '取消' : '上一步'}</button>
          {step < 3 ? <button className="dw-button dw-button-primary" disabled={step === 1 ? !selected : role === 'custom' && !selectedActions.length} onClick={() => setStep(step + 1)}>下一步<ChevronRight size={16} /></button>
            : <button className="dw-button dw-button-primary" disabled={saving} onClick={() => void save()}>{saving ? '保存中…' : '保存授权'}</button>}
        </footer>
      </aside>
    </div>
  )
}

function PreviewPanel({ connectionId, onClose }: { connectionId: string; onClose: () => void }) {
  const [query, setQuery] = useState('')
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [preview, setPreview] = useState<AccessPreview | null>(null)
  const [state, setState] = useState<LoadState>('empty')
  const find = async () => {
    setState('loading')
    try {
      const result = await workshopApi.searchSubjects(query, 'user')
      setSubjects(result)
      setState(result.length ? 'ready' : 'empty')
    } catch { setState('error') }
  }
  const run = async (subject: Subject) => {
    setState('loading')
    try { setPreview(await workshopApi.previewAccess(subject.id, connectionId)); setState('ready') }
    catch { setState('error') }
  }
  return <div className="dw-drawer-layer"><button className="dw-drawer-backdrop" aria-label="关闭权限预览" onClick={onClose} /><aside className="dw-drawer">
    <header><div><span className="dw-eyebrow">实时策略计算</span><h2>权限预览</h2></div><button className="dw-icon-button" onClick={onClose}><X /></button></header>
    <div className="dw-drawer-body">
      <form className="dw-search dw-search-wide" onSubmit={event => { event.preventDefault(); void find() }}><Search size={17} /><input value={query} onChange={e => setQuery(e.target.value)} placeholder="选择要预览的用户" /><button>搜索</button></form>
      {!preview && state === 'ready' && <div className="dw-subject-list">{subjects.map(subject => <button key={subject.id} onClick={() => void run(subject)}><span className="dw-avatar small">{subject.display_name.slice(0, 1)}</span><span><strong>{subject.display_name}</strong><small>{subject.secondary_text}</small></span><Eye size={16} /></button>)}</div>}
      {preview ? <div className="dw-preview-result"><div className="dw-preview-user"><span className="dw-avatar">{preview.subject.display_name.slice(0, 1)}</span><span><strong>{preview.subject.display_name}</strong><small>最终 Actions 由直接授权、用户组授权和显式拒绝共同计算</small></span></div>
        {preview.connections.map(item => <section key={item.connection_id}><h3>{item.connection_name}<span>{item.actions.length} Actions</span></h3><div className="dw-chip-list">{item.actions.map(action => <span key={action.id}>{action.name}</span>)}</div><div className="dw-reasons">{item.reasons.map(reason => <p key={`${reason.grant_id}-${reason.source}`}><Check size={14} />{reason.effect === 'allow' ? '允许' : '拒绝'} · {reason.source}</p>)}</div></section>)}
      </div> : state !== 'ready' && <AsyncState state={state === 'loading' ? 'loading' : state === 'error' ? 'error' : 'empty'} message={state === 'empty' ? '搜索用户后查看其最终可执行 Actions。' : undefined} onRetry={find} />}
    </div>
  </aside></div>
}

export function ConnectionAccess() {
  const params = useParams()
  const [searchParams] = useSearchParams()
  const connectionId = params.id || searchParams.get('connection') || ''
  const [connections, setConnections] = useState<Connection[]>([])
  const [connection, setConnection] = useState<Connection | null>(null)
  const [grants, setGrants] = useState<AccessGrant[]>([])
  const [actions, setActions] = useState<Action[]>([])
  const [state, setState] = useState<LoadState>('loading')
  const [editor, setEditor] = useState<'new' | AccessGrant | null>(null)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [filter, setFilter] = useState('')
  const [notice, setNotice] = useState('')
  const [audit, setAudit] = useState<AuditEvent[]>([])

  const activeId = connectionId || connections[0]?.id
  const load = useCallback(async () => {
    setState('loading')
    setNotice('')
    try {
      const list = await workshopApi.listConnections()
      setConnections(list)
      const selectedConnection = activeId ? list.find(item => item.id === activeId) : list[0]
      if (!selectedConnection) { setState('empty'); return }
      setConnection(selectedConnection)
      const [grantItems, actionItems] = await Promise.all([
        workshopApi.getGrants(selectedConnection.id),
        workshopApi.getActions(selectedConnection.id),
      ])
      setGrants(grantItems)
      setActions(actionItems)
      setAudit(await workshopApi.getAudit(selectedConnection.id))
      setState('ready')
    } catch (error) {
      setState('error')
      setNotice(error instanceof WorkshopApiError && error.status === 503 ? 'OpenConnector 或 Identity 当前不可用。' : '加载授权数据失败。')
    }
  }, [activeId])
  useEffect(() => { void load() }, [load])

  const filtered = useMemo(() => grants.filter(grant => grant.subject_display_snapshot.toLowerCase().includes(filter.toLowerCase())), [filter, grants])
  const revoke = async (grant: AccessGrant) => {
    if (!window.confirm(`确认撤销 ${grant.subject_display_snapshot} 的访问权限？新请求将立即失效。`)) return
    try { await workshopApi.revokeGrant(grant.id); setNotice('授权已撤销'); await load() }
    catch { setNotice('撤销失败，请刷新后重试。') }
  }

  if (state !== 'ready' || !connection) return <div className="dw-page"><div className="dw-page-heading"><span className="dw-eyebrow">连接</span><h1>访问权限</h1></div><AsyncState state={state === 'ready' ? 'empty' : state} message={notice || '创建连接后即可配置用户和用户组权限。'} onRetry={load} /></div>

  return <div className="dw-page">
    <div className="dw-page-heading dw-heading-row"><div><span className="dw-eyebrow">{connection.name}</span><h1>访问权限</h1><p>为用户或用户组授予连接角色，并预览最终 Actions。</p></div><div className="dw-button-row"><button className="dw-button dw-button-secondary" onClick={() => setPreviewOpen(true)}><Eye size={16} />权限预览</button><button className="dw-button dw-button-primary" onClick={() => setEditor('new')}><Plus size={16} />新增授权</button></div></div>
    <div className="dw-access-toolbar"><label className="dw-search"><Search size={17} /><input value={filter} onChange={event => setFilter(event.target.value)} placeholder="搜索已授权用户或用户组" /></label><span>{grants.filter(g => g.status === 'active').length} 条有效授权</span></div>
    {notice && <div className="dw-notice"><AlertTriangle size={16} />{notice}<button onClick={() => setNotice('')}><X size={14} /></button></div>}
    {!filtered.length ? <AsyncState state="empty" title="还没有访问授权" message="连接默认私有。新增授权后，用户才会在 discovery 中看到允许的 Actions。" /> :
      <div className="dw-table-wrap"><table className="dw-table"><thead><tr><th>主体</th><th>类型</th><th>角色</th><th>Actions</th><th>状态</th><th>更新</th><th><span className="sr-only">操作</span></th></tr></thead><tbody>
        {filtered.map(grant => <tr key={grant.id}><td><strong>{grant.subject_display_snapshot}</strong><small>{grant.subject_id}</small></td><td>{grant.subject_type === 'group' ? '用户组' : '用户'}</td><td>{roleLabels[grant.role_id]}</td><td>{grant.action_scope.length}</td><td><span className={`dw-status ${grant.status}`}>{grant.status === 'active' ? '有效' : grant.status === 'conflict' ? '冲突' : '已撤销'}</span></td><td>{grant.updated_at || '-'}<small>{grant.updated_by || ''}</small></td><td><div className="dw-row-actions"><button title="编辑授权" onClick={() => setEditor(grant)}><Pencil size={15} /></button><button title="撤销授权" onClick={() => void revoke(grant)}><Trash2 size={15} /></button></div></td></tr>)}
      </tbody></table></div>}
    <section className="dw-audit-section"><div className="dw-section-heading"><div><h2>访问与调用审计</h2><p>AccessGrant 变更与 MCP allow/deny 判定。</p></div><a href="/connections/trace">前往 Trace <ChevronRight size={16} /></a></div>
      {audit.length ? <div className="dw-audit-events">{audit.slice(0, 5).map(event => <div key={event.id}><Shield size={15} /><span><strong>{event.event_type}</strong><small>{event.subject_display || event.action_name || event.request_id}</small></span><span className={`dw-status ${event.decision === 'deny' ? 'error' : 'ready'}`}>{event.decision || 'changed'}</span><time>{event.created_at}</time></div>)}</div> : <p className="dw-audit-empty">此连接还没有审计事件。授权变更或真实调用后会显示在这里。</p>}
    </section>
    {editor && <GrantEditor connection={connection} actions={actions} editing={editor === 'new' ? null : editor} onClose={() => setEditor(null)} onSaved={() => { setEditor(null); setNotice('授权已保存并立即生效'); void load() }} />}
    {previewOpen && <PreviewPanel connectionId={connection.id} onClose={() => setPreviewOpen(false)} />}
  </div>
}
