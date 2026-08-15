import { useState } from 'react'
import { BarChart3, Bot, DatabaseZap, FilePlus2, GitBranch, LayoutDashboard, Save, Search, Table2 } from 'lucide-react'
import { Button } from '../../../components/ui/button'
import { selectExploreResult, useDataModelingStore } from '../store/useDataModelingStore'
import { Panel, PanelHeader, SectionTitle, StatusPill } from '../components/modelingUi'
import type { ExploreState, SemanticModel, TimeGrain } from '../types'

export function SemanticExploreWorkspace({ model, onReviewModel }: { model: SemanticModel; onReviewModel: () => void }) {
  const updateExplore = useDataModelingStore(state => state.updateExplore)
  const saveExploreArtifact = useDataModelingStore(state => state.saveExploreArtifact)
  const [explanationOpen, setExplanationOpen] = useState(false)
  const [agentQuestion, setAgentQuestion] = useState('Why did paid revenue change by region?')
  const result = selectExploreResult(model)
  const metric = model.metrics.find(item => item.id === model.explore.metricId) ?? model.metrics[0]
  const dimension = model.dimensions.find(item => item.id === model.explore.dimensionId) ?? model.dimensions[0]

  return (
    <main className="min-h-0 flex-1 overflow-y-auto bg-[#171717] p-3 custom-scrollbar">
      <div className="mx-auto grid max-w-[1500px] gap-4">
        <div className="rounded-md border border-brand-orange/25 bg-brand-orange/10 px-4 py-3 text-sm text-[#f4d0bd]">
          The current draft exposes 5 metrics and 7 dimensions from 8 profiled tables; 2 suggestions still need review.
        </div>
        <section className="rounded-md border border-[#2a2a2a] bg-[#1f1f1f]">
          <div className="grid gap-3 border-b border-[#2a2a2a] p-3 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-center">
            <div className="grid min-w-0 gap-2 md:grid-cols-2 xl:grid-cols-[minmax(180px,1fr)_minmax(180px,1fr)_120px_150px_minmax(180px,1fr)_minmax(180px,1fr)]">
              <Select label="Metric" value={model.explore.metricId} onChange={value => updateExplore({ metricId: value })} options={model.metrics.map(item => [item.id, item.businessName])} />
              <Select label="Dimension" value={model.explore.dimensionId} onChange={value => updateExplore({ dimensionId: value })} options={model.dimensions.map(item => [item.id, item.name])} />
              <Select label="Grain" value={model.explore.grain} onChange={value => updateExplore({ grain: value as TimeGrain })} options={[['day', 'Day'], ['week', 'Week'], ['month', 'Month'], ['quarter', 'Quarter']]} />
              <Select label="Range" value={model.explore.timeRange} onChange={value => updateExplore({ timeRange: value as ExploreState['timeRange'] })} options={[['30d', 'Last 30d'], ['90d', 'Last 90d'], ['ytd', 'YTD'], ['12m', 'Last 12m']]} />
              <label className="block min-w-0 text-xs text-[#9a9a9a]">
                Filter
                <input
                  value={model.explore.filter}
                  onChange={event => updateExplore({ filter: event.target.value })}
                  className="mt-1 h-9 w-full rounded-md border border-[#333] bg-[#151515] px-3 font-mono text-xs text-white focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                />
              </label>
              <label className="block min-w-0 text-xs text-[#9a9a9a]">
                Ask Agent
                <input
                  value={agentQuestion}
                  onChange={event => setAgentQuestion(event.target.value)}
                  className="mt-1 h-9 w-full rounded-md border border-[#333] bg-[#151515] px-3 text-sm text-white focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                />
              </label>
            </div>
            <div className="flex flex-wrap items-center gap-2 xl:justify-end">
              <ViewButton active={model.explore.viewMode === 'trend'} onClick={() => updateExplore({ viewMode: 'trend' })} icon={<BarChart3 className="h-4 w-4" />} label="Trend" />
              <ViewButton active={model.explore.viewMode === 'table'} onClick={() => updateExplore({ viewMode: 'table' })} icon={<Table2 className="h-4 w-4" />} label="Table" />
              <ViewButton active={model.explore.viewMode === 'pivot'} onClick={() => updateExplore({ viewMode: 'pivot' })} icon={<GitBranch className="h-4 w-4" />} label="Pivot" />
            </div>
          </div>

          <div className="grid gap-4 p-4 xl:grid-cols-[minmax(0,1fr)_340px]">
            <div className="min-w-0 space-y-4">
              <div className="grid gap-3 md:grid-cols-4">
                <Kpi label="Current value" value={result.kpi} sub={result.delta} />
                <Kpi label="Metric" value={metric.businessName} sub={metric.certification} />
                <Kpi label="Dimension" value={dimension.name} sub={dimension.description} />
                <Kpi label="Model" value={model.publishedVersion} sub={`${model.readiness}% readiness`} />
              </div>

              <div className="rounded-md border border-[#2a2a2a] bg-[#181818] p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <h2 className="text-sm font-semibold text-white">{metric.businessName} by {dimension.name}</h2>
                    <p className="mt-1 text-xs text-[#9a9a9a]">{model.explore.grain} · {model.explore.timeRange} · semantic query result</p>
                  </div>
                  <StatusPill tone="ready">compiled</StatusPill>
                </div>
                {model.explore.viewMode === 'trend' && <TrendChart points={result.trend} />}
                {(model.explore.viewMode === 'table' || model.explore.viewMode === 'pivot') && <ResultTable rows={result.rows} pivot={model.explore.viewMode === 'pivot'} />}
              </div>

              <Breakdown rows={result.rows} />
            </div>

            <aside className="min-w-0 space-y-4">
              <Panel>
                <PanelHeader title="Agent" subtitle="Ask about the current semantic result" action={<Button size="sm" variant="secondary"><Bot className="h-4 w-4" /> Ask</Button>} />
                <div className="space-y-3 p-4">
                  <p className="text-sm text-[#d6d6d6]">The selected view answers: {agentQuestion}</p>
                  <Button className="w-full" variant="secondary" onClick={() => setExplanationOpen(value => !value)}>Why this calculation</Button>
                  {explanationOpen && (
                    <div className="space-y-3 rounded-md border border-[#2a2a2a] bg-[#181818] p-3">
                      <p className="text-sm text-[#d6d6d6]">{metric.preview.explanation}</p>
                      <div>
                        <SectionTitle>Lineage</SectionTitle>
                        <div className="mt-2 flex flex-wrap gap-2">
                          {metric.lineage.map(item => <StatusPill key={item}>{item}</StatusPill>)}
                        </div>
                      </div>
                      <pre className="max-h-48 overflow-auto rounded-md border border-[#333] bg-[#101010] p-3 text-xs text-[#cfcfcf] custom-scrollbar">{metric.preview.sql}</pre>
                    </div>
                  )}
                </div>
              </Panel>

              <Panel>
                <PanelHeader title="Save Result" subtitle="Actions create semantic consumers against the current model version." />
                <div className="grid gap-2 p-4">
                  <Button variant="secondary" onClick={() => saveExploreArtifact('query')}><Save className="h-4 w-4" /> Saved Query ({model.explore.savedQueryCount})</Button>
                  <Button variant="secondary" onClick={() => saveExploreArtifact('dashboard')}><LayoutDashboard className="h-4 w-4" /> Add Dashboard ({model.explore.dashboardAdds})</Button>
                  <Button variant="secondary" onClick={() => saveExploreArtifact('skill')}><DatabaseZap className="h-4 w-4" /> Create Data Skill ({model.explore.skillDrafts})</Button>
                  <Button variant="secondary" onClick={() => saveExploreArtifact('example')}><FilePlus2 className="h-4 w-4" /> Confirmed Example ({model.explore.confirmedExamples})</Button>
                </div>
              </Panel>

              <Panel>
                <PanelHeader title="Next Step" subtitle="Open advanced modeling when the Explore answer needs definition changes." />
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
    <label className="block min-w-0 text-xs text-[#9a9a9a]">
      {label}
      <select value={value} onChange={event => onChange(event.target.value)} className="mt-1 h-9 w-full rounded-md border border-[#333] bg-[#151515] px-3 text-sm text-white focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring">
        {options.map(([id, text]) => <option key={id} value={id} className="bg-[#1a1a1a]">{text}</option>)}
      </select>
    </label>
  )
}

function ViewButton({ active, onClick, icon, label }: { active: boolean; onClick: () => void; icon: React.ReactNode; label: string }) {
  return (
    <Button size="sm" variant={active ? 'brand-primary' : 'secondary'} onClick={onClick} aria-pressed={active}>
      {icon}
      {label}
    </Button>
  )
}

function Kpi({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="rounded-md border border-[#2a2a2a] bg-[#181818] p-3">
      <div className="text-xs uppercase text-[#858585]">{label}</div>
      <div className="mt-1 truncate text-xl font-semibold text-white">{value}</div>
      <div className="mt-1 line-clamp-2 text-xs text-[#9a9a9a]">{sub}</div>
    </div>
  )
}

function TrendChart({ points }: { points: Array<{ period: string; value: number }> }) {
  const max = Math.max(...points.map(point => point.value))
  return (
    <div className="mt-5 h-[340px] rounded-md border border-[#2a2a2a] bg-[#151515] p-4">
      <div className="flex h-[270px] items-end gap-3">
        {points.map(point => (
          <div key={point.period} className="flex min-w-0 flex-1 flex-col items-center gap-2">
            <div className="w-full rounded-t bg-brand-orange/85" style={{ height: `${Math.max(18, point.value / max * 240)}px` }} />
            <span className="text-xs text-[#8d8d8d]">{point.period}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function Breakdown({ rows }: { rows: Array<Record<string, string | number>> }) {
  const keys = Object.keys(rows[0] ?? {})
  const labelKey = keys[0]
  const valueKey = keys[1]
  return (
    <div className="rounded-md border border-[#2a2a2a] bg-[#181818] p-4">
      <div className="mb-3 text-sm font-semibold text-white">Dimension breakdown</div>
      <div className="grid gap-2 md:grid-cols-3">
        {rows.slice(0, 3).map((row, index) => (
          <div key={String(row[labelKey])} className="rounded-md border border-[#2a2a2a] bg-[#151515] p-3">
            <div className="text-sm text-white">{row[labelKey]}</div>
            <div className="mt-1 text-lg font-semibold text-white">{row[valueKey]}</div>
            <div className="mt-2 h-1.5 rounded bg-[#303030]">
              <div className="h-full rounded bg-brand-orange" style={{ width: `${85 - index * 18}%` }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function ResultTable({ rows, pivot }: { rows: Array<Record<string, string | number>>; pivot: boolean }) {
  const keys = Object.keys(rows[0] ?? {})
  return (
    <div className="mt-5 overflow-x-auto rounded-md border border-[#2a2a2a] custom-scrollbar">
      <table className="min-w-[620px] w-full text-left text-sm">
        <thead className="bg-[#181818] text-xs uppercase text-[#858585]">
          <tr>
            {keys.map(key => <th key={key} className="px-3 py-2 font-medium">{pivot && key === keys[0] ? `${key} bucket` : key}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className="border-t border-[#292929] bg-[#151515]">
              {keys.map(key => <td key={key} className="px-3 py-2 text-[#d4d4d4]">{String(row[key])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
