import { Check, Pencil, X } from 'lucide-react'
import { Button } from '../../../components/ui/button'
import { useDataModelingStore } from '../store/useDataModelingStore'
import { CheckLine, PanelHeader, ScoreBar, SectionTitle, StatusPill, readinessTone } from '../components/modelingUi'
import type { SemanticModel } from '../types'

export function ModelInspector({ model, selectedObjectId }: { model: SemanticModel; selectedObjectId: string }) {
  const acceptSuggestion = useDataModelingStore(state => state.acceptSuggestion)
  const editAcceptSuggestion = useDataModelingStore(state => state.editAcceptSuggestion)
  const rejectSuggestion = useDataModelingStore(state => state.rejectSuggestion)
  const fixFanoutRelationship = useDataModelingStore(state => state.fixFanoutRelationship)
  const rejectRelationship = useDataModelingStore(state => state.rejectRelationship)

  const entity = model.entities.find(item => item.id === selectedObjectId)
  const relationship = model.relationships.find(item => item.id === selectedObjectId)
  const metric = model.metrics.find(item => item.id === selectedObjectId)
  const dimension = model.dimensions.find(item => item.id === selectedObjectId)
  const calculated = model.calculatedFields.find(item => item.id === selectedObjectId)
  const suggestion = model.suggestions.find(item => item.id === selectedObjectId)

  if (!selectedObjectId) {
    return (
      <aside className="h-full min-h-0 overflow-y-auto border-l border-[#2a2a2a] bg-[#1b1b1b] custom-scrollbar">
        <PanelHeader title="Inspector" subtitle="Select an object on the canvas or tree." />
        <div className="space-y-4 p-4">
          <Block title="Model Readiness">
            <ScoreBar value={model.readiness} level={model.readinessLevel} />
            <div className="mt-3 space-y-2">
              {model.readinessDetail.blockers.map(item => <CheckLine key={item} tone="blocked">{item}</CheckLine>)}
              {model.readinessDetail.warnings.slice(0, 2).map(item => <CheckLine key={item} tone="warning">{item}</CheckLine>)}
            </div>
          </Block>
          <Block title="Permission">
            <StatusPill tone="info">Draft semantic model</StatusPill>
            <p className="mt-2 text-sm text-[#c7c7c7]">Published versions are available to Agent, MCP, Saved Query, Dashboard, and future Data Skills.</p>
          </Block>
        </div>
      </aside>
    )
  }

  return (
    <aside className="h-full min-h-0 overflow-y-auto border-l border-[#2a2a2a] bg-[#1b1b1b] custom-scrollbar">
      <PanelHeader title="Inspector" subtitle="Definition, mapping, profile, evidence, validation, lineage, permission" />
      <div className="space-y-4 p-4">
        {entity && (
          <>
            <Block title="Definition">
              <h3 className="text-sm font-semibold text-white">{entity.businessName}</h3>
              <p className="mt-2 text-sm text-[#c7c7c7]">{entity.description}</p>
            </Block>
            <Block title="Physical Mapping">
              <KV label="Table" value={entity.table} />
              <KV label="Primary key" value={entity.primaryKey} />
              <KV label="Modeled fields" value={String(entity.fields.length)} />
            </Block>
            <Block title="Permission">
              <StatusPill tone="ready">Available to semantic tools</StatusPill>
            </Block>
          </>
        )}

        {relationship && (
          <>
            <Block title="Relationship Definition">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-sm font-semibold text-white">{relationship.label}</h3>
                <StatusPill tone={readinessTone(relationship.validationStatus)}>{relationship.validationStatus}</StatusPill>
              </div>
              <div className="mt-3 space-y-2">
                <KV label="Join fields" value={relationship.joinFields.map(field => `${field.from} = ${field.to}`).join(', ')} />
                <KV label="Cardinality" value={relationship.cardinality} />
                <KV label="FK evidence" value={relationship.fkEvidence} />
              </div>
            </Block>
            <Block title="Profile">
              <MetricLine label="Unique rate" value={relationship.uniqueRate} />
              <MetricLine label="Orphan rate" value={relationship.orphanRate} />
              <KV label="Fanout risk" value={relationship.fanoutRisk} />
            </Block>
            <Block title="Validation">
              <p className="text-sm text-[#c7c7c7]">{relationship.validationMessage}</p>
              {relationship.fanoutRisk === 'high' && relationship.status !== 'rejected' && (
                <div className="mt-3 grid gap-2">
                  <Button variant="brand-primary" onClick={() => fixFanoutRelationship(relationship.id)}>Fix fanout with order aggregate</Button>
                  <Button variant="secondary" onClick={() => rejectRelationship(relationship.id)}>Reject candidate</Button>
                </div>
              )}
            </Block>
          </>
        )}

        {metric && (
          <>
            <Block title="Metric Definition">
              <h3 className="text-sm font-semibold text-white">{metric.businessName}</h3>
              <p className="mt-2 text-sm text-[#c7c7c7]">{metric.definition}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <StatusPill>{metric.kind}</StatusPill>
                <StatusPill tone={metric.certification === 'certified' ? 'ready' : 'warning'}>{metric.certification}</StatusPill>
              </div>
            </Block>
            <Block title="Formula">
              <KV label="Expression" value={metric.formula} />
              <KV label="Filter" value={metric.filter} />
              <KV label="Time field" value={metric.timeField} />
              <KV label="Default grain" value={metric.defaultGrain} />
              <KV label="Owner" value={metric.owner} />
            </Block>
            <Block title="Validation">
              <p className="text-sm text-[#c7c7c7]">{metric.preview.validation}</p>
            </Block>
            <Block title="Lineage">
              <div className="flex flex-wrap gap-2">{metric.lineage.map(item => <StatusPill key={item}>{item}</StatusPill>)}</div>
            </Block>
          </>
        )}

        {dimension && (
          <Block title="Dimension">
            <h3 className="text-sm font-semibold text-white">{dimension.name}</h3>
            <p className="mt-2 text-sm text-[#c7c7c7]">{dimension.description}</p>
            <div className="mt-3 space-y-2">
              <KV label="Entity" value={dimension.entityId} />
              <KV label="Field" value={dimension.field} />
            </div>
          </Block>
        )}

        {calculated && (
          <Block title="Calculated Field">
            <h3 className="text-sm font-semibold text-white">{calculated.name}</h3>
            <pre className="mt-3 whitespace-pre-wrap rounded border border-[#333] bg-[#151515] p-3 text-xs text-[#d6d6d6]">{calculated.expression}</pre>
            <p className="mt-2 text-sm text-[#bdbdbd]">{calculated.description}</p>
          </Block>
        )}

        {suggestion && (
          <>
            <Block title="Agent Suggestion">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-sm font-semibold text-white">{suggestion.title}</h3>
                <StatusPill tone={readinessTone(suggestion.status === 'rejected' ? 'blocked' : suggestion.status === 'pending' ? 'warning' : 'ready')}>{suggestion.status}</StatusPill>
                <StatusPill tone="info">{Math.round(suggestion.confidence * 100)}%</StatusPill>
              </div>
              <p className="mt-2 text-sm text-[#c7c7c7]">{suggestion.recommendation}</p>
            </Block>
            <Block title="Evidence">
              <div className="space-y-2">{suggestion.evidence.map(item => <KV key={item.label} label={item.label} value={item.detail} />)}</div>
            </Block>
            <Block title="Validation">
              <p className="text-sm text-[#c7c7c7]">{suggestion.validation}</p>
              <div className="mt-3 grid grid-cols-3 gap-2">
                <Button size="sm" variant="brand-ghost" onClick={() => acceptSuggestion(suggestion.id)}><Check className="h-4 w-4" /> Accept</Button>
                <Button size="sm" variant="secondary" onClick={() => editAcceptSuggestion(suggestion.id)}><Pencil className="h-4 w-4" /> Edit</Button>
                <Button size="sm" variant="ghost" onClick={() => rejectSuggestion(suggestion.id)}><X className="h-4 w-4" /> Reject</Button>
              </div>
            </Block>
          </>
        )}
      </div>
    </aside>
  )
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-md border border-[#2a2a2a] bg-[#191919] p-3">
      <SectionTitle>{title}</SectionTitle>
      <div className="mt-2">{children}</div>
    </section>
  )
}

function KV({ label, value }: { label: string; value: string }) {
  return (
    <div className="mb-2 grid gap-1 text-xs last:mb-0">
      <span className="text-[#8d8d8d]">{label}</span>
      <span className="break-words text-[#d6d6d6]">{value}</span>
    </div>
  )
}

function MetricLine({ label, value }: { label: string; value: number }) {
  return (
    <div className="mb-3">
      <div className="mb-1 flex justify-between text-xs text-[#a0a0a0]">
        <span>{label}</span>
        <span>{value}%</span>
      </div>
      <ScoreBar value={value} />
    </div>
  )
}
