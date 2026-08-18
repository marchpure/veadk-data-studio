import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Boxes, Database, GitBranch, Layers3, Plus, RefreshCcw, Search, ShieldCheck, Workflow } from 'lucide-react'
import { Button } from '../../../components/ui/button'
import { Input } from '../../../components/ui/input'
import { useKnowledgeCenterPath } from '../../../contexts/EmbeddedModeContext'
import { CreateModelPanel } from '../components/CreateModelPanel'
import { EmptyState, ErrorState, MetricTile, PermissionState, ScoreBar, StatusPill, modelingStyles } from '../components/modelingUi'
import { useDataModelingStore } from '../store/useDataModelingStore'
import type { SemanticModel } from '../types'

export default function DataModelsHomePage() {
  const kcPath = useKnowledgeCenterPath()
  const [createOpen, setCreateOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState<'all' | 'Draft' | 'Published'>('all')
  const [domain, setDomain] = useState('all')
  const homeMode = useDataModelingStore(state => state.homeMode)
  const homeLoading = useDataModelingStore(state => state.homeLoading)
  const homeError = useDataModelingStore(state => state.homeError)
  const visibleModels = useDataModelingStore(state => state.visibleModels)
  const loadModels = useDataModelingStore(state => state.loadModels)
  const setHomeMode = useDataModelingStore(state => state.setHomeMode)
  const reloadWorkspace = useDataModelingStore(state => state.reloadWorkspace)
  const setActiveModel = useDataModelingStore(state => state.setActiveModel)

  useEffect(() => {
    void loadModels(homeMode)
  }, [homeMode, loadModels])

  const domains = useMemo(() => Array.from(new Set(visibleModels.map(model => model.domain))), [visibleModels])
  const filteredModels = useMemo(() => {
    const lower = query.trim().toLowerCase()
    return visibleModels.filter(model => {
      const textMatch = !lower || [model.name, model.domain, model.owner, model.datasource].some(value => value.toLowerCase().includes(lower))
      const statusMatch = status === 'all' || model.status === status
      const domainMatch = domain === 'all' || model.domain === domain
      return textMatch && statusMatch && domainMatch
    })
  }, [visibleModels, query, status, domain])

  const totalConsumers = filteredModels.reduce((total, model) => total + model.consumers.agents + model.consumers.mcp + model.consumers.skills, 0)

  return (
    <div className={`${modelingStyles.page} p-4 md:p-6`}>
      <div className="mx-auto flex max-w-[1480px] flex-col gap-5">
        <header className="grid gap-4 border-b border-[#30363a] pb-5 xl:grid-cols-[minmax(0,1fr)_420px] xl:items-end">
          <div className="min-w-0 rounded-lg border border-[#2d3439] bg-[#16191c] p-4">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-xl font-semibold text-[#f3f5f5]">Data Models</h1>
              <StatusPill tone="info">Semantic Model workspace</StatusPill>
            </div>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[#a4adb5]">
              Datasources are raw data. Data Models define the business contract used by Agent, MCP, Saved Query, Dashboard, and future Data Skills.
            </p>
            <div className="mt-4 grid gap-2 text-xs text-[#9aa4ac] sm:grid-cols-3">
              <HeaderSignal icon={<Database className="h-4 w-4" />} label="Source first" value="Oracle / Postgres / MySQL / SQLite" />
              <HeaderSignal icon={<GitBranch className="h-4 w-4" />} label="Governed layer" value="Entities, metrics, relationships" />
              <HeaderSignal icon={<Workflow className="h-4 w-4" />} label="Consumers" value="Agent, MCP, dashboard, skills" />
            </div>
          </div>
          <div className="rounded-lg border border-[#2d3439] bg-[#16191c] p-4">
            <div className="text-[11px] font-medium uppercase text-[#818c95]">Modeling state</div>
            <div className="mt-3 grid grid-cols-3 gap-2">
              <MiniStat label="Published" value={String(visibleModels.filter(model => model.status === 'Published').length)} />
              <MiniStat label="Draft" value={String(visibleModels.filter(model => model.status === 'Draft').length)} />
              <MiniStat label="Ready" value={`${Math.round(avg(filteredModels.map(model => model.readiness)))}%`} />
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button variant="secondary" onClick={reloadWorkspace}><RefreshCcw className="h-4 w-4" /> Refresh</Button>
              <Button variant="brand-primary" onClick={() => setCreateOpen(true)}><Plus className="h-4 w-4" /> Generate from Data</Button>
            </div>
          </div>
        </header>

        <section className="grid gap-3 md:grid-cols-4">
          <Summary icon={<Layers3 className="h-4 w-4" />} label="Models" value={String(filteredModels.length)} detail={`${visibleModels.length} total`} />
          <Summary icon={<ShieldCheck className="h-4 w-4" />} label="Avg Readiness" value={`${Math.round(avg(filteredModels.map(model => model.readiness)))}%`} detail="publish gate" />
          <Summary icon={<GitBranch className="h-4 w-4" />} label="Drift Alerts" value={String(filteredModels.reduce((total, model) => total + model.driftAlerts, 0))} detail="schema checks" />
          <Summary icon={<Boxes className="h-4 w-4" />} label="Semantic Consumers" value={String(totalConsumers)} detail="Agent / MCP / Skill" />
        </section>

        <section className={modelingStyles.panel}>
          <div className="flex flex-col gap-3 border-b border-[#30363a] p-3 lg:flex-row lg:items-center">
            <div className="relative min-w-0 flex-1">
              <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-[#7f8a93]" />
              <Input
                value={query}
                onChange={event => setQuery(event.target.value)}
                placeholder="Search models, domains, owners, datasources"
                className={`${modelingStyles.input} pl-9`}
                aria-label="Search Data Models"
              />
            </div>
            <div className="flex flex-wrap gap-2">
              <Select label="Status" value={status} onChange={value => setStatus(value as 'all' | 'Draft' | 'Published')} options={['all', 'Draft', 'Published']} />
              <Select label="Domain" value={domain} onChange={setDomain} options={['all', ...domains]} />
            </div>
          </div>

          <div className="p-3">
            {homeLoading && <LoadingRows />}
            {!homeLoading && homeError && homeMode === 'permission' && <PermissionState action={<Button variant="secondary" onClick={() => setHomeMode('ready')}>Return to Ready</Button>} />}
            {!homeLoading && homeError && homeMode !== 'permission' && <ErrorState title="Unable to load Data Models" body={homeError} action={<Button variant="secondary" onClick={() => setHomeMode('ready')}>Retry Ready State</Button>} />}
            {!homeLoading && !homeError && filteredModels.length === 0 && (
              <EmptyState
                title="No Data Models in this view"
                body="Generate a Semantic Model from an available datasource, then validate and publish it before Agent or MCP consumers use it."
                action={<Button variant="brand-primary" onClick={() => setCreateOpen(true)}><Plus className="h-4 w-4" /> Generate from Data</Button>}
              />
            )}
            {!homeLoading && !homeError && filteredModels.length > 0 && <ModelTable models={filteredModels} onOpen={setActiveModel} toPath={kcPath} />}
          </div>
        </section>
      </div>
      <CreateModelPanel open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  )
}

function ModelTable({ models, onOpen, toPath }: { models: SemanticModel[]; onOpen: (id: string) => void; toPath: (path: string) => string }) {
  return (
    <div className="overflow-x-auto rounded-md border border-[#2d3338] custom-scrollbar">
      <table className="min-w-[1060px] w-full text-left text-sm">
        <thead className={modelingStyles.tableHead}>
          <tr>
            <th className="px-4 py-2.5 font-medium">Model</th>
            <th className="px-3 py-2 font-medium">Domain</th>
            <th className="px-3 py-2 font-medium">Owner</th>
            <th className="px-3 py-2 font-medium">Datasource</th>
            <th className="px-3 py-2 font-medium">Status</th>
            <th className="px-3 py-2 font-medium">Version</th>
            <th className="px-3 py-2 font-medium">Readiness</th>
            <th className="px-3 py-2 font-medium">Drift</th>
            <th className="px-3 py-2 font-medium">Consumers</th>
          </tr>
        </thead>
        <tbody>
          {models.map(model => (
            <tr key={model.id} className={modelingStyles.tableRow}>
              <td className="px-4 py-3">
                <Link
                  to={toPath(`/data-models/${model.id}`)}
                  onClick={() => onOpen(model.id)}
                  className="font-semibold text-[#f3f5f5] underline-offset-4 hover:text-brand-orange hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                >
                  {model.name}
                </Link>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-[#7f8a93]">
                  <span>Updated {model.updatedAt}</span>
                  <span className="h-1 w-1 rounded-full bg-[#4b555e]" />
                  <span>{model.entities.length} entities</span>
                  <span>{model.metrics.length} metrics</span>
                </div>
              </td>
              <td className="px-3 py-3"><StatusPill>{model.domain}</StatusPill></td>
              <td className="px-3 py-3 text-[#d6dde2]">{model.owner}</td>
              <td className="px-3 py-3">
                <div className="max-w-[190px] truncate text-[#d6dde2]">{model.datasource}</div>
                <div className="mt-1 text-xs text-[#7f8a93]">{model.datasourceId}</div>
              </td>
              <td className="px-3 py-3"><StatusPill tone={model.status === 'Published' ? 'ready' : 'warning'}>{model.status}</StatusPill></td>
              <td className="px-3 py-3 text-xs text-[#d6dde2]">
                <div>{model.draftRevision}</div>
                <div className="mt-1 text-[#7f8a93]">{model.publishedVersion}</div>
              </td>
              <td className="px-3 py-3"><ScoreBar value={model.readiness} level={model.readinessLevel} /></td>
              <td className="px-3 py-3">
                <StatusPill tone={model.driftAlerts > 0 ? 'warning' : 'ready'}>{model.driftAlerts}</StatusPill>
              </td>
              <td className="px-3 py-3 text-xs text-[#d6dde2]">
                <div className="grid grid-cols-3 gap-1">
                  <Consumer label="Agent" value={model.consumers.agents} />
                  <Consumer label="MCP" value={model.consumers.mcp} />
                  <Consumer label="Skill" value={model.consumers.skills} />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function LoadingRows() {
  return (
    <div className="space-y-2" aria-label="Loading Data Models">
      {Array.from({ length: 5 }).map((_, index) => (
        <div key={index} className="h-14 animate-pulse rounded border border-[#2d3338] bg-[#181b1f]" />
      ))}
    </div>
  )
}

function HeaderSignal({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-md border border-[#2a3136] bg-[#121518] p-3">
      <div className="flex items-center gap-2 text-[#cdd3d8]">
        <span className="text-brand-orange">{icon}</span>
        <span className="font-medium">{label}</span>
      </div>
      <div className="mt-1 truncate text-[#818c95]">{value}</div>
    </div>
  )
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-[#2a3136] bg-[#121518] p-3">
      <div className="text-lg font-semibold text-[#f3f5f5]">{value}</div>
      <div className="mt-1 text-xs text-[#818c95]">{label}</div>
    </div>
  )
}

function Consumer({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded border border-[#2a3136] bg-[#121518] px-2 py-1">
      <div className="font-medium tabular-nums text-[#f3f5f5]">{value}</div>
      <div className="mt-0.5 text-[10px] uppercase text-[#818c95]">{label}</div>
    </div>
  )
}

function Summary({ icon, label, value, detail }: { icon: React.ReactNode; label: string; value: string; detail: string }) {
  return (
    <MetricTile
      label={label}
      value={value}
      sub={<span className="flex items-center gap-1 text-[#9aa4ac]"><span className="text-brand-orange">{icon}</span> {detail}</span>}
    />
  )
}

function Select({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: string[] }) {
  return (
    <label className="flex items-center gap-2 rounded-md border border-[#343a40] bg-[#0f1113] px-2">
      <span className="text-xs text-[#818c95]">{label}</span>
      <select
        value={value}
        onChange={event => onChange(event.target.value)}
        className="h-8 bg-transparent text-sm text-[#f3f5f5] focus-visible:outline-none"
      >
        {options.map(option => <option key={option} value={option} className="bg-[#15181b]">{option}</option>)}
      </select>
    </label>
  )
}

function avg(values: number[]) {
  if (values.length === 0) return 0
  return values.reduce((total, value) => total + value, 0) / values.length
}
