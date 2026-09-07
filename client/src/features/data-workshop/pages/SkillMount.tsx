import { BookOpen, ChevronDown, Database, Menu, MessageSquare, Plus, Sparkles } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { skillApi } from '../skill/api'
import { Conversation } from '../skill/Conversation'
import { ContextPicker } from '../skill/ContextPicker'
import { NewSkill } from '../skill/NewSkill'
import { SkillRail } from '../skill/SkillRail'
import { SkillInspector } from '../skill/SkillInspector'
import { SkillProgress } from '../skill/SkillProgress'
import '../skill/skill-ux.css'
import '../skill/workbench.css'
import type {
  SkillCatalog,
  SkillContextRef,
  SkillCreateMode,
  SkillRevision,
  SkillSession,
  WorkshopSkill,
} from '../skill/types'
import { openVikingApi } from '../../openviking/api'

type MobilePane = 'skills' | 'conversation' | 'artifact'
type LoadState = 'loading' | 'ready' | 'empty' | 'partial' | 'error' | 'timeout'

function stateForError(reason: unknown): Extract<LoadState, 'error' | 'timeout'> {
  return (reason instanceof Error && 'code' in reason && (reason as { code?: string }).code === 'SKILL_REQUEST_TIMEOUT')
    ? 'timeout'
    : 'error'
}

function messageForError(reason: unknown, fallback: string) {
  return reason instanceof Error && reason.message ? reason.message : fallback
}

function queryFor(skillId?: string, sessionId?: string, mode?: 'new') {
  const search = new URLSearchParams()
  if (mode) search.set('mode', mode)
  if (skillId) search.set('skillId', skillId)
  if (sessionId) search.set('sessionId', sessionId)
  return `/skill${search.size ? `?${search}` : ''}`
}

function ContextSummary({
  session,
  onAddAction,
  onAddKnowledge,
}: {
  session: SkillSession
  onAddAction: () => void
  onAddKnowledge: () => void
}) {
  const { mcp_refs: mcp, knowledge_refs: knowledge } = session.context_refs
  return (
    <div className="dw-context-summary">
      {mcp.length
        ? <span><Database size={13} />{mcp.length} 个 Action</span>
        : <button type="button" onClick={onAddAction}><Database size={13} />添加 Action</button>}
      {knowledge.length
        ? <span><BookOpen size={13} />{knowledge.length} 个知识资源</span>
        : <button type="button" onClick={onAddKnowledge}><BookOpen size={13} />添加知识</button>}
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
  const [loadState, setLoadState] = useState<LoadState>('loading')
  const [catalogState, setCatalogState] = useState<Extract<LoadState, 'loading' | 'ready' | 'error' | 'timeout'>>('loading')
  const [sessionState, setSessionState] = useState<Extract<LoadState, 'loading' | 'ready' | 'empty' | 'partial' | 'error' | 'timeout'>>('ready')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')
  const [catalogError, setCatalogError] = useState('')
  const [mobilePane, setMobilePane] = useState<MobilePane>('conversation')
  const [importedKnowledge, setImportedKnowledge] = useState<SkillContextRef[]>([])
  const [importError, setImportError] = useState('')
  const [contextEditor, setContextEditor] = useState<'action' | 'knowledge' | null>(null)
  const [loadAttempt, setLoadAttempt] = useState(0)
  const [catalogAttempt, setCatalogAttempt] = useState(0)
  const loading = loadState === 'loading'

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
          setImportError(reason instanceof Error ? reason.message : '该知识资源已失效或无权访问')
        }
      })
    return () => { cancelled = true }
  }, [isNew, location.search, query])

  const loadSkills = useCallback(async (signal?: AbortSignal) => {
    const response = await skillApi.listSkills('', { signal })
    return response.items
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    let active = true
    setLoadState('loading')
    setError('')
    void loadSkills(controller.signal)
      .then(items => {
        if (!active) return
        setSkills(items)
        const nextState: LoadState = items.length ? 'ready' : 'empty'
        setLoadState(nextState)
        if (!isNew && !requestedSkillId && requestedSessionId) {
          void skillApi.getSession(requestedSessionId, { signal: controller.signal })
            .then(found => {
              if (active) navigate(queryFor(found.skill_id, found.id), { replace: true })
            })
            .catch(reason => {
              if (active && !controller.signal.aborted && items[0]) navigate(queryFor(items[0].id), { replace: true })
            })
        } else if (!isNew && !requestedSkillId && items[0]) {
          navigate(queryFor(items[0].id), { replace: true })
        } else if (!isNew && requestedSkillId && !items.some(item => item.id === requestedSkillId)) {
          if (items[0]) navigate(queryFor(items[0].id), { replace: true })
          else setError('找不到该 Skill，请从列表中选择或新建。')
        }
      })
      .catch(reason => {
        if (!active || controller.signal.aborted) return
        setLoadState(stateForError(reason))
        setError(messageForError(reason, 'Skill 列表加载失败'))
      })
    return () => {
      active = false
      controller.abort()
    }
  }, [isNew, loadAttempt, loadSkills, navigate, requestedSessionId, requestedSkillId])

  useEffect(() => {
    const controller = new AbortController()
    let active = true
    setCatalogState('loading')
    setCatalogError('')
    void skillApi.catalog({ signal: controller.signal })
      .then(nextCatalog => {
        if (!active) return
        setCatalog(nextCatalog)
        setCatalogState('ready')
        setCatalogError('')
      })
      .catch(reason => {
        if (!active || controller.signal.aborted) return
        setCatalogState(stateForError(reason))
        setCatalogError(messageForError(reason, '能力目录暂时不可用，可稍后重试'))
        setLoadState(current => current === 'loading' ? 'partial' : current)
      })
    return () => {
      active = false
      controller.abort()
    }
  }, [catalogAttempt])

  useEffect(() => {
    if (!selectedSkill || isNew) {
      setSessions([])
      setSession(null)
      setRevisions([])
      return
    }
    const controller = new AbortController()
    let active = true
    setSessionState('loading')
    setSession(null)
    void Promise.allSettled([
      skillApi.listSessions(selectedSkill.id, { signal: controller.signal }),
      skillApi.revisions(selectedSkill.id, { signal: controller.signal }),
    ]).then(results => {
      if (!active) return
      const sessionsResult = results[0]
      const revisionsResult = results[1]
      const sessionsOk = sessionsResult.status === 'fulfilled'
      const revisionsOk = revisionsResult.status === 'fulfilled'
      if (sessionsOk) {
        setSessions(sessionsResult.value.items)
        const requested = requestedSessionId
          ? sessionsResult.value.items.find(item => item.id === requestedSessionId)
          : sessionsResult.value.items[0]
        if (requested) {
          setSession(requested)
          setSessionState(revisionsOk ? 'ready' : 'partial')
          if (requested.id !== requestedSessionId) navigate(queryFor(selectedSkill.id, requested.id), { replace: true })
        } else {
          setSession(null)
          setSessionState(revisionsOk ? 'empty' : 'partial')
        }
      } else {
        setSessions([])
        setSession(null)
        setSessionState(stateForError(sessionsResult.reason))
      }
      if (revisionsOk) setRevisions(revisionsResult.value.items)
      else setRevisions([])
      const failedReason = !sessionsOk ? sessionsResult.reason : !revisionsOk ? revisionsResult.reason : null
      if (failedReason) setError(messageForError(failedReason, '会话或版本记录加载失败'))
      else setError('')
    })
    return () => {
      active = false
      controller.abort()
    }
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

  const invokeSession = async (current: SkillSession, skillId: string, message: string) => {
    if (!current.context_refs.mcp_refs.length && !current.context_refs.knowledge_refs.length) {
      setError('请先添加至少一个 Action 或知识资源，再开始生成。')
      return false
    }
    try {
      const accepted = await skillApi.invoke(current.id, message, crypto.randomUUID())
      const eventPage = await skillApi.events(current.id, accepted.events.length)
      setSession({
        ...accepted,
        events: [...accepted.events, ...eventPage.items],
        status: eventPage.status,
      })
      if (eventPage.done) {
        setSession(await skillApi.getSession(current.id))
        void loadSkills()
        void skillApi.revisions(skillId).then(value => setRevisions(value.items))
      }
      setError('')
      return true
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '发送失败')
      return false
    }
  }

  const send = async (message: string) => {
    if (!session || !selectedSkill) return
    await invokeSession(session, selectedSkill.id, message)
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
      setError(reason instanceof Error ? reason.message : '移除知识资源失败')
    }
  }

  const updateContext = async (mcpRefs: SkillContextRef[], knowledgeRefs: SkillContextRef[]) => {
    if (!session) return
    try {
      setSession(await skillApi.updateContext(session.id, {
        mcp_refs: mcpRefs,
        knowledge_refs: knowledgeRefs,
      }))
      setError('')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '更新上下文失败')
    }
  }

  const createSkill = async (
    value: Parameters<typeof skillApi.createSkill>[0],
    mode: SkillCreateMode,
  ) => {
    setCreating(true)
    try {
      const created = await skillApi.createSkill(value)
      setSkills(current => [created.skill, ...current])
      setSessions([created.session])
      setSession(created.session)
      setError('')
      navigate(queryFor(created.skill.id, created.session.id))
      if (mode === 'generate') {
        const started = await invokeSession(
          created.session,
          created.skill.id,
          value.description || `生成 ${value.title}`,
        )
        if (!started) return
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '创建 Skill 失败')
    } finally {
      setCreating(false)
    }
  }

  const artifact = session?.artifact || null
  const currentStep = isNew
    ? 1
    : session?.status === 'ready' || artifact
      ? 4
      : session?.status === 'running' || session?.status === 'validation_failed' || session?.status === 'error' || session?.status === 'retryable'
        ? 3
        : 2

  return (
    <div className={`dw-skill-workbench has-inspector ${artifact ? 'has-artifact' : ''}`} data-workshop-skill-mount>
      <div className="dw-skill-mobile-tabs" aria-label="Skill 移动视图">
        <button className={mobilePane === 'skills' ? 'active' : ''} onClick={() => setMobilePane('skills')}><Menu size={14} />Skill</button>
        <button className={mobilePane === 'conversation' ? 'active' : ''} onClick={() => setMobilePane('conversation')}><MessageSquare size={14} />对话</button>
        {selectedSkill && session && <button className={mobilePane === 'artifact' ? 'active' : ''} onClick={() => setMobilePane('artifact')}><Sparkles size={14} />信息</button>}
      </div>
      <div className={`dw-skill-mobile-pane pane-${mobilePane}`}>
        <SkillRail
          skills={visibleSkills}
          selectedId={selectedSkill?.id || null}
          search={search}
          loading={loading && skills.length === 0}
          onSearch={setSearch}
          onNew={() => { setMobilePane('conversation'); navigate(queryFor(undefined, undefined, 'new')) }}
          onSelect={selectSkill}
        />
        <main className="dw-skill-center">
          {(error || importError || catalogError) && (
            <div className="dw-inline-error dw-skill-global-error" role="alert">
              <span>{error || importError || catalogError}</span>
              <div className="dw-button-row">
                {error && !isNew && <button className="dw-button dw-button-secondary" onClick={() => setLoadAttempt(value => value + 1)}>重试</button>}
                {catalogError && <button className="dw-button dw-button-secondary" onClick={() => setCatalogAttempt(value => value + 1)}>重试目录</button>}
                <button className="dw-button dw-button-secondary" onClick={() => { setError(''); setImportError(''); setCatalogError('') }}>关闭</button>
              </div>
            </div>
          )}
          {isNew ? (
            <>
              <header className="dw-skill-create-heading">
                <div>
                  <span className="dw-eyebrow">Skill 工作台</span>
                  <h1>创建一个新的 Skill</h1>
                  <p>从目标开始，选择能力，生成后即可复用。</p>
                </div>
                <SkillProgress current={1} />
              </header>
              <NewSkill catalog={catalog} initialKnowledge={importedKnowledge} creating={creating} onCreate={createSkill} />
            </>
          ) : selectedSkill && session ? (
            <>
              <header className="dw-skill-header">
                <div>
                  <span className="dw-eyebrow">Skill 工作台</span>
                  <h1>{selectedSkill.title}</h1>
                  {selectedSkill.description && <p>{selectedSkill.description}</p>}
                  <SkillProgress current={currentStep as 1 | 2 | 3 | 4} compact />
                </div>
                <div className="dw-session-control">
                  <label><span>会话</span><ChevronDown size={13} />
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
                      <option value="__new__">＋ 新建会话</option>
                    </select>
                  </label>
                </div>
              </header>
              <ContextSummary
                session={session}
                onAddAction={() => setContextEditor('action')}
                onAddKnowledge={() => setContextEditor('knowledge')}
              />
              <ResourceRefList session={session} onRemove={item => void removeKnowledgeRef(item)} />
              {contextEditor && (
                <ContextPicker
                  key={contextEditor}
                  catalog={catalog}
                  selectedMcp={session.context_refs.mcp_refs}
                  selectedKnowledge={session.context_refs.knowledge_refs}
                  initialOpen={contextEditor}
                  onMcpChange={items => void updateContext(items, session.context_refs.knowledge_refs)}
                  onKnowledgeChange={items => void updateContext(session.context_refs.mcp_refs, items)}
                />
              )}
              <Conversation
                session={session}
                disabled={creating}
                onSend={send}
                onCancel={() => refreshSession('cancel')}
                onRetry={() => refreshSession('retry')}
                onAddAction={() => setContextEditor('action')}
                onAddKnowledge={() => setContextEditor('knowledge')}
              />
            </>
          ) : (
            <div className="dw-skill-empty">
              <span><Sparkles size={25} /></span>
              <h1>
                {loading ? '正在打开 Skill 工作台'
                  : loadState === 'timeout' ? '加载超时'
                    : loadState === 'error' ? 'Skill 暂时不可用'
                      : sessionState === 'empty' ? '还没有会话'
                        : '把数据能力变成可复用的 Skill'}
              </h1>
              <p>
                {loading ? '正在读取你的 Skill 与会话…'
                  : loadState === 'timeout' ? '请求等待时间过长，请重试。'
                    : loadState === 'error' ? '请检查网络后重试，或新建一个 Skill。'
                      : sessionState === 'empty' && selectedSkill ? '为这个 Skill 创建第一个会话即可开始。'
                        : '从一个明确目标开始，连接可见的 Action 与知识资源。'}
              </p>
              {!loading && (
                <div className="dw-button-row">
                  {(loadState === 'error' || loadState === 'timeout') && <button className="dw-button dw-button-secondary" onClick={() => setLoadAttempt(value => value + 1)}>重试</button>}
                  <button className="dw-button dw-button-primary" onClick={() => selectedSkill ? void createSession() : navigate(queryFor(undefined, undefined, 'new'))}>
                    <Plus size={15} />{selectedSkill ? '新建会话' : '新建 Skill'}
                  </button>
                </div>
              )}
            </div>
          )}
        </main>
        {selectedSkill && session && (
          <SkillInspector skillId={selectedSkill.id} session={session} revisions={revisions} />
        )}
      </div>
    </div>
  )
}
