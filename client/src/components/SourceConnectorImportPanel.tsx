import { useEffect, useMemo, useState } from 'react'
import { AlertCircle, CheckCircle2, ChevronRight, Database, FileText, Folder, HardDrive, Loader2, Search, ShieldCheck } from 'lucide-react'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { Label } from './ui/label'
import {
  useCreateSourceConnection,
  useFeishuStatus,
  useImportSourceResources,
  useListSourceConnectionResources,
  useLocateSourceConnectionResource,
  useSourceConnections,
  useStartFeishuOAuth,
} from '../hooks/useDBConnections'
import { openExternalUrl } from '../lib/tauri-api'
import type {
  ConnectorDefinition,
  SourceResourceImportResult,
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
  const createSourceConnection = useCreateSourceConnection()
  const importSourceResources = useImportSourceResources()
  const locateSourceResource = useLocateSourceConnectionResource()

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
  const selectedList = Object.values(selectedItems)
  const supportedTypes = definition?.supported_resource_types || []
  const scopeTabs = provider === 'feishu' ? feishuScopes : tosScopes
  const typeOptions = provider === 'feishu' ? feishuTypes : tosTypes

  const handleStartFeishuOAuth = async () => {
    const result = await startFeishuOAuth.mutateAsync()
    setWaitingForFeishuOAuth(true)
    await openExternalUrl(result.authorization_url)
  }

  useEffect(() => {
    if (provider !== 'feishu' || !waitingForFeishuOAuth) return
    let stopped = false
    let attempts = 0
    const timer = window.setInterval(() => {
      attempts += 1
      feishuStatus.refetch().then(result => {
        if (stopped) return
        if (result.data?.connected) {
          setWaitingForFeishuOAuth(false)
          return
        }
        if (attempts >= 60) {
          setWaitingForFeishuOAuth(false)
        }
      })
    }, 2000)
    return () => {
      stopped = true
      window.clearInterval(timer)
    }
  }, [feishuStatus, provider, waitingForFeishuOAuth])

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
    if (provider === 'feishu' && item.resource_type === 'feishu_wiki') {
      setScope('wiki')
      setParentToken(item.external_id)
      setBreadcrumbs(prev => [...prev, { label: item.name, token: item.external_id }])
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

  if (definition?.availability === 'planned') {
    return (
      <div className="rounded-lg border border-[#444444] bg-[#1a1a1a] p-5">
        <p className="text-sm font-medium text-white">{definition.display_name}</p>
        <p className="mt-2 text-sm text-gray-400">This connector is listed in the catalog as Planned. It is not exposed as a working connector until an adapter and contract tests exist.</p>
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
            <p className="font-medium">请联系管理员配置飞书连接</p>
            <p className="mt-1 text-amber-100/80">Self-hosted Team Version 需要先配置 Feishu App ID、App Secret、OAuth Redirect URI 和所需权限。这里不会再提供手填 Doc/Sheet URL 的假主流程。</p>
          </div>
        </div>
      </div>
    )
  }

  if (!connected) {
    return (
      <div className="space-y-4">
        <div className="rounded-lg border border-[#444444] bg-[#1a1a1a] p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-medium text-white">{definition?.display_name || providerLabel(provider)}</p>
              <p className="mt-1 text-sm text-gray-400">{definition?.description || 'Connect once, then browse and import resources repeatedly.'}</p>
            </div>
            <span className={`rounded px-2 py-1 text-xs ${requiresReauth ? 'bg-amber-500/20 text-amber-300' : 'bg-gray-500/20 text-gray-300'}`}>
              {requiresReauth ? 'Reauthorization required' : 'Not connected'}
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
            <Button
              onClick={handleStartFeishuOAuth}
              disabled={disabled || startFeishuOAuth.isPending || waitingForFeishuOAuth}
              className="w-full bg-brand-orange hover:bg-brand-orange/90"
            >
              {startFeishuOAuth.isPending || waitingForFeishuOAuth ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
              {waitingForFeishuOAuth ? 'Waiting for Feishu authorization...' : 'Connect Feishu'}
            </Button>
            {waitingForFeishuOAuth && (
              <p className="text-xs text-gray-400">
                Complete authorization in the browser. Byaan will refresh this panel and open the resource picker after the callback succeeds.
              </p>
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
    )
  }

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-green-700/40 bg-green-900/10 p-3 text-sm text-green-200">
        <div className="flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4 text-green-400" />
          <span>Connected: {activeConnection?.display_name}</span>
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
        <div className="space-y-2 rounded-lg border border-[#444444] bg-[#1a1a1a] p-3">
          <div className="text-sm font-medium text-white">Import results</div>
          {importResults.map(result => (
            <div key={`${result.selection.resource_type}:${result.selection.external_id}`} className="flex items-start gap-2 rounded bg-[#242424] px-3 py-2 text-xs">
              {result.status === 'ready' ? <CheckCircle2 className="mt-0.5 h-4 w-4 flex-shrink-0 text-green-400" /> : <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-red-400" />}
              <div className="min-w-0 flex-1">
                <div className="truncate text-white">{result.resource?.name || result.selection.name || result.selection.external_id}</div>
                <div className={result.status === 'ready' ? 'text-green-300' : 'text-red-300'}>
                  {result.status === 'ready'
                    ? `Ready · snapshot ${result.resource?.latest_snapshot_id || 'created'}${result.resource?.projected_dataset_id ? ` · dataset ${result.resource.projected_dataset_id}` : ''}`
                    : `${result.status}${result.error?.message ? ` · ${result.error.message}` : ''}`}
                </div>
              </div>
            </div>
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

function formatBytes(value: number) {
  if (!Number.isFinite(value) || value < 0) return ''
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  if (value < 1024 * 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`
  return `${(value / (1024 * 1024 * 1024)).toFixed(1)} GB`
}
