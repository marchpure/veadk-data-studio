import { useEffect, useMemo, useState } from 'react'
import { CheckCircle2, Copy, Loader2, RefreshCcw, Settings2, ShieldCheck, XCircle } from 'lucide-react'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Switch } from '../ui/switch'
import { ApiService, type FeishuAdminConfigStatus, type FeishuAdminConfigValidation } from '@/services/api'
import { useStore } from '@/stores/useStore'

const requiredScopes = [
  'drive:drive:readonly',
  'docs:doc:readonly',
  'wiki:wiki:readonly',
  'sheets:spreadsheet:readonly',
  'bitable:app:readonly',
]

export function FeishuAdminSettings({ compact = false }: { compact?: boolean }) {
  const activeTenant = useStore(state => state.getActiveTenant())
  const canConfigureApp = activeTenant ? ['owner', 'admin'].includes(activeTenant.role) : true
  const [status, setStatus] = useState<FeishuAdminConfigStatus | null>(null)
  const [validation, setValidation] = useState<FeishuAdminConfigValidation | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [validating, setValidating] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [useCustomApp, setUseCustomApp] = useState(false)
  const [form, setForm] = useState({
    appId: '',
    appSecret: '',
    redirectUri: '',
    scopes: requiredScopes.join('\n'),
  })

  const modeLabel = status?.mode === 'hosted'
    ? 'Byaan 托管应用'
    : status?.mode === 'self_built'
      ? '企业自建应用'
      : '未配置'

  const generatedRedirectUri = status?.generated_redirect_uri || status?.redirect_uri || ''
  const selectedScopes = useMemo(
    () => form.scopes.split(/\s+/).map(item => item.trim()).filter(Boolean),
    [form.scopes],
  )

  const load = async () => {
    setLoading(true)
    setMessage(null)
    try {
      const next = await ApiService.getFeishuAdminConfig()
      setStatus(next)
      setUseCustomApp(next.mode === 'self_built')
      setForm({
        appId: next.app_id || '',
        appSecret: '',
        redirectUri: next.redirect_uri || next.generated_redirect_uri || '',
        scopes: (next.scopes?.length ? next.scopes : next.required_scopes || requiredScopes).join('\n'),
      })
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '无法读取飞书配置。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const copyRedirectUri = async () => {
    if (!generatedRedirectUri) return
    await navigator.clipboard?.writeText(generatedRedirectUri)
    setMessage('回调地址已复制。')
  }

  const saveCustomApp = async () => {
    setSaving(true)
    setMessage(null)
    try {
      const next = await ApiService.saveFeishuAdminConfig({
        app_id: form.appId.trim(),
        app_secret: form.appSecret,
        redirect_uri: form.redirectUri.trim() || generatedRedirectUri,
        scopes: selectedScopes.length ? selectedScopes : requiredScopes,
      })
      setStatus(next)
      setForm(prev => ({ ...prev, appSecret: '' }))
      setMessage('企业自建应用配置已保存；App Secret 不会回显。')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '保存飞书配置失败。')
    } finally {
      setSaving(false)
    }
  }

  const validate = async () => {
    setValidating(true)
    setMessage(null)
    try {
      setValidation(await ApiService.validateFeishuAdminConfig())
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '验证飞书配置失败。')
    } finally {
      setValidating(false)
    }
  }

  if (!canConfigureApp) {
    return (
      <section className="rounded-lg border border-[#444444] bg-[#151515] p-4 text-sm text-gray-300">
        企业自建应用配置仅租户管理员可见。普通成员可直接发起飞书授权或使用已配置的协作机器人。
      </section>
    )
  }

  if (loading) {
    return (
      <section className="rounded-lg border border-[#444444] bg-[#151515] p-4 text-sm text-gray-300">
        <Loader2 className="mr-2 inline h-4 w-4 animate-spin text-brand-orange" />
        正在读取飞书集成配置...
      </section>
    )
  }

  return (
    <section className={`rounded-lg border border-[#444444] bg-[#151515] ${compact ? 'p-4' : 'p-5'} text-white`}>
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="flex items-center gap-2 text-base font-semibold">
            <Settings2 className="h-5 w-5 text-brand-orange" />
            飞书应用配置
          </h2>
          <p className="mt-1 text-sm text-gray-400">默认使用 Byaan 托管应用；企业自建应用仅管理员配置，App Secret 加密保存且不可回显。</p>
        </div>
        <span className="rounded border border-[#555555] bg-[#101010] px-2 py-1 text-xs text-gray-300">{modeLabel}</span>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 text-sm md:grid-cols-3">
        <StatusPill label="托管应用" ok={status?.mode === 'hosted' || status?.configured === true} />
        <StatusPill label="Secret 已配置" ok={!!status?.secret_configured} />
        <StatusPill label="权限完整" ok={(status?.missing_scopes || []).length === 0} />
      </div>

      <div className="mt-4 rounded border border-[#444444] bg-[#101010] p-3">
        <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <div className="min-w-0">
            <div className="text-xs uppercase text-gray-500">系统生成回调地址</div>
            <div className="mt-1 truncate font-mono text-xs text-gray-300">{generatedRedirectUri || '未生成'}</div>
          </div>
          <Button variant="outline" size="sm" onClick={copyRedirectUri} disabled={!generatedRedirectUri} className="border-[#555555] text-white hover:bg-[#333333]">
            <Copy className="h-4 w-4" />
            复制
          </Button>
        </div>
      </div>

      <label className="mt-4 flex items-center justify-between gap-3 rounded border border-[#444444] bg-[#101010] p-3 text-sm">
        <span>
          <span className="block font-medium text-white">使用企业自建应用</span>
          <span className="text-gray-400">Self-hosted/BYOC 高级模式，保留现有自建应用能力。</span>
        </span>
        <Switch checked={useCustomApp} onCheckedChange={setUseCustomApp} />
      </label>

      {useCustomApp && (
        <div className="mt-4 space-y-4 border-t border-[#333333] pt-4">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <Field label="App ID" value={form.appId} onChange={value => setForm(prev => ({ ...prev, appId: value }))} placeholder="cli_xxx" />
            <Field label="App Secret" value={form.appSecret} onChange={value => setForm(prev => ({ ...prev, appSecret: value }))} placeholder={status?.secret_configured ? '输入新密钥后保存；保存后不可回显' : 'App Secret'} type="password" />
          </div>
          <Field label="回调地址" value={form.redirectUri} onChange={value => setForm(prev => ({ ...prev, redirectUri: value }))} placeholder={generatedRedirectUri} />
          <div>
            <Label className="text-white">权限 scopes</Label>
            <textarea
              value={form.scopes}
              onChange={event => setForm(prev => ({ ...prev, scopes: event.target.value }))}
              rows={5}
              className="mt-1 w-full rounded-md border border-[#555555] bg-[#101010] px-3 py-2 font-mono text-xs text-white outline-none focus-visible:ring-1 focus-visible:ring-brand-orange"
            />
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              onClick={saveCustomApp}
              disabled={saving || !form.appId.trim() || (!status?.secret_configured && !form.appSecret)}
              className="bg-brand-orange hover:bg-brand-orange/90"
            >
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
              验证并保存
            </Button>
            <Button variant="outline" onClick={validate} disabled={validating} className="border-[#555555] text-white hover:bg-[#333333]">
              {validating ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCcw className="h-4 w-4" />}
              验证配置
            </Button>
          </div>
        </div>
      )}

      {!useCustomApp && (
        <div className="mt-4 flex flex-wrap gap-2">
          <Button variant="outline" onClick={validate} disabled={validating} className="border-[#555555] text-white hover:bg-[#333333]">
            {validating ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCcw className="h-4 w-4" />}
            验证托管应用状态
          </Button>
        </div>
      )}

      {validation && (
        <div className="mt-4 space-y-2">
          {Object.entries(validation.checks).map(([key, check]) => (
            <div key={key} className="flex items-start gap-2 rounded border border-[#333333] bg-[#101010] px-3 py-2 text-sm">
              {check.ok ? <CheckCircle2 className="mt-0.5 h-4 w-4 flex-shrink-0 text-green-400" /> : <XCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-300" />}
              <div>
                <div className="font-medium text-white">{validationLabel(key)}</div>
                <div className="text-xs text-gray-400">{check.message}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {message && <div className="mt-4 rounded border border-[#444444] bg-[#101010] px-3 py-2 text-sm text-gray-300">{message}</div>}
    </section>
  )
}

function StatusPill({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div className={`rounded border px-3 py-2 ${ok ? 'border-green-800/60 bg-green-900/10 text-green-300' : 'border-[#444444] bg-[#101010] text-gray-400'}`}>
      <span className="mr-2">{ok ? '●' : '○'}</span>
      {label}
    </div>
  )
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
    <div>
      <Label className="text-white">{label}</Label>
      <Input
        type={type}
        value={value}
        onChange={event => onChange(event.target.value)}
        placeholder={placeholder}
        className="mt-1 border-[#555555] bg-[#101010] text-white placeholder:text-gray-600"
      />
    </div>
  )
}

function validationLabel(key: string) {
  switch (key) {
    case 'configured':
      return '应用配置'
    case 'secret':
      return '密钥'
    case 'scopes':
      return '权限范围'
    case 'redirect_uri':
      return '回调地址'
    default:
      return key
  }
}
