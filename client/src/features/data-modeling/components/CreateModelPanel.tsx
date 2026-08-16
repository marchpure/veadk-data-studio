import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Bot, CheckCircle2, Database, Loader2, Play, Table2 } from 'lucide-react'
import { Button } from '../../../components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '../../../components/ui/dialog'
import { DataProfileWorkspace } from '../profile/DataProfileWorkspace'
import { DemoBadge, Panel, PanelHeader, ScoreBar, SectionTitle, StatusPill } from './modelingUi'
import { useDataModelingStore, selectActiveModel } from '../store/useDataModelingStore'
import type { DataSourceProfile } from '../types'

const milestones = ['Data', 'Profile', 'Generate', 'Explore']

export function CreateModelPanel({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const profiles = useDataModelingStore(state => state.profiles)
  const draft = useDataModelingStore(state => state.createDraft)
  const generation = useDataModelingStore(state => state.generation)
  const model = useDataModelingStore(selectActiveModel)
  const updateCreateDraft = useDataModelingStore(state => state.updateCreateDraft)
  const toggleCreateTable = useDataModelingStore(state => state.toggleCreateTable)
  const startSemanticGeneration = useDataModelingStore(state => state.startSemanticGeneration)
  const advanceSemanticGeneration = useDataModelingStore(state => state.advanceSemanticGeneration)
  const setActiveModel = useDataModelingStore(state => state.setActiveModel)
  const setWorkspaceMode = useDataModelingStore(state => state.setWorkspaceMode)

  const profile = profiles.find(item => item.id === draft.datasourceId) ?? profiles[0]

  useEffect(() => {
    if (open && generation.phase === 'completed') {
      setStep(3)
    }
  }, [open, generation.phase])

  const startExploring = () => {
    setActiveModel('sales-growth')
    setWorkspaceMode('explore')
    onOpenChange(false)
    navigate('/data-models/sales-growth')
  }

  const runGeneration = () => {
    if (generation.phase === 'idle' || generation.phase === 'completed') {
      startSemanticGeneration()
    } else {
      advanceSemanticGeneration()
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[94vh] max-w-[1280px] overflow-y-auto border-[#2a2a2a] bg-[#1a1a1a] p-0 text-white custom-scrollbar">
        <DialogHeader className="border-b border-[#2a2a2a] px-5 py-4">
          <div className="flex flex-wrap items-center gap-2">
            <DialogTitle className="text-base">Generate Semantic Model From Data</DialogTitle>
            <DemoBadge />
            <StatusPill tone="info">Rill-first flow</StatusPill>
          </div>
          <DialogDescription>
            Select a datasource, inspect profile evidence, generate a semantic model, then start exploring the generated model.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 p-4 lg:grid-cols-[210px_minmax(0,1fr)]">
          <nav className="space-y-2">
            {milestones.map((item, index) => (
              <button
                key={item}
                type="button"
                onClick={() => setStep(index)}
                className={`flex w-full items-center justify-between rounded-md border px-3 py-2 text-left text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring ${
                  step === index ? 'border-brand-orange/50 bg-brand-orange/10 text-white' : 'border-[#2a2a2a] bg-[#191919] text-[#bdbdbd] hover:border-[#444]'
                }`}
              >
                <span>{item}</span>
                <StatusPill tone={index < step || (index === 3 && generation.phase === 'completed') ? 'ready' : index === step ? 'info' : 'neutral'}>{index + 1}</StatusPill>
              </button>
            ))}
          </nav>

          <div className="min-w-0">
            {step === 0 && profile && (
              <DatasourceStep
                profiles={profiles}
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
                      <div className="text-sm font-semibold text-white">Profile is ready for generation</div>
                      <p className="mt-1 text-xs text-[#9a9a9a]">The generator will use table categories, field roles, sample rows, and PII detection as evidence.</p>
                    </div>
                    <Button variant="brand-primary" onClick={() => setStep(2)}>AI Generate Semantic Model <ArrowRight className="h-4 w-4" /></Button>
                  </div>
                </Panel>
              </div>
            )}

            {step === 2 && (
              <GenerationStep
                generationProgress={generation.progress}
                phase={generation.phase}
                steps={generation.steps}
                summary={generation.summary}
                modelName={model.name}
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
                    <div className="rounded-md border border-[#2a2a2a] bg-[#181818] p-4">
                      <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-white">
                        <Bot className="h-4 w-4 text-brand-orange" />
                        Completion summary
                      </div>
                      <div className="grid gap-2">
                        {(generation.summary.length ? generation.summary : ['Profile evidence loaded.', 'Semantic draft generated.', 'Explore defaults prepared.']).map(item => (
                          <div key={item} className="flex items-start gap-2 text-sm text-[#d6d6d6]">
                            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-300" />
                            <span>{item}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div className="grid gap-3 sm:grid-cols-3">
                      <Summary label="Entities" value={String(model.entities.length)} />
                      <Summary label="Metrics" value={String(model.metrics.length)} />
                      <Summary label="Readiness" value={`${model.readiness}%`} />
                    </div>
                  </div>
                  <div className="rounded-md border border-[#2a2a2a] bg-[#181818] p-4">
                    <SectionTitle>Next action</SectionTitle>
                    <p className="mt-2 text-sm text-[#cfcfcf]">Start with Paid Revenue by Region, then review the model when the Explore answer looks credible.</p>
                    <Button className="mt-4 w-full" variant="brand-primary" onClick={startExploring}>
                      Start exploring <ArrowRight className="h-4 w-4" />
                    </Button>
                  </div>
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
  profiles,
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
  profiles: DataSourceProfile[]
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
        <PanelHeader title="Choose Data" subtitle="Oracle SALES is pre-profiled for this Demo." />
        <div className="grid gap-3 p-4 md:grid-cols-3">
          {profiles.map(item => (
            <button
              key={item.id}
              type="button"
              onClick={() => onSelectDatasource(item.id)}
              className={`rounded-md border p-4 text-left focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring ${
                selectedId === item.id ? 'border-brand-orange/50 bg-brand-orange/10' : 'border-[#2a2a2a] bg-[#191919] hover:border-[#444]'
              }`}
            >
              <Database className="mb-3 h-5 w-5 text-brand-orange" />
              <div className="text-sm font-semibold text-white">{item.name}</div>
              <div className="mt-1 text-xs uppercase text-[#8e8e8e]">{item.kind} · {item.schema}</div>
              <div className="mt-3 flex flex-wrap gap-2">
                <StatusPill tone={item.status === 'ready' ? 'ready' : 'warning'}>{item.status}</StatusPill>
                <StatusPill>{item.profileCoverage}% profile</StatusPill>
              </div>
            </button>
          ))}
        </div>
      </Panel>

      <Panel>
        <PanelHeader title="Recommended Modeling Scope" subtitle="The AI has already classified the sales schema. Business questions are optional." />
        <div className="grid gap-4 p-4 lg:grid-cols-[320px_minmax(0,1fr)]">
          <div className="space-y-3">
            <label className="block text-xs font-medium text-[#9a9a9a]">
              Business domain
              <select
                value={domain}
                onChange={event => onSelectDomain(event.target.value)}
                className="mt-1 h-9 w-full rounded-md border border-[#333] bg-[#151515] px-3 text-sm text-white focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
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
                className="mt-1 min-h-32 w-full rounded-md border border-[#333] bg-[#151515] p-3 text-sm text-white focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              />
            </label>
          </div>
          <div>
            <div className="mb-2 text-xs font-medium text-[#9a9a9a]">Default recommendations</div>
            <div className="grid max-h-[280px] gap-2 overflow-y-auto custom-scrollbar md:grid-cols-2">
              {profile?.tables.map(table => (
                <label key={table.name} className="flex items-center gap-3 rounded-md border border-[#2a2a2a] bg-[#181818] px-3 py-2 text-sm">
                  <input
                    type="checkbox"
                    checked={selectedTables.includes(table.name)}
                    onChange={() => onToggleTable(table.name)}
                    className="h-4 w-4 accent-brand-orange"
                  />
                  <Table2 className="h-4 w-4 text-[#8c8c8c]" />
                  <span className="min-w-0 flex-1 truncate text-white">{table.name}</span>
                  <StatusPill>{table.category}</StatusPill>
                </label>
              ))}
            </div>
          </div>
        </div>
        <div className="flex justify-end border-t border-[#2a2a2a] p-4">
          <Button variant="brand-primary" onClick={onNext}>AI Generate Semantic Model <ArrowRight className="h-4 w-4" /></Button>
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
  modelName,
  onRun,
  onComplete,
}: {
  generationProgress: number
  phase: string
  steps: Array<{ id: string; title: string; detail: string; status: string }>
  summary: string[]
  modelName: string
  onRun: () => void
  onComplete: () => void
}) {
  const completed = phase === 'completed'
  const idle = phase === 'idle'

  return (
    <Panel>
      <PanelHeader
        title="AI Semantic Generation"
        subtitle="Generation creates a draft only; suggestions remain reviewable and publish is separate."
        action={<StatusPill tone={completed ? 'ready' : idle ? 'neutral' : 'info'}>{phase}</StatusPill>}
      />
      <div className="grid gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div>
          <div className="rounded-md border border-[#2a2a2a] bg-[#181818] p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-white">
                <Bot className="h-4 w-4 text-brand-orange" />
                Generate {modelName}
              </div>
              <span className="text-xs tabular-nums text-[#bdbdbd]">{generationProgress}%</span>
            </div>
            <ScoreBar value={generationProgress} level={completed ? 'ready' : generationProgress > 60 ? 'warning' : 'blocked'} />
          </div>

          <div className="mt-4 grid gap-3">
            {steps.map(step => (
              <div key={step.id} className="rounded-md border border-[#2a2a2a] bg-[#181818] p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-sm font-medium text-white">
                    {step.status === 'running' ? <Loader2 className="h-4 w-4 animate-spin text-brand-orange" /> : <CheckCircle2 className={`h-4 w-4 ${step.status === 'done' ? 'text-emerald-300' : 'text-[#666]'}`} />}
                    {step.title}
                  </div>
                  <StatusPill tone={step.status === 'done' ? 'ready' : step.status === 'running' ? 'info' : 'neutral'}>{step.status}</StatusPill>
                </div>
                <p className="mt-2 text-sm text-[#a9a9a9]">{step.detail}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-md border border-[#2a2a2a] bg-[#181818] p-4">
          <SectionTitle>Controls</SectionTitle>
          <p className="mt-2 text-sm text-[#cfcfcf]">Advance the deterministic Demo generation to expose visible progress and completion state.</p>
          <Button className="mt-4 w-full" variant="brand-primary" onClick={completed ? onComplete : onRun}>
            {completed ? 'Continue to Explore' : idle ? 'Start AI generation' : 'Advance generation'}
            {completed ? <ArrowRight className="h-4 w-4" /> : <Play className="h-4 w-4" />}
          </Button>
          {summary.length > 0 && (
            <div className="mt-4 space-y-2">
              {summary.map(item => (
                <div key={item} className="flex items-start gap-2 text-xs text-[#d6d6d6]">
                  <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-300" />
                  <span>{item}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </Panel>
  )
}

function Summary({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-[#2a2a2a] bg-[#181818] p-3">
      <div className="text-xs uppercase text-[#858585]">{label}</div>
      <div className="mt-1 text-lg font-semibold text-white">{value}</div>
    </div>
  )
}
