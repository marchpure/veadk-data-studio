import type { ReactNode } from 'react'
import { AlertCircle, CheckCircle2, Clock, ShieldAlert } from 'lucide-react'
import { cn } from '../../../lib/utils'
import type { ReadinessLevel, ValidationStatus } from '../types'

export function StatusPill({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'ready' | 'warning' | 'blocked' | 'info' }) {
  const classes = {
    neutral: 'border-[#333] bg-[#242424] text-[#cfcfcf]',
    ready: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
    warning: 'border-amber-500/30 bg-amber-500/10 text-amber-300',
    blocked: 'border-red-500/30 bg-red-500/10 text-red-300',
    info: 'border-sky-500/30 bg-sky-500/10 text-sky-300',
  }
  return <span className={cn('inline-flex items-center rounded border px-2 py-0.5 text-xs', classes[tone])}>{children}</span>
}

// eslint-disable-next-line react-refresh/only-export-components
export function readinessTone(level: ReadinessLevel | ValidationStatus | string): 'ready' | 'warning' | 'blocked' | 'neutral' {
  if (level === 'ready' || level === 'valid') return 'ready'
  if (level === 'warning') return 'warning'
  if (level === 'blocked') return 'blocked'
  return 'neutral'
}

export function Panel({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={cn('rounded-lg border border-[#2a2a2a] bg-[#1f1f1f]', className)}>{children}</section>
}

export function PanelHeader({ title, action, subtitle }: { title: string; action?: ReactNode; subtitle?: string }) {
  return (
    <div className="flex min-w-0 items-start justify-between gap-3 border-b border-[#2a2a2a] px-4 py-3">
      <div className="min-w-0">
        <h2 className="truncate text-sm font-semibold text-white">{title}</h2>
        {subtitle && <p className="mt-1 text-xs text-[#9a9a9a]">{subtitle}</p>}
      </div>
      {action}
    </div>
  )
}

export function SectionTitle({ children }: { children: ReactNode }) {
  return <div className="text-xs font-semibold uppercase tracking-normal text-[#8c8c8c]">{children}</div>
}

export function ScoreBar({ value, level }: { value: number; level?: ReadinessLevel }) {
  const tone = readinessTone(level ?? (value >= 85 ? 'ready' : value >= 65 ? 'warning' : 'blocked'))
  const fill = {
    ready: 'bg-emerald-400',
    warning: 'bg-amber-400',
    blocked: 'bg-red-400',
    neutral: 'bg-[#777]',
  }[tone]
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 min-w-0 flex-1 rounded bg-[#333]">
        <div className={cn('h-full rounded', fill)} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
      </div>
      <span className="w-8 text-right text-xs tabular-nums text-[#cfcfcf]">{value}</span>
    </div>
  )
}

export function EmptyState({ title, body, action }: { title: string; body: string; action?: ReactNode }) {
  return (
    <div className="flex min-h-[260px] flex-col items-center justify-center rounded-lg border border-dashed border-[#333] bg-[#1b1b1b] p-8 text-center">
      <Clock className="mb-3 h-6 w-6 text-[#777]" />
      <h3 className="text-sm font-semibold text-white">{title}</h3>
      <p className="mt-2 max-w-md text-sm text-[#a0a0a0]">{body}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function ErrorState({ title, body, action }: { title: string; body: string; action?: ReactNode }) {
  return (
    <div className="flex min-h-[260px] flex-col items-center justify-center rounded-lg border border-red-500/20 bg-red-500/5 p-8 text-center">
      <AlertCircle className="mb-3 h-6 w-6 text-red-300" />
      <h3 className="text-sm font-semibold text-white">{title}</h3>
      <p className="mt-2 max-w-md text-sm text-red-100/70">{body}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function PermissionState({ action }: { action?: ReactNode }) {
  return (
    <div className="flex min-h-[260px] flex-col items-center justify-center rounded-lg border border-amber-500/20 bg-amber-500/5 p-8 text-center">
      <ShieldAlert className="mb-3 h-6 w-6 text-amber-300" />
      <h3 className="text-sm font-semibold text-white">Permission Required</h3>
      <p className="mt-2 max-w-md text-sm text-amber-100/70">You do not have model governance access in this workspace.</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function CheckLine({ children, tone = 'ready' }: { children: ReactNode; tone?: 'ready' | 'warning' | 'blocked' }) {
  const Icon = tone === 'ready' ? CheckCircle2 : AlertCircle
  const iconClass = tone === 'ready' ? 'text-emerald-300' : tone === 'warning' ? 'text-amber-300' : 'text-red-300'
  return (
    <div className="flex items-start gap-2 text-sm text-[#d4d4d4]">
      <Icon className={cn('mt-0.5 h-4 w-4 shrink-0', iconClass)} />
      <span>{children}</span>
    </div>
  )
}
