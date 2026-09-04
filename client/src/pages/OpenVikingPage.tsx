import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import {
  Activity, ChevronDown, ChevronRight, File, FilePlus2, Folder,
  Loader2, Play, RefreshCw, Search, Settings2, Trash2, Upload, X,
} from 'lucide-react'
import { openVikingApi, type OpenVikingProfile } from '../services/openviking'

type Entry = { uri: string; name: string; is_dir?: boolean; isDir?: boolean; size?: number | string; abstract?: string; overview?: string }
type Mode = 'resources' | 'retrieval' | 'tasks' | 'watches' | 'connection'
type Retrieval = 'search' | 'find' | 'grep' | 'glob'

const asEntries = (value: unknown): Entry[] => {
  const raw = value as { entries?: Entry[]; items?: Entry[]; nodes?: Entry[] } | Entry[] | null
  if (Array.isArray(raw)) return raw
  return raw?.entries ?? raw?.items ?? raw?.nodes ?? []
}

const isDir = (entry: Entry) => Boolean(entry.is_dir ?? entry.isDir ?? entry.uri.endsWith('/'))

function ProfilePanel({ profiles, onRefresh, onValidated }: { profiles: OpenVikingProfile[]; onRefresh: () => void; onValidated: (profile: OpenVikingProfile) => void }) {
  const [form, setForm] = useState({ display_name: 'OpenViking', base_url: '', api_key: '', workspace_uri: 'viking://resources/' })
  const [editingId, setEditingId] = useState('')
  const [busy, setBusy] = useState('')
  const [message, setMessage] = useState('')
  const create = async () => {
    setBusy('create'); setMessage('')
    try {
      const profile = await openVikingApi.createProfile(form)
      setMessage(`Profile ${profile.display_name} is Pending. Validate it against the hosted service.`)
      onRefresh()
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Unable to save profile') }
    finally { setBusy('') }
  }
  const validate = async (id: string) => {
    setBusy(id); setMessage('')
    try { onValidated(await openVikingApi.validateProfile(id)) }
    catch (error) { setMessage(error instanceof Error ? error.message : 'Validation failed'); onRefresh() }
    finally { setBusy('') }
  }
  const revoke = async (id: string) => {
    if (!window.confirm('Revoke this profile?')) return
    await openVikingApi.deleteProfile(id); onRefresh()
  }
  const edit = async () => {
    if (!editingId) return
    setBusy(`edit:${editingId}`); setMessage('')
    try {
      const updated = await openVikingApi.updateProfile(editingId, {
        display_name: form.display_name,
        workspace_uri: form.workspace_uri,
        ...(form.base_url ? { base_url: form.base_url } : {}),
        ...(form.api_key ? { api_key: form.api_key } : {}),
      })
      setForm((current) => ({ ...current, api_key: '' }))
      setEditingId('')
      setMessage(`Profile ${updated.display_name} updated and is Pending until validation.`)
      onRefresh()
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Unable to update profile') }
    finally { setBusy('') }
  }
  return <section className="ov-connection">
    <div className="ov-section-title"><Settings2 size={18} /><h2>Connection profiles</h2></div>
    <div className="ov-profile-grid">
      {(['display_name', 'base_url', 'workspace_uri', 'api_key'] as const).map((key) =>
        <label key={key}>{key === 'display_name' ? 'Name' : key === 'base_url' ? 'Hosted base URL' : key === 'workspace_uri' ? 'Workspace URI' : 'API key'}
          <input type={key === 'api_key' ? 'password' : 'text'} autoComplete="off" value={form[key]} onChange={(event) => setForm({ ...form, [key]: event.target.value })} />
        </label>)}
    </div>
    <div className="ov-actions">
      <button className="ov-primary" disabled={busy === 'create'} onClick={() => void create()}><Settings2 size={15} /> Save Pending profile</button>
      {editingId && <button className="ov-secondary" disabled={busy.startsWith('edit:')} onClick={() => void edit()}><Settings2 size={14} /> Save profile changes</button>}
    </div>
    {message && <p className="ov-form-message" role="alert">{message}</p>}
    <div className="ov-profile-list">{profiles.map((profile) => <div className="ov-profile-row" key={profile.profile_id}>
      <div><strong>{profile.display_name}</strong><span className={`ov-status ${profile.status}`}>{profile.status}</span><small>{profile.workspace_uri}</small></div>
      <button className="ov-secondary" onClick={() => { setEditingId(profile.profile_id); setForm((current) => ({ ...current, display_name: profile.display_name, base_url: '', api_key: '', workspace_uri: profile.workspace_uri })); setMessage(`Editing ${profile.display_name}. Enter a new URL or key only when changing credentials.`) }}><Settings2 size={13} /> Edit</button>
      <button className="ov-secondary" disabled={busy === profile.profile_id} onClick={() => void validate(profile.profile_id)}><RefreshCw size={13} /> Validate</button>
      <button className="ov-icon-button" title="Revoke profile" onClick={() => void revoke(profile.profile_id)}><Trash2 size={14} /></button>
    </div>)}</div>
  </section>
}

function ResourceTree({ profileId, root, selected, onSelect }: { profileId: string; root: string; selected: string; onSelect: (entry: Entry) => void }) {
  const [open, setOpen] = useState<Record<string, boolean>>({ [root]: true })
  const [data, setData] = useState<Record<string, Entry[]>>({})
  const [error, setError] = useState('')
  const load = useCallback(async (uri: string) => {
    try {
      const value = await openVikingApi.operation(profileId, 'fs_list', { resource_ref: uri, output: 'agent', node_limit: 200 })
      setData((current) => ({ ...current, [uri]: asEntries(value) }))
    }
    catch (value) { setError(value instanceof Error ? value.message : 'Unable to load directory') }
  }, [profileId])
  useEffect(() => { void load(root) }, [load, root])
  const render = (uri: string, depth: number): ReactNode[] => (data[uri] ?? []).map((entry) => {
    const directory = isDir(entry); const expanded = Boolean(open[entry.uri])
    return <div key={entry.uri}>
      <button className={`ov-tree-row ${selected === entry.uri ? 'is-selected' : ''}`} style={{ paddingLeft: 10 + depth * 16 }} onClick={() => { onSelect(entry); if (directory) { setOpen({ ...open, [entry.uri]: !expanded }); if (!data[entry.uri]) void load(entry.uri) } }}>
        {directory ? (expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />) : <span className="ov-tree-indent" />}
        {directory ? <Folder size={15} /> : <File size={15} />}<span>{entry.name || entry.uri}</span>
      </button>
      {directory && expanded ? render(entry.uri, depth + 1) : null}
    </div>
  })
  return <div className="ov-tree">{error && <p className="ov-form-message">{error}</p>}{render(root, 0)}</div>
}

function ImportPanel({ profileId, root, onDone }: { profileId: string; root: string; onDone: () => void }) {
  const [mode, setMode] = useState<'text' | 'url' | 'file'>('text')
  const [name, setName] = useState('note.md'); const [text, setText] = useState(''); const [url, setUrl] = useState('')
  const [message, setMessage] = useState('')
  const submitText = async () => { try { await openVikingApi.importText(profileId, { parent_ref: root, filename: name, content: text }); setMessage('Import task submitted'); onDone() } catch (e) { setMessage(e instanceof Error ? e.message : 'Import failed') } }
  const submitUrl = async () => { try { await openVikingApi.operation(profileId, 'resource_import', { path: url, parent_ref: root, source_name: url, wait: false }); setMessage('Import task submitted'); onDone() } catch (e) { setMessage(e instanceof Error ? e.message : 'Import failed') } }
  return <section className="ov-panel ov-import-panel">
    <div className="ov-section-title"><FilePlus2 size={17} /><h2>Add resource</h2></div>
    <div className="ov-segmented">{(['text', 'url', 'file'] as const).map((value) => <button className={mode === value ? 'active' : ''} key={value} onClick={() => setMode(value)}>{value === 'text' ? 'Text' : value === 'url' ? 'Web page' : 'File'}</button>)}</div>
    {mode === 'text' && <><input value={name} onChange={(e) => setName(e.target.value)} placeholder="filename.md" /><textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste text to import" /><button className="ov-primary" onClick={() => void submitText()}><Upload size={15} /> Import text</button></>}
    {mode === 'url' && <><input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://example.com/article" /><button className="ov-primary" onClick={() => void submitUrl()}><Upload size={15} /> Import web page</button></>}
    {mode === 'file' && <label className="ov-dropzone"><Upload size={18} /> Select TXT, Markdown, PDF, CSV, JSON, or XLSX<input type="file" accept=".txt,.md,.pdf,.csv,.json,.xlsx" onChange={(e) => { const file = e.target.files?.[0]; if (file) void openVikingApi.upload(profileId, root, file).then(() => { setMessage('Import task submitted'); onDone() }).catch((err) => setMessage(err instanceof Error ? err.message : 'Import failed')) }} /></label>}
    {message && <p className="ov-form-message">{message}</p>}
  </section>
}

function RetrievalPanel({ profileId, root }: { profileId: string; root: string }) {
  const [mode, setMode] = useState<Retrieval>('search'); const [query, setQuery] = useState(''); const [result, setResult] = useState<unknown>(null); const [busy, setBusy] = useState(false)
  const submit = async (nextMode = mode) => { setBusy(true); try { setResult(await openVikingApi.operation(profileId, nextMode, nextMode === 'grep' || nextMode === 'glob' ? { resource_ref: root, pattern: query } : { query, target_ref: root })) } catch (e) { setResult({ error: e instanceof Error ? e.message : 'Retrieval failed' }) } finally { setBusy(false) } }
  const rows = Array.isArray(result) ? result : ((result as { items?: unknown[]; result?: unknown[] } | null)?.items ?? (result as { result?: unknown[] } | null)?.result ?? [])
  return <section className="ov-retrieval"><div className="ov-section-title"><Search size={18} /><h2>Retrieval</h2></div><div className="ov-segmented">{(['search', 'find', 'grep', 'glob'] as const).map((value) => <button className={mode === value ? 'active' : ''} key={value} onClick={() => setMode(value)}>{value}</button>)}</div><div className="ov-retrieval-bar"><input value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') void submit() }} placeholder="Search OpenViking context" /><button className="ov-primary" disabled={busy} onClick={() => void submit()}><Play size={14} /> Run</button></div>{result !== null && <div className="ov-result-list">{rows.length ? rows.map((item, index) => { const row = item as Record<string, unknown>; return <article key={index}><strong>{String(row.title ?? row.name ?? row.uri ?? 'Result')}</strong><small>{String(row.uri ?? row.resource_ref ?? '')}</small><p>{String(row.content ?? row.text ?? row.abstract ?? row.overview ?? 'No preview content returned')}</p></article> }) : <div className="ov-empty">No matching resources returned.</div>}</div>}</section>
}

export default function OpenVikingPage({ connectOnly = false }: { connectOnly?: boolean }) {
  const navigate = useNavigate(); const [profiles, setProfiles] = useState<OpenVikingProfile[]>([]); const [activeId, setActiveId] = useState(''); const [mode, setMode] = useState<Mode>(connectOnly ? 'connection' : 'resources'); const [loading, setLoading] = useState(true); const [error, setError] = useState(''); const [selected, setSelected] = useState<Entry | null>(null); const [preview, setPreview] = useState<unknown>(null); const [refresh, setRefresh] = useState(0)
  const active = useMemo(() => profiles.find((profile) => profile.profile_id === activeId && profile.status === 'ready'), [activeId, profiles]); const root = active?.workspace_uri ?? 'viking://resources/'
  const load = useCallback(async () => { setLoading(true); try { const values = await openVikingApi.listProfiles(); setProfiles(values); const ready = values.find((item) => item.profile_id === activeId && item.status === 'ready') ?? values.find((item) => item.status === 'ready'); setActiveId(ready?.profile_id ?? ''); if (!ready && !connectOnly) navigate('/kb/connect', { replace: true }) } catch (value) { setError(value instanceof Error ? value.message : 'Unable to load profiles') } finally { setLoading(false) } }, [activeId, connectOnly, navigate, refresh])
  useEffect(() => { void load() }, [load])
  const select = async (entry: Entry) => { setSelected(entry); if (isDir(entry)) { setPreview(await openVikingApi.operation(active!.profile_id, 'content_overview', { resource_ref: entry.uri })) } else { setPreview(await openVikingApi.operation(active!.profile_id, 'content_read', { resource_ref: entry.uri, raw: true })) } }
  if (loading) return <main className="ov-page"><Loader2 className="ov-spin" /> Loading OpenViking</main>
  if (!connectOnly && !active) return <Navigate to="/kb/connect" replace />
  return <main className="ov-page">
    <header className="ov-header"><div><p className="ov-eyebrow">Knowledge source</p><h1>OpenViking</h1><p className="ov-muted">Hosted context workspace</p></div><button className="ov-icon-button" title="Refresh" onClick={() => setRefresh((value) => value + 1)}><RefreshCw size={16} /></button></header>
    {error && <div className="ov-error">{error}</div>}
    <nav className="ov-nav">{(['resources', 'retrieval', 'tasks', 'watches', 'connection'] as const).map((item) => <button className={mode === item ? 'active' : ''} key={item} onClick={() => setMode(item)}>{item}</button>)}</nav>
    {mode === 'connection' || !active ? <ProfilePanel profiles={profiles} onRefresh={() => setRefresh((value) => value + 1)} onValidated={(profile) => { setProfiles((current) => current.map((item) => item.profile_id === profile.profile_id ? profile : item)); setActiveId(profile.profile_id); navigate('/kb') }} /> :
      mode === 'resources' ? <div className="ov-resource-layout"><aside className="ov-panel ov-tree-panel"><div className="ov-section-title"><Folder size={17} /><h2>Resource context tree</h2></div><ResourceTree profileId={active.profile_id} root={root} selected={selected?.uri ?? ''} onSelect={(entry) => void select(entry)} /><ImportPanel profileId={active.profile_id} root={root} onDone={() => setRefresh((value) => value + 1)} /></aside><section className="ov-panel ov-preview"><div className="ov-preview-header"><div><span className="ov-muted">Preview</span><h2>{selected?.name ?? 'Select a resource'}</h2></div>{selected && <button className="ov-icon-button" title="Close preview" onClick={() => { setSelected(null); setPreview(null) }}><X size={15} /></button>}</div>{preview ? <pre>{typeof preview === 'string' ? preview : JSON.stringify(preview, null, 2)}</pre> : <div className="ov-empty">Select a file or directory in the context tree.</div>}<div className="ov-preview-actions"><button className="ov-secondary" onClick={() => active && void openVikingApi.authorizeSkillContext(active.profile_id, selected?.uri ?? root).then(setPreview)}><FilePlus2 size={14} /> Add to Skill Context</button>{selected && <button className="ov-secondary ov-danger" onClick={() => active && window.confirm('Delete this resource?') && void openVikingApi.deleteResource(active.profile_id, selected.uri).then(() => { setSelected(null); setPreview(null); setRefresh((value) => value + 1) })}><Trash2 size={14} /> Delete</button>}</div></section></div> :
      mode === 'retrieval' ? <RetrievalPanel profileId={active.profile_id} root={root} /> : <OperationsPanel profileId={active.profile_id} mode={mode} root={root} />}
  </main>
}

function OperationsPanel({ profileId, mode, root }: { profileId: string; mode: 'tasks' | 'watches'; root: string }) {
  const [items, setItems] = useState<unknown[]>([]); const [message, setMessage] = useState('')
  const load = async () => { try { const value = await openVikingApi.operation(profileId, mode, mode === 'tasks' ? { limit: 50 } : { active_only: false }); setItems(Array.isArray(value) ? value : ((value as { items?: unknown[] })?.items ?? [])) } catch (e) { setMessage(e instanceof Error ? e.message : 'Unable to load') } }
  useEffect(() => { void load() }, [profileId, mode])
  const createWatch = async () => {
    try { await openVikingApi.operation(profileId, 'resource_import', { path: root, parent_ref: root, wait: false, watch_interval: 1440 }); setMessage('Watch creation submitted'); await load() }
    catch (error) { setMessage(error instanceof Error ? error.message : 'Unable to create watch') }
  }
  const updateWatch = async (item: Record<string, unknown>) => {
    const id = String(item.task_id ?? item.watch_id ?? item.to_ref ?? '')
    if (!id) return
    try { await openVikingApi.itemOperation(profileId, 'watch_update', id, { is_active: !Boolean(item.is_active), watch_interval: 1440 }); await load() }
    catch (error) { setMessage(error instanceof Error ? error.message : 'Unable to update watch') }
  }
  const deleteWatch = async (item: Record<string, unknown>) => {
    const id = String(item.task_id ?? item.watch_id ?? item.to_ref ?? '')
    if (!id || !window.confirm('Delete this watch?')) return
    try { await openVikingApi.itemOperation(profileId, 'watch_delete', id, {}); await load() }
    catch (error) { setMessage(error instanceof Error ? error.message : 'Unable to delete watch') }
  }
  return <section className="ov-operations"><div className="ov-section-title"><Activity size={18} /><h2>{mode === 'tasks' ? 'Import tasks' : 'Watches'}</h2><button className="ov-icon-button" title="Refresh" onClick={() => void load()}><RefreshCw size={15} /></button>{mode === 'watches' && <button className="ov-primary" onClick={() => void createWatch()}><FilePlus2 size={14} /> Add watch</button>}</div>{message && <p className="ov-form-message">{message}</p>}{items.length === 0 ? <div className="ov-empty">No {mode} returned by the hosted service.</div> : items.map((item, index) => { const row = item as Record<string, unknown>; return <article className="ov-operation-row" key={index}><div><strong>{String(row.task_type ?? row.to_ref ?? 'Operation')}</strong><span>{String(row.status ?? row.is_active ?? '')}</span></div>{mode === 'tasks' && row.status === 'failed' && <button className="ov-secondary" onClick={() => { const resource = String(row.resource_id ?? ''); if (resource) void openVikingApi.operation(profileId, 'content_reindex', { resource_ref: resource, wait: false }).then(() => void load()) }}>Retry</button>}{mode === 'watches' && <><button className="ov-secondary" onClick={() => void updateWatch(row)}>Toggle</button><button className="ov-icon-button" title="Delete watch" onClick={() => void deleteWatch(row)}><Trash2 size={14} /></button></>}</article> })}</section>
}
