import type { ReactNode } from 'react'
import { AlertCircle, CheckCircle2, Clock, ShieldAlert } from 'lucide-react'
import { cn } from '../../../lib/utils'
import type { ReadinessLevel, ValidationStatus } from '../types'

export const modelingStyles = {
  page: 'min-h-full bg-[#0f1113] text-[#f3f5f5]',
  workspace: 'min-h-0 flex-1 overflow-y-auto bg-[#0f1113] text-[#f3f5f5] custom-scrollbar',
  shell: 'mx-auto max-w-[1500px]',
  panel: 'rounded-lg border border-[#2d3439] bg-[#181b1e] shadow-[0_16px_42px_rgba(0,0,0,0.26)]',
  panelFlat: 'rounded-lg border border-[#2d3439] bg-[#16191c]',
  surface: 'rounded-md border border-[#2a3136] bg-[#121518]',
  surfaceMuted: 'rounded-md border border-[#2a3035] bg-[#171b1f]',
  surfaceInset: 'rounded-md border border-[#242a2f] bg-[#0f1113]',
  divider: 'border-[#2d3338]',
  text: 'text-[#f3f5f5]',
  muted: 'text-[#9aa4ac]',
  faint: 'text-[#737d85]',
  input: 'border-[#343c42] bg-[#0f1113] text-[#f3f5f5] placeholder:text-[#6f7981] focus-visible:ring-brand-orange/70',
  tableHead: 'bg-[#121518] text-[11px] uppercase text-[#8b969f]',
  tableRow: 'border-t border-[#272e33] bg-[#171a1d] transition-colors hover:bg-[#1f252a]',
  toolbar: 'rounded-md border border-[#303840] bg-[#15191d]',
  active: 'border-brand-orange/60 bg-brand-orange/10 text-white shadow-[inset_0_0_0_1px_rgba(249,115,22,0.14)]',
  label: 'text-[11px] font-medium uppercase text-[#818c95]',
  control: 'h-9 rounded-md border border-[#343c42] bg-[#0f1113] px-3 text-sm text-[#f3f5f5] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-brand-orange/70',
  segmented: 'inline-flex rounded-md border border-[#313940] bg-[#111417] p-1',
  segmentedItem: 'rounded px-3 py-1.5 text-sm text-[#c4ccd2] transition focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring hover:bg-[#20262b]',
}

export function StatusPill({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'ready' | 'warning' | 'blocked' | 'info' }) {
  const classes = {
    neutral: 'border-[#3a4147] bg-[#20252a] text-[#c4ccd2]',
    ready: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
    warning: 'border-amber-500/30 bg-amber-500/10 text-amber-300',
    blocked: 'border-red-500/30 bg-red-500/10 text-red-300',
    info: 'border-sky-500/30 bg-sky-500/10 text-sky-300',
  }
  return <span className={cn('inline-flex h-5 items-center rounded border px-2 text-[11px] font-medium leading-none', classes[tone])}>{children}</span>
}

// eslint-disable-next-line react-refresh/only-export-components
export function readinessTone(level: ReadinessLevel | ValidationStatus | string): 'ready' | 'warning' | 'blocked' | 'neutral' {
  if (level === 'ready' || level === 'valid') return 'ready'
  if (level === 'warning') return 'warning'
  if (level === 'blocked') return 'blocked'
  return 'neutral'
}

export function Panel({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={cn(modelingStyles.panel, className)}>{children}</section>
}

export function PanelHeader({ title, action, subtitle }: { title: string; action?: ReactNode; subtitle?: string }) {
  return (
    <div className={cn('flex min-w-0 items-start justify-between gap-3 border-b px-4 py-3', modelingStyles.divider)}>
      <div className="min-w-0">
        <h2 className="truncate text-sm font-semibold text-[#f3f5f5]">{title}</h2>
        {subtitle && <p className="mt-1 text-xs leading-5 text-[#9aa4ac]">{subtitle}</p>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  )
}

export function SectionTitle({ children }: { children: ReactNode }) {
  return <div className="text-[11px] font-semibold uppercase tracking-normal text-[#7f8a93]">{children}</div>
}

export function ScoreBar({ value, level }: { value: number; level?: ReadinessLevel }) {
  const tone = readinessTone(level ?? (value >= 85 ? 'ready' : value >= 65 ? 'warning' : 'blocked'))
  const fill = {
    ready: 'bg-emerald-400',
    warning: 'bg-amber-400',
    blocked: 'bg-red-400',
    neutral: 'bg-[#8a949d]',
  }[tone]
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 min-w-0 flex-1 rounded bg-[#2b3136]">
        <div className={cn('h-full rounded', fill)} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
      </div>
      <span className="w-8 text-right text-xs tabular-nums text-[#cdd3d8]">{value}</span>
    </div>
  )
}

export function EmptyState({ title, body, action }: { title: string; body: string; action?: ReactNode }) {
  return (
    <div className="flex min-h-[260px] flex-col items-center justify-center rounded-lg border border-dashed border-[#3a4147] bg-[#121518] p-8 text-center">
      <Clock className="mb-3 h-6 w-6 text-[#7f8a93]" />
      <h3 className="text-sm font-semibold text-[#f3f5f5]">{title}</h3>
      <p className="mt-2 max-w-md text-sm leading-6 text-[#9aa4ac]">{body}</p>
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
    <div className="flex items-start gap-2 text-sm leading-6 text-[#d6dde2]">
      <Icon className={cn('mt-0.5 h-4 w-4 shrink-0', iconClass)} />
      <span>{children}</span>
    </div>
  )
}

export function Surface({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={cn(modelingStyles.surface, className)}>{children}</div>
}

export function MetricTile({ label, value, sub, className = '' }: { label: string; value: string; sub?: ReactNode; className?: string }) {
  return (
    <div className={cn('rounded-md border border-[#2d3338] bg-[#14181b] p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.025)]', className)}>
      <div className="text-[11px] font-medium uppercase text-[#818c95]">{label}</div>
      <div className="mt-1 truncate text-xl font-semibold leading-7 text-[#f3f5f5]">{value}</div>
      {sub && <div className="mt-1 line-clamp-2 text-xs leading-5 text-[#9aa4ac]">{sub}</div>}
    </div>
  )
}
