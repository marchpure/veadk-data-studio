import { AlertTriangle, Bot, CircleStop, RotateCcw, Send, UserRound } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { SkillEvent, SkillSession } from './types'

const phaseCopy: Record<string, { label: string; detail: string }> = {
  invocation_started: { label: '开始生成', detail: '正在根据已选择的能力准备 Skill。' },
  'invocation.started': { label: '开始生成', detail: '正在根据已选择的能力准备 Skill。' },
  retry: { label: '开始生成', detail: '正在重新生成 Skill。' },
  planning: { label: '生成中', detail: '正在整理 Skill 的结构与说明。' },
  action: { label: '生成中', detail: '正在整理已选择的 Action。' },
  tool: { label: '生成中', detail: '正在整理已选择的能力。' },
  tool_call: { label: '生成中', detail: '正在整理已选择的能力。' },
  observation: { label: '生成中', detail: '正在检查生成结果。' },
  validation: { label: '校验中', detail: '正在进行静态能力与产物校验。' },
  'validation.completed': { label: '校验中', detail: '静态校验已完成。' },
  validate: { label: '校验中', detail: '正在进行静态能力与产物校验。' },
  artifact: { label: '生成完成', detail: 'Skill 产物已经准备好。' },
  'artifact.created': { label: '生成完成', detail: 'Skill 产物已经准备好。' },
  'revision.created': { label: '生成完成', detail: '新版本已经保存。' },
  'target.created': { label: '生成完成', detail: 'Skill 已经生成。' },
  'target.updated': { label: '生成完成', detail: 'Skill 已经更新。' },
  succeeded: { label: '生成完成', detail: 'Skill 已经生成并通过校验。' },
  cancelled: { label: '生成已停止', detail: '草稿、上下文和历史记录均已保留。' },
  blocked_auth: { label: '生成失败', detail: '生成服务认证异常，请联系管理员。' },
  blocked_config: { label: '生成失败', detail: '生成服务暂不可用，请联系管理员。' },
  error: { label: '生成失败', detail: '生成未完成，请查看提示后重试。' },
  retryable: { label: '生成失败', detail: '服务暂时繁忙，可以重试。' },
  validation_failed: { label: '校验未通过', detail: '请检查上下文或生成目标后重试。' },
}

function UserPhaseRow({ label, detail }: { label: string; detail: string }) {
  return (
    <div className="dw-skill-event">
      <span>{label}</span>
      <p>{detail}</p>
    </div>
  )
}

function StatusNotice({ status }: { status: SkillSession['status'] }) {
  const copy: Partial<Record<SkillSession['status'], string>> = {
    blocked_auth: '生成服务认证异常，请联系管理员',
    blocked_config: '生成服务暂不可用，请稍后重试或联系管理员',
    validation_failed: '校验未通过，请查看具体检查并继续修改。',
    cancelled: '本轮生成已停止，对话、上下文与历史记录均已保留。',
    retryable: '生成服务暂时繁忙，可以从当前会话重试。',
    error: '生成失败，历史记录已保留。',
  }
  if (!copy[status]) return null
  return <div className={`dw-skill-status-notice ${status}`}><AlertTriangle size={16} /><span>{copy[status]}</span></div>
}

function technicalDetail(event: SkillEvent) {
  const validation = typeof event.validation === 'object' && event.validation
    ? event.validation as {
        checks?: Record<string, boolean> | Array<{ name?: string; message?: string; ok?: boolean }>
        errors?: string[]
        message?: string
      }
    : null
  const checks = validation?.checks
  const failedChecks = Array.isArray(checks)
    ? checks.filter(check => check.ok === false).map(check => check.name || check.message).filter(Boolean)
    : Object.entries(checks || {}).filter(([, ok]) => !ok).map(([name]) => name)
  return [
    event.code,
    event.request_id,
    ...(validation?.errors || []),
    ...failedChecks,
    validation?.message,
    event.message || event.text,
  ].filter(Boolean).join(' · ') || '无附加信息'
}

export function Conversation({
  session,
  disabled,
  onSend,
  onCancel,
  onRetry,
  onAddAction,
  onAddKnowledge,
}: {
  session: SkillSession
  disabled?: boolean
  onSend: (message: string) => Promise<void>
  onCancel: () => Promise<void>
  onRetry: () => Promise<void>
  onAddAction?: () => void
  onAddKnowledge?: () => void
}) {
  const [message, setMessage] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [needsContext, setNeedsContext] = useState(false)
  const running = session.status === 'running'
  const retryable = ['cancelled', 'retryable', 'error', 'validation_failed'].includes(session.status)
  const hasContext = session.context_refs.mcp_refs.length + session.context_refs.knowledge_refs.length > 0
  const phases = useMemo(() => {
    const seen = new Set<string>()
    const eventPhases = session.events.flatMap(event => {
      const phase = phaseCopy[event.type.toLocaleLowerCase()]
      if (!phase || seen.has(phase.label)) return []
      seen.add(phase.label)
      return [phase]
    })
    if (
      session.status === 'draft' ||
      (!session.messages.length && session.events.some(event => event.type === 'session_created'))
    ) {
      return [{ label: '草稿已保存', detail: '名称、用途和上下文已经保存。' }, ...eventPhases]
    }
    return eventPhases
  }, [session.events, session.messages.length, session.status])

  const submit = async () => {
    const value = message.trim()
    if (!value || running || disabled) return
    if (!hasContext) {
      setNeedsContext(true)
      return
    }
    setSubmitting(true)
    try {
      await onSend(value)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="dw-conversation">
      <div className="dw-message-stream" aria-live="polite">
        {!session.messages.length && (
          <div className="dw-conversation-empty">
            <Bot size={22} />
            <strong>{hasContext ? '描述你希望这个 Skill 完成的任务' : '草稿已保存'}</strong>
            <span>{hasContext ? '开始生成后会进行静态能力与产物校验。' : '添加 Action 或知识资源后即可开始生成。'}</span>
          </div>
        )}
        {session.messages.map((item, index) => (
          <article key={`${item.at}-${index}`} className={`dw-message ${item.role}`}>
            <div className="dw-message-avatar">{item.role === 'user' ? <UserRound size={15} /> : <Bot size={15} />}</div>
            <div><strong>{item.role === 'user' ? '你' : 'Skill 助手'}</strong><p>{item.role === 'assistant' ? item.content.replace('W5 已完成本轮处理。', '本轮生成已完成。') : item.content}</p></div>
          </article>
        ))}
        {!!phases.length && (
          <section className="dw-event-stream">
            <header><span>生成进度</span><strong>{running ? '进行中' : '已保存'}</strong></header>
            {phases.map(phase => <UserPhaseRow key={phase.label} {...phase} />)}
          </section>
        )}
        {!!session.events.length && (
          <details className="dw-technical-details">
            <summary>技术详情</summary>
            {session.events.map(event => (
              <div className="dw-skill-event" key={event.id}>
                <span>{event.type}</span>
                <p>{technicalDetail(event)}</p>
              </div>
            ))}
          </details>
        )}
        <StatusNotice status={session.status} />
        {needsContext && (
          <div className="dw-context-guidance" role="status">
            <strong>请先添加至少一个 Action 或知识资源，再开始生成。</strong>
            <div className="dw-button-row">
              <button className="dw-button dw-button-secondary" type="button" onClick={onAddAction}>添加 Action</button>
              <button className="dw-button dw-button-secondary" type="button" onClick={onAddKnowledge}>添加知识</button>
            </div>
          </div>
        )}
      </div>
      <div className="dw-composer">
        <textarea
          value={message}
          onChange={event => setMessage(event.target.value)}
          onKeyDown={event => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              void submit()
            }
          }}
          placeholder={hasContext ? '描述生成目标或修改要求…' : '可以先问“你可以做什么”…'}
          disabled={running || disabled}
          aria-label="Skill 消息"
        />
        <div>
          <span>Enter 发送 · Shift + Enter 换行</span>
          <div className="dw-button-row">
            {retryable && <button className="dw-button dw-button-secondary" onClick={() => void onRetry()}><RotateCcw size={14} />重试</button>}
            {running ? (
              <button className="dw-button dw-button-secondary" onClick={() => void onCancel()}><CircleStop size={14} />停止生成</button>
            ) : (
              <button className="dw-button dw-button-primary" disabled={!message.trim() || submitting || disabled} onClick={() => void submit()}>
                <Send size={14} />{session.active_revision ? '生成新版本' : '开始生成'}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
