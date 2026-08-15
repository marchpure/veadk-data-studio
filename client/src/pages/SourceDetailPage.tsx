import { Link, useParams } from 'react-router-dom'
import { AlertCircle, ArrowLeft, CheckCircle2, Clock, Database, FileText, Loader2, Network, ShieldAlert } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Button } from '../components/ui/button'
import { Card } from '../components/ui/card'
import { Input } from '../components/ui/input'
import { useKnowledgeSearch, useSourceResource, useSourceResourceProcessing, useSourceResourceSnapshots } from '../hooks/useDBConnections'
import type { SourceResource, SourceResourceProcessing, SourceSnapshot } from '../services/api'

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
  const knowledgeQuery = useKnowledgeSearch(sourceId, evidenceQuery, !!sourceId && !!resourceQuery.data?.knowledge_resource)

  const resource = resourceQuery.data
  const processing = processingQuery.data
  const snapshots = snapshotsQuery.data?.items || []
  const latestSnapshot = resource?.latest_snapshot || snapshots[0] || null
  const snapshotMetadata = latestSnapshot?.metadata_json || {}
  const evidence = knowledgeQuery.data?.items || []
  const progressIndex = processingIndex(resource, processing)
  const parserWarnings = Array.isArray(snapshotMetadata.parser_warnings)
    ? snapshotMetadata.parser_warnings
    : Array.isArray(snapshotMetadata.warnings)
      ? snapshotMetadata.warnings
      : []
  const detectedTables = Array.isArray(snapshotMetadata.tables)
    ? snapshotMetadata.tables
    : Array.isArray(snapshotMetadata.detected_tables)
      ? snapshotMetadata.detected_tables
      : []
  const fragmentHint = typeof snapshotMetadata.fragment_hint === 'string' ? snapshotMetadata.fragment_hint : null
  const contentSize = typeof snapshotMetadata.content_size === 'number' ? snapshotMetadata.content_size : null

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
          <Metric label="Evidence" value={`${resource.knowledge_resource?.evidence_count || processing?.evidence_count || 0}`} tone={(resource.knowledge_resource?.evidence_count || processing?.evidence_count || 0) > 0 ? 'ready' : 'muted'} />
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
            <KeyValue label="Connection" value={resource.source_connection_id || resource.connection_id || 'Direct source'} />
            <KeyValue label="Latest snapshot" value={resource.latest_snapshot_id || '-'} />
            <KeyValue label="Projected dataset" value={resource.projected_dataset_id || '-'} />
            <KeyValue label="Knowledge resource" value={resource.knowledge_resource?.id || '-'} />
            <KeyValue label="Context URI" value={resource.knowledge_resource?.context_uri || '-'} />
          </Section>
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          <Section title="Parsed content" icon={<FileText className="h-4 w-4" />}>
            <KeyValue label="Parser version" value={latestSnapshot?.parser_version || resource.knowledge_resource?.parse_status || '-'} />
            <KeyValue label="Parse status" value={resource.knowledge_resource?.parse_status || latestSnapshot?.status || 'pending'} />
            <KeyValue label="Content hash" value={latestSnapshot?.content_hash || '-'} />
            <KeyValue label="Content size" value={contentSize === null ? '-' : `${contentSize.toLocaleString()} bytes`} />
            <KeyValue label="Fragment hint" value={fragmentHint || '-'} />
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
            {resource.projected_dataset_id ? (
              <>
                <KeyValue label="Projection" value={resource.projected_dataset_id} />
                <KeyValue label="Modeling mode" value="Projection review or semantic model generation can use this dataset." />
              </>
            ) : detectedTables.length > 0 ? (
              <div className="space-y-2">
                {detectedTables.slice(0, 6).map((table, index) => (
                  <div key={index} className="rounded border border-[#333333] bg-[#151515] p-3 text-sm text-gray-300">
                    {formatUnknownTable(table, index)}
                  </div>
                ))}
              </div>
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
            <EmptyText>Consumer detail is not yet expanded. The Sources inventory currently shows partial semantic, dashboard, notebook, and MCP counts from the overview facade.</EmptyText>
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

function LoadingRow({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-gray-400">
      <Loader2 className="h-4 w-4 animate-spin text-brand-orange" />
      {label}
    </div>
  )
}

function formatUnknownTable(table: unknown, index: number) {
  if (table && typeof table === 'object') {
    const record = table as Record<string, unknown>
    const name = record.name || record.table_name || record.sheet_name || `Table ${index + 1}`
    const rows = record.rows ?? record.row_count
    const columns = record.columns ?? record.column_count
    const parts = [
      String(name),
      rows !== undefined ? `${String(rows)} rows` : null,
      columns !== undefined ? `${String(columns)} columns` : null,
    ].filter(Boolean)
    return parts.join(' · ')
  }
  return String(table || `Table ${index + 1}`)
}

function EmptyText({ children }: { children: ReactNode }) {
  return <p className="text-sm text-gray-500">{children}</p>
}
