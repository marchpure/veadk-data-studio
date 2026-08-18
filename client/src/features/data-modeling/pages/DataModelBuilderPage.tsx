import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowLeft,
  Database,
  DatabaseZap,
  FileText,
  KeyRound,
  LayoutDashboard,
  Plus,
  Rocket,
  Search,
  Share2,
  ShieldCheck,
  Table2,
  Users,
  X,
} from 'lucide-react'
import { Button } from '../../../components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '../../../components/ui/dialog'
import { useKnowledgeCenterPath } from '../../../contexts/EmbeddedModeContext'
import DashboardWorkspacePage from '../../dashboard/pages/DashboardWorkspacePage'
import { EmptyState, MetricTile, Panel, PanelHeader, SectionTitle, StatusPill, Surface, modelingStyles } from '../components/modelingUi'
import { SemanticGraphWorkspace } from '../model/SemanticGraphWorkspace'
import { DataProfileWorkspace } from '../profile/DataProfileWorkspace'
import { selectActiveModel, useDataModelingStore } from '../store/useDataModelingStore'
import type { DataModelingDatasource, KnowledgeCenterStep, SemanticModel, WorkspaceMode } from '../types'

const steps: Array<{ id: KnowledgeCenterStep; label: string; detail: string }> = [
  { id: 'connectors', label: 'Connectors', detail: 'Workspace sources and this modeling scope' },
  { id: 'model', label: 'Modeling', detail: 'Structure, semantics, conflicts' },
  { id: 'dashboard', label: 'Dashboard', detail: 'Bound semantic version and gate context' },
  { id: 'publish', label: 'Evaluate Share', detail: 'Gate evidence and consumers' },
]

export default function DataModelBuilderPage() {
  const kcPath = useKnowledgeCenterPath()
  const params = useParams()
  const model = useDataModelingStore(selectActiveModel)
  const activeModelId = useDataModelingStore(state => state.activeModelId)
  const setActiveModel = useDataModelingStore(state => state.setActiveModel)
  const loadModel = useDataModelingStore(state => state.loadModel)
  const loadDatasources = useDataModelingStore(state => state.loadDatasources)
  const workspaceMode = useDataModelingStore(state => state.workspaceMode)
  const setWorkspaceMode = useDataModelingStore(state => state.setWorkspaceMode)
  const gate = useDataModelingStore(state => state.gate)
  const publishState = useDataModelingStore(state => state.publishState)

  useEffect(() => {
    void loadDatasources()
  }, [loadDatasources])

  useEffect(() => {
    if (params.modelId && params.modelId !== activeModelId) {
      setActiveModel(params.modelId)
      void loadModel(params.modelId)
    }
  }, [params.modelId, activeModelId, setActiveModel, loadModel])

  if (!model?.id) {
    return (
      <div className={`flex h-full min-h-0 flex-col p-4 ${modelingStyles.page}`}>
        <EmptyState title="Loading Data Model" body="The Semantic Model is being loaded from the backend. Return to the model list if this ID no longer exists." action={<Button asChild variant="secondary"><Link to={kcPath('/data-models')}>Back to models</Link></Button>} />
      </div>
    )
  }

  const stepState = statusForSteps(model, gate.blockers.length)

  return (
    <div className={`flex h-full min-h-0 flex-col overflow-hidden ${modelingStyles.page}`}>
      <header className="shrink-0 border-b border-[#30363a] bg-[#14181b]">
        <div className="grid gap-3 px-4 py-3 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-center">
          <div className="min-w-0">
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <Button asChild size="sm" variant="ghost" className="shrink-0"><Link to={kcPath('/data-models')}><ArrowLeft className="h-4 w-4" /> Models</Link></Button>
              <div className="min-w-0">
                <h1 className="truncate text-lg font-semibold leading-6 text-[#f3f5f5]">{model.name}</h1>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-[#9aa4ac]">
                  <span className="inline-flex items-center gap-1"><Database className="h-3.5 w-3.5 text-[#818c95]" /> {model.datasource}</span>
                  <span className="h-1 w-1 rounded-full bg-[#4b555e]" />
                  <span>{model.dataStudioAsset.freshness}</span>
                  <span className="h-1 w-1 rounded-full bg-[#4b555e]" />
                  <span>Knowledge Center journey</span>
                </div>
              </div>
            </div>
          </div>
          <div className="flex flex-wrap gap-2 xl:justify-end">
            <Button variant="secondary" onClick={() => setWorkspaceMode('model')}><ShieldCheck className="h-4 w-4" /> Review model</Button>
            <Button variant="brand-primary" onClick={() => setWorkspaceMode('publish')}><Rocket className="h-4 w-4" /> Evaluate share</Button>
          </div>
        </div>

        <div className="grid gap-2 border-t border-[#30363a] px-4 py-3 md:grid-cols-4">
          <ContextItem label="Knowledge asset" value={model.name} icon={<FileText className="h-4 w-4" />} />
          <ContextItem label="Modeler" value={model.owner} icon={<Users className="h-4 w-4" />} />
          <ContextItem label="Consumers" value={`${model.consumers.agents} Agent · ${model.consumers.dashboards} Dashboard · ${model.consumers.mcp} MCP`} icon={<DatabaseZap className="h-4 w-4" />} />
          <div className="rounded-md border border-[#2d3338] bg-[#111417] p-3">
            <div className="flex items-center justify-between gap-2">
              <div className="text-[11px] font-medium uppercase text-[#818c95]">Gate</div>
              <StatusPill tone={gate.blockers.length ? 'blocked' : publishState === 'published' ? 'ready' : 'warning'}>{publishState}</StatusPill>
            </div>
            <div className="mt-2 text-sm font-semibold text-[#f3f5f5]">{gate.score} score · {gate.passed}/{gate.total} checks</div>
          </div>
        </div>

        <div className="overflow-x-auto border-t border-[#30363a] px-4 py-3 custom-scrollbar">
          <div className="grid min-w-[820px] grid-cols-4 gap-2">
            {steps.map((step, index) => {
              const active = workspaceMode === step.id
              const state = stepState[step.id]
              return (
                <button
                  key={step.id}
                  type="button"
                  onClick={() => setWorkspaceMode(step.id)}
                  className={`min-w-0 rounded-md border p-3 text-left transition focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring ${
                    active ? 'border-brand-orange/70 bg-brand-orange/10' : 'border-[#2d3338] bg-[#111417] hover:border-[#46505a]'
                  }`}
                  aria-current={active ? 'step' : undefined}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-semibold uppercase text-[#f3f5f5]">Step {index + 1}</span>
                    <StatusPill tone={state === 'blocked' ? 'blocked' : state === 'complete' ? 'ready' : active ? 'info' : 'neutral'}>{state}</StatusPill>
                  </div>
                  <div className="mt-2 truncate text-sm font-semibold text-[#f3f5f5]">{step.label}</div>
                  <div className="mt-1 line-clamp-2 text-xs leading-5 text-[#9aa4ac]">{step.detail}</div>
                </button>
              )
            })}
          </div>
        </div>
      </header>

      {workspaceMode === 'connectors' && <ConnectorsStep model={model} />}
      {workspaceMode === 'model' && <SemanticGraphWorkspace model={model} />}
      {workspaceMode === 'dashboard' && <DashboardStep model={model} />}
      {workspaceMode === 'publish' && <PublishStep model={model} />}
    </div>
  )
}

function ConnectorsStep({ model }: { model: SemanticModel }) {
  const kcPath = useKnowledgeCenterPath()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const datasourceOptions = useDataModelingStore(state => state.datasourceOptions)
  const datasourceLoading = useDataModelingStore(state => state.datasourceLoading)
  const profiles = useDataModelingStore(state => state.profiles)
  const scope = useDataModelingStore(state => state.scope)
  const selectScopeSource = useDataModelingStore(state => state.selectScopeSource)
  const addScopeTable = useDataModelingStore(state => state.addScopeTable)
  const removeScopeItem = useDataModelingStore(state => state.removeScopeItem)
  const setWorkspaceMode = useDataModelingStore(state => state.setWorkspaceMode)

  const sourceId = scope.selectedSourceId || model.datasourceId
  const selectedSource = datasourceOptions.find(item => item.id === sourceId) ?? datasourceOptions[0]
  const profile = profiles.find(item => item.id === selectedSource?.id)
  const availableTables = profile?.tables ?? []

  useEffect(() => {
    if (!scope.selectedSourceId && selectedSource?.id) {
      selectScopeSource(selectedSource.id)
    }
  }, [scope.selectedSourceId, selectedSource?.id, selectScopeSource])

  return (
    <main className={`${modelingStyles.workspace} p-3`}>
      <div className="mx-auto grid max-w-[1500px] gap-4 xl:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
        <Panel>
          <PanelHeader
            title="Workspace Sources"
            subtitle="Sources are long-lived workspace assets. Switching source only changes what you are browsing here."
            action={<Button size="sm" variant="secondary" onClick={() => setDrawerOpen(true)}><Plus className="h-4 w-4" /> Add source</Button>}
          />
          <div className="space-y-3 p-4">
            {datasourceLoading && <div className="text-sm text-[#cdd3d8]">Loading sources...</div>}
            {!datasourceLoading && datasourceOptions.map(item => (
              <SourceButton
                key={item.id}
                item={item}
                selected={selectedSource?.id === item.id}
                onClick={() => selectScopeSource(item.id)}
              />
            ))}
          </div>
        </Panel>

        <div className="grid min-w-0 gap-4">
          <Panel>
            <PanelHeader
              title="This Modeling Scope"
              subtitle="The scope starts at zero for every journey and accumulates across source switches."
              action={<StatusPill tone={scope.items.length ? 'ready' : 'warning'}>{scope.items.length} selected</StatusPill>}
            />
            <div className="grid gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_360px]">
              <div className="min-w-0">
                <SectionTitle>Available tables from current source</SectionTitle>
                {availableTables.length === 0 && (
                  <div className="mt-3 rounded-md border border-[#2d3338] bg-[#121518] p-4 text-sm leading-6 text-[#9aa4ac]">
                    Select a supported source with a loaded profile to add tables to this run.
                  </div>
                )}
                {availableTables.length > 0 && (
                  <div className="mt-3 grid gap-2 md:grid-cols-2">
                    {availableTables.map(table => {
                      const selected = scope.items.some(item => item.sourceId === selectedSource?.id && item.tableName === table.name)
                      return (
                        <button
                          key={table.name}
                          type="button"
                          onClick={() => addScopeTable(table.name)}
                          disabled={selected}
                          className={`min-w-0 rounded-md border p-3 text-left transition focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed ${
                            selected ? 'border-emerald-500/30 bg-emerald-500/10' : 'border-[#2d3338] bg-[#121518] hover:border-brand-orange/50'
                          }`}
                        >
                          <div className="flex items-center gap-2">
                            <Table2 className="h-4 w-4 shrink-0 text-brand-orange" />
                            <span className="truncate text-sm font-semibold text-[#f3f5f5]">{table.name}</span>
                          </div>
                          <div className="mt-2 flex flex-wrap gap-2">
                            <StatusPill>{table.category}</StatusPill>
                            <StatusPill>{formatNumber(table.rowCount)} rows</StatusPill>
                          </div>
                        </button>
                      )
                    })}
                  </div>
                )}
              </div>

              <Surface className="p-4">
                <SectionTitle>Selected run scope</SectionTitle>
                {scope.items.length === 0 && (
                  <div className="mt-3 rounded-md border border-dashed border-[#3a4147] bg-[#0f1113] p-4 text-sm leading-6 text-[#9aa4ac]">
                    Scope is 0. Add fact, dimension, or bridge tables for this modeling run.
                  </div>
                )}
                {scope.items.length > 0 && (
                  <div className="mt-3 space-y-2">
                    {scope.items.map(item => (
                      <div key={item.id} className="flex min-w-0 items-center gap-2 rounded-md border border-[#2d3338] bg-[#0f1113] p-2">
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-sm font-medium text-[#f3f5f5]">{item.label}</div>
                          <div className="mt-1 text-xs text-[#818c95]">{item.category} · {formatNumber(item.rowCount)} rows</div>
                        </div>
                        <Button size="icon" variant="ghost" onClick={() => removeScopeItem(item.id)} aria-label={`Remove ${item.tableName}`}><X className="h-4 w-4" /></Button>
                      </div>
                    ))}
                  </div>
                )}
                <Button className="mt-4 w-full" variant="brand-primary" onClick={() => setWorkspaceMode('model')} disabled={scope.items.length === 0}>
                  Continue to modeling
                </Button>
              </Surface>
            </div>
          </Panel>

          {profile && <Panel><PanelHeader title="Current Source Profile" subtitle="Profile evidence is source-level context, not the selected run scope." /><div className="p-4"><DataProfileWorkspace profile={profile} /></div></Panel>}
        </div>
      </div>

      <Dialog open={drawerOpen} onOpenChange={setDrawerOpen}>
        <DialogContent className="left-auto right-0 top-0 h-full max-h-none w-[92vw] max-w-md translate-x-0 translate-y-0 overflow-y-auto border-[#30363a] bg-[#15181b] p-0 text-[#f3f5f5] sm:rounded-none custom-scrollbar">
          <DialogHeader className="border-b border-[#30363a] p-4">
            <DialogTitle className="text-base">Add Workspace Source</DialogTitle>
            <DialogDescription className="text-[#9aa4ac]">Connector setup stays outside the four-step modeling flow.</DialogDescription>
          </DialogHeader>
          <div className="grid gap-3 p-4">
            {['Database', 'Warehouse', 'Document', 'Object storage', 'API'].map(kind => (
              <Surface key={kind} className="p-3">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-[#f3f5f5]">{kind}</div>
                    <div className="mt-1 text-xs text-[#9aa4ac]">Opens the source connector setup outside this journey.</div>
                  </div>
                  <Button size="sm" variant="secondary" asChild><Link to={kcPath('/sources')}>Open</Link></Button>
                </div>
              </Surface>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    </main>
  )
}

function DashboardStep({ model }: { model: SemanticModel }) {
  return (
    <main className={`${modelingStyles.workspace} p-3`}>
      <div className="mx-auto grid max-w-[1500px] gap-4">
        <Panel>
          <PanelHeader
            title="Dashboard Context"
            subtitle="The dashboard workspace keeps its render, filter, and edit logic unchanged. This step only wraps it with knowledge asset context."
            action={<StatusPill tone={model.gate.blockers.length ? 'blocked' : 'ready'}>{model.gate.score} gate score</StatusPill>}
          />
          <div className="grid gap-3 p-4 md:grid-cols-3">
            <MetricTile label="Bound semantic version" value={model.publishedVersion} sub={model.publishState} />
            <MetricTile label="Dashboard metrics" value={String(model.metrics.length)} sub="entering dashboard canvas" />
            <MetricTile label="Gate state" value={`${model.gate.passed}/${model.gate.total}`} sub={model.gate.blockers.length ? `${model.gate.blockers.length} blockers` : 'ready to share'} />
          </div>
        </Panel>
        <div className="overflow-hidden rounded-lg border border-[#2d3439] bg-[#0d0f11]">
          <DashboardWorkspacePage embedded />
        </div>
      </div>
    </main>
  )
}

function PublishStep({ model }: { model: SemanticModel }) {
  const gate = useDataModelingStore(state => state.gate)
  const publishState = useDataModelingStore(state => state.publishState)
  const runKnowledgeGate = useDataModelingStore(state => state.runKnowledgeGate)
  const publishKnowledgeAsset = useDataModelingStore(state => state.publishKnowledgeAsset)
  const setWorkspaceMode = useDataModelingStore(state => state.setWorkspaceMode)
  const blocked = gate.blockers.length > 0 || publishState === 'validating'

  return (
    <main className={`${modelingStyles.workspace} p-3`}>
      <div className="mx-auto grid max-w-[1500px] gap-4 xl:grid-cols-[minmax(0,1fr)_400px]">
        <div className="space-y-4">
          {gate.blockers.length > 0 && (
            <div className="rounded-md border border-red-500/30 bg-red-500/10 p-4">
              <div className="flex items-center gap-2 text-sm font-semibold text-red-100">
                <AlertTriangle className="h-4 w-4" />
                Publish blockers
              </div>
              <div className="mt-3 grid gap-2">
                {gate.blockers.map((blocker, index) => (
                  <div key={`${blocker}-${index}`} className="rounded border border-red-500/20 bg-[#140f10] p-2 text-sm leading-6 text-red-100/85">{blocker}</div>
                ))}
              </div>
            </div>
          )}

          <Panel>
            <PanelHeader
              title="Gate Results"
              subtitle="Every failed case carries a concrete reason and the evidence needed to fix it."
              action={<Button size="sm" variant="brand-primary" onClick={runKnowledgeGate}>{publishState === 'validating' ? 'Evaluating...' : 'Run evaluation'}</Button>}
            />
            <div className="grid gap-4 p-4 md:grid-cols-[260px_minmax(0,1fr)]">
              <div className="grid gap-3">
                <MetricTile label="Gate score" value={String(gate.score)} sub={gate.blockers.length ? 'blocked' : 'passing'} />
                <MetricTile label="Passed checks" value={`${gate.passed}/${gate.total}`} sub={gate.evaluated ? 'last run complete' : 'pending run'} />
              </div>
              <div className="grid gap-3">
                {gate.checks.map(check => (
                  <Surface key={check.id} className="p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="text-sm font-semibold text-[#f3f5f5]">{check.title}</div>
                      <StatusPill tone={check.status === 'passed' ? 'ready' : 'blocked'}>{check.status}</StatusPill>
                    </div>
                    <p className={`mt-2 text-sm leading-6 ${check.status === 'passed' ? 'text-emerald-100/80' : 'text-red-100/85'}`}>{check.reason}</p>
                    <div className="mt-3 grid gap-2 md:grid-cols-3">
                      <Evidence label="SQL" value={check.evidence.sql} />
                      <Evidence label="Document chapter" value={check.evidence.doc} />
                      <Evidence label="Permission policy" value={check.evidence.policy} />
                    </div>
                  </Surface>
                ))}
              </div>
            </div>
          </Panel>

          <Panel>
            <PanelHeader title="Share Consumers" subtitle="After publish, each consumption entry changes state." action={<StatusPill tone={publishState === 'published' ? 'ready' : 'warning'}>{publishState}</StatusPill>} />
            <div className="grid gap-3 p-4 md:grid-cols-4">
              {model.consumptionEntries.map(entry => (
                <Surface key={entry.id} className="p-3">
                  <div className="flex items-center gap-2 text-sm font-semibold text-[#f3f5f5]">
                    {consumerIcon(entry.id)}
                    {entry.label}
                  </div>
                  <div className="mt-3 text-xs uppercase text-[#818c95]">Before</div>
                  <div className="mt-1 min-h-10 text-sm leading-5 text-[#9aa4ac]">{entry.before}</div>
                  <div className="mt-3 text-xs uppercase text-[#818c95]">After</div>
                  <div className={`mt-1 min-h-10 text-sm leading-5 ${publishState === 'published' ? 'text-emerald-200' : 'text-[#9aa4ac]'}`}>{entry.after}</div>
                </Surface>
              ))}
            </div>
          </Panel>
        </div>

        <div className="space-y-4">
          <Panel>
            <PanelHeader title="Publish Asset" subtitle="The button is truly disabled while the gate is blocked." action={<Rocket className="h-4 w-4 text-brand-orange" />} />
            <div className="grid gap-3 p-4">
              <KV label="Asset type" value={model.dataStudioAsset.asset_type} />
              <KV label="Asset ID" value={model.dataStudioAsset.asset_id} />
              <KV label="Version" value={model.dataStudioAsset.version} />
              <KV label="Usage policy" value={model.dataStudioAsset.usage_policy.join(', ')} />
              <Button variant="brand-primary" onClick={publishKnowledgeAsset} disabled={blocked}>
                <Rocket className="h-4 w-4" />
                Publish knowledge asset
              </Button>
              {blocked && <Button variant="secondary" onClick={() => setWorkspaceMode('model')}><ShieldCheck className="h-4 w-4" /> Fix blockers in modeling</Button>}
            </div>
          </Panel>

          <Panel>
            <PanelHeader title="Sample Evidence" subtitle="Asset evidence contract exposed to Session D." />
            <div className="grid gap-2 p-4">
              {model.dataStudioAsset.sample_evidence.map((item, index) => (
                <div key={`${item}-${index}`} className="rounded border border-[#2d3338] bg-[#121518] p-2 text-sm leading-6 text-[#d6dde2]">{item}</div>
              ))}
            </div>
          </Panel>
        </div>
      </div>
    </main>
  )
}

function SourceButton({ item, selected, onClick }: { item: DataModelingDatasource; selected: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full rounded-md border p-3 text-left transition focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring ${
        selected ? 'border-brand-orange/60 bg-brand-orange/10' : 'border-[#2d3338] bg-[#121518] hover:border-[#46505a]'
      }`}
    >
      <div className="flex min-w-0 items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-[#f3f5f5]">{item.name}</div>
          <div className="mt-1 text-xs text-[#818c95]">{item.sourceFamily} · {item.modelingMode ?? item.kind}</div>
        </div>
        <StatusPill tone={item.modelingStatus === 'supported' ? 'ready' : item.modelingStatus === 'needs_projection' ? 'warning' : 'blocked'}>{item.modelingStatus}</StatusPill>
      </div>
      <p className="mt-2 line-clamp-2 text-xs leading-5 text-[#9aa4ac]">{item.reason ?? 'Workspace source asset'}</p>
    </button>
  )
}

function ContextItem({ label, value, icon }: { label: string; value: string; icon: React.ReactNode }) {
  return (
    <div className="min-w-0 rounded-md border border-[#2d3338] bg-[#111417] p-3">
      <div className="flex items-center gap-2 text-[11px] font-medium uppercase text-[#818c95]">
        <span className="text-brand-orange">{icon}</span>
        {label}
      </div>
      <div className="mt-2 truncate text-sm font-semibold text-[#f3f5f5]">{value}</div>
    </div>
  )
}

function Evidence({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-[#2d3338] bg-[#0f1113] p-2">
      <div className="text-[10px] font-semibold uppercase text-[#818c95]">{label}</div>
      <div className="mt-1 break-words text-xs leading-5 text-[#d6dde2]">{value}</div>
    </div>
  )
}

function KV({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-[#2d3338] bg-[#121518] p-3">
      <div className="text-[10px] font-semibold uppercase text-[#818c95]">{label}</div>
      <div className="mt-1 break-words text-sm text-[#d6dde2]">{value}</div>
    </div>
  )
}

function statusForSteps(model: SemanticModel, blockerCount: number): Record<WorkspaceMode, 'pending' | 'complete' | 'blocked'> {
  return {
    connectors: 'complete',
    model: model.relationships.some(relationship => relationship.validationStatus === 'blocked' && relationship.status !== 'rejected') ? 'blocked' : 'complete',
    dashboard: model.metrics.length ? 'complete' : 'pending',
    publish: blockerCount ? 'blocked' : model.publishState === 'published' ? 'complete' : 'pending',
  }
}

function consumerIcon(id: string) {
  if (id === 'agent') return <Search className="h-4 w-4 text-brand-orange" />
  if (id === 'dashboard') return <LayoutDashboard className="h-4 w-4 text-brand-orange" />
  if (id === 'mcp_api') return <KeyRound className="h-4 w-4 text-brand-orange" />
  return <Share2 className="h-4 w-4 text-brand-orange" />
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('en-US').format(value)
}
