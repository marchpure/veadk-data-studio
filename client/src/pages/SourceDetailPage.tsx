import { Link, useNavigate, useParams } from 'react-router-dom'
import { AlertCircle, ArrowLeft, CheckCircle2, Clock, Database, FileText, Loader2, Network, RefreshCw, ShieldAlert, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { Button } from '../components/ui/button'
import { Card } from '../components/ui/card'
import { Input } from '../components/ui/input'
import {
  useDeleteSourceConnection,
  useDeleteSourceResource,
  useFeishuOAuthResult,
  useKnowledgeSearch,
  useRefreshSourceOverviewConnectionSchema,
  useSourceResource,
  useSourceResourceConsumers,
  useSourceResourceLineage,
  useSourceOverviewItem,
  useSourceResourceParsedAssets,
  useSourceResourceProcessing,
  useSourceResourceSnapshots,
  useStartFeishuOAuth,
  useSyncSourceResource,
  sourceConnectorKeys,
  sourceOverviewKeys,
} from '../hooks/useDBConnections'
import { ApiService, isMultiDatabaseSchema, type DatabaseSchemaResponse, type SourceConsumerItem, type SourceLineageEdge, type SourceLineageNode, type SourceOverviewItem, type SourceParsedAssetItem, type SourceResource, type SourceResourceProcessing, type SourceSnapshot } from '../services/api'
import { useQuery, useQueryClient } from '@tanstack/react-query'

const sourceDetailSteps = [
  'Capture',
  'Parse',
  'Detect tables',
  'Normalize dataset',
  'Index context',
  'Generate semantic suggestions',
  'Ready',
]

type SourceProcessingStepDisplay = NonNullable<SourceResourceProcessing['steps']>[number]

const typeLabel = (type?: string | null) => {
  if (!type) return 'Source'
  return type.replace(/_/g, ' ')
}

const formatDate = (value?: string | null) => {
  if (!value) return '-'
  return new Date(value).toLocaleString()
}

const productStatusLabel = (status?: string | null) => {
  if (!status) return 'Pending'
  const normalized = status.toLowerCase()
  const labels: Record<string, string> = {
    ready: 'Ready',
    pending: 'Pending',
    syncing: 'Syncing',
    analyzing: 'Analyzing',
    authorization_required: 'Authorization required',
    reauthorization_required: 'Reauthorization required',
    permission_lost: 'Permission lost',
    source_unavailable: 'Source unavailable',
    needs_confirmation: 'Needs confirmation',
    failed: 'Failed',
    disconnected: 'Source unavailable',
  }
  return labels[normalized] || status.replace(/_/g, ' ')
}

const processingIndex = (resource?: SourceResource, processing?: SourceResourceProcessing) => {
  if (!resource || processing?.stage === 'failed') return -1
  if (processing?.stage === 'waiting_for_connector') return 0
  if (processing?.stage === 'captured') return 1
  if (processing?.stage === 'indexed') return sourceDetailSteps.length - 1
  if (resource.projected_dataset_id) return 5
  if (resource.latest_snapshot_id) return 4
  return 0
}

const processingStepsForDisplay = (
  resource?: SourceResource,
  processing?: SourceResourceProcessing,
): SourceProcessingStepDisplay[] => {
  const serverSteps = processing?.steps
  if (serverSteps?.length) return serverSteps
  const progressIndex = processingIndex(resource, processing)
  return sourceDetailSteps.map((label, index) => ({
    id: label.toLowerCase().replace(/\s+/g, '_'),
    label,
    status: (processing?.stage === 'failed' && index === 0)
      ? 'failed'
      : index <= progressIndex
        ? 'succeeded'
        : 'pending',
  }))
}

const needsFeishuReauthorization = (source?: SourceOverviewItem) =>
  source?.provider === 'feishu' && source.next_actions.some(action => action.toLowerCase().includes('reauthorize'))

const hasLocalUploadRawArtifact = (resource?: SourceResource | null) => {
  if (!resource || !['file', 'pdf'].includes(resource.resource_type)) return false
  const rawUri = resource.latest_snapshot?.raw_storage_uri
  return Boolean(rawUri && rawUri.startsWith(`file://source-resources/${resource.id}/raw/`))
}

export default function SourceDetailPage() {
  const { sourceId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [evidenceQuery, setEvidenceQuery] = useState('')
  const [removeConfirmation, setRemoveConfirmation] = useState('')
  const [disconnectConfirmation, setDisconnectConfirmation] = useState('')
  const [feishuAuthState, setFeishuAuthState] = useState<string | null>(null)
  const [feishuAuthUrl, setFeishuAuthUrl] = useState<string | null>(null)
  const [feishuAuthMessage, setFeishuAuthMessage] = useState<string | null>(null)
  const [waitingForFeishuOAuth, setWaitingForFeishuOAuth] = useState(false)
  const overviewQuery = useSourceOverviewItem(sourceId)
  const syncResourceMutation = useSyncSourceResource()
  const deleteResourceMutation = useDeleteSourceResource()
  const deleteSourceConnectionMutation = useDeleteSourceConnection()
  const startFeishuOAuth = useStartFeishuOAuth()
  const pollFeishuOAuth = useFeishuOAuthResult()
  const refreshConnectionSchemaMutation = useRefreshSourceOverviewConnectionSchema()
  const overview = overviewQuery.data
  const isSourceResource = overview?.source_kind === 'source_resource'
  const resourceQuery = useSourceResource(isSourceResource ? sourceId : undefined)
  const snapshotsQuery = useSourceResourceSnapshots(isSourceResource ? sourceId : undefined)
  const processingQuery = useSourceResourceProcessing(isSourceResource ? sourceId : undefined)
  const parsedAssetsQuery = useSourceResourceParsedAssets(isSourceResource ? sourceId : undefined)
  const lineageQuery = useSourceResourceLineage(isSourceResource ? sourceId : undefined)
  const consumersQuery = useSourceResourceConsumers(isSourceResource ? sourceId : undefined)
  const schemaQuery = useQuery({
    queryKey: ['source-detail-schema', sourceId],
    queryFn: async () => {
      if (!sourceId) throw new Error('Missing source id')
      return ApiService.getDatasourceSchema(sourceId)
    },
    enabled: !!sourceId && !!overview && overview.source_kind !== 'source_resource',
    staleTime: 60 * 1000,
    gcTime: 5 * 60 * 1000,
    retry: false,
  })
  const knowledgeQuery = useKnowledgeSearch(sourceId, evidenceQuery, !!sourceId && !!resourceQuery.data?.knowledge_resource)

  const refreshAfterFeishuAuthorization = useCallback(() => {
    setWaitingForFeishuOAuth(false)
    setFeishuAuthMessage('Feishu authorization connected. Refreshing source state.')
    queryClient.invalidateQueries({ queryKey: sourceConnectorKeys.connections() })
    queryClient.invalidateQueries({ queryKey: sourceConnectorKeys.connections('feishu') })
    queryClient.invalidateQueries({ queryKey: sourceConnectorKeys.feishuStatus() })
    queryClient.invalidateQueries({ queryKey: sourceOverviewKeys.all })
    if (sourceId) {
      queryClient.invalidateQueries({ queryKey: sourceConnectorKeys.sourceResource(sourceId) })
      queryClient.invalidateQueries({ queryKey: sourceConnectorKeys.processing(sourceId) })
      queryClient.invalidateQueries({ queryKey: sourceConnectorKeys.snapshots(sourceId) })
    }
  }, [queryClient, sourceId])

  const refreshAfterConnectionDisconnect = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: sourceConnectorKeys.all })
    queryClient.invalidateQueries({ queryKey: sourceConnectorKeys.feishuStatus() })
    queryClient.invalidateQueries({ queryKey: sourceOverviewKeys.all })
    if (sourceId) {
      queryClient.invalidateQueries({ queryKey: sourceConnectorKeys.sourceResource(sourceId) })
      queryClient.invalidateQueries({ queryKey: sourceConnectorKeys.processing(sourceId) })
      queryClient.invalidateQueries({ queryKey: sourceConnectorKeys.snapshots(sourceId) })
    }
  }, [queryClient, sourceId])

  const disconnectSourceConnection = (connectionId?: string | null) => {
    if (!connectionId) return
    deleteSourceConnectionMutation.mutate(connectionId, {
      onSuccess: () => {
        setDisconnectConfirmation('')
        refreshAfterConnectionDisconnect()
      },
    })
  }

  const beginFeishuReconnect = async () => {
    const result = await startFeishuOAuth.mutateAsync()
    setFeishuAuthState(result.state)
    setFeishuAuthUrl(result.authorization_url)
    setFeishuAuthMessage(null)
    setWaitingForFeishuOAuth(true)
    const popup = window.open(result.authorization_url, 'byaan-feishu-oauth', 'width=720,height=760')
    if (!popup) {
      setFeishuAuthMessage('Authorization window was blocked. Reopen Feishu authorization to continue.')
    }
  }

  const reopenFeishuAuthorization = () => {
    if (!feishuAuthUrl) return
    const popup = window.open(feishuAuthUrl, 'byaan-feishu-oauth', 'width=720,height=760')
    if (!popup) setFeishuAuthMessage('Authorization window was blocked. Allow popups for this site and try again.')
  }

  useEffect(() => {
    if (!waitingForFeishuOAuth || !feishuAuthState) return
    let stopped = false
    let attempts = 0
    const timer = window.setInterval(() => {
      attempts += 1
      pollFeishuOAuth.mutateAsync(feishuAuthState).then(result => {
        if (stopped || !result) return
        if (result.status === 'connected') {
          refreshAfterFeishuAuthorization()
          return
        }
        if (result.status && result.status !== 'authorizing') {
          setWaitingForFeishuOAuth(false)
          setFeishuAuthMessage(result.error?.message || `Feishu authorization ended with status: ${result.status}.`)
        }
      }).catch(() => {
        if (!stopped && attempts >= 60) {
          setWaitingForFeishuOAuth(false)
          setFeishuAuthMessage('Feishu authorization did not complete. Start authorization again when ready.')
        }
      })
      if (attempts >= 60) {
        setWaitingForFeishuOAuth(false)
        setFeishuAuthMessage('Feishu authorization did not complete. Start authorization again when ready.')
      }
    }, 2000)
    return () => {
      stopped = true
      window.clearInterval(timer)
    }
  }, [feishuAuthState, pollFeishuOAuth, refreshAfterFeishuAuthorization, waitingForFeishuOAuth])

  useEffect(() => {
    if (!waitingForFeishuOAuth || !feishuAuthState) return
    const onMessage = (event: MessageEvent) => {
      const data = event.data
      if (!data || data.type !== 'byaan:feishu-oauth') return
      if (data.state !== feishuAuthState) return
      if (data.status === 'connected') {
        refreshAfterFeishuAuthorization()
      } else {
        setWaitingForFeishuOAuth(false)
        setFeishuAuthMessage(data.message || `Feishu authorization ended with status: ${data.status}.`)
      }
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [feishuAuthState, refreshAfterFeishuAuthorization, waitingForFeishuOAuth])

  const resource = resourceQuery.data
  const processing = processingQuery.data
  const snapshots = snapshotsQuery.data?.items || []
  const latestSnapshot = resource?.latest_snapshot || snapshots[0] || null
  const parsedAssets = parsedAssetsQuery.data || null
  const lineage = lineageQuery.data || null
  const consumers = consumersQuery.data || null
  const evidence = knowledgeQuery.data?.items || []
  const parserWarnings = parsedAssets?.parser_warnings || []
  const contentSize = typeof parsedAssets?.metadata?.content_size === 'number' ? parsedAssets.metadata.content_size : null
  const fragmentHint = typeof parsedAssets?.metadata?.fragment_hint === 'string' ? parsedAssets.metadata.fragment_hint : null
  const evidenceCount = parsedAssets?.evidence_count ?? resource?.knowledge_resource?.evidence_count ?? processing?.evidence_count ?? 0
  const displaySteps = processingStepsForDisplay(resource, processing)

  if (overviewQuery.isLoading || (isSourceResource && resourceQuery.isLoading)) {
    return (
      <div className="flex h-full items-center justify-center bg-[#0a0a0a] text-gray-300">
        <Loader2 className="mr-2 h-5 w-5 animate-spin text-brand-orange" />
        Loading source...
      </div>
    )
  }

  if (overviewQuery.error || !overview || (isSourceResource && (resourceQuery.error || !resource))) {
    return (
      <div className="min-h-screen bg-[#0a0a0a] p-8 text-white">
        <div className="mx-auto max-w-4xl">
          <Button asChild variant="ghost" className="mb-6 text-gray-300 hover:text-white">
            <Link to="/sources"><ArrowLeft className="h-4 w-4" /> Sources</Link>
          </Button>
          <Card className="border-red-900/40 bg-red-950/20 p-6">
            <div className="flex items-start gap-3">
              <AlertCircle className="mt-0.5 h-5 w-5 text-red-300" />
              <div>
                <h1 className="text-lg font-semibold text-white">Source not available</h1>
                <p className="mt-1 text-sm text-red-100/80">{overviewQuery.error?.message || resourceQuery.error?.message || 'The source could not be loaded.'}</p>
              </div>
            </div>
          </Card>
        </div>
      </div>
    )
  }

  if (!isSourceResource) {
    return (
      <OverviewSourceDetail
        source={overview}
        schema={schemaQuery.data}
        schemaLoading={schemaQuery.isLoading}
        schemaError={schemaQuery.error instanceof Error ? schemaQuery.error.message : null}
        refreshingSchema={refreshConnectionSchemaMutation.isPending}
        onRefreshSchema={overview.connection_id ? () => refreshConnectionSchemaMutation.mutate({ connectionId: overview.connection_id as string }) : undefined}
        reconnectingFeishu={waitingForFeishuOAuth || startFeishuOAuth.isPending}
        feishuAuthMessage={feishuAuthMessage}
        feishuAuthUrl={feishuAuthUrl}
        onReconnectFeishu={needsFeishuReauthorization(overview) ? beginFeishuReconnect : undefined}
        onReopenFeishuAuthorization={reopenFeishuAuthorization}
      />
    )
  }

  const sourceResource = resource
  if (!sourceResource) {
    return (
      <div className="min-h-screen bg-[#0a0a0a] p-8 text-white">
        <div className="mx-auto max-w-4xl">
          <Button asChild variant="ghost" className="mb-6 text-gray-300 hover:text-white">
            <Link to="/sources"><ArrowLeft className="h-4 w-4" /> Sources</Link>
          </Button>
          <Card className="border-red-900/40 bg-red-950/20 p-6">
            <div className="flex items-start gap-3">
              <AlertCircle className="mt-0.5 h-5 w-5 text-red-300" />
              <div>
                <h1 className="text-lg font-semibold text-white">Source not available</h1>
                <p className="mt-1 text-sm text-red-100/80">The source resource could not be loaded.</p>
              </div>
            </div>
          </Card>
        </div>
      </div>
    )
  }
  const canRetrySync = Boolean(
    sourceResource.source_connection_id
    || (sourceResource.resource_type === 'web' && sourceResource.source_url)
    || hasLocalUploadRawArtifact(sourceResource),
  )
  const retrySyncLabel = sourceResource.status === 'ready' ? 'Reindex source' : 'Retry sync'
  const canRemoveSource = removeConfirmation.trim() === sourceResource.name.trim()
  const canDisconnectConnection = Boolean(sourceResource.source_connection_id) && disconnectConfirmation.trim() === sourceResource.name.trim()
  const canReconnectFeishu = needsFeishuReauthorization(overview)
  const feishuReconnectLabel = waitingForFeishuOAuth || startFeishuOAuth.isPending ? 'Authorizing...' : 'Reconnect Feishu'
  const handleRetrySync = () => {
    syncResourceMutation.mutate({
      resourceId: sourceResource.id,
      payload: {
        metadata: {
          trigger: 'source_detail_retry',
        },
      },
    })
  }
  const handleRemoveSource = () => {
    deleteResourceMutation.mutate(sourceResource.id, {
      onSuccess: () => navigate('/sources'),
    })
  }
  const handleDisconnectConnection = () => disconnectSourceConnection(sourceResource.source_connection_id)

  return (
    <div className="min-h-screen bg-[#0a0a0a] p-8 text-white">
      <div className="mx-auto max-w-6xl space-y-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <Button asChild variant="ghost" className="-ml-3 mb-3 text-gray-300 hover:text-white">
              <Link to="/sources"><ArrowLeft className="h-4 w-4" /> Sources</Link>
            </Button>
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-md bg-brand-orange/15">
                {sourceResource.projected_dataset_id ? <Database className="h-5 w-5 text-brand-orange" /> : <FileText className="h-5 w-5 text-brand-orange" />}
              </div>
              <div>
                <h1 className="text-2xl font-semibold tracking-normal">{sourceResource.name}</h1>
                <p className="mt-1 text-sm capitalize text-gray-400">{typeLabel(sourceResource.resource_type)} · {sourceResource.visibility}</p>
              </div>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {canReconnectFeishu && (
              <Button
                type="button"
                size="sm"
                variant="brand-primary"
                disabled={waitingForFeishuOAuth || startFeishuOAuth.isPending}
                onClick={beginFeishuReconnect}
              >
                {waitingForFeishuOAuth || startFeishuOAuth.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldAlert className="h-4 w-4" />}
                {feishuReconnectLabel}
              </Button>
            )}
            <Button
              type="button"
              size="sm"
              variant="brand-primary"
              disabled={!canRetrySync || syncResourceMutation.isPending}
              onClick={handleRetrySync}
              title={canRetrySync ? retrySyncLabel : 'This source needs a connector, URL, or uploaded raw artifact before it can be synced again.'}
            >
              {syncResourceMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              {syncResourceMutation.isPending ? 'Syncing...' : retrySyncLabel}
            </Button>
            <span className={`rounded border px-3 py-1.5 text-sm ${sourceResource.status === 'ready' ? 'border-green-700/50 bg-green-900/20 text-green-200' : 'border-amber-700/50 bg-amber-900/20 text-amber-200'}`}>
              {productStatusLabel(sourceResource.status)}
            </span>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-4">
          <Metric label="Snapshot" value={sourceResource.latest_snapshot_id ? 'Captured' : 'Missing'} tone={sourceResource.latest_snapshot_id ? 'ready' : 'warn'} />
          <Metric label="Dataset" value={sourceResource.projected_dataset_id ? 'Projected' : 'Not projected'} tone={sourceResource.projected_dataset_id ? 'ready' : 'muted'} />
          <Metric label="Context" value={sourceResource.knowledge_resource?.index_status || 'Unavailable'} tone={sourceResource.knowledge_resource?.index_status === 'indexed' ? 'ready' : 'muted'} />
          <Metric label="Evidence" value={`${evidenceCount}`} tone={evidenceCount > 0 ? 'ready' : 'muted'} />
        </div>

        <Section title="Processing" icon={<Clock className="h-4 w-4" />}>
          <div className="grid grid-cols-7 gap-2">
            {displaySteps.map(step => {
              const complete = step.status === 'succeeded' || step.status === 'skipped'
              const current = step.status === 'running'
              const failed = step.status === 'failed'
              return (
                <div key={step.id} className="min-w-0">
                  <div className={`h-2 rounded-full ${complete ? 'bg-green-500' : current ? 'bg-brand-orange' : failed ? 'bg-red-500' : 'bg-[#444444]'}`} />
                  <div
                    className={`mt-1 truncate text-xs ${complete ? 'text-green-300' : current ? 'text-brand-orange' : failed ? 'text-red-300' : 'text-gray-500'}`}
                    title={step.message || step.label}
                  >
                    {step.label}
                  </div>
                </div>
              )
            })}
          </div>
          <div className="mt-4 rounded border border-[#333333] bg-[#151515] p-3 text-sm text-gray-300">
            {processing?.message || 'No processing state available yet.'}
          </div>
          {processing?.last_error && (
            <div className="mt-3 rounded border border-red-900/40 bg-red-950/20 p-3 text-sm text-red-100">
              {processing.last_error.message || processing.last_error.code}
            </div>
          )}
          {feishuAuthMessage && (
            <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded border border-amber-700/40 bg-amber-950/20 p-3 text-sm text-amber-100">
              <span>{feishuAuthMessage}</span>
              {feishuAuthUrl && waitingForFeishuOAuth && (
                <Button type="button" size="sm" variant="outline" onClick={reopenFeishuAuthorization}>
                  Open authorization
                </Button>
              )}
            </div>
          )}
          {!!processing?.next_actions?.length && (
            <div className="mt-3 flex flex-wrap gap-2">
              {processing.next_actions.map(action => (
                <span key={action} className="rounded border border-[#444444] px-2 py-1 text-xs text-gray-300">{action}</span>
              ))}
            </div>
          )}
        </Section>

        <div className="grid gap-6 lg:grid-cols-2">
          <Section title="Overview" icon={<ShieldAlert className="h-4 w-4" />}>
            <KeyValue label="External ID" value={sourceResource.external_id || '-'} />
            <KeyValue label="Source URL" value={sourceResource.source_url || '-'} />
            <KeyValue label="Sync mode" value={sourceResource.sync_mode} />
            <KeyValue label="Created" value={formatDate(sourceResource.created_at)} />
            <KeyValue label="Updated" value={formatDate(sourceResource.updated_at)} />
          </Section>

          <Section title="Lineage" icon={<Network className="h-4 w-4" />}>
            {lineageQuery.isLoading ? (
              <LoadingRow label="Loading lineage..." />
            ) : lineage && lineage.nodes.length > 0 ? (
              <LineageList nodes={lineage.nodes} edges={lineage.edges} />
            ) : (
              <EmptyText>No lineage has been captured for this source.</EmptyText>
            )}
          </Section>
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          <Section title="Parsed content" icon={<FileText className="h-4 w-4" />}>
            <KeyValue label="Parser version" value={parsedAssets?.parser_version || latestSnapshot?.parser_version || '-'} />
            <KeyValue label="Parse status" value={parsedAssets?.parse_status || sourceResource.knowledge_resource?.parse_status || latestSnapshot?.status || 'pending'} />
            <KeyValue label="Content hash" value={parsedAssets?.metadata?.content_hash || latestSnapshot?.content_hash || '-'} />
            <KeyValue label="Raw artifact" value={parsedAssets?.metadata?.raw_storage_uri || latestSnapshot?.raw_storage_uri || '-'} />
            <KeyValue label="Content size" value={contentSize === null ? '-' : `${contentSize.toLocaleString()} bytes`} />
            <KeyValue label="Fragment hint" value={fragmentHint || '-'} />
            {parsedAssetsQuery.isLoading && <LoadingRow label="Loading parsed assets..." />}
            {!!parsedAssets?.files.length && (
              <div className="mt-4 space-y-2">
                <div className="text-xs uppercase text-gray-500">Files</div>
                {parsedAssets.files.slice(0, 5).map((file, index) => (
                  <ParsedAssetRow key={`${file.name}-${index}`} item={file} />
                ))}
              </div>
            )}
            {parserWarnings.length > 0 && (
              <div className="mt-4 rounded border border-amber-700/30 bg-amber-950/20 p-3">
                <div className="text-xs uppercase text-amber-200/70">Parser warnings</div>
                <ul className="mt-2 space-y-1 text-sm text-amber-100/80">
                  {parserWarnings.slice(0, 5).map((warning, index) => (
                    <li key={index}>{String(warning)}</li>
                  ))}
                </ul>
              </div>
            )}
          </Section>

          <Section title="Tables" icon={<Database className="h-4 w-4" />}>
            {parsedAssetsQuery.isLoading ? (
              <LoadingRow label="Loading tables..." />
            ) : parsedAssets?.tables.length ? (
              <div className="space-y-2">
                {parsedAssets.tables.slice(0, 8).map((table, index) => (
                  <ParsedAssetRow key={`${table.name}-${index}`} item={table} />
                ))}
              </div>
            ) : parsedAssets?.projected_dataset_id || sourceResource.projected_dataset_id ? (
              <>
                <KeyValue label="Projection" value={parsedAssets?.projected_dataset_id || sourceResource.projected_dataset_id || '-'} />
                <KeyValue label="Modeling mode" value="Projection review or semantic model generation can use this dataset." />
              </>
            ) : (
              <EmptyText>No projected tables detected for this source yet.</EmptyText>
            )}
          </Section>
        </div>

        <Section title="Snapshots" icon={<Database className="h-4 w-4" />}>
          {snapshotsQuery.isLoading ? (
            <LoadingRow label="Loading snapshots..." />
          ) : snapshots.length === 0 ? (
            <EmptyText>No snapshots captured yet.</EmptyText>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-[#333333] text-xs uppercase text-gray-500">
                  <tr>
                    <th className="py-2 pr-3">Captured</th>
                    <th className="py-2 pr-3">Status</th>
                    <th className="py-2 pr-3">Parser</th>
                    <th className="py-2 pr-3">Revision</th>
                    <th className="py-2 pr-3">Raw artifact</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#333333]">
                  {snapshots.map(snapshot => <SnapshotRow key={snapshot.id} snapshot={snapshot} />)}
                </tbody>
              </table>
            </div>
          )}
        </Section>

        <Section title="Evidence" icon={<CheckCircle2 className="h-4 w-4" />}>
          <div className="mb-3 max-w-md">
            <Input
              value={evidenceQuery}
              onChange={event => setEvidenceQuery(event.target.value)}
              placeholder="Search this source's evidence"
              className="border-[#555555] bg-[#1a1a1a] text-white placeholder-[#888888]"
            />
          </div>
          {knowledgeQuery.isLoading ? (
            <LoadingRow label="Loading evidence..." />
          ) : evidence.length === 0 ? (
            <EmptyText>No evidence fragments returned for this source.</EmptyText>
          ) : (
            <div className="space-y-2">
              {evidence.map(item => (
                <div key={item.id} className="rounded border border-[#333333] bg-[#151515] p-3">
                  <div className="flex items-center justify-between gap-3 text-xs text-gray-500">
                    <span>{item.fragment_type}</span>
                    <span>{item.confidence || 'confidence n/a'}</span>
                  </div>
                  <p className="mt-2 line-clamp-3 text-sm text-gray-200">{item.text}</p>
                </div>
              ))}
            </div>
          )}
        </Section>

        <div className="grid gap-6 lg:grid-cols-2">
          <Section title="Consumers" icon={<Network className="h-4 w-4" />}>
            {consumersQuery.isLoading ? (
              <LoadingRow label="Loading consumers..." />
            ) : consumers && consumers.items.length > 0 ? (
              <ConsumerList consumers={consumers.items} counts={consumers.counts} />
            ) : (
              <EmptyText>No semantic models, dashboards, notebooks, or artifacts currently consume this source.</EmptyText>
            )}
          </Section>
          <Section title="Settings" icon={<ShieldAlert className="h-4 w-4" />}>
            {canReconnectFeishu && (
              <div className="mb-4 rounded border border-amber-700/40 bg-amber-950/20 p-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-medium text-amber-100">Feishu authorization required</div>
                    <p className="mt-1 text-xs text-amber-100/70">
                      Reconnect Feishu before browsing, syncing, or using this source for modeling handoff.
                    </p>
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    variant="brand-primary"
                    disabled={waitingForFeishuOAuth || startFeishuOAuth.isPending}
                    onClick={beginFeishuReconnect}
                  >
                    {waitingForFeishuOAuth || startFeishuOAuth.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldAlert className="h-4 w-4" />}
                    {feishuReconnectLabel}
                  </Button>
                </div>
              </div>
            )}
            <div className="mb-4 rounded border border-[#333333] bg-[#151515] p-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-medium text-gray-200">{retrySyncLabel}</div>
                  <p className="mt-1 text-xs text-gray-500">
                    {canRetrySync
                      ? 'Capture a fresh snapshot and refresh parse, projection, context, lineage, and consumer state.'
                      : 'This source does not have a connector-backed resource, URL, or uploaded raw artifact to retry. Re-upload or reselect the resource from Add Source.'}
                  </p>
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="brand-primary"
                  disabled={!canRetrySync || syncResourceMutation.isPending}
                  onClick={handleRetrySync}
                >
                  {syncResourceMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                  {syncResourceMutation.isPending ? 'Syncing...' : retrySyncLabel}
                </Button>
              </div>
            </div>
            <KeyValue label="Visibility" value={sourceResource.visibility} />
            <KeyValue label="Context provider" value={sourceResource.knowledge_resource?.provider || 'Not indexed'} />
            <KeyValue label="Provider status" value={sourceResource.knowledge_resource?.provider_status || sourceResource.knowledge_resource?.index_status || 'Unavailable'} />
            <KeyValue label="Last indexed" value={formatDate(sourceResource.knowledge_resource?.last_indexed_at)} />
            <KeyValue label="Retrieval debug URI" value={sourceResource.knowledge_resource?.retrieval_debug_uri || '-'} />
            {sourceResource.source_connection_id && (
              <div className="mt-4 rounded border border-amber-800/40 bg-amber-950/10 p-3">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium text-amber-100">Disconnect connector authorization</div>
                    <p className="mt-1 text-xs text-amber-100/70">
                      This revokes the saved connector credentials for this source connection. Existing resources stay in inventory with stale snapshots, but fresh browsing, sync, and modeling handoff require reauthorization.
                    </p>
                    <Input
                      value={disconnectConfirmation}
                      onChange={event => setDisconnectConfirmation(event.target.value)}
                      placeholder={`Type ${sourceResource.name} to confirm`}
                      className="mt-3 border-amber-800/50 bg-[#1a1a1a] text-white placeholder-amber-100/35"
                    />
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={!canDisconnectConnection || deleteSourceConnectionMutation.isPending}
                    onClick={handleDisconnectConnection}
                  >
                    {deleteSourceConnectionMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldAlert className="h-4 w-4" />}
                    {deleteSourceConnectionMutation.isPending ? 'Disconnecting...' : 'Disconnect connector'}
                  </Button>
                </div>
              </div>
            )}
            <div className="mt-4 rounded border border-red-900/40 bg-red-950/10 p-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium text-red-100">Remove source from inventory</div>
                  <p className="mt-1 text-xs text-red-100/70">
                    This writes a deletion marker, preserves lineage evidence, and removes the source from the active Sources inventory.
                  </p>
                  <Input
                    value={removeConfirmation}
                    onChange={event => setRemoveConfirmation(event.target.value)}
                    placeholder={`Type ${sourceResource.name} to confirm`}
                    className="mt-3 border-red-900/50 bg-[#1a1a1a] text-white placeholder-red-100/35"
                  />
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="destructive"
                  disabled={!canRemoveSource || deleteResourceMutation.isPending}
                  onClick={handleRemoveSource}
                >
                  {deleteResourceMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                  {deleteResourceMutation.isPending ? 'Removing...' : 'Remove source'}
                </Button>
              </div>
            </div>
            <KeyValue label="Reindex behavior" value={hasLocalUploadRawArtifact(sourceResource) ? 'Retry sync from the uploaded raw artifact to refresh parse, projection, and context state.' : 'Retry sync from the source connector to generate a new snapshot and context state.'} />
            {sourceResource.knowledge_resource?.provider_error && (
              <div className="mt-4 rounded border border-red-900/40 bg-red-950/20 p-3 text-sm text-red-100">
                {JSON.stringify(sourceResource.knowledge_resource.provider_error)}
              </div>
            )}
          </Section>
        </div>
      </div>
    </div>
  )
}

function Section({ title, icon, children }: { title: string; icon: ReactNode; children: ReactNode }) {
  return (
    <Card className="border-gray-800 bg-[#1a1a1a] p-5">
      <h2 className="mb-4 flex items-center gap-2 text-base font-semibold text-white">
        <span className="text-brand-orange">{icon}</span>
        {title}
      </h2>
      {children}
    </Card>
  )
}

function Metric({ label, value, tone }: { label: string; value: string; tone: 'ready' | 'warn' | 'muted' }) {
  const toneClass = tone === 'ready' ? 'text-green-300' : tone === 'warn' ? 'text-amber-300' : 'text-gray-400'
  return (
    <Card className="border-gray-800 bg-[#1a1a1a] p-4">
      <div className="text-xs uppercase text-gray-500">{label}</div>
      <div className={`mt-2 text-lg font-semibold capitalize ${toneClass}`}>{value}</div>
    </Card>
  )
}

function OverviewSourceDetail({
  source,
  schema,
  schemaLoading,
  schemaError,
  refreshingSchema,
  onRefreshSchema,
  reconnectingFeishu,
  feishuAuthMessage,
  feishuAuthUrl,
  onReconnectFeishu,
  onReopenFeishuAuthorization,
}: {
  source: SourceOverviewItem
  schema?: DatabaseSchemaResponse
  schemaLoading: boolean
  schemaError: string | null
  refreshingSchema: boolean
  onRefreshSchema?: () => void
  reconnectingFeishu: boolean
  feishuAuthMessage: string | null
  feishuAuthUrl: string | null
  onReconnectFeishu?: () => void
  onReopenFeishuAuthorization: () => void
}) {
  const schemaTables = sourceSchemaTables(schema)
  const progressIndex = overviewProgressIndex(source)
  const icon = source.family === 'warehouses' || source.family === 'databases'
    ? <Database className="h-5 w-5 text-brand-orange" />
    : <FileText className="h-5 w-5 text-brand-orange" />

  return (
    <div className="min-h-screen bg-[#0a0a0a] p-8 text-white">
      <div className="mx-auto max-w-6xl space-y-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <Button asChild variant="ghost" className="-ml-3 mb-3 text-gray-300 hover:text-white">
              <Link to="/sources"><ArrowLeft className="h-4 w-4" /> Sources</Link>
            </Button>
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-md bg-brand-orange/15">
                {icon}
              </div>
              <div>
                <h1 className="text-2xl font-semibold tracking-normal">{source.name}</h1>
                <p className="mt-1 text-sm capitalize text-gray-400">{typeLabel(source.resource_type || source.provider)} · {source.family.replace(/_/g, ' ')}</p>
              </div>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {onReconnectFeishu && (
              <Button
                type="button"
                size="sm"
                variant="brand-primary"
                disabled={reconnectingFeishu}
                onClick={onReconnectFeishu}
              >
                {reconnectingFeishu ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldAlert className="h-4 w-4" />}
                {reconnectingFeishu ? 'Authorizing...' : 'Reconnect Feishu'}
              </Button>
            )}
            {source.source_kind === 'connection' && (
              <Button
                type="button"
                size="sm"
                variant="brand-primary"
                disabled={!onRefreshSchema || refreshingSchema}
                onClick={onRefreshSchema}
                title={onRefreshSchema ? 'Refresh schema/profile from the source connection' : 'This source has no backing connection to refresh.'}
              >
                {refreshingSchema ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                {refreshingSchema ? 'Refreshing...' : 'Refresh profile'}
              </Button>
            )}
            <span className={`rounded border px-3 py-1.5 text-sm ${overviewStatusTone(source)}`}>
              {source.status}
            </span>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-4">
          <Metric label="Freshness" value={source.freshness_status} tone={source.freshness_status === 'fresh' ? 'ready' : source.freshness_status === 'stale' ? 'warn' : 'muted'} />
          <Metric label="Parsed tables" value={`${source.parsed_asset_counts.tables || schemaTables.length}`} tone={source.parsed_asset_counts.tables || schemaTables.length ? 'ready' : 'muted'} />
          <Metric label="Context" value={source.context_index_status.replace(/_/g, ' ')} tone={source.context_index_status === 'indexed' ? 'ready' : source.context_index_status === 'failed' ? 'warn' : 'muted'} />
          <Metric label="Semantic models" value={`${source.consumer_counts.semantic_models}`} tone={source.consumer_counts.semantic_models > 0 ? 'ready' : 'muted'} />
        </div>

        <Section title="Processing" icon={<Clock className="h-4 w-4" />}>
          <div className="grid grid-cols-7 gap-2">
            {sourceDetailSteps.map((step, index) => {
              const complete = index <= progressIndex
              return (
                <div key={step} className="min-w-0">
                  <div className={`h-2 rounded-full ${complete ? 'bg-green-500' : 'bg-[#444444]'}`} />
                  <div className={`mt-1 truncate text-xs ${complete ? 'text-green-300' : 'text-gray-500'}`} title={step}>{step}</div>
                </div>
              )
            })}
          </div>
          <div className="mt-4 rounded border border-[#333333] bg-[#151515] p-3 text-sm text-gray-300">
            {overviewReadinessMessage(source)}
          </div>
          {source.next_actions.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {source.next_actions.map(action => (
                <span key={action} className="rounded border border-[#444444] px-2 py-1 text-xs text-gray-300">{action}</span>
              ))}
            </div>
          )}
          {feishuAuthMessage && (
            <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded border border-amber-700/40 bg-amber-950/20 p-3 text-sm text-amber-100">
              <span>{feishuAuthMessage}</span>
              {feishuAuthUrl && reconnectingFeishu && (
                <Button type="button" size="sm" variant="outline" onClick={onReopenFeishuAuthorization}>
                  Open authorization
                </Button>
              )}
            </div>
          )}
        </Section>

        <div className="grid gap-6 lg:grid-cols-2">
          <Section title="Overview" icon={<ShieldAlert className="h-4 w-4" />}>
            <KeyValue label="Source kind" value={source.source_kind} />
            <KeyValue label="Provider" value={source.provider} />
            <KeyValue label="Resource type" value={source.resource_type || '-'} />
            <KeyValue label="Visibility" value={source.visibility} />
            <KeyValue label="Owner" value={source.owner?.name || source.owner?.id || '-'} />
            <KeyValue label="Last synced" value={formatDate(source.last_synced_at)} />
            <KeyValue label="Created" value={formatDate(source.created_at)} />
            <KeyValue label="Updated" value={formatDate(source.updated_at)} />
          </Section>

          <Section title="Lineage" icon={<Network className="h-4 w-4" />}>
            <LineageList
              nodes={[
                { id: source.id, node_type: source.source_kind, label: source.name, status: source.status, metadata: {} },
                ...(source.projected_dataset_id ? [{ id: source.projected_dataset_id, node_type: 'projected_dataset', label: 'Projected dataset', status: 'available', metadata: {} }] : []),
              ]}
              edges={source.projected_dataset_id ? [{ from_id: source.id, to_id: source.projected_dataset_id, relationship: 'projects_to', metadata: {} }] : []}
            />
          </Section>
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          <Section title="Parsed content" icon={<FileText className="h-4 w-4" />}>
            <KeyValue label="Parse status" value={source.parse_status} />
            <KeyValue label="Latest snapshot" value={source.latest_snapshot_id || '-'} />
            <KeyValue label="Raw artifact" value={source.raw_artifact_uri || '-'} />
            <KeyValue label="Projected dataset" value={source.projected_dataset_id || '-'} />
            <KeyValue label="Blocks" value={`${source.parsed_asset_counts.blocks}`} />
            <KeyValue label="Evidence" value={`${source.parsed_asset_counts.evidence}`} />
            <KeyValue label="Files" value={`${source.parsed_asset_counts.files}`} />
            <KeyValue label="Counts partial" value={source.counts_partial ? 'Yes' : 'No'} />
          </Section>

          <Section title="Tables" icon={<Database className="h-4 w-4" />}>
            {schemaLoading ? (
              <LoadingRow label="Loading schema/profile..." />
            ) : schemaError ? (
              <div className="rounded border border-amber-700/30 bg-amber-950/20 p-3 text-sm text-amber-100/80">
                {schemaError}
              </div>
            ) : schemaTables.length > 0 ? (
              <div className="space-y-2">
                {schemaTables.slice(0, 12).map(table => (
                  <div key={table.name} className="rounded border border-[#333333] bg-[#151515] p-3 text-sm">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-medium text-gray-200">{table.name}</span>
                      <span className="rounded border border-[#444444] px-2 py-0.5 text-xs text-gray-400">{table.columns} columns</span>
                    </div>
                    <div className="mt-1 text-xs text-gray-500">{table.rows === null ? 'row count unavailable' : `${table.rows.toLocaleString()} rows`}</div>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyText>No schema/profile tables are available for this source yet.</EmptyText>
            )}
          </Section>
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          <Section title="Consumers" icon={<Network className="h-4 w-4" />}>
            <div className="flex flex-wrap gap-2">
              {Object.entries(source.consumer_counts).map(([type, count]) => (
                <span key={type} className="rounded border border-[#444444] px-2 py-1 text-xs text-gray-300">
                  {typeLabel(type)}: {count}
                </span>
              ))}
            </div>
            {source.counts_partial && <p className="mt-3 text-sm text-gray-500">Consumer counts are partial until dashboard and MCP references are fully indexed.</p>}
          </Section>

          <Section title="Settings" icon={<ShieldAlert className="h-4 w-4" />}>
            {onReconnectFeishu && (
              <div className="mb-4 rounded border border-amber-700/40 bg-amber-950/20 p-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-medium text-amber-100">Feishu authorization required</div>
                    <p className="mt-1 text-xs text-amber-100/70">
                      Reconnect Feishu before refreshing source metadata or using this source for modeling handoff.
                    </p>
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    variant="brand-primary"
                    disabled={reconnectingFeishu}
                    onClick={onReconnectFeishu}
                  >
                    {reconnectingFeishu ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldAlert className="h-4 w-4" />}
                    {reconnectingFeishu ? 'Authorizing...' : 'Reconnect Feishu'}
                  </Button>
                </div>
              </div>
            )}
            {source.source_kind === 'connection' && (
              <div className="mb-4 rounded border border-[#333333] bg-[#151515] p-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-medium text-gray-200">Refresh schema/profile</div>
                    <p className="mt-1 text-xs text-gray-500">
                      Pull a fresh schema/profile from the database or warehouse before regenerating semantic suggestions.
                    </p>
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    variant="brand-primary"
                    disabled={!onRefreshSchema || refreshingSchema}
                    onClick={onRefreshSchema}
                  >
                    {refreshingSchema ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                    {refreshingSchema ? 'Refreshing...' : 'Refresh profile'}
                  </Button>
                </div>
              </div>
            )}
            <KeyValue label="Delete behavior" value="Delete is handled from the Sources inventory and keeps downstream impact explicit." />
            <KeyValue label="Refresh behavior" value={source.source_kind === 'connection' ? 'Refresh schema/profile before regenerating semantic suggestions.' : 'Re-profile the dataset or source projection before publishing dependent models.'} />
            <KeyValue label="Production modeling" value={source.family === 'databases' || source.family === 'warehouses' ? 'Supported through schema/profile evidence.' : 'Requires projection or context-assisted handoff.'} />
          </Section>
        </div>
      </div>
    </div>
  )
}

function overviewStatusTone(source: SourceOverviewItem): string {
  const status = source.status.toLowerCase()
  if (status === 'ready') return 'border-green-700/50 bg-green-900/20 text-green-200'
  if (status.includes('failed') || status.includes('permission') || status.includes('authorization')) {
    return 'border-red-700/50 bg-red-900/20 text-red-200'
  }
  return 'border-amber-700/50 bg-amber-900/20 text-amber-200'
}

function overviewProgressIndex(source: SourceOverviewItem): number {
  if (source.status.toLowerCase() === 'failed') return -1
  if (source.context_index_status === 'indexed') return sourceDetailSteps.length - 1
  if (source.context_index_status === 'indexing') return 4
  if (source.projected_dataset_id) return 5
  if (source.parsed_asset_counts.tables > 0) return 3
  if (source.parse_status === 'parsed') return 2
  if (source.latest_snapshot_id) return 1
  return 0
}

function overviewReadinessMessage(source: SourceOverviewItem): string {
  if (source.status.toLowerCase() !== 'ready') {
    return `${source.status}. ${source.next_actions[0] || 'Review the source before modeling or dashboard generation.'}`
  }
  if (source.family === 'databases' || source.family === 'warehouses') {
    return 'Schema/profile evidence is available for semantic model generation.'
  }
  if (source.projected_dataset_id) {
    return 'A projected dataset exists. Review projection shape before production semantic modeling.'
  }
  if (source.context_index_status === 'indexed') {
    return 'Context is indexed for evidence and policy support. Use a governed fact source for production metrics.'
  }
  return 'Source is connected, but a projection or context index is still needed before deeper modeling.'
}

function sourceSchemaTables(schema?: DatabaseSchemaResponse): Array<{ name: string; columns: number; rows: number | null }> {
  if (!schema) return []
  if (isMultiDatabaseSchema(schema)) {
    return schema.databases.flatMap(database => Object.entries(database.schema || {}).map(([name, info]) => schemaTableSummary(name, info)))
  }
  return Object.entries(schema.schema || {}).map(([name, info]) => schemaTableSummary(name, info))
}

function schemaTableSummary(name: string, info: any): { name: string; columns: number; rows: number | null } {
  const columns = Array.isArray(info?.columns)
    ? info.columns.length
    : Array.isArray(info?.sample_fields)
      ? info.sample_fields.length
      : 0
  const rows = typeof info?.row_count === 'number' ? info.row_count : null
  return { name, columns, rows }
}

function KeyValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="mb-3 last:mb-0">
      <div className="text-xs uppercase text-gray-500">{label}</div>
      <div className="mt-1 break-all text-sm text-gray-200">{value}</div>
    </div>
  )
}

function SnapshotRow({ snapshot }: { snapshot: SourceSnapshot }) {
  return (
    <tr>
      <td className="py-3 pr-3 text-gray-300">{formatDate(snapshot.captured_at)}</td>
      <td className="py-3 pr-3 text-gray-300">{snapshot.status}</td>
      <td className="py-3 pr-3 text-gray-300">{snapshot.parser_version || '-'}</td>
      <td className="py-3 pr-3 text-gray-300">{snapshot.external_revision || '-'}</td>
      <td className="max-w-[280px] truncate py-3 pr-3 text-gray-500" title={snapshot.raw_storage_uri}>{snapshot.raw_storage_uri}</td>
    </tr>
  )
}

function ParsedAssetRow({ item }: { item: SourceParsedAssetItem }) {
  const details = [
    item.status,
    formatAssetMetric(item.metadata.rows ?? item.metadata.row_count, 'rows'),
    formatAssetMetric(item.metadata.columns ?? item.metadata.column_count, 'columns'),
    formatAssetMetric(item.metadata.size ?? item.metadata.content_size, 'bytes'),
  ].filter(Boolean)

  return (
    <div className="rounded border border-[#333333] bg-[#151515] p-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-medium text-gray-200">{item.name}</span>
        <span className="rounded border border-[#444444] px-2 py-0.5 text-xs capitalize text-gray-400">{item.asset_type}</span>
      </div>
      {details.length > 0 && <div className="mt-1 text-xs text-gray-500">{details.join(' · ')}</div>}
      {Object.keys(item.locator || {}).length > 0 && (
        <div className="mt-2 truncate text-xs text-gray-500" title={JSON.stringify(item.locator)}>
          locator: {JSON.stringify(item.locator)}
        </div>
      )}
    </div>
  )
}

function LineageList({ nodes, edges }: { nodes: SourceLineageNode[]; edges: SourceLineageEdge[] }) {
  return (
    <div className="space-y-3">
      <div className="space-y-2">
        {nodes.map(node => (
          <div key={node.id} className="rounded border border-[#333333] bg-[#151515] p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm font-medium text-gray-200">{node.label}</span>
              <span className="rounded border border-[#444444] px-2 py-0.5 text-xs text-gray-400">{typeLabel(node.node_type)}</span>
            </div>
            <div className="mt-1 flex flex-wrap gap-2 text-xs text-gray-500">
              <span>{node.id}</span>
              {node.status && <span>{node.status}</span>}
            </div>
          </div>
        ))}
      </div>
      {edges.length > 0 && (
        <div className="rounded border border-[#333333] bg-[#101010] p-3">
          <div className="mb-2 text-xs uppercase text-gray-500">Edges</div>
          <div className="space-y-1 text-xs text-gray-400">
            {edges.map(edge => (
              <div key={`${edge.from_id}-${edge.relationship}-${edge.to_id}`} className="truncate" title={`${edge.from_id} -> ${edge.to_id}`}>
                {typeLabel(edge.relationship)}: {edge.from_id} {'->'} {edge.to_id}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function ConsumerList({ consumers, counts }: { consumers: SourceConsumerItem[]; counts: Record<string, number> }) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {Object.entries(counts).map(([type, count]) => (
          <span key={type} className="rounded border border-[#444444] px-2 py-1 text-xs text-gray-300">
            {typeLabel(type)}: {count}
          </span>
        ))}
      </div>
      <div className="space-y-2">
        {consumers.map(consumer => (
          <div key={`${consumer.consumer_type}-${consumer.id}`} className="rounded border border-[#333333] bg-[#151515] p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm font-medium text-gray-200">{consumer.name}</span>
              <span className="rounded border border-[#444444] px-2 py-0.5 text-xs text-gray-400">{typeLabel(consumer.consumer_type)}</span>
            </div>
            <div className="mt-1 flex flex-wrap gap-2 text-xs text-gray-500">
              <span>{typeLabel(consumer.relationship)}</span>
              {consumer.status && <span>{consumer.status}</span>}
              <span>{formatDate(consumer.updated_at || consumer.created_at)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function LoadingRow({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-gray-400">
      <Loader2 className="h-4 w-4 animate-spin text-brand-orange" />
      {label}
    </div>
  )
}

function formatAssetMetric(value: unknown, unit: string) {
  if (value === undefined || value === null || value === '') return null
  if (typeof value === 'number') return `${value.toLocaleString()} ${unit}`
  return `${String(value)} ${unit}`
}

function EmptyText({ children }: { children: ReactNode }) {
  return <p className="text-sm text-gray-500">{children}</p>
}
