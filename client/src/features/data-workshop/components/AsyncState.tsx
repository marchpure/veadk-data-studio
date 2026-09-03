import { AlertCircle, Inbox, LoaderCircle, RefreshCw } from 'lucide-react'

interface AsyncStateProps {
  state: 'loading' | 'empty' | 'error'
  title?: string
  message?: string
  onRetry?: () => void
}

export function AsyncState({ state, title, message, onRetry }: AsyncStateProps) {
  const Icon = state === 'loading' ? LoaderCircle : state === 'empty' ? Inbox : AlertCircle
  const defaultTitle = state === 'loading' ? '正在加载' : state === 'empty' ? '暂无数据' : '暂时无法加载'
  return (
    <div className="dw-async" role={state === 'error' ? 'alert' : 'status'}>
      <Icon className={state === 'loading' ? 'dw-spin' : ''} size={22} />
      <strong>{title || defaultTitle}</strong>
      {message && <span>{message}</span>}
      {state === 'error' && onRetry && (
        <button className="dw-button dw-button-secondary" onClick={onRetry}>
          <RefreshCw size={15} /> 重试
        </button>
      )}
    </div>
  )
}
