import { useEffect, useState } from 'react'
import { Bot, CheckCircle2, Loader2, PlugZap, Power, RefreshCcw, Send, Trash2, UserRound } from 'lucide-react'
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
    loadIdentities,
    loadTeamMembers,
    mapIdentity,
    unmapIdentity,
    refreshHealth,
  } = useFeishuIntegration(open, { loadDetails: true })
  const { data: llmConnections = [] } = useLLMConnections()

  const [appId, setAppId] = useState('')
  const [appSecret, setAppSecret] = useState('')
  const [verificationToken, setVerificationToken] = useState('')
  const [encryptKey, setEncryptKey] = useState('')
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

  useEffect(() => {
    if (installation) {
      setAppId(installation.app_id || '')
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
        app_id: appId.trim(),
        app_secret: appSecret,
        connection_mode: 'websocket',
        default_llm_connection_id: llmConnectionId || null,
        verification_token: verificationToken || null,
        encrypt_key: encryptKey || null,
      }),
      'Feishu credentials validated and saved.'
    )
    setAppSecret('')
    setVerificationToken('')
    setEncryptKey('')
  }

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
            配置飞书自建应用 WebSocket 长连接。本地 self-hosted 不需要公网 URL；Webhook 在完成验签、解密和防重放前不开放。
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
                    需要飞书 App ID、App Secret，并在事件订阅中启用 im.message.receive_v1。
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
                  <Label>App ID</Label>
                  <Input value={appId} onChange={(event) => setAppId(event.target.value)} placeholder="cli_xxx" />
                </div>
                <div className="space-y-2">
                  <Label>App Secret</Label>
                  <Input
                    type="password"
                    value={appSecret}
                    onChange={(event) => setAppSecret(event.target.value)}
                    placeholder={installation ? 'Leave blank unless rotating secret' : 'App Secret'}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Verification Token（可选，供安全 callback URL verification）</Label>
                  <Input
                    type="password"
                    value={verificationToken}
                    onChange={(event) => setVerificationToken(event.target.value)}
                    placeholder={installation?.callback?.verification_token_configured ? 'Leave blank to reuse existing token' : 'Verification Token'}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Encrypt Key（可选，供安全 callback 解密/验签）</Label>
                  <Input
                    type="password"
                    value={encryptKey}
                    onChange={(event) => setEncryptKey(event.target.value)}
                    placeholder={installation?.callback?.encrypt_key_configured ? 'Leave blank to reuse existing key' : 'Encrypt Key'}
                  />
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
                  disabled={!appId.trim() || (!installation && !appSecret) || saving || busyAction === 'configure'}
                  onClick={handleConfigure}
                >
                  {busyAction === 'configure' ? <Loader2 className="w-4 h-4 animate-spin" /> : <PlugZap className="w-4 h-4" />}
                  连接 / 更新
                </Button>
                <Button variant="outline" disabled={!installation || busyAction === 'probe'} onClick={() => runAction('probe', probe, 'Probe succeeded.')}>
                  <RefreshCcw className="w-4 h-4" />
                  测试凭证
                </Button>
              </div>
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
                        chat: {event.chat_id || '—'} · attempts: {event.attempt_count} · {event.created_at || '—'}
                      </div>
                      {(event.conversation_id || event.notebook_id || event.run_id) && (
                        <div className="mt-1 text-gray-500">
                          conversation: {event.conversation_id || '—'} · notebook: {event.notebook_id || '—'} · run: {event.run_id || '—'}
                        </div>
                      )}
                      {event.response_ref && (
                        <div className="mt-1 text-gray-500">
                          response message: {event.response_ref.message_id} · status: {event.response_ref.status} · sequence: {event.response_ref.sequence}
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
                            {chat.name} ({chat.chat_id})
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
                  <Label>root_id（可选）</Label>
                  <Input value={rootId} onChange={(event) => setRootId(event.target.value)} placeholder="om_xxx" />
                </div>
              </div>
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
                              type: {target.target_type} · chat: {target.chat_id} · root: {target.root_id || 'whole chat'} · source: {target.source || '—'}
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
                          {target.display_name || target.chat_id}
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
