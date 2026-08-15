import { Link, useParams } from 'react-router-dom'
import { AlertCircle, ArrowLeft, CheckCircle2, Clock, Database, FileText, Loader2, Network, ShieldAlert } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Button } from '../components/ui/button'
import { Card } from '../components/ui/card'
import { Input } from '../components/ui/input'
import {
  useKnowledgeSearch,
  useSourceResource,
  useSourceResourceConsumers,
  useSourceResourceLineage,
  useSourceResourceParsedAssets,
  useSourceResourceProcessing,
  useSourceResourceSnapshots,
} from '../hooks/useDBConnections'
import type { SourceConsumerItem, SourceLineageEdge, SourceLineageNode, SourceParsedAssetItem, SourceResource, SourceResourceProcessing, SourceSnapshot } from '../services/api'

const sourceDetailSteps = [
  'Capture',
  'Parse',
  'Detect tables',
  'Normalize dataset',
  'Index context',
  'Generate semantic suggestions',
  'Ready',
]

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

export default function SourceDetailPage() {
  const { sourceId } = useParams()
  const [evidenceQuery, setEvidenceQuery] = useState('')
  const resourceQuery = useSourceResource(sourceId)
  const snapshotsQuery = useSourceResourceSnapshots(sourceId)
  const processingQuery = useSourceResourceProcessing(sourceId)
  const parsedAssetsQuery = useSourceResourceParsedAssets(sourceId)
  const lineageQuery = useSourceResourceLineage(sourceId)
  const consumersQuery = useSourceResourceConsumers(sourceId)
  const knowledgeQuery = useKnowledgeSearch(sourceId, evidenceQuery, !!sourceId && !!resourceQuery.data?.knowledge_resource)

  const resource = resourceQuery.data
  const processing = processingQuery.data
  const snapshots = snapshotsQuery.data?.items || []
  const latestSnapshot = resource?.latest_snapshot || snapshots[0] || null
  const parsedAssets = parsedAssetsQuery.data || null
  const lineage = lineageQuery.data || null
  const consumers = consumersQuery.data || null
  const evidence = knowledgeQuery.data?.items || []
  const progressIndex = processingIndex(resource, processing)
  const parserWarnings = parsedAssets?.parser_warnings || []
  const contentSize = typeof parsedAssets?.metadata?.content_size === 'number' ? parsedAssets.metadata.content_size : null
  const fragmentHint = typeof parsedAssets?.metadata?.fragment_hint === 'string' ? parsedAssets.metadata.fragment_hint : null
  const evidenceCount = parsedAssets?.evidence_count ?? resource?.knowledge_resource?.evidence_count ?? processing?.evidence_count ?? 0

  if (resourceQuery.isLoading) {
    return (
      <div className="flex h-full items-center justify-center bg-[#0a0a0a] text-gray-300">
        <Loader2 className="mr-2 h-5 w-5 animate-spin text-brand-orange" />
        Loading source...
      </div>
    )
  }

  if (resourceQuery.error || !resource) {
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
                <p className="mt-1 text-sm text-red-100/80">{resourceQuery.error?.message || 'The source resource could not be loaded.'}</p>
              </div>
            </div>
          </Card>
        </div>
      </div>
    )
  }

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
                {resource.projected_dataset_id ? <Database className="h-5 w-5 text-brand-orange" /> : <FileText className="h-5 w-5 text-brand-orange" />}
              </div>
              <div>
                <h1 className="text-2xl font-semibold tracking-normal">{resource.name}</h1>
                <p className="mt-1 text-sm capitalize text-gray-400">{typeLabel(resource.resource_type)} · {resource.visibility}</p>
              </div>
            </div>
          </div>
          <span className={`rounded border px-3 py-1.5 text-sm ${resource.status === 'ready' ? 'border-green-700/50 bg-green-900/20 text-green-200' : 'border-amber-700/50 bg-amber-900/20 text-amber-200'}`}>
            {productStatusLabel(resource.status)}
          </span>
        </div>

        <div className="grid gap-4 md:grid-cols-4">
          <Metric label="Snapshot" value={resource.latest_snapshot_id ? 'Captured' : 'Missing'} tone={resource.latest_snapshot_id ? 'ready' : 'warn'} />
          <Metric label="Dataset" value={resource.projected_dataset_id ? 'Projected' : 'Not projected'} tone={resource.projected_dataset_id ? 'ready' : 'muted'} />
          <Metric label="Context" value={resource.knowledge_resource?.index_status || 'Unavailable'} tone={resource.knowledge_resource?.index_status === 'indexed' ? 'ready' : 'muted'} />
          <Metric label="Evidence" value={`${evidenceCount}`} tone={evidenceCount > 0 ? 'ready' : 'muted'} />
        </div>

        <Section title="Processing" icon={<Clock className="h-4 w-4" />}>
          <div className="grid grid-cols-7 gap-2">
            {sourceDetailSteps.map((step, index) => {
              const complete = index <= progressIndex && processing?.stage !== 'failed'
              return (
                <div key={step} className="min-w-0">
                  <div className={`h-2 rounded-full ${complete ? 'bg-green-500' : processing?.stage === 'failed' && index === 0 ? 'bg-red-500' : 'bg-[#444444]'}`} />
                  <div className={`mt-1 truncate text-xs ${complete ? 'text-green-300' : 'text-gray-500'}`} title={step}>{step}</div>
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
            <KeyValue label="External ID" value={resource.external_id || '-'} />
            <KeyValue label="Source URL" value={resource.source_url || '-'} />
            <KeyValue label="Sync mode" value={resource.sync_mode} />
            <KeyValue label="Created" value={formatDate(resource.created_at)} />
            <KeyValue label="Updated" value={formatDate(resource.updated_at)} />
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
            <KeyValue label="Parse status" value={parsedAssets?.parse_status || resource.knowledge_resource?.parse_status || latestSnapshot?.status || 'pending'} />
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
            ) : parsedAssets?.projected_dataset_id || resource.projected_dataset_id ? (
              <>
                <KeyValue label="Projection" value={parsedAssets?.projected_dataset_id || resource.projected_dataset_id || '-'} />
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
            <KeyValue label="Visibility" value={resource.visibility} />
            <KeyValue label="Context provider" value={resource.knowledge_resource?.provider || 'Not indexed'} />
            <KeyValue label="Provider status" value={resource.knowledge_resource?.provider_status || resource.knowledge_resource?.index_status || 'Unavailable'} />
            <KeyValue label="Last indexed" value={formatDate(resource.knowledge_resource?.last_indexed_at)} />
            <KeyValue label="Retrieval debug URI" value={resource.knowledge_resource?.retrieval_debug_uri || '-'} />
            <KeyValue label="Delete behavior" value="Deleting a source keeps lineage explicit and removes it from the active Sources inventory." />
            <KeyValue label="Reindex behavior" value="Retry sync from the source connector to generate a new snapshot and context state." />
            {resource.knowledge_resource?.provider_error && (
              <div className="mt-4 rounded border border-red-900/40 bg-red-950/20 p-3 text-sm text-red-100">
                {JSON.stringify(resource.knowledge_resource.provider_error)}
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
