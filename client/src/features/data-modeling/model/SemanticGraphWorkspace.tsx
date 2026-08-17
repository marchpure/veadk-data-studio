import { useMemo, useState } from 'react'
import { Check, Code2, GitCompare, Menu, PanelLeftClose, PanelLeftOpen, Play, TableProperties, X } from 'lucide-react'
import { Button } from '../../../components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../../components/ui/dialog'
import { ObjectTree } from './ObjectTree'
import { ModelInspector } from './ModelInspector'
import { MetricEditor } from './MetricEditor'
import { DataProfileWorkspace } from '../profile/DataProfileWorkspace'
import { CheckLine, Panel, PanelHeader, ScoreBar, SectionTitle, StatusPill, Surface, modelingStyles, readinessTone } from '../components/modelingUi'
import { useDataModelingStore } from '../store/useDataModelingStore'
import type { Entity, Relationship, SemanticModel } from '../types'

const positions: Record<string, { x: number; y: number }> = {
  customers: { x: 12, y: 30 },
  stores: { x: 12, y: 58 },
  channels: { x: 12, y: 78 },
  orders: { x: 43, y: 48 },
  order_items: { x: 68, y: 48 },
  products: { x: 88, y: 48 },
  refunds: { x: 43, y: 78 },
}

export function SemanticGraphWorkspace({ model }: { model: SemanticModel }) {
  const selectedObjectId = useDataModelingStore(state => state.selectedObjectId)
  const selectObject = useDataModelingStore(state => state.selectObject)
  const validateModel = useDataModelingStore(state => state.validateModel)
  const profile = useDataModelingStore(state => state.profiles.find(item => item.id === model.datasourceId) ?? state.profiles[0])
  const [treeOpen, setTreeOpen] = useState(false)
  const [inspectorOpen, setInspectorOpen] = useState(false)
  const [validationOpen, setValidationOpen] = useState(false)
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [treeCollapsed, setTreeCollapsed] = useState(false)

  const selectedMetric = model.metrics.find(metric => metric.id === selectedObjectId)
  const hasInspector = Boolean(selectedObjectId)

  const selectAndInspect = (id: string) => {
    selectObject(id)
  }

  return (
    <main className={`grid min-h-0 flex-1 bg-[#0f1113] ${hasInspector ? (treeCollapsed ? 'lg:grid-cols-[56px_minmax(0,1fr)_360px]' : 'lg:grid-cols-[272px_minmax(0,1fr)_360px]') : (treeCollapsed ? 'lg:grid-cols-[56px_minmax(0,1fr)]' : 'lg:grid-cols-[272px_minmax(0,1fr)]')}`}>
      <aside className="hidden min-h-0 border-r border-[#30363a] bg-[#14181b] lg:block">
        <div className="flex items-center justify-between border-b border-[#30363a] px-3 py-2">
          {!treeCollapsed && (
            <div>
              <span className="text-xs font-semibold text-[#d6dde2]">Model Objects</span>
              <div className="mt-0.5 text-[11px] text-[#818c95]">{model.entities.length} entities · {model.metrics.length} metrics</div>
            </div>
          )}
          <Button size="icon" variant="ghost" onClick={() => setTreeCollapsed(value => !value)} aria-label={treeCollapsed ? 'Expand object tree' : 'Collapse object tree'}>
            {treeCollapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
          </Button>
        </div>
        {!treeCollapsed && <ObjectTree model={model} selectedObjectId={selectedObjectId} onSelect={selectObject} />}
      </aside>

      <section className="min-w-0 overflow-y-auto p-3 custom-scrollbar">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap gap-2 lg:hidden">
            <Button size="sm" variant="secondary" onClick={() => setTreeOpen(true)}><Menu className="h-4 w-4" /> Objects</Button>
            <Button size="sm" variant="secondary" onClick={() => setInspectorOpen(true)}>Inspector</Button>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="secondary" onClick={() => setValidationOpen(true)}><Play className="h-4 w-4" /> Validation Drawer</Button>
            <Button size="sm" variant="secondary" onClick={() => setAdvancedOpen(true)}><Code2 className="h-4 w-4" /> Advanced DSL</Button>
          </div>
        </div>

        <div className="grid gap-4">
          <ModelingEvidenceSummary model={model} />
          <RelationshipCanvas model={model} selectedObjectId={selectedObjectId} onSelect={selectAndInspect} />

          {selectedMetric && <MetricEditor metric={selectedMetric} />}

          <Panel>
            <PanelHeader title="Fields and Profile Evidence" subtitle="Profile evidence stays close to model editing." />
            {profile && <div className="p-4"><DataProfileWorkspace profile={profile} showSuggestions /></div>}
          </Panel>
        </div>
      </section>

      {hasInspector && (
        <div className="hidden min-h-0 border-l border-[#30363a] bg-[#14181b] lg:block">
          <div className="flex items-center justify-between border-b border-[#30363a] px-4 py-2">
            <span className="text-sm font-medium text-[#f3f5f5]">Inspector</span>
            <Button size="icon" variant="ghost" onClick={() => selectObject('')} aria-label="Close inspector"><X className="h-4 w-4" /></Button>
          </div>
          <div className="h-[calc(100%-49px)] min-h-0">
            <ModelInspector model={model} selectedObjectId={selectedObjectId} />
          </div>
        </div>
      )}

      <Dialog open={treeOpen} onOpenChange={setTreeOpen}>
        <DialogContent className="left-0 top-0 h-full max-h-none w-[88vw] max-w-sm translate-x-0 translate-y-0 overflow-hidden border-[#30363a] bg-[#15181b] p-0 text-[#f3f5f5] sm:rounded-none">
          <DialogHeader className="border-b border-[#30363a] p-4">
            <DialogTitle className="text-base">Model Objects</DialogTitle>
          </DialogHeader>
          <ObjectTree model={model} selectedObjectId={selectedObjectId} onSelect={(id) => { selectObject(id); setTreeOpen(false) }} />
        </DialogContent>
      </Dialog>

      <Dialog open={inspectorOpen} onOpenChange={setInspectorOpen}>
        <DialogContent className="left-auto right-0 top-0 h-full max-h-none w-[92vw] max-w-md translate-x-0 translate-y-0 overflow-hidden border-[#30363a] bg-[#15181b] p-0 text-[#f3f5f5] sm:rounded-none">
          <DialogHeader className="border-b border-[#30363a] p-4">
            <DialogTitle className="text-base">Model Inspector</DialogTitle>
          </DialogHeader>
          <div className="h-[calc(100%-57px)] min-h-0">
            <ModelInspector model={model} selectedObjectId={selectedObjectId} />
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={validationOpen} onOpenChange={setValidationOpen}>
        <DialogContent className="max-h-[88vh] max-w-4xl overflow-y-auto border-[#30363a] bg-[#15181b] p-0 text-[#f3f5f5] custom-scrollbar">
          <DialogHeader className="border-b border-[#30363a] p-4">
            <DialogTitle className="text-base">Model Validation</DialogTitle>
          </DialogHeader>
          <ValidationDrawer model={model} onValidate={validateModel} />
        </DialogContent>
      </Dialog>

      <Dialog open={advancedOpen} onOpenChange={setAdvancedOpen}>
        <DialogContent className="max-h-[88vh] max-w-5xl overflow-y-auto border-[#30363a] bg-[#15181b] p-0 text-[#f3f5f5] custom-scrollbar">
          <DialogHeader className="border-b border-[#30363a] p-4">
            <DialogTitle className="text-base">Model Advanced DSL</DialogTitle>
          </DialogHeader>
          <AdvancedDsl model={model} />
        </DialogContent>
      </Dialog>
    </main>
  )
}

function ModelingEvidenceSummary({ model }: { model: SemanticModel }) {
  const selectObject = useDataModelingStore(state => state.selectObject)
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <Panel>
        <PanelHeader title="Structure Understanding" subtitle="Main tables, dimension tables, keys, cardinality, time fields, and fanout risk." />
        <div className="grid gap-3 p-4 md:grid-cols-2">
          {model.entities.map(entity => (
            <Surface key={entity.id} className="p-3">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-[#f3f5f5]">{entity.businessName}</div>
                  <div className="mt-1 text-xs text-[#818c95]">{entity.table}</div>
                </div>
                <StatusPill>{entityKind(entity)}</StatusPill>
              </div>
              <div className="mt-3 grid gap-2 text-xs text-[#cdd3d8]">
                <KV label="Primary key" value={entity.primaryKey} />
                <KV label="Time fields" value={entity.fields.filter(field => field.role === 'time').map(field => field.name).join(', ') || 'None detected'} />
              </div>
            </Surface>
          ))}
        </div>
        <div className="border-t border-[#30363a] p-4">
          <SectionTitle>Relationship cardinality and fanout</SectionTitle>
          <div className="mt-3 grid gap-2">
            {model.relationships.map(relationship => (
              <Surface key={relationship.id} className="p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-sm font-semibold text-[#f3f5f5]">{relationship.fromEntity} to {relationship.toEntity}</span>
                  <div className="flex flex-wrap gap-2">
                    <StatusPill>{relationship.cardinality}</StatusPill>
                    <StatusPill tone={relationship.fanoutRisk === 'high' ? 'blocked' : relationship.fanoutRisk === 'medium' ? 'warning' : 'ready'}>{relationship.fanoutRisk} fanout</StatusPill>
                  </div>
                </div>
                <p className="mt-2 text-sm leading-6 text-[#9aa4ac]">{relationship.validationMessage || relationship.fkEvidence}</p>
              </Surface>
            ))}
          </div>
        </div>
      </Panel>

      <div className="grid gap-4">
        <Panel>
          <PanelHeader title="Semantic Suggestions" subtitle="Confirm metrics, dimensions, and permission policy one suggestion at a time." />
          <div className="grid gap-3 p-4">
            {model.metrics.map(metric => (
              <Surface key={metric.id} className="p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-[#f3f5f5]">{metric.businessName}</div>
                    <p className="mt-1 text-sm leading-6 text-[#9aa4ac]">{metric.definition}</p>
                  </div>
                  <StatusPill tone={metric.certification === 'certified' ? 'ready' : 'warning'}>{metric.certification}</StatusPill>
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <Button size="sm" variant="secondary" onClick={() => selectObject(metric.id)}>Open metric editor</Button>
                  <StatusPill>metric</StatusPill>
                </div>
              </Surface>
            ))}
            {model.suggestions.slice(0, 5).map(suggestion => (
              <Surface key={suggestion.id} className="p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-[#f3f5f5]">{suggestion.title}</div>
                    <p className="mt-1 text-sm leading-6 text-[#9aa4ac]">{suggestion.recommendation}</p>
                  </div>
                  <StatusPill tone={suggestion.status === 'accepted' ? 'ready' : suggestion.status === 'rejected' ? 'blocked' : 'warning'}>{suggestion.status}</StatusPill>
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <Button size="sm" variant="secondary" onClick={() => useDataModelingStore.getState().acceptSuggestion(suggestion.id)}><Check className="h-4 w-4" /> Confirm</Button>
                  <StatusPill>{Math.round(suggestion.confidence * 100)}% confidence</StatusPill>
                  <StatusPill>{suggestion.type}</StatusPill>
                </div>
              </Surface>
            ))}
          </div>
        </Panel>

        <Panel>
          <PanelHeader title="Conflicts" subtitle="Resolve conflicts by choosing one authority." action={<GitCompare className="h-4 w-4 text-brand-orange" />} />
          <div className="grid gap-3 p-4">
            <ConflictChoice
              title="Document metric definition vs field reality"
              left="Use doc wording: gross revenue includes pending orders."
              right="Use field state: paid_revenue excludes pending and refunded order amounts."
            />
            <ConflictChoice
              title="Two authority sources define region differently"
              left="CRM region from customer owner hierarchy."
              right="Store operations region from fulfillment location."
            />
          </div>
        </Panel>
      </div>
    </div>
  )
}

function ConflictChoice({ title, left, right }: { title: string; left: string; right: string }) {
  const [choice, setChoice] = useState<'left' | 'right'>('right')
  return (
    <Surface className="p-3">
      <div className="text-sm font-semibold text-[#f3f5f5]">{title}</div>
      <div className="mt-3 grid gap-2 md:grid-cols-2">
        <button
          type="button"
          onClick={() => setChoice('left')}
          className={`rounded border p-3 text-left text-sm leading-6 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring ${choice === 'left' ? 'border-brand-orange/60 bg-brand-orange/10 text-[#f3f5f5]' : 'border-[#2d3338] bg-[#101316] text-[#9aa4ac]'}`}
        >
          {left}
        </button>
        <button
          type="button"
          onClick={() => setChoice('right')}
          className={`rounded border p-3 text-left text-sm leading-6 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring ${choice === 'right' ? 'border-brand-orange/60 bg-brand-orange/10 text-[#f3f5f5]' : 'border-[#2d3338] bg-[#101316] text-[#9aa4ac]'}`}
        >
          {right}
        </button>
      </div>
    </Surface>
  )
}

function KV({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-[#2d3338] bg-[#0f1113] p-2">
      <div className="text-[10px] font-semibold uppercase text-[#818c95]">{label}</div>
      <div className="mt-1 break-words text-xs text-[#d6dde2]">{value}</div>
    </div>
  )
}

function RelationshipCanvas({ model, selectedObjectId, onSelect }: { model: SemanticModel; selectedObjectId: string; onSelect: (id: string) => void }) {
  const relationships = useMemo(() => model.relationships.filter(rel => rel.status !== 'rejected'), [model.relationships])

  return (
      <Panel className="overflow-hidden">
      <PanelHeader
        title="Relationship Canvas"
        subtitle="Business entities, candidate joins, fanout risk, and validation evidence in one modeling surface."
        action={<StatusPill tone={model.readinessLevel === 'ready' ? 'ready' : model.readinessLevel === 'blocked' ? 'blocked' : 'warning'}>{model.readiness}% ready</StatusPill>}
      />
      <div className="p-4">
        <div
          className="relative min-h-[620px] overflow-hidden rounded-md border border-[#273038] bg-[#0f1113]"
          style={{
            backgroundImage: 'linear-gradient(#1f252a 1px, transparent 1px), linear-gradient(90deg, #1f252a 1px, transparent 1px)',
            backgroundSize: '28px 28px',
          }}
        >
          <div className="absolute left-4 top-4 z-10 flex flex-wrap gap-2">
            <StatusPill tone="info">{relationships.length} relationships</StatusPill>
            <StatusPill tone={model.relationships.some(rel => rel.fanoutRisk === 'high' && rel.status !== 'rejected') ? 'blocked' : 'ready'}>fanout check</StatusPill>
          </div>
          <svg className="absolute inset-0 h-full w-full" aria-hidden="true">
            {relationships.map((rel, index) => <RelationshipLine key={`${rel.id}-line-${index}`} relationship={rel} selected={selectedObjectId === rel.id} />)}
          </svg>
          {model.entities.map(entity => (
            <EntityNode key={entity.id} entity={entity} selected={selectedObjectId === entity.id} onSelect={() => onSelect(entity.id)} />
          ))}
          {relationships.map((rel, index) => <RelationshipHotspot key={`${rel.id}-hotspot-${index}`} relationship={rel} selected={selectedObjectId === rel.id} onSelect={() => onSelect(rel.id)} />)}
        </div>
      </div>
    </Panel>
  )
}

function RelationshipLine({ relationship, selected }: { relationship: Relationship; selected: boolean }) {
  const from = positions[relationship.fromEntity] ?? { x: 45, y: 45 }
  const to = positions[relationship.toEntity] ?? { x: 55, y: 55 }
  const tone = relationship.fanoutRisk === 'high' ? '#f87171' : relationship.fanoutRisk === 'medium' ? '#fbbf24' : '#f97316'
  return <line x1={`${from.x}%`} y1={`${from.y}%`} x2={`${to.x}%`} y2={`${to.y}%`} stroke={tone} strokeWidth={selected ? 4 : 2} strokeDasharray={relationship.status === 'candidate' ? '8 6' : undefined} opacity={selected ? 0.95 : 0.55} />
}

function RelationshipHotspot({ relationship, selected, onSelect }: { relationship: Relationship; selected: boolean; onSelect: () => void }) {
  const from = positions[relationship.fromEntity] ?? { x: 45, y: 45 }
  const to = positions[relationship.toEntity] ?? { x: 55, y: 55 }
  const left = (from.x + to.x) / 2
  const top = (from.y + to.y) / 2
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`absolute -translate-x-1/2 -translate-y-1/2 rounded-md border px-2 py-1 text-xs shadow-[0_10px_24px_rgba(0,0,0,0.22)] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring ${
        selected ? 'border-brand-orange bg-brand-orange text-white' : 'border-[#3a4147] bg-[#1b2025] text-[#d6dde2] hover:border-brand-orange/60 hover:bg-[#242b31]'
      }`}
      style={{ left: `${left}%`, top: `${top}%` }}
    >
      {relationship.cardinality} · {relationship.validationStatus}
    </button>
  )
}

function EntityNode({ entity, selected, onSelect }: { entity: Entity; selected: boolean; onSelect: () => void }) {
  const pos = positions[entity.id] ?? { x: 50, y: 50 }
  const kind = entityKind(entity)
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`absolute w-[176px] -translate-x-1/2 -translate-y-1/2 rounded-md border p-3 text-left shadow-[0_18px_34px_rgba(0,0,0,0.26)] transition focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring ${
        selected ? 'border-brand-orange bg-brand-orange/15 ring-1 ring-brand-orange/20' : 'border-[#384149] bg-[#191d21] hover:border-brand-orange/50 hover:bg-[#20262b]'
      }`}
      style={{ left: `${pos.x}%`, top: `${pos.y}%` }}
    >
      <div className="flex items-center gap-2">
        <TableProperties className="h-4 w-4 text-brand-orange" />
        <span className="truncate text-sm font-semibold text-[#f3f5f5]">{entity.businessName}</span>
      </div>
      <div className="mt-1 truncate text-xs text-[#9aa4ac]">{entity.table} · PK {entity.primaryKey}</div>
      <div className="mt-2 flex items-center justify-between text-xs text-[#cdd3d8]">
        <span>{entity.fields.length} fields</span>
        <span className="rounded border border-[#303840] bg-[#111417] px-1.5 py-0.5 text-[10px] uppercase text-[#818c95]">{kind}</span>
      </div>
    </button>
  )
}

function entityKind(entity: Entity) {
  if (entity.id.includes('order_items')) return 'detail'
  if (entity.id.includes('orders') || entity.id.includes('refunds')) return 'fact'
  return 'dim'
}

function ValidationDrawer({ model, onValidate }: { model: SemanticModel; onValidate: () => void }) {
  return (
    <div className="grid gap-4 p-4 md:grid-cols-2">
      <Panel>
        <PanelHeader title="Agent Readiness" subtitle="Scores do not override blockers." action={<Button size="sm" variant="brand-primary" onClick={onValidate}><Play className="h-4 w-4" /> Validate</Button>} />
        <div className="space-y-4 p-4">
          {model.readinessDetail.components.map((component, index) => (
            <div key={`${component.id}-${index}`}>
              <div className="mb-1 flex justify-between text-sm">
                <span className="text-white">{component.name}</span>
                <StatusPill tone={readinessTone(component.status)}>{component.status}</StatusPill>
              </div>
              <ScoreBar value={component.score} level={component.status} />
            </div>
          ))}
        </div>
      </Panel>
      <Panel>
        <PanelHeader title="Coverage and Issues" subtitle="Readiness changes after fixes." />
        <div className="grid gap-4 p-4">
          <IssueBlock title="Reliable Questions" tone="ready" items={model.readinessDetail.reliableQuestions} />
          <IssueBlock title="Not Reliable Yet" tone="warning" items={model.readinessDetail.unreliableQuestions} />
          <IssueBlock title="Blockers" tone="blocked" items={model.readinessDetail.blockers} empty="No hard blockers remain." />
          <IssueBlock title="Warnings" tone="warning" items={model.readinessDetail.warnings} empty="No warnings remain." />
        </div>
      </Panel>
    </div>
  )
}

function AdvancedDsl({ model }: { model: SemanticModel }) {
  const compact = {
    model: model.name,
    status: model.status,
    version: model.publishedVersion,
    entities: model.entities.map(entity => ({ name: entity.name, table: entity.table, primary_key: entity.primaryKey })),
    relationships: model.relationships.map(rel => ({ from: rel.fromEntity, to: rel.toEntity, join: rel.joinFields, cardinality: rel.cardinality, validation: rel.validationStatus })),
    metrics: model.metrics.map(metric => ({ name: metric.name, formula: metric.formula, filter: metric.filter, owner: metric.owner, certification: metric.certification })),
  }
  return (
    <div className="p-4">
      <pre className="overflow-x-auto rounded-md border border-[#2d3338] bg-[#101214] p-4 text-xs text-[#d6dde2] custom-scrollbar">{JSON.stringify(compact, null, 2)}</pre>
    </div>
  )
}

function IssueBlock({ title, tone, items, empty }: { title: string; tone: 'ready' | 'warning' | 'blocked'; items: string[]; empty?: string }) {
  return (
    <Surface className="p-3">
      <div className="mb-2 flex items-center justify-between">
        <SectionTitle>{title}</SectionTitle>
        <StatusPill tone={tone}>{items.length}</StatusPill>
      </div>
      <div className="space-y-2">
        {(items.length ? items : [empty ?? 'None']).map((item, index) => <CheckLine key={`${item}-${index}`} tone={items.length ? tone : 'ready'}>{item}</CheckLine>)}
      </div>
    </Surface>
  )
}
