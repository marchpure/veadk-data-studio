import { Calculator, GitBranch, Lightbulb, Link2, Sigma, TableProperties } from 'lucide-react'
import type { SemanticModel } from '../types'

interface ObjectTreeProps {
  model: SemanticModel
  selectedObjectId: string
  onSelect: (id: string) => void
}

export function ObjectTree({ model, selectedObjectId, onSelect }: ObjectTreeProps) {
  return (
    <div className="min-h-0 overflow-y-auto p-3 custom-scrollbar">
      <ObjectGroup title="Entities" icon={<TableProperties className="h-4 w-4" />}>
        {model.entities.map(entity => (
          <ObjectButton key={entity.id} id={entity.id} active={selectedObjectId === entity.id} onSelect={onSelect} title={entity.businessName} subtitle={entity.table} />
        ))}
      </ObjectGroup>
      <ObjectGroup title="Relationships" icon={<Link2 className="h-4 w-4" />}>
        {model.relationships.map(rel => (
          <ObjectButton key={rel.id} id={rel.id} active={selectedObjectId === rel.id} onSelect={onSelect} title={rel.label} subtitle={`${rel.cardinality} · ${rel.validationMessage}`} attention={rel.validationStatus === 'blocked' ? 'blocked' : rel.validationStatus === 'warning' ? 'review' : undefined} />
        ))}
      </ObjectGroup>
      <ObjectGroup title="Metrics" icon={<Sigma className="h-4 w-4" />}>
        {model.metrics.map(metric => (
          <ObjectButton key={metric.id} id={metric.id} active={selectedObjectId === metric.id} onSelect={onSelect} title={metric.businessName} subtitle={`${metric.kind} · ${metric.certification}`} attention={metric.certification === 'draft' ? 'draft' : undefined} />
        ))}
      </ObjectGroup>
      <ObjectGroup title="Dimensions" icon={<GitBranch className="h-4 w-4" />}>
        {model.dimensions.map(dimension => (
          <ObjectButton key={dimension.id} id={dimension.id} active={selectedObjectId === dimension.id} onSelect={onSelect} title={dimension.name} subtitle={dimension.field} />
        ))}
      </ObjectGroup>
      <ObjectGroup title="Calculated Fields" icon={<Calculator className="h-4 w-4" />}>
        {model.calculatedFields.map(field => (
          <ObjectButton key={field.id} id={field.id} active={selectedObjectId === field.id} onSelect={onSelect} title={field.name} subtitle={field.expression} />
        ))}
      </ObjectGroup>
      <ObjectGroup title="Suggestions" icon={<Lightbulb className="h-4 w-4" />}>
        {model.suggestions.map(suggestion => (
          <ObjectButton key={suggestion.id} id={suggestion.id} active={selectedObjectId === suggestion.id} onSelect={onSelect} title={suggestion.title} subtitle={suggestion.status} attention={suggestion.status === 'pending' ? 'review' : suggestion.status === 'rejected' ? 'rejected' : undefined} />
        ))}
      </ObjectGroup>
    </div>
  )
}

function ObjectGroup({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="mb-4">
      <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase text-[#8b8b8b]">
        {icon}
        {title}
      </div>
      <div className="space-y-1">{children}</div>
    </section>
  )
}

function ObjectButton({ id, active, onSelect, title, subtitle, attention }: {
  id: string
  active: boolean
  onSelect: (id: string) => void
  title: string
  subtitle: string
  attention?: string
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(id)}
      className={`w-full rounded-md border px-2.5 py-2 text-left transition focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring ${
        active ? 'border-brand-orange/50 bg-brand-orange/10' : 'border-transparent bg-transparent hover:border-[#333] hover:bg-[#222]'
      }`}
    >
      <div className="flex min-w-0 items-center justify-between gap-2">
        <span className="truncate text-sm text-white">{title}</span>
        {attention && <span className="shrink-0 text-[11px] text-amber-300">{attention}</span>}
      </div>
      <div className="mt-1 truncate text-xs text-[#8d8d8d]">{subtitle}</div>
    </button>
  )
}
