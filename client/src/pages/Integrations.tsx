import { useState } from 'react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Bot, CheckCircle2, Database, Loader2, MessageSquare, PlugZap, ShieldCheck } from 'lucide-react'
import { Button } from '../components/ui/button'
import { FeishuAdminSettings } from '../components/collaboration/FeishuAdminSettings'
import { FeishuIntegrationModal } from '../components/collaboration/FeishuIntegrationModal'
import { useFeishuStatus } from '../hooks/useDBConnections'
import { useFeishuIntegration } from '../hooks/useFeishuIntegration'

export default function IntegrationsPage() {
  const feishuStatus = useFeishuStatus()
  const feishuBot = useFeishuIntegration(true)
  const [botOpen, setBotOpen] = useState(false)

  const sourceStatus = feishuStatus.data?.source_authorization?.status || feishuStatus.data?.status || 'not_configured'
  const botStatus = feishuBot.installation?.is_active ? 'installed' : 'not_installed'

  return (
    <div className="min-h-screen bg-[#0d0d0d] text-white">
      <div className="mx-auto w-full max-w-5xl px-6 py-10">
        <div className="mb-8 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Integrations</h1>
            <p className="mt-2 text-sm text-gray-400">飞书数据读取授权和协作机器人安装是两个独立授权域，可共享应用安装状态，但分别管理权限和撤销入口。</p>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <IntegrationCard
            icon={<Database className="h-5 w-5 text-brand-orange" />}
            title="飞书数据源授权"
            description="读取用户选择的文档、Wiki、电子表格和多维表格。"
            status={sourceStatus}
            loading={feishuStatus.isLoading}
            scopes={feishuStatus.data?.source_authorization?.scopes || feishuStatus.data?.admin_config.required_scopes || []}
            actionLabel={feishuStatus.data?.connected ? '已连接，可在 Sources 管理资源' : '前往 Sources 授权'}
            href="/sources"
          />
          <IntegrationCard
            icon={<Bot className="h-5 w-5 text-brand-orange" />}
            title="飞书协作机器人"
            description="接收消息、回复消息，并向明确选择的非生产测试群发送测试消息。"
            status={botStatus}
            loading={feishuBot.loading}
            scopes={['im:message', 'im:chat']}
            actionLabel="将 Byaan 添加到飞书"
            onAction={() => setBotOpen(true)}
          />
        </div>

        <div className="mt-6">
          <FeishuAdminSettings />
        </div>

        <FeishuIntegrationModal open={botOpen} onClose={() => setBotOpen(false)} />
      </div>
    </div>
  )
}

function IntegrationCard({
  icon,
  title,
  description,
  status,
  loading,
  scopes,
  actionLabel,
  href,
  onAction,
}: {
  icon: ReactNode
  title: string
  description: string
  status: string
  loading: boolean
  scopes: string[]
  actionLabel: string
  href?: string
  onAction?: () => void
}) {
  const statusText = statusCopy(status)
  return (
    <section className="rounded-lg border border-[#444444] bg-[#151515] p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="rounded-md border border-[#444444] bg-[#101010] p-2">{icon}</div>
          <div>
            <h2 className="text-base font-semibold text-white">{title}</h2>
            <p className="mt-1 text-sm text-gray-400">{description}</p>
          </div>
        </div>
        <span className={`inline-flex items-center gap-1 rounded border px-2 py-1 text-xs ${statusText.className}`}>
          {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : statusText.ok ? <CheckCircle2 className="h-3 w-3" /> : <ShieldCheck className="h-3 w-3" />}
          {loading ? 'Checking' : statusText.label}
        </span>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        {scopes.map(scope => (
          <span key={scope} className="rounded border border-[#444444] bg-[#101010] px-2 py-1 font-mono text-[11px] text-gray-400">{scope}</span>
        ))}
      </div>
      <div className="mt-5">
        {href ? (
          <Button asChild className="bg-brand-orange hover:bg-brand-orange/90">
            <Link to={href}>
              <PlugZap className="h-4 w-4" />
              {actionLabel}
            </Link>
          </Button>
        ) : (
          <Button onClick={onAction} className="bg-brand-orange hover:bg-brand-orange/90">
            <MessageSquare className="h-4 w-4" />
            {actionLabel}
          </Button>
        )}
      </div>
    </section>
  )
}

function statusCopy(status: string) {
  switch (status) {
    case 'connected':
    case 'installed':
      return { label: 'Connected', ok: true, className: 'border-green-800/60 bg-green-900/10 text-green-300' }
    case 'ready_to_authorize':
      return { label: 'Ready', ok: false, className: 'border-[#555555] bg-[#101010] text-gray-300' }
    case 'needs_reauth':
      return { label: 'Needs reauth', ok: false, className: 'border-amber-800/60 bg-amber-900/10 text-amber-300' }
    case 'scope_missing':
      return { label: 'Scope missing', ok: false, className: 'border-amber-800/60 bg-amber-900/10 text-amber-300' }
    case 'not_installed':
      return { label: 'Not installed', ok: false, className: 'border-[#555555] bg-[#101010] text-gray-300' }
    default:
      return { label: 'Not configured', ok: false, className: 'border-[#555555] bg-[#101010] text-gray-300' }
  }
}
