import { useEffect, useState } from 'react'
import { Bot, CheckCircle2, Loader2, PlugZap, Power, QrCode, RefreshCcw, Send, Trash2, UserRound } from 'lucide-react'
import QRCode from 'qrcode'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '../ui/dialog'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'
import { useLLMConnections } from '@/hooks/useLLMConnections'
import { useFeishuIntegration } from '@/hooks/useFeishuIntegration'

interface FeishuIntegrationModalProps {
  open: boolean
  onClose: () => void
}

export function FeishuIntegrationModal({ open, onClose }: FeishuIntegrationModalProps) {
  const {
    installation,
    health,
    isConnected,
    loading,
    saving,
    error,
    configure,
    probe,
    start,
    stop,
    disconnect,
    testMessage,
    chats,
    loadingChats,
    loadChats,
    events,
    loadingEvents,
    loadEvents,
    deliveryTargets,
    loadingDeliveryTargets,
    loadDeliveryTargets,
    bindDeliveryTarget,
    pauseDeliveryTarget,
    resumeDeliveryTarget,
    unbindDeliveryTarget,
    sendOutboundMessage,
    identities,
    loadingIdentities,
    teamMembers,
    loadingTeamMembers,
    oauthSession,
    oauthResult,
    oauthLoading,
    loadIdentities,
    loadTeamMembers,
    mapIdentity,
    unmapIdentity,
    refreshHealth,
    startOAuth,
    pollOAuth,
  } = useFeishuIntegration(open, { loadDetails: true })
  const { data: llmConnections = [] } = useLLMConnections()

  const [llmConnectionId, setLlmConnectionId] = useState<string>('')
  const [selectedChatId, setSelectedChatId] = useState('')
  const [rootId, setRootId] = useState('')
  const [outboundTargetId, setOutboundTargetId] = useState('')
  const [outboundText, setOutboundText] = useState('')
  const [outboundIdempotencyKey, setOutboundIdempotencyKey] = useState('')
  const [outboundConfirmed, setOutboundConfirmed] = useState(false)
  const [identitySelections, setIdentitySelections] = useState<Record<string, string>>({})
  const [statusMessage, setStatusMessage] = useState<string | null>(null)
  const [busyAction, setBusyAction] = useState<string | null>(null)
  const [oauthPolling, setOauthPolling] = useState(false)
  const [oauthQrDataUrl, setOauthQrDataUrl] = useState<string | null>(null)
  const [oauthQrError, setOauthQrError] = useState<string | null>(null)

  useEffect(() => {
    if (installation) {
      setLlmConnectionId(installation.default_llm_connection_id || '')
    }
  }, [installation])

  async function runAction(label: string, action: () => Promise<unknown>, success: string) {
    setBusyAction(label)
    setStatusMessage(null)
    try {
      await action()
      setStatusMessage(success)
    } catch (err) {
      setStatusMessage(err instanceof Error ? err.message : 'Action failed')
    } finally {
      setBusyAction(null)
    }
  }

  async function handleConfigure() {
    await runAction(
      'configure',
      () => configure({
        connection_mode: 'websocket',
        default_llm_connection_id: llmConnectionId || null,
      }),
      'Feishu managed app validated and saved.'
    )
  }

  async function handleStartOAuth() {
    await runAction(
      'oauth-start',
      async () => {
        const session = await startOAuth({ default_llm_connection_id: llmConnectionId || null })
        window.open(session.authorization_url, '_blank', 'noopener,noreferrer,width=720,height=760')
        setOauthPolling(true)
      },
      'Feishu authorization opened. Complete it in the Feishu window, then this page will update automatically.'
    )
  }

  useEffect(() => {
    if (!oauthSession?.authorization_url) {
      setOauthQrDataUrl(null)
      setOauthQrError(null)
      return
    }

    let cancelled = false
    setOauthQrDataUrl(null)
    setOauthQrError(null)
    void QRCode.toDataURL(oauthSession.authorization_url, {
      errorCorrectionLevel: 'M',
      margin: 2,
      scale: 6,
      type: 'image/png',
      color: {
        dark: '#111827',
        light: '#ffffff',
      },
    })
      .then((dataUrl) => {
        if (!cancelled) setOauthQrDataUrl(dataUrl)
      })
      .catch((err) => {
        if (!cancelled) {
          setOauthQrError(err instanceof Error ? err.message : 'Failed to render QR code')
        }
      })

    return () => {
      cancelled = true
    }
  }, [oauthSession])

  useEffect(() => {
    if (!oauthPolling || !oauthSession?.state) return
    let stopped = false
    const timer = window.setInterval(() => {
      void pollOAuth(oauthSession.state)
        .then((result) => {
          if (stopped) return
          if (result.status === 'success') {
            setOauthPolling(false)
            setStatusMessage('Feishu authorization completed. Choose a test chat and start WebSocket.')
            void loadChats()
            void loadDeliveryTargets()
            void loadIdentities()
          } else if (result.status === 'failed') {
            setOauthPolling(false)
            setStatusMessage(result.error || 'Feishu authorization failed.')
          }
        })
        .catch((err) => {
          if (!stopped) setStatusMessage(err instanceof Error ? err.message : 'Failed to poll Feishu authorization.')
        })
    }, 2500)
    return () => {
      stopped = true
      window.clearInterval(timer)
    }
  }, [oauthPolling, oauthSession, pollOAuth, loadChats, loadDeliveryTargets, loadIdentities])

  const healthStatus = health?.health_status || installation?.health_status || 'not_configured'
  const adminState = health?.admin_state || installation?.admin_state || (installation ? healthStatus : 'not_installed')
  const healthError = health?.health_error || installation?.health_error
  const lastConnectedAt = health?.last_connected_at || installation?.last_connected_at
  const lastEventAt = health?.last_event_at || installation?.last_event_at
  const reconnectCount = health?.reconnect_count ?? installation?.reconnect_count ?? 0
  const isActive = health?.is_active ?? installation?.is_active ?? false
  const callbackStatus = health?.callback || installation?.callback
  const eventSubscription = health?.event_subscription || installation?.event_subscription
  const unmappedIdentityCount = identities.filter((identity) => !identity.byaan_user_id).length
  const enabledDeliveryTargets = deliveryTargets.filter((target) => target.is_enabled && target.is_verified)
  const selectedChat = chats.find((chat) => chat.chat_id === selectedChatId)
  const healthColor = healthStatus === 'connected'
    ? 'text-green-400'
    : healthStatus === 'failed'
      ? 'text-red-400'
      : healthStatus === 'connecting' || healthStatus === 'reconnecting' || healthStatus === 'leased_elsewhere'
        ? 'text-amber-300'
        : 'text-gray-400'

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-3xl max-h-[88vh] overflow-y-auto bg-[#1f1f1f] border-[#555555] text-white">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Bot className="w-5 h-5 text-brand-orange" />
            协作集成 → 飞书
          </DialogTitle>
          <DialogDescription>
            使用 Byaan 托管或管理员配置的飞书应用建立 WebSocket 长连接。本地 self-hosted 不需要公网 URL；Webhook 不作为本阶段生产入口。
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center gap-2 text-sm text-gray-400 py-8">
            <Loader2 className="w-4 h-4 animate-spin" />
            Loading Feishu integration...
          </div>
        ) : (
          <div className="space-y-6">
            <section className="rounded-lg border border-gray-700 bg-[#151515] p-4 space-y-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h3 className="text-sm font-semibold text-white">连接</h3>
                  <p className="text-xs text-gray-400 mt-1">
                    普通用户不需要填写 App ID 或 App Secret。点击连接后，后端使用管理员配置的 Byaan managed/BYOC 应用完成 Probe，并保存 WebSocket installation。
                  </p>
                </div>
                {installation && (
                  <span className={`inline-flex items-center gap-1 text-xs ${isConnected ? 'text-green-400' : 'text-gray-400'}`}>
                    <CheckCircle2 className="w-4 h-4" />
                    {isConnected ? 'Connected' : 'Configured'}
                  </span>
                )}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>飞书授权方式</Label>
                  <div className="min-h-10 rounded-md border border-input bg-background px-3 py-2 text-sm text-gray-300">
                    Byaan managed app / 管理员 BYOC 高级配置
                  </div>
                </div>
                <div className="space-y-2">
                  <Label>二维码授权</Label>
                  <div className="flex min-h-10 items-center gap-2 rounded-md border border-input bg-background px-3 py-2 text-sm text-gray-300">
                    <QrCode className="h-4 w-4 text-gray-500" />
                    数据源 OAuth 二维码在 Datasources 授权页打开；机器人消息接入使用 WebSocket。
                  </div>
                </div>
                <div className="space-y-2">
                  <Label>连接模式</Label>
                  <div className="h-10 rounded-md border border-input bg-background px-3 py-2 text-sm text-gray-300">
                    WebSocket 长连接（唯一生产入口）
                  </div>
                </div>
                <div className="space-y-2">
                  <Label>默认 LLM</Label>
                  <Select value={llmConnectionId || 'none'} onValueChange={(value) => setLlmConnectionId(value === 'none' ? '' : value)}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select LLM" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">未选择</SelectItem>
                      {llmConnections.map((conn) => (
                        <SelectItem key={conn.id} value={conn.id}>
                          {conn.name || conn.type}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <Button
                  variant="brand-primary"
                  disabled={oauthLoading || busyAction === 'oauth-start' || oauthPolling}
                  onClick={handleStartOAuth}
                >
                  {busyAction === 'oauth-start' || oauthLoading || oauthPolling ? <Loader2 className="w-4 h-4 animate-spin" /> : <QrCode className="w-4 h-4" />}
                  {oauthPolling ? '等待飞书授权完成' : '连接飞书'}
                </Button>
                <Button
                  variant="outline"
                  disabled={saving || busyAction === 'configure'}
                  onClick={handleConfigure}
                >
                  {busyAction === 'configure' ? <Loader2 className="w-4 h-4 animate-spin" /> : <PlugZap className="w-4 h-4" />}
                  使用管理员配置直接创建
                </Button>
                <Button variant="outline" disabled={!installation || busyAction === 'probe'} onClick={() => runAction('probe', probe, 'Probe succeeded.')}>
                  <RefreshCcw className="w-4 h-4" />
                  测试凭证
                </Button>
              </div>
              {oauthSession && (
                <div className="rounded border border-gray-800 bg-[#101010] p-3 text-xs text-gray-300">
                  <div className="flex flex-wrap items-center gap-2">
                    <QrCode className="h-4 w-4 text-gray-500" />
                    <span>授权链接已生成；下方二维码和“重新打开授权页”使用同一个授权 URL，完成后页面会短轮询刷新。</span>
                  </div>
                  <div className="mt-3 flex flex-col gap-3 md:flex-row md:items-start">
                    <div className="flex min-h-[188px] w-[188px] items-center justify-center rounded bg-white p-2">
                      {oauthQrDataUrl ? (
                        <img
                          alt="Feishu authorization QR code"
                          src={oauthQrDataUrl}
                          className="h-[172px] w-[172px]"
                        />
                      ) : oauthQrError ? (
                        <div className="px-2 text-center text-xs text-red-700">二维码生成失败，请使用授权链接。</div>
                      ) : (
                        <Loader2 className="h-5 w-5 animate-spin text-gray-700" />
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-gray-500">授权 URL / QR payload</div>
                      <div className="mt-1 break-all font-mono text-gray-500">{oauthSession.qr_payload}</div>
                    </div>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <Button variant="outline" size="sm" onClick={() => window.open(oauthSession.authorization_url, '_blank', 'noopener,noreferrer')}>
                      重新打开授权页
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => navigator.clipboard?.writeText(oauthSession.authorization_url)}>
                      复制授权链接
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => runAction('oauth-poll', () => pollOAuth(oauthSession.state), 'Authorization status refreshed.')}>
                      手动刷新授权状态
                    </Button>
                  </div>
                  <div className="mt-2 text-gray-500">
                    OAuth status: {oauthResult?.status || (oauthPolling ? 'pending' : 'not polled')}
                    {oauthResult?.external_identity?.display_name ? ` · ${oauthResult.external_identity.display_name}` : ''}
                  </div>
                  {oauthResult?.error ? <div className="mt-1 text-red-300">{oauthResult.error}</div> : null}
                </div>
              )}
            </section>

            <section className="rounded-lg border border-gray-700 bg-[#151515] p-4 space-y-3">
              <h3 className="text-sm font-semibold text-white">运行状态</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                <div><span className="text-gray-500">Tenant:</span> {installation?.external_tenant_name || installation?.external_tenant_id || 'Not configured'}</div>
                <div><span className="text-gray-500">Bot:</span> {installation?.bot_external_id || 'Unknown'}</div>
                <div><span className="text-gray-500">Mode:</span> WebSocket</div>
                <div><span className="text-gray-500">Health:</span> <span className={healthColor}>{healthStatus}</span></div>
                <div><span className="text-gray-500">Admin state:</span> {adminState}</div>
                <div><span className="text-gray-500">Desired active:</span> {isActive ? 'yes' : 'no'}</div>
                <div><span className="text-gray-500">Last connected:</span> {lastConnectedAt || '—'}</div>
                <div><span className="text-gray-500">Last event:</span> {lastEventAt || '—'}</div>
                <div><span className="text-gray-500">Reconnects:</span> {reconnectCount}</div>
                <div><span className="text-gray-500">Lease owner:</span> {health?.owner_id || '—'}</div>
                <div><span className="text-gray-500">Lease expires:</span> {health?.lease_expires_at || '—'}</div>
                <div><span className="text-gray-500">Tenant token expires:</span> {installation?.tenant_token_expires_at || '—'}</div>
                <div><span className="text-gray-500">Callback token:</span> {callbackStatus?.verification_token_configured ? 'configured' : 'not configured'}</div>
                <div><span className="text-gray-500">Callback encrypt key:</span> {callbackStatus?.encrypt_key_configured ? 'configured' : 'not configured'}</div>
                <div><span className="text-gray-500">URL verification:</span> <span className={callbackStatus?.url_verification === 'verified' ? 'text-green-400' : 'text-amber-300'}>{callbackStatus?.url_verification || 'not verified'}</span></div>
                <div><span className="text-gray-500">URL verified at:</span> {callbackStatus?.last_url_verification_at || '—'}</div>
                <div><span className="text-gray-500">Event subscription:</span> <span className={eventSubscription?.ready ? 'text-green-400' : 'text-amber-300'}>{eventSubscription?.remote_status || 'manual check required'}</span></div>
                <div><span className="text-gray-500">Last observed event:</span> {eventSubscription?.last_event_observed_at || '—'}</div>
              </div>
              {installation?.required_scopes?.length ? (
                <p className="text-xs text-gray-500">Minimum scopes: {installation.required_scopes.join(', ')}</p>
              ) : null}
              {eventSubscription?.required_event_types?.length ? (
                <p className="text-xs text-gray-500">Required Feishu events: {eventSubscription.required_event_types.join(', ')}</p>
              ) : null}
              {eventSubscription?.operator_action && !eventSubscription.ready ? (
                <p className="text-xs text-amber-300">{eventSubscription.operator_action}</p>
              ) : null}
              {installation?.data_use && <p className="text-xs text-gray-500">Data use: {installation.data_use}</p>}
              {healthError && <p className="text-sm text-red-400">{healthError}</p>}
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" disabled={!installation || busyAction === 'refresh-health'} onClick={() => runAction('refresh-health', refreshHealth, 'Health refreshed.')}>
                  <RefreshCcw className="w-4 h-4" />
                  刷新状态
                </Button>
                <Button variant="outline" disabled={!installation || busyAction === 'start'} onClick={() => runAction('start', start, 'WebSocket connect requested.')}>
                  <Power className="w-4 h-4" />
                  启动长连接
                </Button>
                <Button variant="outline" disabled={!installation || busyAction === 'stop'} onClick={() => runAction('stop', stop, 'WebSocket disconnected.')}>
                  停止长连接
                </Button>
              </div>
            </section>

            <section className="rounded-lg border border-gray-700 bg-[#151515] p-4 space-y-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold text-white">最近事件</h3>
                  <p className="text-xs text-gray-400 mt-1">只展示事件元数据，不展示消息正文、密钥或 token。</p>
                </div>
                <Button variant="outline" disabled={!installation || loadingEvents} onClick={() => runAction('load-events', loadEvents, 'Events refreshed.')}>
                  {loadingEvents ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCcw className="w-4 h-4" />}
                  刷新
                </Button>
              </div>
              {events.length ? (
                <div className="space-y-2">
                  {events.slice(0, 5).map((event) => (
                    <div key={event.id} className="rounded border border-gray-800 bg-[#101010] p-3 text-xs text-gray-300">
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                        <span className="font-medium text-white">{event.status}</span>
                        <span className="text-gray-500">{event.event_type}</span>
                        <span className="text-gray-500">{event.event_id}</span>
                      </div>
                      <div className="mt-1 text-gray-500">
                        target: {maskExternalRef(event.chat_id)} · attempts: {event.attempt_count} · {event.created_at || '—'}
                      </div>
                      {(event.conversation_id || event.notebook_id || event.run_id) && (
                        <div className="mt-1 text-gray-500">
                          conversation: {event.conversation_id || '—'} · notebook: {event.notebook_id || '—'} · run: {event.run_id || '—'}
                        </div>
                      )}
                      {event.response_ref && (
                        <div className="mt-1 text-gray-500">
                          response: {maskExternalRef(event.response_ref.message_id)} · status: {event.response_ref.status} · sequence: {event.response_ref.sequence}
                        </div>
                      )}
                      {event.error && <div className="mt-1 text-red-400">{event.error}</div>}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-gray-500">暂无事件。连接 WebSocket 后，群聊 @ 或私聊消息会出现在这里。</p>
              )}
            </section>

            <section className="rounded-lg border border-gray-700 bg-[#151515] p-4 space-y-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold text-white">飞书身份映射</h3>
                  <p className="text-xs text-gray-400 mt-1">
                    飞书用户必须显式映射到当前 Team 成员后，才能触发 Agent 访问 tenant 数据。
                    {unmappedIdentityCount > 0 && <span className="text-amber-300"> 当前有 {unmappedIdentityCount} 个未映射身份。</span>}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    disabled={!installation || loadingIdentities}
                    onClick={() => runAction('load-identities', loadIdentities, 'Identities refreshed.')}
                  >
                    {loadingIdentities ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCcw className="w-4 h-4" />}
                    刷新身份
                  </Button>
                  <Button
                    variant="outline"
                    disabled={!installation || loadingTeamMembers}
                    onClick={() => runAction('load-team-members', loadTeamMembers, 'Team members refreshed.')}
                  >
                    {loadingTeamMembers ? <Loader2 className="w-4 h-4 animate-spin" /> : <UserRound className="w-4 h-4" />}
                    刷新成员
                  </Button>
                </div>
              </div>

              {identities.length ? (
                <div className="space-y-2">
                  {identities.slice(0, 8).map((identity) => {
                    const selectedUserId = identitySelections[identity.id] || identity.byaan_user_id || ''
                    const mappedUser = identity.mapped_user
                    const isBusy = busyAction === `map-${identity.id}` || busyAction === `unmap-${identity.id}`
                    return (
                      <div key={identity.id} className="rounded border border-gray-800 bg-[#101010] p-3 text-xs text-gray-300">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="font-medium text-white">{identity.external_user_id}</span>
                              <span className={identity.byaan_user_id ? 'text-green-400' : 'text-amber-300'}>
                                {identity.byaan_user_id ? 'linked' : 'needs mapping'}
                              </span>
                            </div>
                            <div className="mt-1 text-gray-500">
                              union: {identity.union_id || '—'} · last seen: {identity.last_seen_at || '—'}
                            </div>
                            <div className="mt-1 text-gray-500">
                              mapped user: {mappedUser ? `${mappedUser.full_name || mappedUser.email} (${mappedUser.email})` : '—'}
                            </div>
                          </div>
                          <div className="flex min-w-[280px] flex-1 flex-col gap-2 md:flex-row md:items-center md:justify-end">
                            <Select
                              value={selectedUserId || 'none'}
                              onValueChange={(value) => setIdentitySelections((current) => ({
                                ...current,
                                [identity.id]: value === 'none' ? '' : value,
                              }))}
                              disabled={teamMembers.length === 0 || loadingTeamMembers}
                            >
                              <SelectTrigger className="md:w-[240px]">
                                <SelectValue placeholder={teamMembers.length ? '选择 Team 成员' : '先刷新成员'} />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="none">未选择</SelectItem>
                                {teamMembers.map((member) => (
                                  <SelectItem key={member.user_id} value={member.user_id}>
                                    {member.user?.full_name || member.user?.email || member.user_id}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                            <Button
                              variant="outline"
                              disabled={!selectedUserId || isBusy}
                              onClick={() => runAction(`map-${identity.id}`, () => mapIdentity(identity.id, selectedUserId), 'Identity mapped.')}
                            >
                              {busyAction === `map-${identity.id}` ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                              映射
                            </Button>
                            <Button
                              variant="outline"
                              disabled={!identity.byaan_user_id || isBusy}
                              onClick={() => runAction(`unmap-${identity.id}`, () => unmapIdentity(identity.id), 'Identity unmapped.')}
                            >
                              解除
                            </Button>
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <p className="text-sm text-gray-500">
                  暂无飞书身份记录。用户在群聊 @ 或私聊机器人后，会先出现在这里；管理员映射后，该用户才能触发 Agent。
                </p>
              )}
            </section>

            <section className="rounded-lg border border-gray-700 bg-[#151515] p-4 space-y-4">
              <div>
                <h3 className="text-sm font-semibold text-white">发送测试消息</h3>
                <p className="text-xs text-gray-400 mt-1">
                  先加载 Bot 可见群列表，再由管理员明确选择测试群。系统不会向未知群自动发送消息。
                </p>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>测试群</Label>
                  <div className="flex gap-2">
                    <Select value={selectedChatId} onValueChange={setSelectedChatId} disabled={!installation || loadingChats || chats.length === 0}>
                      <SelectTrigger>
                        <SelectValue placeholder={chats.length ? '选择测试群' : '先加载群列表'} />
                      </SelectTrigger>
                      <SelectContent>
                        {chats.map((chat) => (
                          <SelectItem key={chat.chat_id} value={chat.chat_id}>
                            {chatLabel(chat)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Button variant="outline" disabled={!installation || loadingChats} onClick={() => runAction('load-chats', loadChats, 'Chat list loaded.')}>
                      {loadingChats ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCcw className="w-4 h-4" />}
                      加载
                    </Button>
                  </div>
                </div>
                <div className="space-y-2">
                  <Label>话题 root_id（高级可选）</Label>
                  <Input value={rootId} onChange={(event) => setRootId(event.target.value)} placeholder="om_xxx" />
                </div>
              </div>
              {selectedChat && (
                <p className="text-xs text-gray-500">
                  已选择：{chatLabel(selectedChat)} · target ref {maskExternalRef(selectedChat.chat_id)}
                </p>
              )}
              <Button
                variant="outline"
                disabled={!installation || !selectedChatId || busyAction === 'test-message'}
                onClick={() => runAction('test-message', () => testMessage(selectedChatId, 'Byaan 飞书连接测试消息。', rootId.trim() || null), 'Test message sent.')}
              >
                <Send className="w-4 h-4" />
                发送测试
              </Button>
            </section>

            <section className="rounded-lg border border-gray-700 bg-[#151515] p-4 space-y-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold text-white">允许的群/私聊/话题</h3>
                  <p className="text-xs text-gray-400 mt-1">
                    只有管理员显式绑定并启用的群、私聊或话题会触发 Agent。未绑定的 @ 或私聊只记录事件，不访问 tenant 数据。
                  </p>
                </div>
                <Button variant="outline" disabled={!installation || loadingDeliveryTargets} onClick={() => runAction('load-targets', loadDeliveryTargets, 'Delivery targets refreshed.')}>
                  {loadingDeliveryTargets ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCcw className="w-4 h-4" />}
                  刷新
                </Button>
              </div>

              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  disabled={!installation || !selectedChatId || busyAction === 'bind-target'}
                  onClick={() => runAction('bind-target', () => bindDeliveryTarget(selectedChatId, rootId.trim() || null), 'Delivery target bound.')}
                >
                  绑定当前测试会话
                </Button>
              </div>

              {deliveryTargets.length ? (
                <div className="space-y-2">
                  {deliveryTargets.slice(0, 8).map((target) => {
                    const isBusy = busyAction === `pause-target-${target.id}` || busyAction === `resume-target-${target.id}` || busyAction === `unbind-target-${target.id}`
                    return (
                      <div key={target.id} className="rounded border border-gray-800 bg-[#101010] p-3 text-xs text-gray-300">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="font-medium text-white">{target.display_name || target.chat_id}</span>
                              <span className={target.is_enabled && target.is_verified ? 'text-green-400' : 'text-amber-300'}>
                                {target.status || (target.is_enabled && target.is_verified ? 'enabled' : 'paused/unbound')}
                              </span>
                            </div>
                            <div className="mt-1 text-gray-500">
                              type: {target.target_type} · target ref: {maskExternalRef(target.chat_id)} · root: {maskExternalRef(target.root_id) || 'whole chat'} · source: {target.source || '—'}
                            </div>
                            {target.last_error ? (
                              <div className="mt-1 text-red-300">
                                last error: {target.last_error}
                              </div>
                            ) : null}
                          </div>
                          <div className="flex flex-wrap gap-2">
                            {target.is_enabled ? (
                              <Button variant="outline" disabled={isBusy} onClick={() => runAction(`pause-target-${target.id}`, () => pauseDeliveryTarget(target.id), 'Delivery target paused.')}>
                                暂停
                              </Button>
                            ) : (
                              <Button variant="outline" disabled={isBusy} onClick={() => runAction(`resume-target-${target.id}`, () => resumeDeliveryTarget(target.id), 'Delivery target resumed.')}>
                                启用
                              </Button>
                            )}
                            <Button variant="outline" disabled={isBusy} onClick={() => runAction(`unbind-target-${target.id}`, () => unbindDeliveryTarget(target.id), 'Delivery target unbound.')}>
                              解绑
                            </Button>
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <p className="text-sm text-gray-500">暂无绑定目标。请先加载会话列表，选择测试会话，再点击“绑定当前测试会话”。</p>
              )}
            </section>

            <section className="rounded-lg border border-gray-700 bg-[#151515] p-4 space-y-3">
              <div>
                <h3 className="text-sm font-semibold text-white">Byaan 主动发送</h3>
                <p className="text-xs text-gray-400 mt-1">
                  只能发送到已启用的目标；必须显式确认，并通过 idempotency key 避免重复发送。
                </p>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>目标</Label>
                  <Select value={outboundTargetId} onValueChange={setOutboundTargetId} disabled={enabledDeliveryTargets.length === 0}>
                    <SelectTrigger>
                      <SelectValue placeholder={enabledDeliveryTargets.length ? '选择已启用目标' : '无已启用目标'} />
                    </SelectTrigger>
                    <SelectContent>
                      {enabledDeliveryTargets.map((target) => (
                        <SelectItem key={target.id} value={target.id}>
                          {target.display_name || maskExternalRef(target.chat_id)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Idempotency Key</Label>
                  <Input value={outboundIdempotencyKey} onChange={(event) => setOutboundIdempotencyKey(event.target.value)} placeholder="unique-send-key" />
                </div>
                <div className="space-y-2 md:col-span-2">
                  <Label>消息内容</Label>
                  <Input value={outboundText} onChange={(event) => setOutboundText(event.target.value)} placeholder="发送到飞书的确认消息" />
                </div>
              </div>
              <label className="flex items-center gap-2 text-xs text-gray-300">
                <input type="checkbox" checked={outboundConfirmed} onChange={(event) => setOutboundConfirmed(event.target.checked)} />
                我确认向所选飞书目标发送这条消息
              </label>
              <Button
                variant="outline"
                disabled={!installation || !outboundTargetId || !outboundText.trim() || outboundIdempotencyKey.trim().length < 8 || !outboundConfirmed || busyAction === 'outbound-message'}
                onClick={() => runAction(
                  'outbound-message',
                  () => sendOutboundMessage(outboundTargetId, outboundText.trim(), outboundIdempotencyKey.trim(), outboundConfirmed),
                  'Outbound message sent or deduped.'
                )}
              >
                <Send className="w-4 h-4" />
                确认发送
              </Button>
            </section>

            <section className="rounded-lg border border-red-900/40 bg-red-950/10 p-4 space-y-3">
              <h3 className="text-sm font-semibold text-red-300">断开</h3>
              <p className="text-xs text-gray-400">断开会停用当前 Feishu installation，但不会删除 Slack 表、历史 Notebook 或事件记录。</p>
              <Button variant="destructive" disabled={!installation || saving} onClick={() => runAction('disconnect', disconnect, 'Feishu integration disconnected.')}>
                <Trash2 className="w-4 h-4" />
                断开飞书
              </Button>
            </section>

            {(statusMessage || error) && (
              <div className="rounded border border-gray-700 bg-[#111] px-3 py-2 text-sm text-gray-300">
                {statusMessage || error}
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

function maskExternalRef(value?: string | null) {
  if (!value) return ''
  if (value.length <= 8) return '***'
  return `${value.slice(0, 4)}…${value.slice(-4)}`
}

function chatLabel(chat: { name?: string | null; chat_type?: string | null; chat_id: string }) {
  const typeLabel = chat.chat_type === 'p2p' ? '私聊' : chat.chat_type === 'topic_group' ? '话题群' : '群聊'
  return `${chat.name || '未命名会话'} · ${typeLabel}`
}
