import { useCallback, useEffect, useState } from 'react'
import { Check, Download, FileCode2, FileText, Folder, History, RefreshCw, Send, ShieldAlert, Square } from 'lucide-react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ApiService } from '../../services/api'
import { skillCreatorApi, type SkillArtifact, type SkillRef, type SkillSession } from './api'
import './skill-creator.css'

export default function SkillWorkspacePage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const sessionId = params.get('session')
  const [catalog, setCatalog] = useState<{ mcp_refs: SkillRef[]; knowledge_refs: SkillRef[]; backend: SkillSession['backend'] }>()
  const [session, setSession] = useState<SkillSession | null>(null)
  const [sessions, setSessions] = useState<SkillSession[]>([])
  const [target, setTarget] = useState('')
  const [goal, setGoal] = useState('')
  const [mcp, setMcp] = useState<string[]>([])
  const [knowledge, setKnowledge] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [tab, setTab] = useState<'preview' | 'diff' | 'revision'>('preview')
  useEffect(() => {
    skillCreatorApi.catalog().then(setCatalog).catch(error => setError(error.message))
    skillCreatorApi.listSessions().then(result => setSessions(result.items)).catch(() => {})
    if (id && id !== 'new') {
      ApiService.getCustomSkill(id).then(result => setTarget(result.data?.name || '')).catch(() => {})
    }
  }, [id])
  const load = useCallback(async (idToLoad: string) => { const value = await skillCreatorApi.getSession(idToLoad); setSession(value); setTarget(value.target); setMcp(value.mcp_refs.map(ref => ref.id)); setKnowledge(value.knowledge_refs.map(ref => ref.id)) }, [])
  useEffect(() => { if (sessionId) void load(sessionId) }, [sessionId, load])
  const ensure = async () => {
    if (session) return session
    const value = await skillCreatorApi.createSession({ skill_id: id === 'new' ? undefined : id, target, mcp_refs: (catalog?.mcp_refs || []).filter(ref => mcp.includes(ref.id)), knowledge_refs: (catalog?.knowledge_refs || []).filter(ref => knowledge.includes(ref.id)) })
    setSession(value)
    return value
  }
  const poll = useCallback(async (sid: string, after: number) => {
    const result = await skillCreatorApi.events(sid, after)
    const fresh = await skillCreatorApi.getSession(sid)
    setSession(fresh)
    if (!result.done) void poll(sid, result.next)
  }, [])
  const run = async (validate = false) => {
    if (!goal.trim() || busy) return
    setBusy(true); setError('')
    try { const active = await ensure(); const accepted = await skillCreatorApi.invoke(active.id, { message: goal.trim(), validate, client_invocation_id: `${active.id}:${Date.now()}` }); setSession(accepted); setGoal(''); void poll(active.id, accepted.events.length) } catch (caught) { setError(caught instanceof Error ? caught.message : 'Invocation failed') } finally { setBusy(false) }
  }
  const artifact: SkillArtifact | null = session?.artifact || null
  const previewUrl = artifact?.preview_url ? String(artifact.preview_url) : ''
  const downloadUrl = artifact?.download_url ? String(artifact.download_url) : ''
  const securitySummary = artifact ? 'Artifact metadata is supplied by the Skill Agent. Review before download.' : ''
  return <div className="skill-workspace"><header><Link to="/skill">Skills</Link><div><span>DATA WORKSHOP / {id === 'new' ? 'NEW' : 'SKILL'}</span><h1>{target || 'Untitled skill'}</h1></div><strong>{session?.backend || catalog?.backend || 'REAL AGENT'}</strong></header><div className="workspace-grid"><aside className="workspace-panel context-panel"><h2>Context</h2><label>Skill<input value={target} onChange={event => setTarget(event.target.value)} placeholder="Skill target" /></label><RefGroup title="MCP capability refs" refs={catalog?.mcp_refs || []} selected={mcp} onChange={setMcp} /><RefGroup title="Knowledge ResourceRefs" refs={catalog?.knowledge_refs || []} selected={knowledge} onChange={setKnowledge} /><label>Session<select value={session?.id || ''} onChange={event => event.target.value && void load(event.target.value)}><option value="">Current session</option>{sessions.map(item => <option value={item.id} key={item.id}>{item.id.slice(0, 8)} · {item.revision || 'new'}</option>)}</select></label></aside><main className="workspace-panel conversation-panel"><div className="panel-heading"><h2>Conversation</h2>{session && <span className={`state state-${session.status}`}>{session.status}</span>}</div><div className="event-stream">{session?.messages.map((message, index) => <article className={`message ${message.role}`} key={`${message.at}-${index}`}><small>{message.role}</small><p>{message.content}</p></article>)}{session?.events.map(event => <article className="event" key={String(event.id)}><strong>{String(event.type).replaceAll('_', ' ')}</strong>{event.message && <p>{String(event.message)}</p>}{event.code && <code>{String(event.code)}</code>}{event.name && <p>Tool Call: {String(event.name)}</p>}</article>)}</div>{error && <div className="auth-error"><ShieldAlert size={16} /><span>{error.includes('BLOCKED_AUTH') ? 'BLOCKED_AUTH: complete OAuth or re-authorize.' : error}</span>{error.includes('BLOCKED_AUTH') && <button onClick={() => navigate('/integrations')}>Complete OAuth</button>}</div>}<textarea value={goal} onChange={event => setGoal(event.target.value)} placeholder="Describe the skill or next revision..." /><div className="composer"><button onClick={() => void run(true)} disabled={busy || !goal.trim()}><Check size={15} /> Validate</button>{session && <button title="Cancel invocation" onClick={() => void skillCreatorApi.cancel(session.id).then(setSession)}><Square size={15} /></button>}<button className="primary" onClick={() => void run()} disabled={busy || !goal.trim()}>{busy ? 'Running...' : <><Send size={15} /> Send</>}</button></div></main>{artifact ? <ArtifactPanel artifact={artifact} tab={tab} setTab={setTab} previewUrl={previewUrl} downloadUrl={downloadUrl} securitySummary={securitySummary} /> : <aside className="workspace-panel artifact-empty"><FileText size={24} /><h2>No Artifact yet</h2><p>Artifact files, preview, revision, and download appear after the Skill Agent returns one.</p>{session && ['blocked_auth', 'validation_failed', 'cancelled', 'retryable'].includes(session.status) && <button onClick={() => void skillCreatorApi.retry(session.id).then(setSession)}><RefreshCw size={15} /> Retry</button>}</aside>}</div></div>
}

function RefGroup({ title, refs, selected, onChange }: { title: string; refs: SkillRef[]; selected: string[]; onChange: (value: string[]) => void }) {
  return <section className="ref-group"><h3>{title}</h3>{refs.length ? refs.map(ref => <label key={ref.id}><input type="checkbox" checked={selected.includes(ref.id)} onChange={event => onChange(event.target.checked ? [...selected, ref.id] : selected.filter(id => id !== ref.id))} />{ref.name}<small>{ref.source}</small></label>) : <p className="muted">No visible refs</p>}</section>
}

function ArtifactPanel({ artifact, tab, setTab, previewUrl, downloadUrl, securitySummary }: { artifact: SkillArtifact; tab: string; setTab: (value: 'preview' | 'diff' | 'revision') => void; previewUrl: string; downloadUrl: string; securitySummary: string }) {
  const files = artifact.files || []
  return <aside className="workspace-panel artifact-panel"><div className="panel-heading"><h2>Artifact</h2><span className="ready"><Check size={14} /> Present</span></div><div className="artifact-tabs">{(['preview', 'diff', 'revision'] as const).map(item => <button className={tab === item ? 'selected' : ''} onClick={() => setTab(item)} key={item}>{item}</button>)}</div><div className="file-tree"><div><Folder size={14} /> artifact</div>{files.map(file => <div key={file}><FileCode2 size={14} /> {file}</div>)}</div>{tab === 'preview' && (artifact.mime_type === 'text/html' && artifact.content ? <iframe title="Skill artifact HTML preview" sandbox="" srcDoc={artifact.content} /> : artifact.content ? <pre>{artifact.content}</pre> : previewUrl ? <iframe title="Skill artifact preview" sandbox="" src={previewUrl} /> : <p className="muted artifact-note">W5 returned artifact metadata without preview content.</p>)}{tab === 'diff' && <pre>{artifact.content ? `+ ${artifact.content.replaceAll('\n', '\n+ ')}` : 'Diff is available from the returned artifact files.'}</pre>}{tab === 'revision' && <div className="revision"><strong>{artifact.revision || 'Revision returned by W5'}</strong><p>Revision metadata is read from the Skill Agent response.</p></div>}<div className="security">{securitySummary}</div>{downloadUrl && <a className="download" href={downloadUrl} onClick={event => { if (!window.confirm('Security check: download the Skill Agent artifact?')) event.preventDefault() }}><Download size={15} /> Download</a>}{previewUrl && <a className="download" href={previewUrl} target="_blank" rel="noreferrer"><FileText size={15} /> Open Preview</a>}</aside>
}
