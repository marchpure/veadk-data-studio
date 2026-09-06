import { BookOpen, ChevronDown, Database, Menu, MessageSquare, Plus, Sparkles } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { ArtifactPanel } from '../skill/ArtifactPanel'
import { skillApi } from '../skill/api'
import { Conversation } from '../skill/Conversation'
import { NewSkill } from '../skill/NewSkill'
import { SkillRail } from '../skill/SkillRail'
import type { SkillCatalog, SkillContextRef, SkillRevision, SkillSession, WorkshopSkill } from '../skill/types'
import { openVikingApi } from '../../openviking/api'

type MobilePane = 'skills' | 'conversation' | 'artifact'

function queryFor(skillId?: string, sessionId?: string, mode?: 'new') {
  const search = new URLSearchParams()
  if (mode) search.set('mode', mode)
  if (skillId) search.set('skillId', skillId)
  if (sessionId) search.set('sessionId', sessionId)
  return `/skill${search.size ? `?${search}` : ''}`
}

function ContextSummary({ session }: { session: SkillSession }) {
  const { mcp_refs: mcp, knowledge_refs: knowledge } = session.context_refs
  return (
    <div className="dw-context-summary">
      <span><Database size={13} />{mcp.length ? `${mcp.length} 个 Action` : '未选择 Action'}</span>
      <span><BookOpen size={13} />{knowledge.length ? `${knowledge.length} 个 ResourceRef` : '未选择知识'}</span>
    </div>
  )
}

function ResourceRefList({
  session,
  onRemove,
}: {
  session: SkillSession
  onRemove: (item: SkillContextRef) => void
}) {
  return (
    <div className="dw-context-summary">
      {session.context_refs.knowledge_refs.map(item => (
        <span key={item.id} title={item.id}>
          <BookOpen size={13} />
          {item.name}
          <button type="button" aria-label={`移除 ${item.name}`} onClick={() => onRemove(item)}>移除</button>
        </span>
      ))}
    </div>
  )
}

export function SkillMount() {
  const location = useLocation()
  const navigate = useNavigate()
  const query = useMemo(() => new URLSearchParams(location.search), [location.search])
  const requestedSkillId = query.get('skillId')
  const requestedSessionId = query.get('sessionId')
  const isNew = query.get('mode') === 'new'
  const [skills, setSkills] = useState<WorkshopSkill[]>([])
  const [sessions, setSessions] = useState<SkillSession[]>([])
  const [session, setSession] = useState<SkillSession | null>(null)
  const [catalog, setCatalog] = useState<SkillCatalog | null>(null)
  const [revisions, setRevisions] = useState<SkillRevision[]>([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')
  const [mobilePane, setMobilePane] = useState<MobilePane>('conversation')
  const [importedKnowledge, setImportedKnowledge] = useState<SkillContextRef[]>([])
  const [importError, setImportError] = useState('')

  const selectedSkill = skills.find(item => item.id === requestedSkillId) || null
  const visibleSkills = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase()
    if (!needle) return skills
    return skills.filter(skill =>
      `${skill.title} ${skill.target_skill} ${skill.description}`.toLocaleLowerCase().includes(needle),
    )
  }, [search, skills])

  useEffect(() => {
    const resourceRef = query.get('resource_ref')
    const profileRef = query.get('profile_ref')
    if (!isNew || !resourceRef || !profileRef) {
      setImportedKnowledge([])
      setImportError('')
      return
    }
    let cancelled = false
    void openVikingApi.resolveResource(profileRef, resourceRef)
      .then(value => {
        if (cancelled) return
        setImportedKnowledge([{
          id: value.resource_ref,
          kind: 'knowledge_resource',
          name: value.display_name,
          source: 'OpenViking ResourceRef',
          metadata: {
            profile_ref: profileRef,
            profile_name: value.profile_name,
            resource_type: value.resource_type,
            summary: value.summary,
          },
        }])
        setImportError('')
      })
      .catch(reason => {
        if (!cancelled) {
          setImportedKnowledge([])
          setImportError(reason instanceof Error ? reason.message : '该 ResourceRef 已失效或无权访问')
        }
      })
    return () => { cancelled = true }
  }, [isNew, location.search, query])

  const loadSkills = useCallback(async () => {
    const response = await skillApi.listSkills()
    setSkills(response.items)
    return response.items
  }, [])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    Promise.all([loadSkills(), skillApi.catalog()])
      .then(([items, nextCatalog]) => {
        if (cancelled) return
        setCatalog(nextCatalog)
        setError('')
        if (!isNew && !requestedSkillId && requestedSessionId) {
          void skillApi.getSession(requestedSessionId)
            .then(found => navigate(queryFor(found.skill_id, found.id), { replace: true }))
            .catch(() => {
              if (items[0]) navigate(queryFor(items[0].id), { replace: true })
            })
        } else if (!isNew && !requestedSkillId && items[0]) {
          navigate(queryFor(items[0].id), { replace: true })
        }
      })
      .catch(reason => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : 'Skill 工作台加载失败')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [isNew, loadSkills, navigate, requestedSessionId, requestedSkillId])

  useEffect(() => {
    if (!selectedSkill || isNew) {
      setSessions([])
      setSession(null)
      setRevisions([])
      return
    }
    let cancelled = false
    Promise.all([skillApi.listSessions(selectedSkill.id), skillApi.revisions(selectedSkill.id)])
      .then(async ([sessionResult, revisionResult]) => {
        if (cancelled) return
        setSessions(sessionResult.items)
        setRevisions(revisionResult.items)
        const requested = requestedSessionId
          ? sessionResult.items.find(item => item.id === requestedSessionId)
          : sessionResult.items[0]
        if (requested) {
          setSession(requested)
          if (requested.id !== requestedSessionId) {
            navigate(queryFor(selectedSkill.id, requested.id), { replace: true })
          }
        } else {
          setSession(null)
        }
      })
      .catch(reason => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : '会话加载失败')
      })
    return () => { cancelled = true }
  }, [isNew, navigate, requestedSessionId, selectedSkill])

  useEffect(() => {
    if (!session || session.status !== 'running') return
    let cancelled = false
    const timer = window.setInterval(() => {
      const after = session.events.length
      void skillApi.events(session.id, after).then(async eventPage => {
        if (cancelled) return
        setSession(current => current?.id === session.id
          ? {
              ...current,
              events: [...current.events, ...eventPage.items],
              status: eventPage.status,
            }
          : current)
        if (eventPage.done) {
          window.clearInterval(timer)
          const finalSession = await skillApi.getSession(session.id)
          if (cancelled) return
          setSession(finalSession)
          void loadSkills()
          if (selectedSkill) void skillApi.revisions(selectedSkill.id).then(value => setRevisions(value.items))
        }
      }).catch(reason => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : '执行状态刷新失败')
      })
    }, 800)
    return () => { cancelled = true; window.clearInterval(timer) }
  }, [loadSkills, selectedSkill, session])

  const selectSkill = (skillId: string) => {
    setMobilePane('conversation')
    navigate(queryFor(skillId))
  }

  const createSession = async () => {
    if (!selectedSkill) return
    try {
      const created = await skillApi.createSession(selectedSkill.id)
      setSessions(current => [created, ...current])
      setSession(created)
      navigate(queryFor(selectedSkill.id, created.id))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '新建会话失败')
    }
  }

  const send = async (message: string) => {
    if (!session) return
    try {
      const accepted = await skillApi.invoke(session.id, message, crypto.randomUUID())
      const eventPage = await skillApi.events(session.id, accepted.events.length)
      setSession({
        ...accepted,
        events: [...accepted.events, ...eventPage.items],
        status: eventPage.status,
      })
      if (eventPage.done) {
        setSession(await skillApi.getSession(session.id))
        void loadSkills()
        if (selectedSkill) {
          void skillApi.revisions(selectedSkill.id).then(value => setRevisions(value.items))
        }
      }
      setError('')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '发送失败')
    }
  }

  const refreshSession = async (action: 'cancel' | 'retry') => {
    if (!session) return
    try {
      setSession(action === 'cancel' ? await skillApi.cancel(session.id) : await skillApi.retry(session.id))
      setError('')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '操作失败')
    }
  }

  const removeKnowledgeRef = async (item: SkillContextRef) => {
    if (!session) return
    try {
      setSession(await skillApi.updateContext(session.id, {
        mcp_refs: session.context_refs.mcp_refs,
        knowledge_refs: session.context_refs.knowledge_refs.filter(ref => ref.id !== item.id),
      }))
      setError('')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '移除 ResourceRef 失败')
    }
  }

  const createSkill = async (value: Parameters<typeof skillApi.createSkill>[0]) => {
    setCreating(true)
    try {
      const created = await skillApi.createSkill(value)
      setSkills(current => [created.skill, ...current])
      setSessions([created.session])
      setSession(created.session)
      setError('')
      navigate(queryFor(created.skill.id, created.session.id))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '创建 Skill 失败')
    } finally {
      setCreating(false)
    }
  }

  const artifact = session?.artifact || null

  return (
    <div className={`dw-skill-workbench ${artifact ? 'has-artifact' : ''}`} data-workshop-skill-mount>
      <div className="dw-skill-mobile-tabs" aria-label="Skill 移动视图">
        <button className={mobilePane === 'skills' ? 'active' : ''} onClick={() => setMobilePane('skills')}><Menu size={14} />Skill</button>
        <button className={mobilePane === 'conversation' ? 'active' : ''} onClick={() => setMobilePane('conversation')}><MessageSquare size={14} />对话</button>
        {artifact && <button className={mobilePane === 'artifact' ? 'active' : ''} onClick={() => setMobilePane('artifact')}><Sparkles size={14} />Artifact</button>}
      </div>
      <div className={`dw-skill-mobile-pane pane-${mobilePane}`}>
        <SkillRail
          skills={visibleSkills}
          selectedId={selectedSkill?.id || null}
          search={search}
          loading={loading}
          onSearch={setSearch}
          onNew={() => { setMobilePane('conversation'); navigate(queryFor(undefined, undefined, 'new')) }}
          onSelect={selectSkill}
        />
        <main className="dw-skill-center">
          {(error || importError) && <div className="dw-inline-error dw-skill-global-error">{error || importError}<button onClick={() => { setError(''); setImportError('') }}>关闭</button></div>}
          {isNew ? (
            <NewSkill catalog={catalog} initialKnowledge={importedKnowledge} creating={creating} onCreate={createSkill} />
          ) : selectedSkill && session ? (
            <>
              <header className="dw-skill-header">
                <div><span className="dw-eyebrow">Skill Workspace</span><h1>{selectedSkill.title}</h1><p>{selectedSkill.description || selectedSkill.target_skill}</p></div>
                <div className="dw-session-control">
                  <label><span>Session</span><ChevronDown size={13} />
                    <select
                      value={session.id}
                      onChange={event => {
                        if (event.target.value === '__new__') {
                          void createSession()
                        } else {
                          const next = sessions.find(item => item.id === event.target.value)
                          if (next) {
                            setSession(next)
                            navigate(queryFor(selectedSkill.id, next.id))
                          }
                        }
                      }}
                    >
                      {sessions.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}
                      <option value="__new__">＋ 新建 Session</option>
                    </select>
                  </label>
                </div>
              </header>
              <ContextSummary session={session} />
              <ResourceRefList session={session} onRemove={item => void removeKnowledgeRef(item)} />
              <Conversation
                session={session}
                disabled={creating}
                onSend={send}
                onCancel={() => refreshSession('cancel')}
                onRetry={() => refreshSession('retry')}
              />
            </>
          ) : (
            <div className="dw-skill-empty">
              <span><Sparkles size={25} /></span>
              <h1>{loading ? '正在打开 Skill 工作台' : '把数据能力变成可复用的 Skill'}</h1>
              <p>{loading ? '正在读取你的 Skill 与 Session…' : '从一个明确目标开始，连接可见的 Actions 与知识资源。'}</p>
              {!loading && <button className="dw-button dw-button-primary" onClick={() => navigate(queryFor(undefined, undefined, 'new'))}><Plus size={15} />新建 Skill</button>}
            </div>
          )}
        </main>
        {artifact && selectedSkill && <ArtifactPanel skillId={selectedSkill.id} artifact={artifact} revisions={revisions} />}
      </div>
    </div>
  )
}
