import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertCircle, ArrowRight, Bot, CheckCircle2, Database, Loader2, Play, Table2 } from 'lucide-react'
import { Button } from '../../../components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '../../../components/ui/dialog'
import { DataProfileWorkspace } from '../profile/DataProfileWorkspace'
import { EmptyState, ErrorState, MetricTile, Panel, PanelHeader, ScoreBar, SectionTitle, StatusPill, Surface, modelingStyles } from './modelingUi'
import { useDataModelingStore, selectActiveModel } from '../store/useDataModelingStore'
import type { DataModelingDatasource, DataSourceProfile } from '../types'

const milestones = ['Data', 'Profile', 'Generate', 'Explore']

export function CreateModelPanel({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const profiles = useDataModelingStore(state => state.profiles)
  const datasourceOptions = useDataModelingStore(state => state.datasourceOptions)
  const datasourceLoading = useDataModelingStore(state => state.datasourceLoading)
  const datasourceError = useDataModelingStore(state => state.datasourceError)
  const draft = useDataModelingStore(state => state.createDraft)
  const generation = useDataModelingStore(state => state.generation)
  const model = useDataModelingStore(selectActiveModel)
  const loadDatasources = useDataModelingStore(state => state.loadDatasources)
  const updateCreateDraft = useDataModelingStore(state => state.updateCreateDraft)
  const toggleCreateTable = useDataModelingStore(state => state.toggleCreateTable)
  const startSemanticGeneration = useDataModelingStore(state => state.startSemanticGeneration)
  const setActiveModel = useDataModelingStore(state => state.setActiveModel)
  const setWorkspaceMode = useDataModelingStore(state => state.setWorkspaceMode)

  const profile = profiles.find(item => item.id === draft.datasourceId) ?? profiles[0]

  useEffect(() => {
    if (open) {
      void loadDatasources()
    }
  }, [open, loadDatasources])

  useEffect(() => {
    if (open && generation.phase === 'completed') {
      setStep(3)
    }
  }, [open, generation.phase])

  const startExploring = () => {
    if (!model?.id) return
    setActiveModel(model.id)
    setWorkspaceMode('explore')
    onOpenChange(false)
    navigate(`/data-models/${model.id}`)
  }

  const runGeneration = () => {
    if (generation.phase === 'idle' || generation.phase === 'completed') {
      startSemanticGeneration()
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[94vh] max-w-[1280px] overflow-y-auto border-[#30363a] bg-[#15181b] p-0 text-[#f3f5f5] shadow-2xl custom-scrollbar">
        <DialogHeader className="border-b border-[#30363a] px-5 py-4">
          <div className="flex flex-wrap items-center gap-2">
            <DialogTitle className="text-base text-[#f3f5f5]">Generate Semantic Model From Data</DialogTitle>
            <StatusPill tone="info">Rill-first flow</StatusPill>
          </div>
          <DialogDescription className="text-[#9aa4ac]">
            Select a datasource, inspect profile evidence, generate a semantic model, then start exploring the generated model.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 p-4 lg:grid-cols-[210px_minmax(0,1fr)]">
          <nav className="space-y-2">
            {milestones.map((item, index) => (
              <button
                key={`${item}-${index}`}
                type="button"
                onClick={() => setStep(index)}
                className={`flex w-full items-center justify-between rounded-md border px-3 py-2 text-left text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring ${
                  step === index ? modelingStyles.active : 'border-[#2d3338] bg-[#181b1f] text-[#c4ccd2] hover:border-[#46505a] hover:bg-[#20252a]'
                }`}
              >
                <span>{item}</span>
                <StatusPill tone={index < step || (index === 3 && generation.phase === 'completed') ? 'ready' : index === step ? 'info' : 'neutral'}>{index + 1}</StatusPill>
              </button>
            ))}
          </nav>

          <div className="min-w-0">
            {step === 0 && (
              <DatasourceStep
                datasources={datasourceOptions}
                profiles={profiles}
                loading={datasourceLoading}
                error={datasourceError}
                selectedId={draft.datasourceId}
                selectedTables={draft.selectedTables}
                domain={draft.domain}
                businessQuestions={draft.businessQuestions}
                onSelectDatasource={datasourceId => updateCreateDraft({ datasourceId })}
                onSelectDomain={domain => updateCreateDraft({ domain })}
                onQuestionsChange={businessQuestions => updateCreateDraft({ businessQuestions })}
                onToggleTable={toggleCreateTable}
                onNext={() => setStep(1)}
              />
            )}

            {step === 1 && profile && (
              <div className="space-y-4">
                <DataProfileWorkspace profile={profile} />
                <Panel>
                  <div className="flex flex-wrap items-center justify-between gap-3 p-4">
                    <div>
                      <div className="text-sm font-semibold text-[#f3f5f5]">Profile is ready for generation</div>
                      <p className="mt-1 text-xs text-[#9aa4ac]">The generator will use table categories, field roles, sample rows, and PII detection as evidence.</p>
                    </div>
                    <Button variant="brand-primary" onClick={() => setStep(2)}>AI Generate Semantic Model <ArrowRight className="h-4 w-4" /></Button>
                  </div>
                </Panel>
              </div>
            )}

            {step === 1 && !profile && (
              <EmptyState
                title="No profile loaded"
                body="Choose a datasource first. The profile panel will use the backend schema or Source Understanding profile for the selected datasource."
                action={<Button variant="secondary" onClick={() => setStep(0)}>Choose datasource</Button>}
              />
            )}

            {step === 2 && (
              <GenerationStep
                generationProgress={generation.progress}
                phase={generation.phase}
                steps={generation.steps}
                summary={generation.summary}
                error={generation.error}
                modelName={model?.name || 'Semantic Model'}
                onRun={runGeneration}
                onComplete={() => setStep(3)}
              />
            )}

            {step === 3 && (
              <Panel>
                <PanelHeader
                  title="Generated Explore Is Ready"
                  subtitle="The builder opens in Explore mode so users can verify business answers before advanced modeling."
                  action={<StatusPill tone="ready">AI draft complete</StatusPill>}
                />
                <div className="grid gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_280px]">
                  <div className="space-y-4">
                    <Surface className="p-4">
                      <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-[#f3f5f5]">
                        <Bot className="h-4 w-4 text-brand-orange" />
                        Completion summary
                      </div>
                      <div className="grid gap-2">
                        {(generation.summary.length ? generation.summary : ['Profile evidence loaded.', 'Semantic draft generated.', 'Explore defaults prepared.']).map((item, index) => (
                          <div key={`${item}-${index}`} className="flex items-start gap-2 text-sm text-[#d6dde2]">
                            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-300" />
                            <span>{item}</span>
                          </div>
                        ))}
                      </div>
                    </Surface>
                    <div className="grid gap-3 sm:grid-cols-3">
                      <Summary label="Entities" value={String(model.entities.length)} />
                      <Summary label="Metrics" value={String(model.metrics.length)} />
                      <Summary label="Readiness" value={`${model.readiness}%`} />
                    </div>
                  </div>
                  <Surface className="p-4">
                    <SectionTitle>Next action</SectionTitle>
                    <p className="mt-2 text-sm leading-6 text-[#cdd3d8]">Start with Paid Revenue by Region, then review the model when the Explore answer looks credible.</p>
                    <Button className="mt-4 w-full" variant="brand-primary" onClick={startExploring} disabled={!model?.id}>
                      Start exploring <ArrowRight className="h-4 w-4" />
                    </Button>
                  </Surface>
                </div>
              </Panel>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function DatasourceStep({
  datasources,
  profiles,
  loading,
  error,
  selectedId,
  selectedTables,
  domain,
  businessQuestions,
  onSelectDatasource,
  onSelectDomain,
  onQuestionsChange,
  onToggleTable,
  onNext,
}: {
  datasources: DataModelingDatasource[]
  profiles: DataSourceProfile[]
  loading: boolean
  error: string | null
  selectedId: string
  selectedTables: string[]
  domain: string
  businessQuestions: string
  onSelectDatasource: (id: string) => void
  onSelectDomain: (domain: string) => void
  onQuestionsChange: (questions: string) => void
  onToggleTable: (table: string) => void
  onNext: () => void
}) {
  const profile = profiles.find(item => item.id === selectedId) ?? profiles[0]

  return (
    <div className="space-y-4">
      <Panel>
        <PanelHeader title="Choose Data" subtitle="Select a real datasource, then inspect the live schema/profile evidence before generating a draft." />
        {loading && <div className="p-4 text-sm text-[#cdd3d8]">Loading datasources...</div>}
        {!loading && error && <div className="p-4"><ErrorState title="Unable to load datasources" body={error} /></div>}
        {!loading && !error && datasources.length === 0 && (
          <div className="p-4">
            <EmptyState title="No supported datasource found" body="Connect an Oracle, Postgres, MySQL, or SQLite datasource before generating a Semantic Model." />
          </div>
        )}
        <div className="grid gap-3 p-4 md:grid-cols-3">
          {datasources.map(item => {
            const profiled = profiles.find(profile => profile.id === item.id)
            return (
            <button
              key={item.id}
              type="button"
              onClick={() => onSelectDatasource(item.id)}
              className={`rounded-md border p-4 text-left focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring ${
                selectedId === item.id ? modelingStyles.active : 'border-[#2d3338] bg-[#181b1f] hover:border-[#46505a] hover:bg-[#20252a]'
              }`}
            >
              <Database className="mb-3 h-5 w-5 text-brand-orange" />
              <div className="text-sm font-semibold text-[#f3f5f5]">{item.name}</div>
              <div className="mt-1 text-xs uppercase text-[#7f8a93]">{item.kind} · {item.sourceType}</div>
              <div className="mt-3 flex flex-wrap gap-2">
                <StatusPill tone={profiled?.status === 'ready' ? 'ready' : item.status === 'error' ? 'blocked' : 'warning'}>{profiled?.status ?? item.status ?? 'not profiled'}</StatusPill>
                {profiled && <StatusPill>{profiled.profileCoverage}% profile</StatusPill>}
              </div>
            </button>
          )})}
        </div>
      </Panel>

      <Panel>
        <PanelHeader title="Recommended Modeling Scope" subtitle="Choose the business domain, core tables, and the questions this model should answer." />
        <div className="grid gap-4 p-4 lg:grid-cols-[320px_minmax(0,1fr)]">
          <div className="space-y-3">
            <label className="block text-xs font-medium text-[#9a9a9a]">
              Business domain
              <select
                value={domain}
                onChange={event => onSelectDomain(event.target.value)}
                className={`mt-1 h-9 w-full rounded-md px-3 text-sm focus-visible:outline-none focus-visible:ring-1 ${modelingStyles.input}`}
              >
                <option>Sales / Orders</option>
                <option>Customers</option>
                <option>Store Operations</option>
              </select>
            </label>
            <label className="block text-xs font-medium text-[#9a9a9a]">
              Optional business question
              <textarea
                value={businessQuestions}
                onChange={event => onQuestionsChange(event.target.value)}
                className={`mt-1 min-h-32 w-full rounded-md p-3 text-sm focus-visible:outline-none focus-visible:ring-1 ${modelingStyles.input}`}
              />
            </label>
          </div>
          <div>
            <div className="mb-2 text-xs font-medium text-[#9aa4ac]">Default recommendations</div>
            <div className="grid max-h-[280px] gap-2 overflow-y-auto custom-scrollbar md:grid-cols-2">
              {profile?.tables.map(table => (
                <label key={table.name} className="flex items-center gap-3 rounded-md border border-[#2d3338] bg-[#15181b] px-3 py-2 text-sm">
                  <input
                    type="checkbox"
                    checked={selectedTables.includes(table.name)}
                    onChange={() => onToggleTable(table.name)}
                    className="h-4 w-4 accent-brand-orange"
                  />
                  <Table2 className="h-4 w-4 text-[#7f8a93]" />
                  <span className="min-w-0 flex-1 truncate text-[#f3f5f5]">{table.name}</span>
                  <StatusPill>{table.category}</StatusPill>
                </label>
              ))}
            </div>
          </div>
        </div>
        <div className="flex justify-end border-t border-[#30363a] p-4">
          <Button variant="brand-primary" onClick={onNext}>Continue to Profile <ArrowRight className="h-4 w-4" /></Button>
        </div>
      </Panel>
    </div>
  )
}

function GenerationStep({
  generationProgress,
  phase,
  steps,
  summary,
  error,
  modelName,
  onRun,
  onComplete,
}: {
  generationProgress: number
  phase: string
  steps: Array<{ id: string; title: string; detail: string; status: string }>
  summary: string[]
  error: string | null
  modelName: string
  onRun: () => void
  onComplete: () => void
}) {
  const completed = phase === 'completed'
  const idle = phase === 'idle'
  const running = !idle && !completed

  return (
    <Panel>
      <PanelHeader
        title="AI Semantic Generation"
        subtitle="Generation creates a draft only; suggestions remain reviewable and publish is separate."
        action={<StatusPill tone={completed ? 'ready' : idle ? 'neutral' : 'info'}>{phase}</StatusPill>}
      />
      <div className="grid gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div>
          <Surface className="p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-[#f3f5f5]">
                <Bot className="h-4 w-4 text-brand-orange" />
                Generate {modelName}
              </div>
              <span className="text-xs tabular-nums text-[#c4ccd2]">{generationProgress}%</span>
            </div>
            <ScoreBar value={generationProgress} level={completed ? 'ready' : generationProgress > 60 ? 'warning' : 'blocked'} />
          </Surface>

          <div className="mt-4 grid gap-3">
            {steps.map(step => (
              <Surface key={step.id} className="p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-sm font-medium text-[#f3f5f5]">
                    {step.status === 'running' ? <Loader2 className="h-4 w-4 animate-spin text-brand-orange" /> : <CheckCircle2 className={`h-4 w-4 ${step.status === 'done' ? 'text-emerald-300' : 'text-[#666]'}`} />}
                    {step.title}
                  </div>
                  <StatusPill tone={step.status === 'done' ? 'ready' : step.status === 'running' ? 'info' : 'neutral'}>{step.status}</StatusPill>
                </div>
                <p className="mt-2 text-sm leading-6 text-[#9aa4ac]">{step.detail}</p>
              </Surface>
            ))}
          </div>
        </div>

        <Surface className="p-4">
          <SectionTitle>Controls</SectionTitle>
          <p className="mt-2 text-sm leading-6 text-[#cdd3d8]">Generation calls Source Understanding review APIs and creates a persisted Semantic Model draft.</p>
          {error && (
            <div className="mt-4 rounded-md border border-red-500/25 bg-red-500/10 p-3 text-sm leading-5 text-red-100">
              <div className="flex items-start gap-2">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-300" />
                <div>
                  <div className="font-medium text-red-100">Generation failed</div>
                  <div className="mt-1 text-red-100/75">{error}</div>
                </div>
              </div>
            </div>
          )}
          <Button className="mt-4 w-full" variant="brand-primary" onClick={completed ? onComplete : onRun} disabled={running}>
            {completed ? 'Continue to Explore' : running ? 'Generating...' : error ? 'Retry generation' : 'Start AI generation'}
            {running ? <Loader2 className="h-4 w-4 animate-spin" /> : completed ? <ArrowRight className="h-4 w-4" /> : <Play className="h-4 w-4" />}
          </Button>
          {summary.length > 0 && (
            <div className="mt-4 space-y-2">
              {summary.map((item, index) => (
                <div key={`${item}-${index}`} className="flex items-start gap-2 text-xs text-[#d6dde2]">
                  <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-300" />
                  <span>{item}</span>
                </div>
              ))}
            </div>
          )}
        </Surface>
      </div>
    </Panel>
  )
}

function Summary({ label, value }: { label: string; value: string }) {
  return <MetricTile label={label} value={value} />
}
