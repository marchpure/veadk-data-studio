import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Boxes, Plus, RefreshCcw, Search } from 'lucide-react'
import { Button } from '../../../components/ui/button'
import { Input } from '../../../components/ui/input'
import { CreateModelPanel } from '../components/CreateModelPanel'
import { EmptyState, ErrorState, PermissionState, ScoreBar, StatusPill } from '../components/modelingUi'
import { useDataModelingStore } from '../store/useDataModelingStore'
import type { SemanticModel } from '../types'

export default function DataModelsHomePage() {
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
  const refreshWorkspace = useDataModelingStore(state => state.refreshWorkspace)
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
    <div className="min-h-full bg-[#171717] p-4 text-white md:p-6">
      <div className="mx-auto flex max-w-[1480px] flex-col gap-4">
        <header className="flex flex-col gap-3 border-b border-[#2a2a2a] pb-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-xl font-semibold text-white">Data Models</h1>
              <StatusPill tone="info">Semantic Model workspace</StatusPill>
            </div>
            <p className="mt-2 max-w-3xl text-sm text-[#a6a6a6]">
              Datasources are raw data. Data Models define the business contract used by Agent, MCP, Saved Query, Dashboard, and future Data Skills.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={refreshWorkspace}><RefreshCcw className="h-4 w-4" /> Refresh workspace</Button>
            <Button variant="brand-primary" onClick={() => setCreateOpen(true)}><Plus className="h-4 w-4" /> Generate from Data</Button>
          </div>
        </header>

        <section className="grid gap-3 md:grid-cols-4">
          <Summary label="Models" value={String(filteredModels.length)} />
          <Summary label="Avg Readiness" value={`${Math.round(avg(filteredModels.map(model => model.readiness)))}%`} />
          <Summary label="Drift Alerts" value={String(filteredModels.reduce((total, model) => total + model.driftAlerts, 0))} />
          <Summary label="Semantic Consumers" value={String(totalConsumers)} />
        </section>

        <section className="rounded-lg border border-[#2a2a2a] bg-[#1f1f1f]">
          <div className="flex flex-col gap-3 border-b border-[#2a2a2a] p-3 lg:flex-row lg:items-center">
            <div className="relative min-w-0 flex-1">
              <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-[#777]" />
              <Input
                value={query}
                onChange={event => setQuery(event.target.value)}
                placeholder="Search models, domains, owners, datasources"
                className="border-[#333] bg-[#151515] pl-9 text-white"
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
                body="Generate a model from a profiled datasource, or adjust the current filters."
                action={<Button variant="brand-primary" onClick={() => setCreateOpen(true)}><Plus className="h-4 w-4" /> Generate from Data</Button>}
              />
            )}
            {!homeLoading && !homeError && filteredModels.length > 0 && <ModelTable models={filteredModels} onOpen={setActiveModel} />}
          </div>
        </section>
      </div>
      <CreateModelPanel open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  )
}

function ModelTable({ models, onOpen }: { models: SemanticModel[]; onOpen: (id: string) => void }) {
  return (
    <div className="overflow-x-auto custom-scrollbar">
      <table className="min-w-[1050px] w-full text-left text-sm">
        <thead className="text-xs uppercase text-[#858585]">
          <tr className="border-b border-[#333]">
            <th className="px-3 py-2 font-medium">Model</th>
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
            <tr key={model.id} className="border-b border-[#292929] hover:bg-[#242424]">
              <td className="px-3 py-3">
                <Link
                  to={`/data-models/${model.id}`}
                  onClick={() => onOpen(model.id)}
                  className="font-medium text-white underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                >
                  {model.name}
                </Link>
                <div className="mt-1 text-xs text-[#8c8c8c]">Updated {model.updatedAt}</div>
              </td>
              <td className="px-3 py-3 text-[#d0d0d0]">{model.domain}</td>
              <td className="px-3 py-3 text-[#d0d0d0]">{model.owner}</td>
              <td className="px-3 py-3 text-[#d0d0d0]">{model.datasource}</td>
              <td className="px-3 py-3"><StatusPill tone={model.status === 'Published' ? 'ready' : 'warning'}>{model.status}</StatusPill></td>
              <td className="px-3 py-3 text-[#d0d0d0]">{model.draftRevision} / {model.publishedVersion}</td>
              <td className="px-3 py-3"><ScoreBar value={model.readiness} level={model.readinessLevel} /></td>
              <td className="px-3 py-3">
                <StatusPill tone={model.driftAlerts > 0 ? 'warning' : 'ready'}>{model.driftAlerts}</StatusPill>
              </td>
              <td className="px-3 py-3 text-xs text-[#d0d0d0]">
                Agent {model.consumers.agents} · MCP {model.consumers.mcp} · Skill {model.consumers.skills}
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
        <div key={index} className="h-14 animate-pulse rounded border border-[#292929] bg-[#202020]" />
      ))}
    </div>
  )
}

function Summary({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-[#2a2a2a] bg-[#1f1f1f] p-4">
      <div className="flex items-center gap-2 text-xs uppercase text-[#858585]"><Boxes className="h-4 w-4" /> {label}</div>
      <div className="mt-2 text-xl font-semibold text-white">{value}</div>
    </div>
  )
}

function Select({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: string[] }) {
  return (
    <label className="flex items-center gap-2 rounded-md border border-[#333] bg-[#151515] px-2">
      <span className="text-xs text-[#858585]">{label}</span>
      <select
        value={value}
        onChange={event => onChange(event.target.value)}
        className="h-8 bg-transparent text-sm text-white focus-visible:outline-none"
      >
        {options.map(option => <option key={option} value={option} className="bg-[#1a1a1a]">{option}</option>)}
      </select>
    </label>
  )
}

function avg(values: number[]) {
  if (values.length === 0) return 0
  return values.reduce((total, value) => total + value, 0) / values.length
}
