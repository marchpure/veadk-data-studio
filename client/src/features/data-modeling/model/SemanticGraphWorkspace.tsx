import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  type Edge,
  type Node,
  type NodeProps,
  type ReactFlowInstance,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Code2, Menu, PanelLeftClose, PanelLeftOpen, Play, Search, TableProperties, X } from 'lucide-react'
import { Button } from '../../../components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../../components/ui/dialog'
import { Input } from '../../../components/ui/input'
import { ObjectTree } from './ObjectTree'
import { ModelInspector } from './ModelInspector'
import { MetricEditor } from './MetricEditor'
import { DataProfileWorkspace } from '../profile/DataProfileWorkspace'
import { CheckLine, Panel, PanelHeader, ScoreBar, SectionTitle, StatusPill, readinessTone } from '../components/modelingUi'
import { useDataModelingStore } from '../store/useDataModelingStore'
import type { Entity, Relationship, SemanticModel, ValidationStatus } from '../types'

const NODE_WIDTH = 220
const NODE_HEIGHT = 126

const baseLayout: Record<string, { x: number; y: number }> = {
  customers: { x: 40, y: 80 },
  stores: { x: 40, y: 270 },
  channels: { x: 40, y: 460 },
  orders: { x: 390, y: 235 },
  order_items: { x: 720, y: 235 },
  products: { x: 1050, y: 235 },
  refunds: { x: 390, y: 455 },
}

function layoutForEntities(entities: Entity[]) {
  const fallbackColumns = 3
  return Object.fromEntries(entities.map((entity, index) => {
    const fallback = {
      x: 80 + (index % fallbackColumns) * 330,
      y: 80 + Math.floor(index / fallbackColumns) * 190,
    }
    return [entity.id, baseLayout[entity.id] ?? fallback]
  }))
}

const nodeTypes = { entityNode: EntityFlowNode }

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

  return (
    <main className={`grid min-h-0 flex-1 bg-[#171717] ${hasInspector ? (treeCollapsed ? 'lg:grid-cols-[56px_minmax(0,1fr)_360px]' : 'lg:grid-cols-[260px_minmax(0,1fr)_360px]') : (treeCollapsed ? 'lg:grid-cols-[56px_minmax(0,1fr)]' : 'lg:grid-cols-[260px_minmax(0,1fr)]')}`}>
      <aside className="hidden min-h-0 border-r border-[#2a2a2a] bg-[#1b1b1b] lg:block">
        <div className="flex items-center justify-between border-b border-[#2a2a2a] px-3 py-2">
          {!treeCollapsed && <span className="text-xs font-medium text-[#a8a8a8]">Objects</span>}
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
          <ReactFlowProvider>
            <RelationshipCanvas model={model} selectedObjectId={selectedObjectId} onSelect={selectObject} />
          </ReactFlowProvider>

          {selectedMetric && <MetricEditor metric={selectedMetric} />}

          <Panel>
            <PanelHeader title="Fields and Profile Evidence" subtitle="Profile evidence stays close to model editing." />
            {profile && <div className="p-4"><DataProfileWorkspace profile={profile} showSuggestions /></div>}
          </Panel>
        </div>
      </section>

      {hasInspector && (
        <div className="hidden min-h-0 lg:block">
          <div className="flex items-center justify-between border-b border-[#2a2a2a] bg-[#1b1b1b] px-4 py-2">
            <span className="text-sm font-medium text-white">Inspector</span>
            <Button size="icon" variant="ghost" onClick={() => selectObject('')} aria-label="Close inspector"><X className="h-4 w-4" /></Button>
          </div>
          <div className="h-[calc(100%-49px)] min-h-0">
            <ModelInspector model={model} selectedObjectId={selectedObjectId} />
          </div>
        </div>
      )}

      <Dialog open={treeOpen} onOpenChange={setTreeOpen}>
        <DialogContent className="left-0 top-0 h-full max-h-none w-[88vw] max-w-sm translate-x-0 translate-y-0 overflow-hidden border-[#2a2a2a] bg-[#1b1b1b] p-0 text-white sm:rounded-none">
          <DialogHeader className="border-b border-[#2a2a2a] p-4">
            <DialogTitle className="text-base">Model Objects</DialogTitle>
          </DialogHeader>
          <ObjectTree model={model} selectedObjectId={selectedObjectId} onSelect={(id) => { selectObject(id); setTreeOpen(false) }} />
        </DialogContent>
      </Dialog>

      <Dialog open={inspectorOpen} onOpenChange={setInspectorOpen}>
        <DialogContent className="left-auto right-0 top-0 h-full max-h-none w-[92vw] max-w-md translate-x-0 translate-y-0 overflow-hidden border-[#2a2a2a] bg-[#1b1b1b] p-0 text-white sm:rounded-none">
          <DialogHeader className="border-b border-[#2a2a2a] p-4">
            <DialogTitle className="text-base">Model Inspector</DialogTitle>
          </DialogHeader>
          <div className="h-[calc(100%-57px)] min-h-0">
            <ModelInspector model={model} selectedObjectId={selectedObjectId} />
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={validationOpen} onOpenChange={setValidationOpen}>
        <DialogContent className="max-h-[88vh] max-w-4xl overflow-y-auto border-[#2a2a2a] bg-[#1a1a1a] p-0 text-white custom-scrollbar">
          <DialogHeader className="border-b border-[#2a2a2a] p-4">
            <DialogTitle className="text-base">Model Validation</DialogTitle>
          </DialogHeader>
          <ValidationDrawer model={model} onValidate={validateModel} />
        </DialogContent>
      </Dialog>

      <Dialog open={advancedOpen} onOpenChange={setAdvancedOpen}>
        <DialogContent className="max-h-[88vh] max-w-5xl overflow-y-auto border-[#2a2a2a] bg-[#1a1a1a] p-0 text-white custom-scrollbar">
          <DialogHeader className="border-b border-[#2a2a2a] p-4">
            <DialogTitle className="text-base">Model Advanced DSL</DialogTitle>
          </DialogHeader>
          <AdvancedDsl model={model} />
        </DialogContent>
      </Dialog>
    </main>
  )
}

function RelationshipCanvas({ model, selectedObjectId, onSelect }: { model: SemanticModel; selectedObjectId: string; onSelect: (id: string) => void }) {
  const [flow, setFlow] = useState<ReactFlowInstance | null>(null)
  const [query, setQuery] = useState('')
  const [layoutVersion, setLayoutVersion] = useState(0)
  const positions = useMemo(() => layoutForEntities(model.entities), [model.entities, layoutVersion])
  const activeRelationships = useMemo(() => model.relationships.filter(rel => rel.status !== 'rejected'), [model.relationships])

  const nodes: Node[] = useMemo(() => model.entities.map(entity => ({
    id: entity.id,
    type: 'entityNode',
    position: positions[entity.id],
    data: {
      entity,
      selected: selectedObjectId === entity.id,
      relationshipCount: activeRelationships.filter(rel => rel.fromEntity === entity.id || rel.toEntity === entity.id).length,
    },
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
  })), [activeRelationships, model.entities, positions, selectedObjectId])

  const edges: Edge[] = useMemo(() => activeRelationships.map(relationship => {
    const blocked = relationship.validationStatus === 'blocked'
    const warning = relationship.validationStatus === 'warning' || relationship.fanoutRisk === 'medium'
    const selected = selectedObjectId === relationship.id
    const color = blocked ? '#f87171' : warning ? '#fbbf24' : '#f97316'
    return {
      id: relationship.id,
      source: relationship.fromEntity,
      target: relationship.toEntity,
      label: `${relationship.cardinality} · ${relationship.fanoutRisk}`,
      type: 'smoothstep',
      animated: selected || blocked,
      markerEnd: { type: MarkerType.ArrowClosed, color },
      style: { stroke: color, strokeWidth: selected ? 3 : 2, opacity: selected ? 0.95 : 0.7 },
      labelStyle: { fill: '#d4d4d4', fontSize: 12 },
      labelBgStyle: { fill: selected ? '#2f1f16' : '#202020', fillOpacity: 0.94 },
      data: { relationship },
    }
  }), [activeRelationships, selectedObjectId])

  const fit = useCallback(() => {
    requestAnimationFrame(() => flow?.fitView({ padding: 0.18, duration: 240 }))
  }, [flow])

  useEffect(() => {
    fit()
  }, [fit, hasCanvasSelectionKey(nodes, edges)])

  const focusObject = () => {
    const lower = query.trim().toLowerCase()
    if (!lower) {
      fit()
      return
    }
    const entity = model.entities.find(item => [item.businessName, item.table, item.id].some(value => value.toLowerCase().includes(lower)))
    const relationship = activeRelationships.find(item => item.label.toLowerCase().includes(lower))
    const targetId = entity?.id ?? relationship?.id
    if (!targetId) return
    onSelect(targetId)
    if (entity && flow) {
      flow.setCenter(positions[entity.id].x + NODE_WIDTH / 2, positions[entity.id].y + NODE_HEIGHT / 2, { zoom: 1.1, duration: 260 })
    }
  }

  return (
    <Panel className="overflow-hidden">
      <PanelHeader
        title="Advanced Relationship Canvas"
        subtitle="Pan, zoom, drag nodes, inspect relationships, and repair validation risks."
        action={<StatusPill tone="info">Interactive</StatusPill>}
      />
      <div className="hidden p-4 lg:block">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <label className="relative min-w-[260px] flex-1">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-[#777]" />
            <Input
              value={query}
              onChange={event => setQuery(event.target.value)}
              onKeyDown={event => { if (event.key === 'Enter') focusObject() }}
              placeholder="Search entity, table, or relationship"
              className="border-[#333] bg-[#151515] pl-9 text-white"
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="secondary" onClick={focusObject}>Focus</Button>
            <Button size="sm" variant="secondary" onClick={fit}>Fit view</Button>
            <Button size="sm" variant="secondary" onClick={() => { setLayoutVersion(value => value + 1); setTimeout(fit, 0) }}>Reset layout</Button>
          </div>
        </div>
        <div className="h-[620px] overflow-hidden rounded-md border border-[#2a2a2a] bg-[#151515]">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onInit={setFlow}
            fitView
            minZoom={0.35}
            maxZoom={1.7}
            nodesDraggable
            panOnDrag
            zoomOnScroll
            proOptions={{ hideAttribution: true }}
            onNodeClick={(_, node) => onSelect(node.id)}
            onEdgeClick={(_, edge) => onSelect(edge.id)}
          >
            <Background color="#333" gap={22} />
            <MiniMap
              pannable
              zoomable
              nodeStrokeColor="#f97316"
              nodeColor="#262626"
              maskColor="rgba(0,0,0,0.45)"
              className="!bg-[#191919]"
            />
            <Controls className="!border !border-[#333] !bg-[#1f1f1f] [&_button]:!border-[#333] [&_button]:!bg-[#1f1f1f] [&_button_svg]:!fill-[#d0d0d0]" />
          </ReactFlow>
        </div>
      </div>
      <div className="grid gap-3 p-4 lg:hidden">
        {activeRelationships.map(relationship => (
          <button
            key={relationship.id}
            type="button"
            onClick={() => onSelect(relationship.id)}
            className={`rounded-md border p-3 text-left focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring ${selectedObjectId === relationship.id ? 'border-brand-orange bg-brand-orange/10' : 'border-[#2a2a2a] bg-[#181818]'}`}
          >
            <div className="text-sm font-medium text-white">{relationship.label}</div>
            <div className="mt-2 flex flex-wrap gap-2">
              <StatusPill>{relationship.cardinality}</StatusPill>
              <StatusPill tone={readinessTone(relationship.validationStatus)}>{relationship.validationStatus}</StatusPill>
              <StatusPill tone={relationship.fanoutRisk === 'high' ? 'blocked' : relationship.fanoutRisk === 'medium' ? 'warning' : 'ready'}>{relationship.fanoutRisk} fanout</StatusPill>
            </div>
          </button>
        ))}
      </div>
    </Panel>
  )
}

function EntityFlowNode({ data }: NodeProps<Node<{ entity: Entity; selected: boolean; relationshipCount: number }>>) {
  const entity = data.entity
  const selected = data.selected
  const type = entity.table.includes('ORDER') ? 'fact' : entity.table.includes('REFUND') ? 'log' : entity.table.includes('ITEM') ? 'bridge' : 'dimension'
  const validation: ValidationStatus = entity.fields.length > 0 ? 'valid' : 'warning'
  return (
    <div className={`w-[220px] rounded-md border p-3 shadow-lg ${selected ? 'border-brand-orange bg-brand-orange/15' : 'border-[#333] bg-[#1f1f1f]'}`}>
      <div className="flex items-center gap-2">
        <TableProperties className="h-4 w-4 text-brand-orange" />
        <span className="min-w-0 flex-1 truncate text-sm font-semibold text-white">{entity.businessName}</span>
      </div>
      <div className="mt-1 truncate text-xs text-[#9a9a9a]">{entity.table}</div>
      <div className="mt-3 grid gap-1 text-xs text-[#cfcfcf]">
        <div className="flex justify-between gap-2"><span>Type</span><span className="capitalize">{type}</span></div>
        <div className="flex justify-between gap-2"><span>Primary key</span><span className="truncate">{entity.primaryKey}</span></div>
        <div className="flex justify-between gap-2"><span>Fields</span><span>{entity.fields.length}</span></div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <StatusPill tone={readinessTone(validation)}>{validation}</StatusPill>
        <StatusPill>{data.relationshipCount} edges</StatusPill>
      </div>
    </div>
  )
}

function hasCanvasSelectionKey(nodes: Node[], edges: Edge[]) {
  return `${nodes.length}:${edges.length}:${nodes.map(node => node.data?.selected ? node.id : '').join('|')}`
}

function ValidationDrawer({ model, onValidate }: { model: SemanticModel; onValidate: () => void }) {
  return (
    <div className="grid gap-4 p-4 md:grid-cols-2">
      <Panel>
        <PanelHeader title="Agent Readiness" subtitle="Scores do not override blockers." action={<Button size="sm" variant="brand-primary" onClick={onValidate}><Play className="h-4 w-4" /> Validate</Button>} />
        <div className="space-y-4 p-4">
          {model.readinessDetail.components.map(component => (
            <div key={component.id}>
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
      <pre className="overflow-x-auto rounded-md border border-[#2a2a2a] bg-[#101010] p-4 text-xs text-[#d4d4d4] custom-scrollbar">{JSON.stringify(compact, null, 2)}</pre>
    </div>
  )
}

function IssueBlock({ title, tone, items, empty }: { title: string; tone: 'ready' | 'warning' | 'blocked'; items: string[]; empty?: string }) {
  return (
    <div className="rounded-md border border-[#2a2a2a] bg-[#181818] p-3">
      <div className="mb-2 flex items-center justify-between">
        <SectionTitle>{title}</SectionTitle>
        <StatusPill tone={tone}>{items.length}</StatusPill>
      </div>
      <div className="space-y-2">
        {(items.length ? items : [empty ?? 'None']).map(item => <CheckLine key={item} tone={items.length ? tone : 'ready'}>{item}</CheckLine>)}
      </div>
    </div>
  )
}
