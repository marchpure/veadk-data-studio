import { useMemo, useState } from 'react'
import { Check, Pencil, X } from 'lucide-react'
import { Button } from '../../../components/ui/button'
import { StatusPill, Panel, PanelHeader, SectionTitle, readinessTone } from './modelingUi'
import { useDataModelingStore } from '../store/useDataModelingStore'
import type { AgentSuggestion, DataSourceProfile, TableCategory } from '../types'

const categoryLabels: Record<TableCategory, string> = {
  fact: 'Fact',
  dimension: 'Dimension',
  bridge: 'Bridge',
  log: 'Log',
}

export function SchemaProfilePanel({ profile, compact = false }: { profile: DataSourceProfile; compact?: boolean }) {
  const [tableName, setTableName] = useState(profile.tables[0]?.name ?? '')
  const selectedTable = useMemo(() => profile.tables.find(table => table.name === tableName) ?? profile.tables[0], [profile.tables, tableName])

  return (
    <Panel className="min-w-0 overflow-hidden">
      <PanelHeader
        title={`${profile.name} Schema / Profile`}
        subtitle={`${profile.schema} schema · ${profile.profileCoverage}% profiled · ${profile.tables.length} tables`}
        action={<StatusPill tone={profile.status === 'ready' ? 'ready' : profile.status === 'stale' ? 'warning' : 'neutral'}>{profile.status}</StatusPill>}
      />
      <div className={`grid min-w-0 gap-0 ${compact ? 'lg:grid-cols-[240px_1fr]' : 'lg:grid-cols-[280px_1fr]'}`}>
        <div className="min-w-0 border-b border-[#2a2a2a] lg:border-b-0 lg:border-r">
          <div className="max-h-[420px] overflow-y-auto p-3 custom-scrollbar">
            {profile.tables.map(table => (
              <button
                key={table.name}
                onClick={() => setTableName(table.name)}
                className={`mb-2 w-full rounded-md border p-3 text-left transition focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring ${
                  selectedTable?.name === table.name ? 'border-brand-orange/40 bg-brand-orange/10' : 'border-[#2a2a2a] bg-[#191919] hover:border-[#3a3a3a]'
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium text-white">{table.name}</span>
                  <StatusPill tone={table.category === 'fact' ? 'info' : table.category === 'dimension' ? 'ready' : table.category === 'bridge' ? 'warning' : 'neutral'}>
                    {categoryLabels[table.category]}
                  </StatusPill>
                </div>
                <div className="mt-2 text-xs tabular-nums text-[#9a9a9a]">{table.rowCount.toLocaleString()} rows</div>
              </button>
            ))}
          </div>
        </div>
        {selectedTable && (
          <div className="min-w-0 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-sm font-semibold text-white">{selectedTable.label}</h3>
              <StatusPill>{selectedTable.name}</StatusPill>
              {selectedTable.timeRange && <StatusPill tone="info">{selectedTable.timeRange}</StatusPill>}
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-3">
              <MiniStat label="Rows" value={selectedTable.rowCount.toLocaleString()} />
              <MiniStat label="Fields" value={String(selectedTable.fields.length)} />
              <MiniStat label="PII fields" value={String(selectedTable.fields.filter(field => field.pii).length)} />
            </div>
            <div className="mt-4 overflow-x-auto custom-scrollbar">
              <table className="min-w-full text-left text-xs">
                <thead className="text-[#8d8d8d]">
                  <tr className="border-b border-[#333]">
                    <th className="py-2 pr-3 font-medium">Field</th>
                    <th className="py-2 pr-3 font-medium">Type</th>
                    <th className="py-2 pr-3 font-medium">Role</th>
                    <th className="py-2 pr-3 font-medium">Null</th>
                    <th className="py-2 pr-3 font-medium">Distinct</th>
                    <th className="py-2 pr-3 font-medium">Min / Max</th>
                    <th className="py-2 pr-3 font-medium">Top values</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedTable.fields.map((field, index) => (
                    <tr key={`${field.name}-${index}`} className="border-b border-[#292929] text-[#d8d8d8]">
                      <td className="py-2 pr-3 font-mono text-[11px] text-white">{field.name}</td>
                      <td className="py-2 pr-3">{field.type}</td>
                      <td className="py-2 pr-3"><StatusPill tone={field.pii ? 'blocked' : field.role === 'amount' ? 'info' : 'neutral'}>{field.role}</StatusPill></td>
                      <td className="py-2 pr-3 tabular-nums">{field.nullRate}%</td>
                      <td className="py-2 pr-3 tabular-nums">{field.distinctCount.toLocaleString()}</td>
                      <td className="py-2 pr-3">{field.min ?? '-'} / {field.max ?? '-'}</td>
                      <td className="py-2 pr-3">{field.topValues.slice(0, 2).map(value => `${value.value} (${value.count})`).join(', ') || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-4">
              <SectionTitle>Sample Rows</SectionTitle>
              <div className="mt-2 grid gap-2">
                {selectedTable.sampleRows.map((row, index) => (
                  <pre key={index} className="overflow-x-auto rounded border border-[#2a2a2a] bg-[#161616] p-3 text-xs text-[#cfcfcf] custom-scrollbar">
                    {JSON.stringify(row, null, 2)}
                  </pre>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </Panel>
  )
}

export function AgentSuggestionList({ suggestions }: { suggestions: AgentSuggestion[] }) {
  const acceptSuggestion = useDataModelingStore(state => state.acceptSuggestion)
  const editAcceptSuggestion = useDataModelingStore(state => state.editAcceptSuggestion)
  const rejectSuggestion = useDataModelingStore(state => state.rejectSuggestion)

  return (
    <div className="grid gap-3">
      {suggestions.map((suggestion, index) => (
        <div key={`${suggestion.id}-${index}`} className="rounded-lg border border-[#2a3136] bg-[#14181b] p-3">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h4 className="text-sm font-medium text-[#f3f5f5]">{suggestion.title}</h4>
                <StatusPill tone={readinessTone(suggestion.status === 'rejected' ? 'blocked' : suggestion.status === 'pending' ? 'warning' : 'ready')}>
                  {suggestion.status}
                </StatusPill>
                <StatusPill tone="info">{Math.round(suggestion.confidence * 100)}% confidence</StatusPill>
              </div>
              <p className="mt-2 text-sm leading-6 text-[#c4ccd2]">{suggestion.recommendation}</p>
            </div>
            <div className="flex shrink-0 gap-1">
              <Button size="sm" variant="brand-ghost" onClick={() => acceptSuggestion(suggestion.id)} aria-label={`Accept ${suggestion.title}`}>
                <Check className="h-4 w-4" /> Accept
              </Button>
              <Button size="sm" variant="secondary" onClick={() => editAcceptSuggestion(suggestion.id)} aria-label={`Edit and accept ${suggestion.title}`}>
                <Pencil className="h-4 w-4" /> Edit
              </Button>
              <Button size="sm" variant="ghost" onClick={() => rejectSuggestion(suggestion.id)} aria-label={`Reject ${suggestion.title}`}>
                <X className="h-4 w-4" /> Reject
              </Button>
            </div>
          </div>
          <div className="mt-3 grid gap-2 md:grid-cols-2">
            <div className="rounded border border-[#252c31] bg-[#0f1113] p-2">
              <SectionTitle>Evidence</SectionTitle>
              <ul className="mt-2 space-y-1 text-xs text-[#bdbdbd]">
                {suggestion.evidence.map((item, index) => <li key={`${item.label}-${index}`}><span className="text-[#f3f5f5]">{item.label}:</span> {item.detail}</li>)}
              </ul>
            </div>
            <div className="rounded border border-[#252c31] bg-[#0f1113] p-2">
              <SectionTitle>Validation</SectionTitle>
              <p className="mt-2 text-xs text-[#bdbdbd]">{suggestion.validation}</p>
              {suggestion.editedNote && <p className="mt-2 text-xs text-brand-orange">{suggestion.editedNote}</p>}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-[#2a3136] bg-[#14181b] p-3">
      <div className="text-xs text-[#818c95]">{label}</div>
      <div className="mt-1 text-sm font-semibold text-[#f3f5f5]">{value}</div>
    </div>
  )
}
