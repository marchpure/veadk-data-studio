import { useEffect, useMemo, useState } from 'react'
import { Bot, CheckCircle2, ExternalLink, Loader2, PlugZap, Power, RefreshCcw, Send, Settings2, ShieldCheck, Trash2 } from 'lucide-react'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '../ui/dialog'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'
import { useLLMConnections } from '@/hooks/useLLMConnections'
import { useFeishuIntegration } from '@/hooks/useFeishuIntegration'
import { useStore } from '@/stores/useStore'

interface FeishuIntegrationModalProps {
  open: boolean
  onClose: () => void
}

export function FeishuIntegrationModal({ open, onClose }: FeishuIntegrationModalProps) {
  const {
    installation,
    isConnected,
    loading,
    saving,
    error,
    chats,
    configure,
    probe,
    start,
    stop,
    disconnect,
    loadChats,
    selectChat,
    testMessage,
  } = useFeishuIntegration(open)
  const { data: llmConnections = [] } = useLLMConnections()
  const activeTenant = useStore(state => state.getActiveTenant())
  const canConfigureApp = activeTenant ? ['owner', 'admin'].includes(activeTenant.role) : false
  const installUrl = (import.meta.env.VITE_BYAAN_FEISHU_INSTALL_URL as string | undefined) || ''

  const [showAdvanced, setShowAdvanced] = useState(false)
  const [appId, setAppId] = useState('')
  const [appSecret, setAppSecret] = useState('')
  const [connectionMode, setConnectionMode] = useState<'websocket' | 'webhook'>('websocket')
  const [llmConnectionId, setLlmConnectionId] = useState<string>('')
  const [selectedChatId, setSelectedChatId] = useState('')
  const [confirmTestGroup, setConfirmTestGroup] = useState(false)
  const [statusMessage, setStatusMessage] = useState<string | null>(null)
  const [busyAction, setBusyAction] = useState<string | null>(null)

  useEffect(() => {
    if (installation) {
      setAppId(installation.app_id || '')
      setConnectionMode(installation.connection_mode === 'webhook' ? 'webhook' : 'websocket')
      setLlmConnectionId(installation.default_llm_connection_id || '')
    }
  }, [installation])

  useEffect(() => {
    if (open && installation) {
      loadChats().catch(() => null)
    }
  }, [installation, loadChats, open])

  const selectedTarget = useMemo(() => {
    const targets = chats?.selected_targets || []
    return targets.find(item => item.chat_id === selectedChatId) || targets[0] || null
  }, [chats?.selected_targets, selectedChatId])

  const chatOptions = useMemo(() => {
    const map = new Map<string, { chat_id: string; name: string; chat_type: string }>()
    for (const chat of chats?.items || []) {
      map.set(chat.chat_id, { chat_id: chat.chat_id, name: chat.name, chat_type: chat.chat_type })
    }
    for (const target of chats?.selected_targets || []) {
      if (!map.has(target.chat_id)) {
        map.set(target.chat_id, {
          chat_id: target.chat_id,
          name: target.display_name || target.chat_id,
          chat_type: target.chat_type || 'feishu_chat',
        })
      }
    }
    return Array.from(map.values())
  }, [chats?.items, chats?.selected_targets])

  useEffect(() => {
    if (!selectedChatId && selectedTarget) setSelectedChatId(selectedTarget.chat_id)
  }, [selectedChatId, selectedTarget])

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
        connection_mode: connectionMode,
        default_llm_connection_id: llmConnectionId || null,
      }),
      '飞书自建应用配置已验证并保存。'
    )
    setAppSecret('')
  }

  async function handleSelectChat() {
    const item = chatOptions.find(chat => chat.chat_id === selectedChatId)
    if (!item) throw new Error('请选择一个飞书群聊')
    await selectChat({
      chat_id: item.chat_id,
      name: item.name,
      chat_type: item.chat_type,
      confirm_non_production: confirmTestGroup,
    })
  }

  const healthColor = installation?.health_status === 'connected' || installation?.health_status === 'configured'
    ? 'text-green-400'
    : installation?.health_status === 'failed'
      ? 'text-red-400'
      : 'text-gray-400'

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-4xl max-h-[88vh] overflow-y-auto bg-[#1f1f1f] border-[#555555] text-white">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Bot className="w-5 h-5 text-brand-orange" />
            将 Byaan 添加到飞书
          </DialogTitle>
          <DialogDescription>
            协作 bot 安装与数据源授权相互独立。普通成员不需要填写应用密钥或群聊 ID。
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center gap-2 text-sm text-gray-400 py-8">
            <Loader2 className="w-4 h-4 animate-spin" />
            Loading Feishu integration...
          </div>
        ) : (
          <div className="space-y-5">
            <section className="rounded-lg border border-[#444444] bg-[#151515] p-4">
              <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-white">安装状态</h3>
                  <p className="mt-1 text-xs text-gray-400">Source authorization 读取飞书资源；Collaboration bot 负责群聊协作和通知。</p>
                </div>
                {isConnected && (
                  <span className="inline-flex items-center gap-1 rounded border border-green-700/50 bg-green-900/20 px-2 py-1 text-xs text-green-300">
                    <CheckCircle2 className="w-4 h-4" />
                    Installed
                  </span>
                )}
              </div>
              <div className="mt-4 grid grid-cols-1 gap-3 text-sm md:grid-cols-2">
                <StatusRow label="Tenant" value={installation?.external_tenant_name || installation?.external_tenant_id || 'Not installed'} />
                <StatusRow label="Bot" value={installation?.bot_external_id || 'Unknown'} />
                <StatusRow label="Mode" value={installation?.connection_mode || connectionMode} />
                <div><span className="text-gray-500">Health:</span> <span className={healthColor}>{installation?.health_status || 'not_configured'}</span></div>
                <StatusRow label="Last connected" value={installation?.last_connected_at || '-'} />
                <StatusRow label="Last event" value={installation?.last_event_at || '-'} />
              </div>
              {installation?.health_error && <p className="mt-3 text-sm text-red-400">{installation.health_error}</p>}
              <div className="mt-4 flex flex-wrap gap-2">
                <Button variant="outline" disabled={!installation || busyAction === 'probe'} onClick={() => runAction('probe', probe, 'Probe succeeded.')}>
                  <RefreshCcw className="w-4 h-4" />
                  测试安装
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

            <section className="rounded-lg border border-[#444444] bg-[#151515] p-4 space-y-4">
              <div>
                <h3 className="text-sm font-semibold text-white">测试群选择</h3>
                <p className="mt-1 text-xs text-gray-400">测试消息只能发送到已选择并确认的非生产测试群。</p>
              </div>
              {!installation ? (
                <div className="rounded border border-amber-700/50 bg-amber-900/20 p-3 text-sm text-amber-100">
                  <p>飞书 bot 尚未安装。请管理员安装 Byaan 飞书应用，或在高级配置中接入企业自建应用。</p>
                  {installUrl ? (
                    <Button asChild size="sm" className="mt-3 bg-brand-orange hover:bg-brand-orange/90">
                      <a href={installUrl} target="_blank" rel="noreferrer">
                        <ExternalLink className="h-4 w-4" />
                        打开飞书管理员安装页
                      </a>
                    </Button>
                  ) : (
                    <p className="mt-2 text-xs text-amber-100/80">当前环境未配置托管安装链接，请联系租户管理员。</p>
                  )}
                </div>
              ) : (
                <>
                  <div className="grid grid-cols-1 gap-3 md:grid-cols-[1fr_auto]">
                    <Select value={selectedChatId || selectedTarget?.chat_id || ''} onValueChange={setSelectedChatId}>
                      <SelectTrigger>
                        <SelectValue placeholder="选择飞书群聊" />
                      </SelectTrigger>
                      <SelectContent>
                        {chatOptions.map(chat => (
                          <SelectItem key={chat.chat_id} value={chat.chat_id}>
                            {chat.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Button variant="outline" disabled={busyAction === 'load-chats'} onClick={() => runAction('load-chats', loadChats, '群聊列表已刷新。')}>
                      <RefreshCcw className="w-4 h-4" />
                      刷新
                    </Button>
                  </div>
                  <label className="flex items-center gap-2 text-sm text-gray-300">
                    <input
                      type="checkbox"
                      checked={confirmTestGroup}
                      onChange={(event) => setConfirmTestGroup(event.target.checked)}
                      className="accent-brand-orange"
                    />
                    我确认这是非生产测试群
                  </label>
                  {selectedTarget && (
                    <div className="rounded border border-[#444444] bg-[#101010] p-3 text-xs text-gray-400">
                      <div className="font-medium text-gray-200">已选择：{selectedTarget.display_name || selectedTarget.chat_id}</div>
                      <div className="mt-1">机器人权限：读取群聊事件、回复消息、向该测试群发送验证消息。</div>
                      <div className="mt-1">可执行动作：刷新群聊、设为测试群、发送测试消息、断开机器人安装。</div>
                    </div>
                  )}
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="outline"
                      disabled={!selectedChatId || !confirmTestGroup || busyAction === 'select-chat'}
                      onClick={() => runAction('select-chat', handleSelectChat, '测试群已选择。')}
                    >
                      <ShieldCheck className="w-4 h-4" />
                      设为测试群
                    </Button>
                    <Button
                      variant="brand-primary"
                      disabled={!selectedTarget || !confirmTestGroup || busyAction === 'test-message'}
                      onClick={() => runAction('test-message', () => testMessage(selectedTarget!.id, 'Byaan 飞书连接测试消息。'), 'Test message sent.')}
                    >
                      {busyAction === 'test-message' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                      发送测试
                    </Button>
                  </div>
                </>
              )}
            </section>

            {canConfigureApp ? (
              <section className="rounded-lg border border-[#444444] bg-[#151515] p-4 space-y-4">
                <button
                  type="button"
                  onClick={() => setShowAdvanced(value => !value)}
                  className="flex w-full items-center justify-between text-left text-sm font-semibold text-white"
                >
                  <span className="inline-flex items-center gap-2"><Settings2 className="w-4 h-4 text-brand-orange" /> 管理员高级配置</span>
                  <span className="text-xs text-gray-400">{showAdvanced ? 'Hide' : 'Show'}</span>
                </button>
                {showAdvanced && (
                  <div className="space-y-4 border-t border-[#333333] pt-4">
                    <div className="rounded border border-[#444444] bg-[#101010] p-3 text-xs text-gray-400">
                      App Secret 只会发送到服务端加密保存，API 响应不会回显。
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <Field label="App ID" value={appId} onChange={setAppId} placeholder="cli_xxx" />
                      <Field label="App Secret" value={appSecret} onChange={setAppSecret} type="password" placeholder={installation ? '留空表示沿用已保存密钥' : 'App Secret'} />
                      <div className="space-y-2">
                        <Label>连接模式</Label>
                        <Select value={connectionMode} onValueChange={(value) => setConnectionMode(value as 'websocket' | 'webhook')}>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="websocket">WebSocket 长连接</SelectItem>
                            <SelectItem value="webhook">Webhook</SelectItem>
                          </SelectContent>
                        </Select>
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
                    <Button
                      variant="brand-primary"
                      disabled={!appId.trim() || (!installation && !appSecret) || saving || busyAction === 'configure'}
                      onClick={handleConfigure}
                    >
                      {busyAction === 'configure' ? <Loader2 className="w-4 h-4 animate-spin" /> : <PlugZap className="w-4 h-4" />}
                      验证并保存
                    </Button>
                  </div>
                )}
              </section>
            ) : (
              <section className="rounded-lg border border-[#444444] bg-[#151515] p-4 text-sm text-gray-300">
                企业自建应用配置仅管理员可见。请联系管理员完成飞书 bot 安装。
              </section>
            )}

            <section className="rounded-lg border border-red-900/40 bg-red-950/10 p-4 space-y-3">
              <h3 className="text-sm font-semibold text-red-300">断开</h3>
              <p className="text-xs text-gray-400">断开会停用当前 Feishu installation，但不会删除历史 Notebook 或事件记录。</p>
              <Button variant="destructive" disabled={!installation || saving} onClick={() => runAction('disconnect', disconnect, 'Feishu integration disconnected.')}>
                <Trash2 className="w-4 h-4" />
                断开飞书
              </Button>
            </section>

            {(statusMessage || error) && (
              <div className="rounded border border-[#444444] bg-[#111] px-3 py-2 text-sm text-gray-300">
                {statusMessage || error}
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

function StatusRow({ label, value }: { label: string; value: string }) {
  return <div><span className="text-gray-500">{label}:</span> {value}</div>
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  type = 'text',
}: {
  label: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
  type?: string
}) {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <Input
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
      />
    </div>
  )
}
