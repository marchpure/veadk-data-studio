import { useEffect, useState } from 'react'
import { Bot, CheckCircle2, Loader2, PlugZap, Power, RefreshCcw, Send, Trash2 } from 'lucide-react'
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
  } = useFeishuIntegration(open)
  const { data: llmConnections = [] } = useLLMConnections()

  const [appId, setAppId] = useState('')
  const [appSecret, setAppSecret] = useState('')
  const [connectionMode, setConnectionMode] = useState<'websocket' | 'webhook'>('websocket')
  const [llmConnectionId, setLlmConnectionId] = useState<string>('')
  const [chatId, setChatId] = useState('')
  const [rootId, setRootId] = useState('')
  const [statusMessage, setStatusMessage] = useState<string | null>(null)
  const [busyAction, setBusyAction] = useState<string | null>(null)

  useEffect(() => {
    if (installation) {
      setAppId(installation.app_id || '')
      setConnectionMode(installation.connection_mode === 'webhook' ? 'webhook' : 'websocket')
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
        connection_mode: connectionMode,
        default_llm_connection_id: llmConnectionId || null,
      }),
      'Feishu credentials validated and saved.'
    )
    setAppSecret('')
  }

  const healthColor = installation?.health_status === 'connected' || installation?.health_status === 'configured'
    ? 'text-green-400'
    : installation?.health_status === 'failed'
      ? 'text-red-400'
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
            配置飞书自建应用长连接。WebSocket 模式不需要公网 URL；Webhook 可在后续生产部署启用。
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
                {isConnected && (
                  <span className="inline-flex items-center gap-1 text-xs text-green-400">
                    <CheckCircle2 className="w-4 h-4" />
                    Configured
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
                  <Label>连接模式</Label>
                  <Select value={connectionMode} onValueChange={(value) => setConnectionMode(value as 'websocket' | 'webhook')}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="websocket">WebSocket 长连接（推荐）</SelectItem>
                      <SelectItem value="webhook">Webhook（后续生产部署）</SelectItem>
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
                <div><span className="text-gray-500">Mode:</span> {installation?.connection_mode || connectionMode}</div>
                <div><span className="text-gray-500">Health:</span> <span className={healthColor}>{installation?.health_status || 'not_configured'}</span></div>
                <div><span className="text-gray-500">Last connected:</span> {installation?.last_connected_at || '—'}</div>
                <div><span className="text-gray-500">Last event:</span> {installation?.last_event_at || '—'}</div>
              </div>
              {installation?.health_error && <p className="text-sm text-red-400">{installation.health_error}</p>}
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" disabled={!installation || busyAction === 'start'} onClick={() => runAction('start', start, 'WebSocket connect requested.')}>
                  <Power className="w-4 h-4" />
                  启动长连接
                </Button>
                <Button variant="outline" disabled={!installation || busyAction === 'stop'} onClick={() => runAction('stop', stop, 'WebSocket disconnected.')}>
                  停止长连接
                </Button>
              </div>
            </section>

            <section className="rounded-lg border border-gray-700 bg-[#151515] p-4 space-y-4">
              <div>
                <h3 className="text-sm font-semibold text-white">发送测试消息</h3>
                <p className="text-xs text-gray-400 mt-1">需要 Bot 已加入目标群聊；chat_id 可从飞书事件或 OpenAPI 获取。</p>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>chat_id</Label>
                  <Input value={chatId} onChange={(event) => setChatId(event.target.value)} placeholder="oc_xxx" />
                </div>
                <div className="space-y-2">
                  <Label>root_id（可选）</Label>
                  <Input value={rootId} onChange={(event) => setRootId(event.target.value)} placeholder="om_xxx" />
                </div>
              </div>
              <Button
                variant="outline"
                disabled={!installation || !chatId.trim() || busyAction === 'test-message'}
                onClick={() => runAction('test-message', () => testMessage(chatId.trim(), 'Byaan 飞书连接测试消息。', rootId.trim() || null), 'Test message sent.')}
              >
                <Send className="w-4 h-4" />
                发送测试
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
