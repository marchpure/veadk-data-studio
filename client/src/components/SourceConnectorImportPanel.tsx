import { useEffect, useMemo, useState } from 'react'
import QRCode from 'qrcode'
import { AlertCircle, CheckCircle2, ChevronRight, Copy, Database, FileText, Folder, HardDrive, Loader2, QrCode, Search, ShieldCheck } from 'lucide-react'
import { Button } from './ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from './ui/dialog'
import { Input } from './ui/input'
import { Label } from './ui/label'
import {
  useCreateSourceConnection,
  useDeleteSourceConnection,
  useFeishuStatus,
  useImportSourceResources,
  useListSourceConnectionResources,
  useLocateSourceConnectionResource,
  useFeishuOAuthResult,
  useSourceResourceProcessing,
  useSourceConnections,
  useStartFeishuOAuth,
} from '../hooks/useDBConnections'
import type {
  ConnectorDefinition,
  SourceResourceImportResult,
  SourceResourceProcessing,
  SourceResourceImportSelection,
  SourceResourcePickerItem,
  SourceResourcePickerType,
  SourceResourceType,
} from '../services/api'

type ProviderId = 'feishu' | 'volcengine_tos'

interface SourceConnectorImportPanelProps {
  provider: ProviderId
  definition?: ConnectorDefinition
  disabled?: boolean
  onImported?: () => void
}

const feishuScopes = [
  { id: 'recent', label: 'Recent' },
  { id: 'drive', label: 'Drive' },
  { id: 'wiki', label: 'Wiki' },
  { id: 'search', label: 'Search' },
]

const tosScopes = [
  { id: 'bucket', label: 'Buckets' },
  { id: 'children', label: 'Objects' },
]

const feishuTypes: Array<{ value: string; label: string }> = [
  { value: '', label: 'All supported' },
  { value: 'feishu_doc', label: 'Docs' },
  { value: 'feishu_wiki', label: 'Wiki' },
  { value: 'feishu_sheet', label: 'Sheets' },
  { value: 'feishu_base', label: 'Base' },
]

const tosTypes: Array<{ value: string; label: string }> = [
  { value: '', label: 'All objects' },
  { value: 'tos_prefix', label: 'Prefixes' },
  { value: 'tos_object', label: 'Objects' },
]

const readinessGateSummary = (definition?: ConnectorDefinition): string | null => {
  if (!definition?.readiness_gates?.length) return null
  const passed = definition.readiness_gates.filter(gate => gate.status === 'passed').length
  return `${passed}/${definition.readiness_gates.length} gates`
}

const missingReadinessGates = (definition?: ConnectorDefinition) =>
  definition?.readiness_gates?.filter(gate => gate.status !== 'passed') || []

const isSelectable = (item: SourceResourcePickerItem) =>
  item.already_added ? false : item.resource_type !== 'feishu_folder'

const isImportableResourceType = (type: SourceResourcePickerType): type is SourceResourceType =>
  type !== 'feishu_folder'

const isImportablePickerItem = (
  item: SourceResourcePickerItem,
): item is SourceResourcePickerItem & { resource_type: SourceResourceType } =>
  isImportableResourceType(item.resource_type)

const itemKey = (item: SourceResourcePickerItem) => `${item.resource_type}:${item.external_id}`

const providerLabel = (provider: ProviderId) => provider === 'feishu' ? 'Feishu' : 'Volcengine TOS'

const wikiBrowseToken = (item: SourceResourcePickerItem) => {
  const spaceId = item.metadata?.space_id
  if (typeof spaceId === 'string' && spaceId) {
    return item.resource_type === 'feishu_folder'
      ? spaceId
      : `${spaceId}:${item.external_id}`
  }
  return item.external_id
}

const resourceLabel = (type: SourceResourceType | string) => {
  switch (type) {
    case 'feishu_doc':
      return 'Doc'
    case 'feishu_wiki':
      return 'Wiki'
    case 'feishu_sheet':
      return 'Sheet'
    case 'feishu_base':
      return 'Base'
    case 'tos_bucket':
      return 'Bucket'
    case 'tos_prefix':
      return 'Prefix'
    case 'tos_object':
      return 'Object'
    default:
      return type
  }
}

const processingSteps = [
  { id: 'capture', label: 'Capture' },
  { id: 'parse', label: 'Parse' },
  { id: 'detect', label: 'Detect tables' },
  { id: 'normalize', label: 'Normalize dataset' },
  { id: 'index', label: 'Index context' },
  { id: 'suggest', label: 'Generate semantic suggestions' },
  { id: 'ready', label: 'Ready' },
] as const

const processingProgressIndex = (processing: SourceResourceProcessing | undefined, result: SourceResourceImportResult) => {
  if (result.status === 'needs_confirmation' || processing?.stage === 'needs_confirmation') return -1
  if (result.status !== 'ready' || processing?.stage === 'failed') return -1
  if (processing?.stage === 'waiting_for_connector') return 0
  if (processing?.stage === 'captured') return 1
  if (processing?.stage === 'indexed') return processingSteps.length - 1
  if (result.resource.projected_dataset_id) return 5
  if (result.resource.latest_snapshot_id) return 4
  return 1
}

const processingTone = (processing: SourceResourceProcessing | undefined, result: SourceResourceImportResult) => {
  if (result.status === 'needs_confirmation' || processing?.stage === 'needs_confirmation') return 'needs_confirmation'
  if (result.status !== 'ready' || processing?.stage === 'failed') return 'failed'
  if (processing?.stage === 'indexed') return 'ready'
  return 'processing'
}

export function SourceConnectorImportPanel({
  provider,
  definition,
  disabled,
  onImported,
}: SourceConnectorImportPanelProps) {
  const [selectedConnectionId, setSelectedConnectionId] = useState<string>('')
  const [scope, setScope] = useState(provider === 'feishu' ? 'recent' : 'bucket')
  const [parentToken, setParentToken] = useState<string>('')
  const [breadcrumbs, setBreadcrumbs] = useState<Array<{ label: string; token: string }>>([])
  const [resourceType, setResourceType] = useState('')
  const [query, setQuery] = useState('')
  const [pageToken, setPageToken] = useState('')
  const [quickLocateUrl, setQuickLocateUrl] = useState('')
  const [quickLocateMessage, setQuickLocateMessage] = useState<string | null>(null)
  const [selectedItems, setSelectedItems] = useState<Record<string, SourceResourcePickerItem>>({})
  const [importResults, setImportResults] = useState<SourceResourceImportResult[] | null>(null)
  const [waitingForFeishuOAuth, setWaitingForFeishuOAuth] = useState(false)
  const [authDialogOpen, setAuthDialogOpen] = useState(false)
  const [authUrl, setAuthUrl] = useState('')
  const [authState, setAuthState] = useState('')
  const [authMode, setAuthMode] = useState<'browser' | 'qr'>('browser')
  const [authMessage, setAuthMessage] = useState<string | null>(null)
  const [popupBlocked, setPopupBlocked] = useState(false)
  const [tosForm, setTosForm] = useState({
    displayName: 'Volcengine TOS',
    endpoint: '',
    region: '',
    accessKeyId: '',
    secretAccessKey: '',
    sessionToken: '',
    defaultBucket: '',
    defaultPrefix: '',
    verifySsl: true,
  })

  const feishuStatus = useFeishuStatus()
  const sourceConnections = useSourceConnections(provider)
  const startFeishuOAuth = useStartFeishuOAuth()
  const pollFeishuOAuth = useFeishuOAuthResult()
  const createSourceConnection = useCreateSourceConnection()
  const importSourceResources = useImportSourceResources()
  const locateSourceResource = useLocateSourceConnectionResource()
  const deleteSourceConnection = useDeleteSourceConnection()

  const connections = useMemo(
    () => (sourceConnections.data?.items || []).filter(item => item.status !== 'disconnected'),
    [sourceConnections.data?.items],
  )
  const activeConnection = useMemo(() => {
    if (provider === 'feishu' && feishuStatus.data?.connection) {
      return feishuStatus.data.connection
    }
    return connections.find(item => item.id === selectedConnectionId) || connections[0] || null
  }, [connections, feishuStatus.data?.connection, provider, selectedConnectionId])

  useEffect(() => {
    if (!selectedConnectionId && connections.length > 0) {
      setSelectedConnectionId(connections[0].id)
    }
  }, [connections, selectedConnectionId])

  useEffect(() => {
    setScope(provider === 'feishu' ? 'recent' : 'bucket')
    setParentToken('')
    setBreadcrumbs([])
    setResourceType('')
    setQuery('')
    setPageToken('')
    setQuickLocateUrl('')
    setQuickLocateMessage(null)
    setSelectedItems({})
    setImportResults(null)
  }, [provider])

  const resources = useListSourceConnectionResources({
    connectionId: activeConnection?.id,
    provider,
    scope,
    parent_token: parentToken || undefined,
    resource_type: resourceType || undefined,
    query: query.trim() || undefined,
    page_token: pageToken || undefined,
    page_size: 50,
  })

  const connected = !!activeConnection && activeConnection.status === 'connected'
  const requiresReauth = !!activeConnection && activeConnection.status === 'reauthorization_required'
  const resourceErrorCode = (resources.error as (Error & { code?: string }) | null)?.code
  const resourceRequiresReauth = provider === 'feishu' && resourceErrorCode === 'reauthorization_required'
  const selectedList = Object.values(selectedItems)
  const supportedTypes = definition?.supported_resource_types || []
  const scopeTabs = provider === 'feishu' ? feishuScopes : tosScopes
  const typeOptions = provider === 'feishu' ? feishuTypes : tosTypes
  const feishuProductStatus = provider === 'feishu'
    ? feishuStatus.data?.status || (connected ? 'connected' : requiresReauth ? 'needs_reauth' : 'ready_to_authorize')
    : activeConnection?.status || 'pending'
  const feishuStatusCopy = feishuStateCopy(feishuProductStatus)

  const handleStartFeishuOAuth = async () => {
    const result = await startFeishuOAuth.mutateAsync()
    setAuthUrl(result.authorization_url)
    setAuthState(result.state)
    setAuthMessage(null)
    setPopupBlocked(false)
    setWaitingForFeishuOAuth(true)
    const popup = window.open(result.authorization_url, 'byaan-feishu-oauth', 'width=720,height=760')
    if (!popup) {
      setPopupBlocked(true)
      setAuthMessage(feishuStateCopy('popup_blocked').description)
    }
  }

  const beginFeishuAuthorization = async (mode: 'browser' | 'qr' = 'browser') => {
    setAuthMode(mode)
    setAuthDialogOpen(true)
    await handleStartFeishuOAuth()
  }

  const reopenAuthorization = () => {
    if (!authUrl) return
    const popup = window.open(authUrl, 'byaan-feishu-oauth', 'width=720,height=760')
    if (!popup) setPopupBlocked(true)
  }

  const copyAuthorizationUrl = async () => {
    if (!authUrl) return
    await navigator.clipboard?.writeText(authUrl)
    setAuthMessage('授权链接已复制。')
  }

  useEffect(() => {
    if (provider !== 'feishu' || !waitingForFeishuOAuth) return
    let stopped = false
    let attempts = 0
    const timer = window.setInterval(() => {
      attempts += 1
      const poll = authState
        ? pollFeishuOAuth.mutateAsync(authState).catch(() => null)
        : Promise.resolve(null)
      poll.then(result => {
        if (stopped || !result) return
        if (result.status === 'connected') {
          setWaitingForFeishuOAuth(false)
          setAuthDialogOpen(false)
          setAuthMessage(null)
          feishuStatus.refetch()
          sourceConnections.refetch()
          return
        }
        if (result.status && result.status !== 'authorizing') {
          setWaitingForFeishuOAuth(false)
          const copy = feishuStateCopy(result.status)
          setAuthMessage(result.error?.message || `${copy.description} ${copy.action}`)
        }
      })
      feishuStatus.refetch().then(() => {
        if (stopped) return
        if (attempts >= 60) {
          setWaitingForFeishuOAuth(false)
          const copy = feishuStateCopy('callback_unreachable')
          setAuthMessage(`${copy.description} ${copy.action}`)
        }
      })
    }, 2000)
    return () => {
      stopped = true
      window.clearInterval(timer)
    }
  }, [authState, feishuStatus, pollFeishuOAuth, provider, sourceConnections, waitingForFeishuOAuth])

  useEffect(() => {
    if (provider !== 'feishu') return
    const onMessage = (event: MessageEvent) => {
      const data = event.data
      if (!data || data.type !== 'byaan:feishu-oauth') return
      if (authState && data.state !== authState) return
      if (data.status === 'connected') {
        setWaitingForFeishuOAuth(false)
        setAuthDialogOpen(false)
        feishuStatus.refetch()
        sourceConnections.refetch()
      } else {
        setWaitingForFeishuOAuth(false)
        const copy = feishuStateCopy(data.status)
        setAuthMessage(data.message || `${copy.description} ${copy.action}`)
      }
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [authState, feishuStatus, provider, sourceConnections])

  const handleCreateTosConnection = async () => {
    const connection = await createSourceConnection.mutateAsync({
      provider: 'volcengine_tos',
      auth_mode: 'access_key',
      display_name: tosForm.displayName.trim() || 'Volcengine TOS',
      credentials: {
        endpoint: tosForm.endpoint.trim(),
        region: tosForm.region.trim(),
        access_key_id: tosForm.accessKeyId.trim(),
        secret_access_key: tosForm.secretAccessKey,
        session_token: tosForm.sessionToken.trim() || undefined,
        default_bucket: tosForm.defaultBucket.trim() || undefined,
        default_prefix: tosForm.defaultPrefix.trim() || undefined,
        verify_ssl: tosForm.verifySsl,
      },
      test_connection: true,
    })
    setSelectedConnectionId(connection.id)
  }

  const handleOpenFolder = (item: SourceResourcePickerItem) => {
    if (provider === 'feishu' && (item.resource_type === 'feishu_wiki' || item.metadata?.type === 'wiki_space')) {
      setScope('wiki')
      const token = wikiBrowseToken(item)
      setParentToken(token)
      setBreadcrumbs(prev => [...prev, { label: item.name, token }])
      setPageToken('')
      return
    }
    if (provider === 'feishu' && item.is_folder) {
      setScope('drive')
      setParentToken(item.external_id)
      setBreadcrumbs(prev => [...prev, { label: item.name, token: item.external_id }])
      setPageToken('')
      return
    }
    if (provider === 'volcengine_tos' && item.has_children) {
      setScope('children')
      setParentToken(item.external_id)
      setBreadcrumbs(prev => [...prev, { label: item.name, token: item.external_id }])
      setPageToken('')
    }
  }

  const toggleItem = (item: SourceResourcePickerItem) => {
    if (!isSelectable(item)) return
    const key = itemKey(item)
    setSelectedItems(prev => {
      const next = { ...prev }
      if (next[key]) delete next[key]
      else next[key] = item
      return next
    })
  }

  const addSelectedItem = (item: SourceResourcePickerItem) => {
    if (!isSelectable(item)) return
    setSelectedItems(prev => ({ ...prev, [itemKey(item)]: item }))
  }

  const handleQuickLocate = async () => {
    if (provider !== 'feishu' || !activeConnection || !quickLocateUrl.trim()) return
    const result = await locateSourceResource.mutateAsync({
      connectionId: activeConnection.id,
      url: quickLocateUrl.trim(),
    })
    if (result.connection_status !== 'connected') {
      setQuickLocateMessage(`Connection status is ${result.connection_status}; reconnect before locating resources.`)
      return
    }
    if (!result.item) {
      setQuickLocateMessage('No resource matched this link.')
      return
    }
    addSelectedItem(result.item)
    setQuickLocateMessage(
      result.item.already_added
        ? `${result.item.name} is already added.`
        : `${result.item.name} located and selected. Import still uses the same picker sync path.`,
    )
    setQuickLocateUrl('')
  }

  const clearNavigation = () => {
    setParentToken('')
    setBreadcrumbs([])
    setPageToken('')
  }

  const handleImport = async () => {
    if (!activeConnection || selectedList.length === 0) return
    const selections: SourceResourceImportSelection[] = selectedList
      .filter(isImportablePickerItem)
      .map(item => ({
        external_id: item.external_id,
        resource_type: item.resource_type,
        name: item.name,
        source_url: item.source_url,
        parent_external_id: item.parent_external_id,
        selection_config: {
          imported_from: 'datasources_connector_picker',
        },
        metadata: item.metadata,
      }))
    if (selections.length === 0) return
    const response = await importSourceResources.mutateAsync({
      connection_id: activeConnection.id,
      selections,
      sync_mode: 'manual',
      schedule: null,
    })
    setImportResults(response.results)
    setSelectedItems({})
    resources.refetch()
    onImported?.()
  }

  const handleDisconnectFeishu = async () => {
    if (!activeConnection) return
    await deleteSourceConnection.mutateAsync(activeConnection.id)
    setSelectedConnectionId('')
    setSelectedItems({})
    setImportResults(null)
    await feishuStatus.refetch()
    await sourceConnections.refetch()
  }

  if (definition?.availability === 'planned') {
    return (
      <div className="rounded-lg border border-[#444444] bg-[#1a1a1a] p-5">
        <p className="text-sm font-medium text-white">{definition.display_name}</p>
        <p className="mt-2 text-sm text-gray-400">
          This connector is listed in the catalog as Planned. It is not exposed as a working connector until an adapter and contract tests exist.
        </p>
        {definition.limitations?.length > 0 && (
          <p className="mt-3 rounded border border-amber-700/40 bg-amber-950/20 px-3 py-2 text-xs text-amber-100/75">
            {definition.limitations[0]}
          </p>
        )}
        <div className="mt-3 flex flex-wrap gap-2 text-xs text-gray-400">
          <span className="rounded border border-[#444444] px-2 py-1">Status: {definition.status}</span>
          <span className="rounded border border-[#444444] px-2 py-1">Picker: {definition.resource_picker_type}</span>
          {readinessGateSummary(definition) && (
            <span className="rounded border border-[#444444] px-2 py-1">Readiness: {readinessGateSummary(definition)}</span>
          )}
        </div>
        {missingReadinessGates(definition).length > 0 && (
          <div className="mt-4">
            <div className="text-xs uppercase text-gray-500">Missing readiness gates</div>
            <ul className="mt-2 space-y-1 text-xs text-gray-400">
              {missingReadinessGates(definition).slice(0, 5).map(gate => (
                <li key={gate.key}>{gate.label}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    )
  }

  if (provider === 'feishu' && feishuStatus.isLoading) {
    return <LoadingBox label="Checking Feishu connector status..." />
  }

  if (provider === 'feishu' && !feishuStatus.data?.configured) {
    return (
      <div className="rounded-lg border border-amber-700/40 bg-amber-900/20 p-5 text-sm text-amber-100">
        <div className="flex items-start gap-3">
          <AlertCircle className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-300" />
          <div>
            <p className="font-medium">飞书集成尚未就绪</p>
            <p className="mt-1 text-amber-100/80">请管理员在「设置 → 集成 → 飞书」启用托管应用或配置企业自建应用。普通用户不需要填写 App ID、App Secret 或回调地址。</p>
          </div>
        </div>
      </div>
    )
  }

  if (!connected) {
    return (
      <>
        <div className="space-y-4">
          <div className="rounded-lg border border-[#444444] bg-[#1a1a1a] p-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-sm font-medium text-white">{definition?.display_name || providerLabel(provider)}</p>
                <p className="mt-1 text-sm text-gray-400">{definition?.description || 'Connect once, then browse and import resources repeatedly.'}</p>
              </div>
              <span className={`rounded px-2 py-1 text-xs ${feishuStatusCopy.badgeClass}`}>
                {provider === 'feishu' ? feishuStatusCopy.label : requiresReauth ? 'Reauthorization required' : 'Not connected'}
              </span>
            </div>
            {supportedTypes.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {supportedTypes.map(type => (
                  <span key={type} className="rounded bg-[#2a2a2a] px-2 py-1 text-xs text-gray-300">{resourceLabel(type)}</span>
                ))}
              </div>
            )}
          </div>

          {provider === 'feishu' ? (
            <div className="space-y-3">
            <div className="rounded-lg border border-[#444444] bg-[#151515] p-4">
              <div className="flex items-start gap-3">
                <ShieldCheck className="mt-0.5 h-5 w-5 flex-shrink-0 text-brand-orange" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-white">连接飞书</p>
                  <p className="mt-1 text-sm text-gray-400">授权后进入资源选择器。Byaan 只读取你选择导入的文档、Wiki、表格和多维表格。</p>
                  <div className="mt-3 flex flex-wrap gap-2 text-xs text-gray-400">
                    {(feishuStatus.data?.admin_config.required_scopes || []).map(scopeName => (
                      <span key={scopeName} className="rounded border border-[#444444] bg-[#1f1f1f] px-2 py-1">{scopeName}</span>
                    ))}
                  </div>
                </div>
              </div>
              <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2">
                <Button
                  onClick={() => beginFeishuAuthorization('browser')}
                  disabled={disabled || startFeishuOAuth.isPending || waitingForFeishuOAuth}
                  className="bg-brand-orange hover:bg-brand-orange/90"
                >
                  {startFeishuOAuth.isPending || (waitingForFeishuOAuth && authMode === 'browser') ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
                  在飞书中授权
                </Button>
                <Button
                  variant="outline"
                  onClick={() => beginFeishuAuthorization('qr')}
                  disabled={disabled || startFeishuOAuth.isPending || waitingForFeishuOAuth}
                  className="border-[#555555] text-white hover:bg-[#3a3a3a]"
                >
                  {waitingForFeishuOAuth && authMode === 'qr' ? <Loader2 className="h-4 w-4 animate-spin" /> : <QrCode className="h-4 w-4" />}
                  使用飞书扫码
                </Button>
              </div>
            </div>
            {waitingForFeishuOAuth && (
              <p className="text-xs text-gray-400">
                授权完成后本页面会自动刷新；如果回调窗口无法关闭，轮询也会接管状态。
              </p>
            )}
            {(feishuStatusCopy.description || feishuStatusCopy.action) && (
              <div className="rounded border border-[#444444] bg-[#151515] px-3 py-2 text-xs text-gray-300">
                {feishuStatusCopy.description}
                {feishuStatusCopy.action && <span className="ml-1 text-brand-orange">{feishuStatusCopy.action}</span>}
              </div>
            )}
            </div>
          ) : (
            <div className="space-y-4 rounded-lg border border-[#444444] bg-[#1a1a1a] p-4">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Connection name" value={tosForm.displayName} onChange={value => setTosForm(prev => ({ ...prev, displayName: value }))} disabled={disabled || createSourceConnection.isPending} />
              <Field label="Region" value={tosForm.region} onChange={value => setTosForm(prev => ({ ...prev, region: value }))} placeholder="cn-beijing" disabled={disabled || createSourceConnection.isPending} required />
            </div>
            <Field label="Endpoint" value={tosForm.endpoint} onChange={value => setTosForm(prev => ({ ...prev, endpoint: value }))} placeholder="https://tos-cn-beijing.volces.com" disabled={disabled || createSourceConnection.isPending} required />
            <div className="grid grid-cols-2 gap-3">
              <Field label="Access Key ID" value={tosForm.accessKeyId} onChange={value => setTosForm(prev => ({ ...prev, accessKeyId: value }))} disabled={disabled || createSourceConnection.isPending} required />
              <Field label="Secret Access Key" type="password" value={tosForm.secretAccessKey} onChange={value => setTosForm(prev => ({ ...prev, secretAccessKey: value }))} disabled={disabled || createSourceConnection.isPending} required />
            </div>
            <Field label="Session Token / STS" value={tosForm.sessionToken} onChange={value => setTosForm(prev => ({ ...prev, sessionToken: value }))} disabled={disabled || createSourceConnection.isPending} />
            <div className="grid grid-cols-2 gap-3">
              <Field label="Default bucket" value={tosForm.defaultBucket} onChange={value => setTosForm(prev => ({ ...prev, defaultBucket: value }))} disabled={disabled || createSourceConnection.isPending} />
              <Field label="Default prefix" value={tosForm.defaultPrefix} onChange={value => setTosForm(prev => ({ ...prev, defaultPrefix: value }))} disabled={disabled || createSourceConnection.isPending} />
            </div>
            <label className="flex items-center gap-2 text-sm text-gray-300">
              <input
                type="checkbox"
                checked={tosForm.verifySsl}
                onChange={event => setTosForm(prev => ({ ...prev, verifySsl: event.target.checked }))}
                className="accent-brand-orange"
              />
              Verify TLS certificates
            </label>
            <Button
              onClick={handleCreateTosConnection}
              disabled={
                disabled ||
                createSourceConnection.isPending ||
                !tosForm.endpoint.trim() ||
                !tosForm.region.trim() ||
                !tosForm.accessKeyId.trim() ||
                !tosForm.secretAccessKey
              }
              className="w-full bg-brand-orange hover:bg-brand-orange/90"
            >
              {createSourceConnection.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <HardDrive className="h-4 w-4" />}
              Test and connect TOS
            </Button>
            </div>
          )}
        </div>
        <FeishuAuthorizationDialog
          open={authDialogOpen}
          mode={authMode}
          authorizationUrl={authUrl}
          waiting={waitingForFeishuOAuth}
          popupBlocked={popupBlocked}
          message={authMessage}
          onOpenChange={setAuthDialogOpen}
          onReopen={reopenAuthorization}
          onCopy={copyAuthorizationUrl}
        />
      </>
    )
  }

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-green-700/40 bg-green-900/10 p-3 text-sm text-green-200">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-green-400" />
              <span>Connected: {activeConnection?.display_name}</span>
            </div>
            {provider === 'feishu' && (
              <div className="mt-2 grid grid-cols-1 gap-2 text-xs text-green-100/80 md:grid-cols-4">
                <span>授权身份：{activeConnection?.display_name || 'Feishu user'}</span>
                <span>已选资源：{resources.data?.items.filter(item => item.already_added).length ?? 0}</span>
                <span>最近同步：{importResults?.[0]?.resource?.updated_at || activeConnection?.updated_at || '-'}</span>
                <span>权限状态：{feishuStateCopy(feishuProductStatus).label}</span>
              </div>
            )}
          </div>
          {provider === 'feishu' && (
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                size="sm"
                onClick={() => beginFeishuAuthorization('browser')}
                disabled={disabled || startFeishuOAuth.isPending || waitingForFeishuOAuth}
                className="bg-brand-orange hover:bg-brand-orange/90"
              >
                {startFeishuOAuth.isPending || waitingForFeishuOAuth ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
                重新授权
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={handleDisconnectFeishu}
                disabled={deleteSourceConnection.isPending}
                className="border-red-800 text-red-300 hover:bg-red-900/20"
              >
                断开连接
              </Button>
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="col-span-2">
          <Label className="text-white">Search / prefix filter</Label>
          <div className="relative mt-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500" />
            <Input
              value={query}
              onChange={event => {
                setQuery(event.target.value)
                setPageToken('')
                if (provider === 'feishu' && event.target.value.trim()) setScope('search')
              }}
              placeholder={provider === 'feishu' ? 'Search docs, sheets, base...' : 'Filter by prefix'}
              className="bg-[#1a1a1a] border-[#555555] pl-9 text-white placeholder-[#888888]"
            />
          </div>
        </div>
        <div>
          <Label className="text-white">Type</Label>
          <select
            value={resourceType}
            onChange={event => {
              setResourceType(event.target.value)
              setPageToken('')
            }}
            className="mt-1 w-full rounded-md border border-[#555555] bg-[#1a1a1a] px-3 py-2 text-sm text-white"
          >
            {typeOptions.map(option => (
              <option key={option.value || 'all'} value={option.value}>{option.label}</option>
            ))}
          </select>
        </div>
      </div>

      {provider === 'feishu' && (
        <div className="rounded-lg border border-[#444444] bg-[#1a1a1a] p-3">
          <Label className="text-white">Quick locate by Feishu link</Label>
          <div className="mt-2 flex gap-2">
            <Input
              value={quickLocateUrl}
              onChange={event => {
                setQuickLocateUrl(event.target.value)
                setQuickLocateMessage(null)
              }}
              placeholder="Paste a Docx, Wiki, Sheet, or Base URL to locate it with current OAuth permissions"
              className="bg-[#101010] border-[#555555] text-white placeholder-[#888888]"
            />
            <Button
              type="button"
              variant="outline"
              onClick={handleQuickLocate}
              disabled={!quickLocateUrl.trim() || locateSourceResource.isPending || importSourceResources.isPending}
              className="border-[#555555] text-white hover:bg-[#3a3a3a]"
            >
              {locateSourceResource.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Locate
            </Button>
          </div>
          {quickLocateMessage && <p className="mt-2 text-xs text-gray-400">{quickLocateMessage}</p>}
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        {scopeTabs.map(tab => (
          <button
            key={tab.id}
            type="button"
            onClick={() => {
              setScope(tab.id)
              setPageToken('')
              if (tab.id === 'bucket' || tab.id === 'recent' || tab.id === 'drive' || tab.id === 'wiki') {
                clearNavigation()
              }
            }}
            className={`rounded px-3 py-1.5 text-xs transition ${scope === tab.id ? 'bg-brand-orange text-white' : 'bg-[#1a1a1a] text-gray-300 hover:bg-[#333333]'}`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {breadcrumbs.length > 0 && (
        <div className="flex flex-wrap items-center gap-1 rounded border border-[#444444] bg-[#1a1a1a] px-3 py-2 text-xs text-gray-300">
          <button type="button" onClick={clearNavigation} className="text-brand-orange hover:underline">Root</button>
          {breadcrumbs.map((crumb, index) => (
            <span key={`${crumb.token}:${index}`} className="flex items-center gap-1">
              <ChevronRight className="h-3 w-3 text-gray-500" />
              <button
                type="button"
                onClick={() => {
                  setParentToken(crumb.token)
                  setBreadcrumbs(breadcrumbs.slice(0, index + 1))
                  setPageToken('')
                }}
                className="hover:text-white"
              >
                {crumb.label}
              </button>
            </span>
          ))}
        </div>
      )}

      <div className="min-h-[260px] rounded-lg border border-[#444444] bg-[#1a1a1a]">
        {resources.isLoading ? (
          <LoadingBox label="Loading resources..." />
        ) : resourceRequiresReauth ? (
          <div className="p-5 text-sm text-amber-100">
            <div className="flex items-start gap-3">
              <AlertCircle className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-300" />
              <div>
                <p className="font-medium">当前飞书授权不包含云盘读取权限</p>
                <p className="mt-1 text-amber-100/75">管理员配置权限后，已有用户令牌不会自动升级。请重新授权并在飞书页面确认本次新增权限。</p>
                <Button
                  type="button"
                  size="sm"
                  onClick={() => beginFeishuAuthorization('browser')}
                  disabled={disabled || startFeishuOAuth.isPending || waitingForFeishuOAuth}
                  className="mt-3 bg-brand-orange hover:bg-brand-orange/90"
                >
                  {startFeishuOAuth.isPending || waitingForFeishuOAuth ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
                  重新授权飞书
                </Button>
              </div>
            </div>
          </div>
        ) : resources.error ? (
          <div className="p-5 text-sm text-red-200">
            <div className="flex items-start gap-2">
              <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-red-400" />
              <span>{resources.error.message}</span>
            </div>
          </div>
        ) : resources.data?.connection_status !== 'connected' ? (
          <div className="p-5 text-sm text-amber-200">
            Connection status is {resources.data?.connection_status || activeConnection?.status}. Refresh or reconnect before browsing resources.
          </div>
        ) : resources.data.items.length === 0 ? (
          <div className="p-8 text-center text-sm text-gray-400">No resources returned for this scope.</div>
        ) : (
          <div className="max-h-[310px] divide-y divide-[#333333] overflow-y-auto custom-scrollbar">
            {resources.data.items.map(item => {
              const selected = !!selectedItems[itemKey(item)]
              return (
                <div key={itemKey(item)} className={`flex items-center gap-3 px-3 py-2.5 ${selected ? 'bg-brand-orange/10' : ''}`}>
                  <input
                    type="checkbox"
                    checked={selected}
                    disabled={!isSelectable(item) || importSourceResources.isPending}
                    onChange={() => toggleItem(item)}
                    className="accent-brand-orange"
                  />
                  {item.has_children || item.is_folder ? <Folder className="h-4 w-4 flex-shrink-0 text-amber-300" /> : item.resource_type.startsWith('tos') ? <Database className="h-4 w-4 flex-shrink-0 text-cyan-300" /> : <FileText className="h-4 w-4 flex-shrink-0 text-brand-orange" />}
                  <button
                    type="button"
                    onClick={() => item.has_children || item.is_folder ? handleOpenFolder(item) : toggleItem(item)}
                    className="min-w-0 flex-1 text-left"
                  >
                    <div className="truncate text-sm text-white" title={item.name}>{item.name}</div>
                    <div className="flex flex-wrap items-center gap-2 text-xs text-gray-500">
                      <span>{resourceLabel(item.resource_type)}</span>
                      {item.metadata?.size != null && <span>{formatBytes(Number(item.metadata.size))}</span>}
                      {item.metadata?.last_modified && <span>{String(item.metadata.last_modified)}</span>}
                      {item.already_added && <span className="text-green-400">Already added</span>}
                    </div>
                  </button>
                  {(item.has_children || item.is_folder) && (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => handleOpenFolder(item)}
                      className="h-8 text-gray-300 hover:text-white"
                    >
                      Browse
                    </Button>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      <div className="flex items-center justify-between rounded border border-[#444444] bg-[#1a1a1a] px-3 py-2 text-sm">
        <span className="text-gray-300">
          {selectedList.length === 0 ? 'No resources selected' : `${selectedList.length} selected for immediate sync`}
        </span>
        <div className="flex items-center gap-2">
          {resources.data?.next_page_token && (
            <Button
              type="button"
              variant="outline"
              onClick={() => setPageToken(resources.data?.next_page_token || '')}
              className="border-[#555555] text-white hover:bg-[#3a3a3a]"
            >
              Load more
            </Button>
          )}
          {selectedList.length > 0 && (
            <Button type="button" variant="ghost" onClick={() => setSelectedItems({})} className="text-gray-400 hover:text-white">
              Clear
            </Button>
          )}
          <Button
            type="button"
            onClick={handleImport}
            disabled={selectedList.length === 0 || importSourceResources.isPending}
            className="bg-brand-orange hover:bg-brand-orange/90"
          >
            {importSourceResources.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Import and sync
          </Button>
        </div>
      </div>

      {importResults && (
        <div className="space-y-3 rounded-lg border border-[#444444] bg-[#1a1a1a] p-3">
          <div>
            <div className="text-sm font-medium text-white">Processing</div>
            <p className="mt-1 text-xs text-gray-400">Imported resources stay here until capture, parse, dataset projection, context indexing, semantic suggestions, and readiness are clear.</p>
          </div>
          {importResults.map(result => (
            <ImportProcessingCard key={`${result.selection.resource_type}:${result.selection.external_id}`} result={result} />
          ))}
        </div>
      )}
    </div>
  )
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  disabled,
  type = 'text',
  required,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
  disabled?: boolean
  type?: string
  required?: boolean
}) {
  return (
    <div>
      <Label className="text-white">
        {label} {required && <span className="text-red-400">*</span>}
      </Label>
      <Input
        type={type}
        value={value}
        onChange={event => onChange(event.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        className="mt-1 bg-[#1a1a1a] border-[#555555] text-white placeholder-[#888888]"
      />
    </div>
  )
}

function LoadingBox({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3 p-5 text-sm text-gray-300">
      <Loader2 className="h-4 w-4 animate-spin text-brand-orange" />
      {label}
    </div>
  )
}

function ImportProcessingCard({ result }: { result: SourceResourceImportResult }) {
  const resourceId = result.resource?.id
  const processingQuery = useSourceResourceProcessing(resourceId, Boolean(resourceId))
  const processing = processingQuery.data
  const progressIndex = processingProgressIndex(processing, result)
  const tone = processingTone(processing, result)
  const title = result.resource?.name || result.selection.name || result.selection.external_id
  const errorMessage = result.error?.message || processing?.last_error?.message
  const nextActions = processing?.next_actions || []

  return (
    <div className="rounded border border-[#333333] bg-[#242424] p-3">
      <div className="flex items-start gap-2">
        {tone === 'failed' ? (
          <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-red-400" />
        ) : tone === 'needs_confirmation' ? (
          <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-yellow-400" />
        ) : tone === 'ready' ? (
          <CheckCircle2 className="mt-0.5 h-4 w-4 flex-shrink-0 text-green-400" />
        ) : (
          <Loader2 className="mt-0.5 h-4 w-4 flex-shrink-0 animate-spin text-brand-orange" />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate text-sm font-medium text-white">{title}</span>
            <span className="rounded bg-[#1a1a1a] px-2 py-0.5 text-[10px] uppercase text-gray-400">
              {resourceLabel(result.selection.resource_type)}
            </span>
          </div>
          <div className={`mt-1 text-xs ${tone === 'failed' ? 'text-red-300' : tone === 'ready' ? 'text-green-300' : 'text-gray-300'}`}>
            {tone === 'failed'
              ? `${result.status}${errorMessage ? ` · ${errorMessage}` : ''}`
              : tone === 'needs_confirmation'
                ? processing?.message || errorMessage || 'Review and confirm this source before retrying sync.'
              : processing?.message || `Snapshot ${result.resource?.latest_snapshot_id || 'created'}${result.resource?.projected_dataset_id ? ` · dataset ${result.resource.projected_dataset_id}` : ''}`}
          </div>

          <div className="mt-3 grid grid-cols-7 gap-1">
            {processingSteps.map((step, index) => {
              const complete = tone !== 'failed' && tone !== 'needs_confirmation' && index <= progressIndex
              const current = tone === 'processing' && index === Math.max(progressIndex + 1, 0)
              return (
                <div key={step.id} className="min-w-0">
                  <div className={`h-1.5 rounded-full ${complete ? 'bg-green-500' : current ? 'bg-brand-orange' : tone === 'failed' && index === 0 ? 'bg-red-500' : tone === 'needs_confirmation' && index === 0 ? 'bg-yellow-400' : 'bg-[#444444]'}`} />
                  <div className={`mt-1 truncate text-[10px] ${complete ? 'text-green-300' : current ? 'text-brand-orange' : tone === 'needs_confirmation' && index === 0 ? 'text-yellow-300' : 'text-gray-500'}`} title={step.label}>
                    {step.label}
                  </div>
                </div>
              )
            })}
          </div>

          {(processingQuery.isLoading || processingQuery.isFetching) && tone !== 'failed' && (
            <div className="mt-2 text-[11px] text-gray-500">Refreshing processing state...</div>
          )}

          {nextActions.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {nextActions.slice(0, 3).map(action => (
                <span key={action} className="rounded border border-[#444444] px-2 py-1 text-[11px] text-gray-300">
                  {action}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function FeishuAuthorizationDialog({
  open,
  mode,
  authorizationUrl,
  waiting,
  popupBlocked,
  message,
  onOpenChange,
  onReopen,
  onCopy,
}: {
  open: boolean
  mode: 'browser' | 'qr'
  authorizationUrl: string
  waiting: boolean
  popupBlocked: boolean
  message: string | null
  onOpenChange: (open: boolean) => void
  onReopen: () => void
  onCopy: () => void
}) {
  const [qrDataUrl, setQrDataUrl] = useState('')

  useEffect(() => {
    let cancelled = false
    if (!authorizationUrl || mode !== 'qr') {
      setQrDataUrl('')
      return
    }
    QRCode.toDataURL(authorizationUrl, { width: 220, margin: 1, errorCorrectionLevel: 'M' })
      .then(value => {
        if (!cancelled) setQrDataUrl(value)
      })
      .catch(() => {
        if (!cancelled) setQrDataUrl('')
      })
    return () => {
      cancelled = true
    }
  }, [authorizationUrl, mode])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl border-[#555555] bg-[#1f1f1f] text-white">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {mode === 'qr' ? <QrCode className="h-5 w-5 text-brand-orange" /> : <ShieldCheck className="h-5 w-5 text-brand-orange" />}
            飞书授权
          </DialogTitle>
          <DialogDescription>授权窗口和二维码使用同一个 OAuth 链接。</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          {mode === 'qr' && (
            <div className="flex justify-center rounded-lg border border-[#444444] bg-white p-4">
              {qrDataUrl ? (
                <img src={qrDataUrl} alt="Feishu OAuth QR code" className="h-[220px] w-[220px]" />
              ) : (
                <div className="flex h-[220px] w-[220px] items-center justify-center text-sm text-gray-500">生成二维码中...</div>
              )}
            </div>
          )}
          <div className="rounded border border-[#444444] bg-[#151515] p-3 text-sm text-gray-300">
            {waiting ? '等待飞书回调。你可以在弹出的飞书页面完成授权，或扫码授权。' : '授权未在当前等待窗口内完成。'}
          </div>
          {popupBlocked && (
            <div className="rounded border border-amber-700/50 bg-amber-900/20 p-3 text-sm text-amber-100">
              浏览器拦截了授权窗口。请允许弹窗后重新打开，或复制链接到浏览器。
            </div>
          )}
          {message && <div className="rounded border border-[#444444] bg-[#101010] p-3 text-sm text-gray-300">{message}</div>}
          <div className="flex flex-wrap gap-2">
            <Button onClick={onReopen} disabled={!authorizationUrl} className="bg-brand-orange hover:bg-brand-orange/90">
              <ShieldCheck className="h-4 w-4" />
              重新打开授权页
            </Button>
            <Button variant="outline" onClick={onCopy} disabled={!authorizationUrl} className="border-[#555555] text-white hover:bg-[#3a3a3a]">
              <Copy className="h-4 w-4" />
              复制授权链接
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function formatBytes(value: number) {
  if (!Number.isFinite(value) || value < 0) return ''
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  if (value < 1024 * 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`
  return `${(value / (1024 * 1024 * 1024)).toFixed(1)} GB`
}

function feishuStateCopy(status: string) {
  switch (status) {
    case 'not_configured':
      return {
        label: 'Not configured',
        description: '飞书应用尚未配置。',
        action: '请管理员前往 Integrations 配置托管应用或企业自建应用。',
        badgeClass: 'bg-gray-500/20 text-gray-300',
      }
    case 'ready_to_authorize':
      return {
        label: 'Ready to authorize',
        description: '飞书应用已就绪，可以发起最小权限 OAuth 授权。',
        action: '点击“在飞书中授权”。',
        badgeClass: 'bg-brand-orange/20 text-brand-orange',
      }
    case 'authorizing':
      return {
        label: 'Authorizing',
        description: '正在等待飞书 OAuth 回调。',
        action: '完成弹窗授权或扫码授权。',
        badgeClass: 'bg-blue-500/20 text-blue-300',
      }
    case 'connected':
      return {
        label: 'Connected',
        description: '飞书账号已授权，可进入资源选择器。',
        action: '选择文档、Wiki、Sheet 或 Base 后导入。',
        badgeClass: 'bg-green-500/20 text-green-300',
      }
    case 'selecting_resources':
      return {
        label: 'Selecting resources',
        description: '正在选择可导入资源。',
        action: '勾选资源并点击导入。',
        badgeClass: 'bg-blue-500/20 text-blue-300',
      }
    case 'syncing':
      return {
        label: 'Syncing',
        description: '资源正在同步。',
        action: '稍后刷新同步状态。',
        badgeClass: 'bg-blue-500/20 text-blue-300',
      }
    case 'needs_reauth':
    case 'reauthorization_required':
      return {
        label: 'Needs reauth',
        description: '飞书 token 已失效或 refresh token 不可用。',
        action: '请重新授权。',
        badgeClass: 'bg-amber-500/20 text-amber-300',
      }
    case 'admin_approval_required':
      return {
        label: 'Admin approval required',
        description: '飞书企业可能要求管理员审批应用权限。',
        action: '请管理员在飞书后台审批并发布应用。',
        badgeClass: 'bg-amber-500/20 text-amber-300',
      }
    case 'scope_missing':
      return {
        label: 'Scope missing',
        description: '飞书应用缺少读取文档、Wiki、表格或 Base 的最小权限。',
        action: '请管理员补齐权限后重新授权。',
        badgeClass: 'bg-amber-500/20 text-amber-300',
      }
    case 'state_expired':
      return {
        label: 'State expired',
        description: '授权链接已过期。',
        action: '请重新打开授权页。',
        badgeClass: 'bg-amber-500/20 text-amber-300',
      }
    case 'popup_blocked':
      return {
        label: 'Popup blocked',
        description: '浏览器拦截了授权窗口。',
        action: '允许弹窗、重新打开授权页，或复制授权链接。',
        badgeClass: 'bg-amber-500/20 text-amber-300',
      }
    case 'callback_unreachable':
      return {
        label: 'Callback unreachable',
        description: '授权窗口无法通知原页面。',
        action: '页面会短轮询结果；仍失败时请重新授权。',
        badgeClass: 'bg-amber-500/20 text-amber-300',
      }
    case 'installation_revoked':
      return {
        label: 'Installation revoked',
        description: '飞书应用安装或授权已被撤销。',
        action: '请重新安装应用并重新授权。',
        badgeClass: 'bg-amber-500/20 text-amber-300',
      }
    default:
      return {
        label: 'Not connected',
        description: '尚未连接飞书。',
        action: '请发起授权。',
        badgeClass: 'bg-gray-500/20 text-gray-300',
      }
  }
}
