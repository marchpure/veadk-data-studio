import { Check, Pencil, X } from 'lucide-react'
import { Button } from '../../../components/ui/button'
import { useDataModelingStore } from '../store/useDataModelingStore'
import { CheckLine, PanelHeader, ScoreBar, SectionTitle, StatusPill, Surface, modelingStyles, readinessTone } from '../components/modelingUi'
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
      <aside className="h-full min-h-0 overflow-y-auto bg-[#14181b] custom-scrollbar">
        <PanelHeader title="Inspector" subtitle="Select an object on the canvas or tree." />
        <div className="space-y-4 p-4">
          <Block title="Model Readiness">
            <ScoreBar value={model.readiness} level={model.readinessLevel} />
            <div className="mt-3 space-y-2">
              {model.readinessDetail.blockers.map((item, index) => <CheckLine key={`${item}-${index}`} tone="blocked">{item}</CheckLine>)}
              {model.readinessDetail.warnings.slice(0, 2).map((item, index) => <CheckLine key={`${item}-${index}`} tone="warning">{item}</CheckLine>)}
            </div>
          </Block>
          <Block title="Permission">
            <StatusPill tone="info">Draft semantic model</StatusPill>
            <p className="mt-2 text-sm leading-6 text-[#c4ccd2]">Published versions are available to Agent, MCP, Saved Query, Dashboard, and future Data Skills.</p>
          </Block>
        </div>
      </aside>
    )
  }

  return (
    <aside className="h-full min-h-0 overflow-y-auto bg-[#14181b] custom-scrollbar">
      <PanelHeader title="Inspector" subtitle="Definition, mapping, profile, evidence, validation, lineage, permission" />
      <div className="space-y-4 p-4">
        {entity && (
          <>
            <Block title="Definition">
              <h3 className="text-sm font-semibold text-[#f3f5f5]">{entity.businessName}</h3>
              <p className="mt-2 text-sm leading-6 text-[#c4ccd2]">{entity.description}</p>
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
                <h3 className="text-sm font-semibold text-[#f3f5f5]">{relationship.label}</h3>
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
              <p className="text-sm leading-6 text-[#c4ccd2]">{relationship.validationMessage}</p>
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
              <h3 className="text-sm font-semibold text-[#f3f5f5]">{metric.businessName}</h3>
              <p className="mt-2 text-sm leading-6 text-[#c4ccd2]">{metric.definition}</p>
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
              <p className="text-sm leading-6 text-[#c4ccd2]">{metric.preview.validation}</p>
            </Block>
            <Block title="Lineage">
              <div className="flex flex-wrap gap-2">{metric.lineage.map((item, index) => <StatusPill key={`${item}-${index}`}>{item}</StatusPill>)}</div>
            </Block>
          </>
        )}

        {dimension && (
          <Block title="Dimension">
            <h3 className="text-sm font-semibold text-[#f3f5f5]">{dimension.name}</h3>
            <p className="mt-2 text-sm leading-6 text-[#c4ccd2]">{dimension.description}</p>
            <div className="mt-3 space-y-2">
              <KV label="Entity" value={dimension.entityId} />
              <KV label="Field" value={dimension.field} />
            </div>
          </Block>
        )}

        {calculated && (
          <Block title="Calculated Field">
            <h3 className="text-sm font-semibold text-[#f3f5f5]">{calculated.name}</h3>
            <pre className="mt-3 whitespace-pre-wrap rounded border border-[#343a40] bg-[#111315] p-3 text-xs text-[#d6dde2]">{calculated.expression}</pre>
            <p className="mt-2 text-sm leading-6 text-[#c4ccd2]">{calculated.description}</p>
          </Block>
        )}

        {suggestion && (
          <>
            <Block title="Agent Suggestion">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-sm font-semibold text-[#f3f5f5]">{suggestion.title}</h3>
                <StatusPill tone={readinessTone(suggestion.status === 'rejected' ? 'blocked' : suggestion.status === 'pending' ? 'warning' : 'ready')}>{suggestion.status}</StatusPill>
                <StatusPill tone="info">{Math.round(suggestion.confidence * 100)}%</StatusPill>
              </div>
              <p className="mt-2 text-sm leading-6 text-[#c4ccd2]">{suggestion.recommendation}</p>
            </Block>
            <Block title="Evidence">
              <div className="space-y-2">{suggestion.evidence.map((item, index) => <KV key={`${item.label}-${index}`} label={item.label} value={item.detail} />)}</div>
            </Block>
            <Block title="Validation">
              <p className="text-sm leading-6 text-[#c4ccd2]">{suggestion.validation}</p>
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
    <Surface className="p-3">
      <SectionTitle>{title}</SectionTitle>
      <div className="mt-2">{children}</div>
    </Surface>
  )
}

function KV({ label, value }: { label: string; value: string }) {
  return (
    <div className={`${modelingStyles.surfaceInset} mb-2 grid gap-1 p-2 text-xs last:mb-0`}>
      <span className="text-[#87929b]">{label}</span>
      <span className="break-words text-[#d6dde2]">{value}</span>
    </div>
  )
}

function MetricLine({ label, value }: { label: string; value: number }) {
  return (
    <div className="mb-3">
      <div className="mb-1 flex justify-between text-xs text-[#9aa4ac]">
        <span>{label}</span>
        <span>{value}%</span>
      </div>
      <ScoreBar value={value} />
    </div>
  )
}
