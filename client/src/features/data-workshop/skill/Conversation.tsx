import { AlertTriangle, Bot, CircleStop, RotateCcw, Send, UserRound } from 'lucide-react'
import { useState } from 'react'
import type { SkillEvent, SkillSession } from './types'

const phaseLabel: Record<string, string> = {
  invocation_started: '开始',
  'invocation.started': '开始',
  planning: '规划',
  action: '行动',
  tool: '工具',
  tool_call: '工具',
  observation: '观察',
  validation: '校验',
  'validation.blocked': '校验阻塞',
  'validation.completed': '校验',
  validate: '校验',
  artifact: '产物',
  'artifact.created': '产物',
  'revision.created': 'Revision',
  'target.created': '创建完成',
  'target.updated': '更新完成',
  'target.resolved': '目标',
  retry: '重试',
  cancelled: '已停止',
  blocked_auth: '授权阻塞',
  blocked_config: '配置阻塞',
  error: '失败',
}

function EventRow({ event }: { event: SkillEvent }) {
  const label = phaseLabel[event.type] || event.type
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
  const detail = [...(validation?.errors || []), ...failedChecks].join('；') ||
    validation?.message || event.message || event.text || event.name || event.code || event.status
  return (
    <div className={`dw-skill-event ${event.type}`}>
      <span>{label}</span>
      <p>{typeof detail === 'string' ? detail : 'W5 正在处理'}</p>
    </div>
  )
}

function StatusNotice({ status }: { status: SkillSession['status'] }) {
  const copy: Partial<Record<SkillSession['status'], string>> = {
    blocked_auth: '需要完成 OAuth 或重新授权后才能继续。',
    blocked_config: 'W5 production transport 尚未配置。',
    validation_failed: '校验未通过，请查看具体检查并继续修改。',
    cancelled: '本轮任务已停止，对话、上下文与事件均已保留。',
    retryable: '运行暂时失败，可以从当前会话重试。',
    error: '运行失败，历史记录已保留。',
  }
  if (!copy[status]) return null
  return <div className={`dw-skill-status-notice ${status}`}><AlertTriangle size={16} /><span>{copy[status]}</span></div>
}

export function Conversation({
  session,
  disabled,
  onSend,
  onCancel,
  onRetry,
}: {
  session: SkillSession
  disabled?: boolean
  onSend: (message: string) => Promise<void>
  onCancel: () => Promise<void>
  onRetry: () => Promise<void>
}) {
  const [message, setMessage] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const running = session.status === 'running'
  const retryable = ['cancelled', 'retryable', 'error', 'validation_failed', 'blocked_auth', 'blocked_config'].includes(session.status)

  const submit = async () => {
    const value = message.trim()
    if (!value || running || disabled) return
    setSubmitting(true)
    try {
      await onSend(value)
      setMessage('')
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
            <strong>描述你希望这个 Skill 完成的任务</strong>
            <span>我会保留规划、Action 调用、观察与校验过程。</span>
          </div>
        )}
        {session.messages.map((item, index) => (
          <article key={`${item.at}-${index}`} className={`dw-message ${item.role}`}>
            <div className="dw-message-avatar">{item.role === 'user' ? <UserRound size={15} /> : <Bot size={15} />}</div>
            <div><strong>{item.role === 'user' ? '你' : 'Skill Agent'}</strong><p>{item.content}</p></div>
          </article>
        ))}
        {!!session.events.length && (
          <section className="dw-event-stream">
            <header><span>执行过程</span><strong>{running ? '进行中' : '已保存'}</strong></header>
            {session.events.map(event => <EventRow key={event.id} event={event} />)}
          </section>
        )}
        <StatusNotice status={session.status} />
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
          placeholder="描述要创建或继续修改的 Skill…"
          disabled={running || disabled}
          aria-label="Skill 消息"
        />
        <div>
          <span>Enter 发送 · Shift + Enter 换行</span>
          <div className="dw-button-row">
            {retryable && <button className="dw-button dw-button-secondary" onClick={() => void onRetry()}><RotateCcw size={14} />重试</button>}
            {running ? (
              <button className="dw-button dw-button-secondary" onClick={() => void onCancel()}><CircleStop size={14} />停止</button>
            ) : (
              <button className="dw-button dw-button-primary" disabled={!message.trim() || submitting || disabled} onClick={() => void submit()}>
                <Send size={14} />发送
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
