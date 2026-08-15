import { GitCompare, Play, Rocket, ShieldCheck } from 'lucide-react'
import { Button } from '../../../components/ui/button'
import { Switch } from '../../../components/ui/switch'
import { useDataModelingStore } from '../store/useDataModelingStore'
import { CheckLine, Panel, PanelHeader, ScoreBar, SectionTitle, StatusPill, readinessTone } from '../components/modelingUi'
import type { SemanticModel } from '../types'

export function PublishWorkspace({ model }: { model: SemanticModel }) {
  return (
    <main className="min-h-0 flex-1 overflow-y-auto bg-[#171717] p-3 custom-scrollbar">
      <div className="mx-auto grid max-w-[1500px] gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="space-y-4">
          <ReadinessSection model={model} />
          <ReviewSection model={model} />
        </div>
        <McpExposure model={model} />
      </div>
    </main>
  )
}

function ReadinessSection({ model }: { model: SemanticModel }) {
  const validateModel = useDataModelingStore(state => state.validateModel)
  const setWorkspaceMode = useDataModelingStore(state => state.setWorkspaceMode)
  const selectObject = useDataModelingStore(state => state.selectObject)

  const fixRelationship = () => {
    selectObject('rel-orders-refunds-risk')
    setWorkspaceMode('model')
  }

  return (
    <Panel>
      <PanelHeader title="Agent Readiness" subtitle="Five-part publish readiness with blockers and reliable question coverage." action={<Button size="sm" variant="brand-primary" onClick={validateModel}><Play className="h-4 w-4" /> Validate</Button>} />
      <div className="grid gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="space-y-4">
          {model.readinessDetail.components.map(component => (
            <div key={component.id}>
              <div className="mb-1 flex justify-between gap-3 text-sm">
                <span className="text-white">{component.name}</span>
                <StatusPill tone={readinessTone(component.status)}>{component.status}</StatusPill>
              </div>
              <ScoreBar value={component.score} level={component.status} />
            </div>
          ))}
        </div>
        <div className="grid gap-3">
          <IssueBlock title="Reliable Questions" tone="ready" items={model.readinessDetail.reliableQuestions} />
          <IssueBlock title="Cannot Reliably Answer" tone="warning" items={model.readinessDetail.unreliableQuestions} />
          <IssueBlock title="Blockers" tone="blocked" items={model.readinessDetail.blockers} empty="No hard blockers remain." action={model.readinessDetail.blockers.length ? <Button size="sm" variant="secondary" onClick={fixRelationship}>Fix relationship</Button> : undefined} />
          <IssueBlock title="Warnings" tone="warning" items={model.readinessDetail.warnings} empty="No warnings remain." />
        </div>
      </div>
    </Panel>
  )
}

function ReviewSection({ model }: { model: SemanticModel }) {
  const openReview = useDataModelingStore(state => state.openReview)
  const markReviewed = useDataModelingStore(state => state.markReviewed)
  const publishModel = useDataModelingStore(state => state.publishModel)
  const updatePublishNotes = useDataModelingStore(state => state.updatePublishNotes)

  return (
    <Panel>
      <PanelHeader title="Review / Publish" subtitle="Review draft changes, create an immutable published version, and update affected consumers." action={<StatusPill tone={model.status === 'Published' ? 'ready' : 'warning'}>{model.publishedVersion}</StatusPill>} />
      <div className="grid gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-3">
          <DiffRow type="Added" object="Refund aggregate relationship repair" impact="Fixes fanout for Refund Rate" />
          <DiffRow type="Modified" object="Paid Revenue certification" impact="MCP query_metric can expose certified definition" />
          <DiffRow type="Modified" object="PII policy for Customers" impact="EMAIL and PHONE masked from semantic tools" />
          <DiffRow type="Breaking" object="Raw customer contact dimensions removed" impact="1 legacy saved query requires review" danger />
          <div className="rounded-md border border-[#2a2a2a] bg-[#181818] p-3">
            <SectionTitle>Affected Consumers</SectionTitle>
            <div className="mt-2 flex flex-wrap gap-2">
              <StatusPill>Agent {model.consumers.agents}</StatusPill>
              <StatusPill>MCP {model.consumers.mcp}</StatusPill>
              <StatusPill>Saved Query {model.consumers.savedQueries}</StatusPill>
              <StatusPill>Dashboard {model.consumers.dashboards}</StatusPill>
              <StatusPill>Data Skill {model.consumers.skills}</StatusPill>
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-md border border-[#2a2a2a] bg-[#181818] p-3">
            <SectionTitle>Validation Summary</SectionTitle>
            <div className="mt-2 space-y-2">
              <CheckLine tone={model.readinessDetail.blockers.length ? 'blocked' : 'ready'}>{model.readinessDetail.blockers.length ? `${model.readinessDetail.blockers.length} blocker remains` : 'No hard blockers'}</CheckLine>
              <CheckLine tone={model.readinessDetail.warnings.length ? 'warning' : 'ready'}>{model.readinessDetail.warnings.length} warnings</CheckLine>
              <CheckLine tone="ready">Breaking changes identified and scoped</CheckLine>
            </div>
          </div>
          <label className="block text-xs text-[#9a9a9a]">
            Publish notes
            <textarea value={model.review.publishNotes} onChange={event => updatePublishNotes(event.target.value)} className="mt-1 min-h-28 w-full rounded-md border border-[#333] bg-[#151515] p-3 text-sm text-white focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring" />
          </label>
          <div className="grid gap-2">
            <Button variant="secondary" onClick={openReview}><GitCompare className="h-4 w-4" /> Open Review</Button>
            <Button variant="secondary" onClick={markReviewed}><ShieldCheck className="h-4 w-4" /> Mark Reviewed</Button>
            <Button variant="brand-primary" onClick={publishModel}><Rocket className="h-4 w-4" /> Publish v3</Button>
          </div>
          {model.review.publishedAt && <StatusPill tone="ready">Published at {model.review.publishedAt}</StatusPill>}
        </div>
      </div>
    </Panel>
  )
}

function McpExposure({ model }: { model: SemanticModel }) {
  const runMcpQuery = useDataModelingStore(state => state.runMcpQuery)
  const setRawSqlFallback = useDataModelingStore(state => state.setRawSqlFallback)

  return (
    <div className="space-y-4">
      <Panel>
        <PanelHeader title="MCP Exposure" subtitle="MCP exposes semantic tools over the published model version." />
        <div className="space-y-3 p-4 text-sm">
          <KV label="Current exposed model version" value={model.mcp.exposedVersion} />
          <KV label="Consumer identity" value={model.mcp.consumerIdentity} />
          <KV label="Semantic tools" value="search_semantic_models, describe_semantic_model, list_metrics, explain_metric, query_metric, explore_dimension, run_semantic_query, get_model_lineage, get_metric_examples" />
          <KV label="Metric permissions" value={model.mcp.allowedMetrics.join(', ')} />
          <KV label="Dimension permissions" value={model.mcp.allowedDimensions.join(', ')} />
          <label className="flex items-center justify-between gap-3 rounded-md border border-[#2a2a2a] bg-[#181818] p-3">
            <span className="text-[#d6d6d6]">Raw SQL fallback</span>
            <Switch checked={model.mcp.rawSqlFallback} onCheckedChange={setRawSqlFallback} />
          </label>
        </div>
      </Panel>

      <Panel>
        <PanelHeader title="MCP Test Console" subtitle="Calls query_metric against the exposed semantic model version." action={<Button size="sm" variant="brand-primary" onClick={runMcpQuery}>Run query_metric</Button>} />
        <div className="p-4">
          <pre className="overflow-x-auto rounded-md border border-[#2a2a2a] bg-[#101010] p-4 text-xs text-[#d4d4d4] custom-scrollbar">
{JSON.stringify({
  tool: 'query_metric',
  arguments: {
    model_id: model.id,
    metric: model.explore.metricId,
    dimensions: [model.explore.dimensionId],
    grain: model.explore.grain,
    time_range: model.explore.timeRange,
  },
}, null, 2)}
          </pre>
          {model.mcp.lastResult && (
            <div className="mt-4 rounded-md border border-emerald-500/20 bg-emerald-500/5 p-4">
              <SectionTitle>Result</SectionTitle>
              <div className="mt-3 grid gap-2 text-sm text-[#d6d6d6]">
                <KV label="resolved metric" value={model.mcp.lastResult.resolvedMetric} />
                <KV label="model version" value={model.mcp.lastResult.modelVersion} />
                <KV label="result" value={model.mcp.lastResult.result} />
                <KV label="freshness" value={model.mcp.lastResult.freshness} />
                <KV label="lineage" value={model.mcp.lastResult.lineage.join(' -> ')} />
                <KV label="policy decision" value={model.mcp.lastResult.policyDecision} />
              </div>
            </div>
          )}
        </div>
      </Panel>
    </div>
  )
}

function IssueBlock({ title, tone, items, empty, action }: { title: string; tone: 'ready' | 'warning' | 'blocked'; items: string[]; empty?: string; action?: React.ReactNode }) {
  return (
    <div className="rounded-md border border-[#2a2a2a] bg-[#181818] p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <SectionTitle>{title}</SectionTitle>
        <StatusPill tone={tone}>{items.length}</StatusPill>
      </div>
      <div className="space-y-2">
        {(items.length ? items : [empty ?? 'None']).map(item => <CheckLine key={item} tone={items.length ? tone : 'ready'}>{item}</CheckLine>)}
      </div>
      {action && <div className="mt-3">{action}</div>}
    </div>
  )
}

function DiffRow({ type, object, impact, danger = false }: { type: string; object: string; impact: string; danger?: boolean }) {
  return (
    <div className="rounded-md border border-[#2a2a2a] bg-[#181818] p-3">
      <div className="flex flex-wrap items-center gap-2">
        <StatusPill tone={danger ? 'blocked' : type === 'Added' ? 'ready' : 'warning'}>{type}</StatusPill>
        <span className="text-sm font-medium text-white">{object}</span>
      </div>
      <p className="mt-2 text-sm text-[#bdbdbd]">{impact}</p>
    </div>
  )
}

function KV({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid gap-1 rounded-md border border-[#2a2a2a] bg-[#181818] p-3 text-xs">
      <span className="uppercase text-[#8d8d8d]">{label}</span>
      <span className="break-words text-[#d6d6d6]">{value}</span>
    </div>
  )
}
