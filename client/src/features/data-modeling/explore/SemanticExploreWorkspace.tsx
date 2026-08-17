import { useState } from 'react'
import { BarChart3, Bot, DatabaseZap, FilePlus2, GitBranch, Info, LayoutDashboard, Save, Search, Table2 } from 'lucide-react'
import { Button } from '../../../components/ui/button'
import { selectExploreResult, useDataModelingStore } from '../store/useDataModelingStore'
import { MetricTile, Panel, PanelHeader, SectionTitle, StatusPill, Surface, modelingStyles } from '../components/modelingUi'
import type { ExploreState, SemanticModel, TimeGrain } from '../types'

export function SemanticExploreWorkspace({ model, onReviewModel }: { model: SemanticModel; onReviewModel: () => void }) {
  const updateExplore = useDataModelingStore(state => state.updateExplore)
  const saveExploreArtifact = useDataModelingStore(state => state.saveExploreArtifact)
  const runMcpQuery = useDataModelingStore(state => state.runMcpQuery)
  const [explanationOpen, setExplanationOpen] = useState(false)
  const [agentQuestion, setAgentQuestion] = useState('Why did paid revenue change by region?')
  const result = selectExploreResult(model)
  const metric = model.metrics.find(item => item.id === model.explore.metricId) ?? model.metrics[0]
  const availableDimensions = metric?.dimensions.length
    ? model.dimensions.filter(item => metric.dimensions.includes(item.id))
    : model.dimensions
  const dimension = availableDimensions.find(item => item.id === model.explore.dimensionId) ?? availableDimensions[0] ?? model.dimensions[0]

  return (
    <main className={`${modelingStyles.workspace} p-3`}>
      <div className="mx-auto grid max-w-[1500px] gap-4">
        <div className="flex flex-col gap-3 rounded-lg border border-[#2d3439] bg-[#15191d] px-4 py-3 text-sm text-[#c4ccd2] md:flex-row md:items-center md:justify-between">
          <div className="flex min-w-0 items-start gap-3">
            <Info className="mt-0.5 h-4 w-4 shrink-0 text-brand-orange" />
            <div className="min-w-0">
              <div className="font-medium text-[#f3f5f5]">Published semantic query surface</div>
              <div className="mt-1 text-xs leading-5 text-[#9aa4ac]">Explore uses the published Semantic Model through query_metric. Draft changes must be validated and published before MCP consumers see them.</div>
            </div>
          </div>
          <StatusPill tone={model.publishedVersion !== 'v0' ? 'ready' : 'warning'}>{model.publishedVersion}</StatusPill>
        </div>
        <section className={modelingStyles.panel}>
          <div className="grid gap-3 border-b border-[#30363a] bg-[#15191d] p-3 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-end">
            <div className="grid min-w-0 gap-2 md:grid-cols-2 xl:grid-cols-[minmax(180px,1fr)_minmax(180px,1fr)_120px_150px_minmax(180px,1fr)_minmax(180px,1fr)]">
              <Select
                label="Metric"
                value={metric?.id ?? model.explore.metricId}
                onChange={value => {
                  const nextMetric = model.metrics.find(item => item.id === value)
                  const nextDimensionId = nextMetric?.dimensions.includes(model.explore.dimensionId)
                    ? model.explore.dimensionId
                    : nextMetric?.dimensions[0] ?? availableDimensions[0]?.id ?? ''
                  updateExplore({ metricId: value, dimensionId: nextDimensionId })
                }}
                options={model.metrics.map(item => [item.id, item.businessName])}
              />
              <Select label="Dimension" value={dimension?.id ?? model.explore.dimensionId} onChange={value => updateExplore({ dimensionId: value })} options={availableDimensions.map(item => [item.id, item.name])} />
              <Select label="Grain" value={model.explore.grain} onChange={value => updateExplore({ grain: value as TimeGrain })} options={[['day', 'Day'], ['week', 'Week'], ['month', 'Month'], ['quarter', 'Quarter']]} />
              <Select label="Range" value={model.explore.timeRange} onChange={value => updateExplore({ timeRange: value as ExploreState['timeRange'] })} options={[['30d', 'Last 30d'], ['90d', 'Last 90d'], ['ytd', 'YTD'], ['12m', 'Last 12m']]} />
              <label className="block min-w-0 text-xs text-[#818c95]">
                Filter
                <input
                  value={model.explore.filter}
                  onChange={event => updateExplore({ filter: event.target.value })}
                className={`mt-1 h-9 w-full rounded-md px-3 font-mono text-xs focus-visible:outline-none focus-visible:ring-1 ${modelingStyles.input}`}
                />
              </label>
              <label className="block min-w-0 text-xs text-[#818c95]">
                Ask Agent
                <input
                  value={agentQuestion}
                  onChange={event => setAgentQuestion(event.target.value)}
                className={`mt-1 h-9 w-full rounded-md px-3 text-sm focus-visible:outline-none focus-visible:ring-1 ${modelingStyles.input}`}
                />
              </label>
            </div>
            <div className="flex flex-wrap items-center gap-2 xl:justify-end">
              <div className={modelingStyles.segmented}>
                <ViewButton active={model.explore.viewMode === 'trend'} onClick={() => updateExplore({ viewMode: 'trend' })} icon={<BarChart3 className="h-4 w-4" />} label="Trend" />
                <ViewButton active={model.explore.viewMode === 'table'} onClick={() => updateExplore({ viewMode: 'table' })} icon={<Table2 className="h-4 w-4" />} label="Table" />
                <ViewButton active={model.explore.viewMode === 'pivot'} onClick={() => updateExplore({ viewMode: 'pivot' })} icon={<GitBranch className="h-4 w-4" />} label="Pivot" />
              </div>
            </div>
          </div>

          <div className="grid gap-4 p-4 xl:grid-cols-[minmax(0,1fr)_340px]">
            <div className="min-w-0 space-y-4">
              <div className="grid gap-3 md:grid-cols-4">
                <Kpi label="Current value" value={result.kpi} sub={result.delta} />
                <Kpi label="Metric" value={metric?.businessName ?? 'No metric'} sub={metric?.certification ?? ''} />
                <Kpi label="Dimension" value={dimension?.name ?? 'No dimension'} sub={dimension?.description ?? ''} />
                <Kpi label="Model" value={model.publishedVersion} sub={`${model.readiness}% readiness`} />
              </div>

              <Surface className="p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <h2 className="text-sm font-semibold text-[#f3f5f5]">{metric?.businessName ?? 'No metric'} by {dimension?.name ?? 'No dimension'}</h2>
                    <p className="mt-1 text-xs text-[#9aa4ac]">{model.explore.grain} · {model.explore.timeRange} · semantic query result</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <StatusPill tone={model.mcp.lastResult ? 'ready' : 'warning'}>{model.mcp.lastResult ? 'query result' : 'not queried'}</StatusPill>
                    <Button size="sm" variant="brand-primary" onClick={runMcpQuery}>Run query_metric</Button>
                  </div>
                </div>
                {result.rows.length === 0 && <EmptyQueryResult published={model.publishedVersion !== 'v0'} />}
                {result.rows.length > 0 && model.explore.viewMode === 'trend' && <TrendChart points={result.trend} />}
                {result.rows.length > 0 && (model.explore.viewMode === 'table' || model.explore.viewMode === 'pivot') && <ResultTable rows={result.rows} pivot={model.explore.viewMode === 'pivot'} />}
              </Surface>

              {result.rows.length > 0 && <Breakdown rows={result.rows} />}
            </div>

            <aside className="min-w-0 space-y-4">
              <Panel>
                <PanelHeader title="Agent" subtitle="Ask about the current semantic result" action={<Button size="sm" variant="secondary"><Bot className="h-4 w-4" /> Ask</Button>} />
                <div className="space-y-3 p-4">
                  <p className="rounded-md border border-[#2a3136] bg-[#0f1113] p-3 text-sm leading-6 text-[#d6dde2]">The selected view answers: {agentQuestion}</p>
                  <Button className="w-full" variant="secondary" onClick={() => setExplanationOpen(value => !value)}>Why this calculation</Button>
                  {explanationOpen && (
                    <Surface className="space-y-3 p-3">
                      <p className="text-sm leading-6 text-[#d6dde2]">{metric?.preview.explanation}</p>
                      <div>
                        <SectionTitle>Lineage</SectionTitle>
                        <div className="mt-2 flex flex-wrap gap-2">
                          {(metric?.lineage ?? []).map((item, index) => <StatusPill key={`${item}-${index}`}>{item}</StatusPill>)}
                        </div>
                      </div>
                      <div className="rounded-md border border-[#343a40] bg-[#101214] p-3 text-xs leading-5 text-[#cdd3d8]">
                        Raw query text is hidden in the commercial workspace. Use lineage, metric formula, and validation status for review.
                      </div>
                    </Surface>
                  )}
                </div>
              </Panel>

              <Panel>
                <PanelHeader title="Save Result" subtitle="Actions update the persisted model state and consumer counters." />
                <div className="grid gap-2 p-4">
                  <Button variant="secondary" onClick={() => saveExploreArtifact('query')}><Save className="h-4 w-4" /> Saved Query ({model.explore.savedQueryCount})</Button>
                  <Button variant="secondary" onClick={() => saveExploreArtifact('dashboard')}><LayoutDashboard className="h-4 w-4" /> Add Dashboard ({model.explore.dashboardAdds})</Button>
                  <Button variant="secondary" onClick={() => saveExploreArtifact('skill')}><DatabaseZap className="h-4 w-4" /> Create Data Skill ({model.explore.skillDrafts})</Button>
                  <Button variant="secondary" onClick={() => saveExploreArtifact('example')}><FilePlus2 className="h-4 w-4" /> Confirmed Example ({model.explore.confirmedExamples})</Button>
                </div>
              </Panel>

              <Panel>
                <PanelHeader title="Next Step" subtitle="Advanced WrenAI-style modeling is available after review." />
                <div className="p-4">
                  <Button className="w-full" variant="brand-primary" onClick={onReviewModel}>
                    <Search className="h-4 w-4" />
                    Review model
                  </Button>
                </div>
              </Panel>
            </aside>
          </div>
        </section>
      </div>
    </main>
  )
}

function Select({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: string[][] }) {
  return (
    <label className="block min-w-0 text-xs text-[#818c95]">
      {label}
      <select value={value} onChange={event => onChange(event.target.value)} className={`mt-1 h-9 w-full rounded-md px-3 text-sm focus-visible:outline-none focus-visible:ring-1 ${modelingStyles.input}`}>
        {options.map(([id, text]) => <option key={id} value={id} className="bg-[#15181b]">{text}</option>)}
      </select>
    </label>
  )
}

function ViewButton({ active, onClick, icon, label }: { active: boolean; onClick: () => void; icon: React.ReactNode; label: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`${modelingStyles.segmentedItem} inline-flex items-center gap-2 ${active ? 'bg-brand-orange text-white hover:bg-brand-orange' : ''}`}
    >
      {icon}
      {label}
    </button>
  )
}

function Kpi({ label, value, sub }: { label: string; value: string; sub: string }) {
  return <MetricTile label={label} value={value} sub={sub} />
}

function TrendChart({ points }: { points: Array<{ period: string; value: number }> }) {
  const max = Math.max(...points.map(point => point.value))
  return (
    <div className="mt-5 h-[340px] rounded-md border border-[#263038] bg-[#0f1113] p-4">
      <div className="flex h-[270px] items-end gap-3 border-b border-l border-[#263038] px-2 pb-2">
        {points.map(point => (
          <div key={point.period} className="flex min-w-0 flex-1 flex-col items-center gap-2">
            <div className="w-full rounded-t border border-brand-orange/30 bg-brand-orange/80 shadow-[0_0_18px_rgba(249,115,22,0.08)]" style={{ height: `${Math.max(18, point.value / max * 240)}px` }} />
            <span className="text-xs text-[#87929b]">{point.period}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function EmptyQueryResult({ published }: { published: boolean }) {
  return (
    <div className="mt-5 flex min-h-[300px] flex-col items-center justify-center rounded-md border border-dashed border-[#3a4147] bg-[#111315] p-6 text-center">
      <DatabaseZap className="mb-3 h-6 w-6 text-[#7f8a93]" />
      <h3 className="text-sm font-semibold text-[#f3f5f5]">{published ? 'Run query_metric to load semantic results' : 'Publish before querying'}</h3>
      <p className="mt-2 max-w-md text-sm leading-6 text-[#9aa4ac]">
        {published
          ? 'Explore does not synthesize chart data. Results appear here only after the backend semantic query succeeds.'
          : 'MCP and Agent consumers use published Semantic Model versions only. Validate and publish this draft before running query_metric.'}
      </p>
    </div>
  )
}

function Breakdown({ rows }: { rows: Array<Record<string, string | number>> }) {
  const keys = Object.keys(rows[0] ?? {})
  const labelKey = keys[0]
  const valueKey = keys[1]
  return (
    <Surface className="p-4">
      <div className="mb-3 text-sm font-semibold text-[#f3f5f5]">Dimension breakdown</div>
      <div className="grid gap-2 md:grid-cols-3">
        {rows.slice(0, 3).map((row, index) => (
          <div key={`${String(row[labelKey])}-${index}`} className="rounded-md border border-[#2d3338] bg-[#0f1113] p-3">
            <div className="text-sm text-[#f3f5f5]">{row[labelKey]}</div>
            <div className="mt-1 text-lg font-semibold text-[#f3f5f5]">{row[valueKey]}</div>
            <div className="mt-2 h-1.5 rounded bg-[#2b3136]">
              <div className="h-full rounded bg-brand-orange" style={{ width: `${85 - index * 18}%` }} />
            </div>
          </div>
        ))}
      </div>
    </Surface>
  )
}

function ResultTable({ rows, pivot }: { rows: Array<Record<string, string | number>>; pivot: boolean }) {
  const keys = Object.keys(rows[0] ?? {})
  return (
    <div className="mt-5 overflow-x-auto rounded-md border border-[#2d3338] custom-scrollbar">
      <table className="min-w-[620px] w-full text-left text-sm">
        <thead className={modelingStyles.tableHead}>
          <tr>
            {keys.map(key => <th key={key} className="px-3 py-2 font-medium">{pivot && key === keys[0] ? `${key} bucket` : key}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className={modelingStyles.tableRow}>
              {keys.map(key => <td key={key} className="px-3 py-2 text-[#d6dde2]">{String(row[key])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
