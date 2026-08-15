import { Bot, ChevronRight, Database, PanelRightClose, ShieldAlert, Table2 } from 'lucide-react'
import { Button } from '../../../components/ui/button'
import { AgentSuggestionList } from '../components/SchemaProfilePanel'
import { Panel, PanelHeader, SectionTitle, StatusPill } from '../components/modelingUi'
import { useDataModelingStore, selectActiveModel } from '../store/useDataModelingStore'
import type { DataSourceProfile, FieldRole, ProfileField, TableCategory } from '../types'

const categoryTone: Record<TableCategory, 'ready' | 'warning' | 'info' | 'neutral'> = {
  fact: 'info',
  dimension: 'ready',
  bridge: 'warning',
  log: 'neutral',
}

const roleTone: Record<FieldRole, 'ready' | 'warning' | 'blocked' | 'info' | 'neutral'> = {
  id: 'info',
  amount: 'ready',
  time: 'warning',
  status: 'neutral',
  pii: 'blocked',
  attribute: 'neutral',
  measure: 'ready',
}

export function DataProfileWorkspace({ profile, showSuggestions = false }: { profile: DataSourceProfile; showSuggestions?: boolean }) {
  const selectedTableName = useDataModelingStore(state => state.selectedProfileTable)
  const selectedFieldName = useDataModelingStore(state => state.selectedProfileField)
  const selectProfileTable = useDataModelingStore(state => state.selectProfileTable)
  const selectProfileField = useDataModelingStore(state => state.selectProfileField)
  const model = useDataModelingStore(selectActiveModel)

  const selectedTable = profile.tables.find(table => table.name === selectedTableName) ?? profile.tables[0]
  const selectedField = selectedTable?.fields.find(field => field.name === selectedFieldName) ?? selectedTable?.fields[0]

  return (
    <div className={`grid min-w-0 gap-4 ${selectedFieldName ? 'xl:grid-cols-[220px_minmax(0,1fr)_340px]' : 'xl:grid-cols-[220px_minmax(0,1fr)]'}`}>
      <Panel className="min-w-0 overflow-hidden">
        <PanelHeader
          title={`${profile.name} Tables`}
          subtitle={`${profile.schema} schema · ${profile.profileCoverage}% profiled`}
          action={<StatusPill tone={profile.status === 'ready' ? 'ready' : 'warning'}>{profile.status}</StatusPill>}
        />
        <div className="max-h-[620px] overflow-y-auto p-3 custom-scrollbar">
          {profile.tables.map(table => (
            <button
              key={table.name}
              type="button"
              onClick={() => selectProfileTable(table.name)}
              className={`mb-2 w-full rounded-md border p-3 text-left transition focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring ${
                selectedTable?.name === table.name ? 'border-brand-orange/50 bg-brand-orange/10' : 'border-[#2a2a2a] bg-[#191919] hover:border-[#444]'
              }`}
            >
              <div className="flex min-w-0 items-center justify-between gap-2">
                <span className="truncate text-sm font-medium text-white">{table.name}</span>
                <span className="text-xs capitalize text-[#9a9a9a]">{table.category}</span>
              </div>
              <div className="mt-2 flex items-center justify-between text-xs text-[#8f8f8f]">
                <span>{table.rowCount.toLocaleString()} rows</span>
                <ChevronRight className="h-3.5 w-3.5" />
              </div>
            </button>
          ))}
        </div>
      </Panel>

      <Panel className="min-w-0 overflow-hidden">
        <PanelHeader
          title={selectedTable ? `${selectedTable.label} Profile` : 'Table Profile'}
          subtitle={selectedTable ? `${selectedTable.name} · ${selectedTable.timeRange ?? 'snapshot profile'}` : undefined}
          action={<span className="text-xs text-[#9a9a9a]">{selectedTable?.category ?? 'table'}</span>}
        />
        {selectedTable && (
          <div className="p-4">
            <div className="grid gap-3 sm:grid-cols-3">
              <ProfileStat label="Rows" value={selectedTable.rowCount.toLocaleString()} />
              <ProfileStat label="Fields" value={String(selectedTable.fields.length)} />
              <ProfileStat label="PII Fields" value={String(selectedTable.fields.filter(field => field.pii).length)} />
            </div>

            <div className="mt-4 overflow-x-auto rounded-md border border-[#2a2a2a] custom-scrollbar">
              <table className="min-w-[760px] w-full text-left text-xs">
                <thead className="bg-[#181818] text-[#8d8d8d]">
                  <tr>
                    <th className="px-3 py-2 font-medium">Field</th>
                    <th className="px-3 py-2 font-medium">Type</th>
                    <th className="px-3 py-2 font-medium">Role</th>
                    <th className="px-3 py-2 font-medium">Null</th>
                    <th className="px-3 py-2 font-medium">Distinct</th>
                    <th className="px-3 py-2 font-medium">Min / Max</th>
                    <th className="px-3 py-2 font-medium">Top Values</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedTable.fields.map(field => (
                    <tr
                      key={field.name}
                      className={`border-t border-[#292929] ${selectedField?.name === field.name ? 'bg-brand-orange/10' : 'bg-[#151515]'}`}
                    >
                      <td className="px-3 py-2">
                        <button
                          type="button"
                          onClick={() => selectProfileField(field.name)}
                          className="font-mono text-[11px] text-white underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                        >
                          {field.name}
                        </button>
                      </td>
                      <td className="px-3 py-2 text-[#d0d0d0]">{field.type}</td>
                      <td className="px-3 py-2"><StatusPill tone={roleTone[field.role]}>{field.role}</StatusPill></td>
                      <td className="px-3 py-2 tabular-nums text-[#d0d0d0]">{field.nullRate}%</td>
                      <td className="px-3 py-2 tabular-nums text-[#d0d0d0]">{field.distinctCount.toLocaleString()}</td>
                      <td className="px-3 py-2 text-[#d0d0d0]">{field.min ?? '-'} / {field.max ?? '-'}</td>
                      <td className="px-3 py-2 text-[#d0d0d0]">{field.topValues.slice(0, 2).map(value => `${value.value} (${value.count})`).join(', ') || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="mt-4">
              <SectionTitle>Sample Rows</SectionTitle>
              <div className="mt-2 overflow-x-auto rounded-md border border-[#2a2a2a] custom-scrollbar">
                <table className="min-w-[720px] w-full text-left text-xs">
                  <thead className="bg-[#181818] text-[#8d8d8d]">
                    <tr>{Object.keys(selectedTable.sampleRows[0] ?? {}).map(key => <th key={key} className="px-3 py-2 font-medium">{key}</th>)}</tr>
                  </thead>
                  <tbody>
                    {selectedTable.sampleRows.map((row, index) => (
                      <tr key={index} className="border-t border-[#292929] bg-[#151515]">
                        {Object.values(row).map((value, cell) => <td key={cell} className="px-3 py-2 text-[#d4d4d4]">{String(value)}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {showSuggestions && (
              <div className="mt-4 rounded-md border border-[#2a2a2a] bg-[#181818] p-3">
                <div className="mb-3 flex items-center gap-2 text-sm font-medium text-white">
                  <Bot className="h-4 w-4 text-brand-orange" />
                  Evidence-backed recommendations
                </div>
                <AgentSuggestionList suggestions={model.suggestions} />
              </div>
            )}
          </div>
        )}
      </Panel>

      {selectedFieldName && selectedField && (
        <Panel className="min-w-0 overflow-hidden">
          <PanelHeader
            title="Field Profile"
            subtitle="Profile evidence used by the generator"
            action={<Button size="sm" variant="ghost" onClick={() => selectProfileField('')} aria-label="Close field profile"><PanelRightClose className="h-4 w-4" /></Button>}
          />
          <FieldInspector field={selectedField} table={selectedTable} />
        </Panel>
      )}
    </div>
  )
}

function FieldInspector({ field, table }: { field: ProfileField; table?: DataSourceProfile['tables'][number] }) {
  const histogramSeed = Math.max(4, Math.min(10, Math.round((field.distinctCount % 9) + 4)))
  const histogram = Array.from({ length: 8 }, (_, index) => 18 + ((histogramSeed * (index + 3)) % 72))
  const topMax = Math.max(1, ...field.topValues.map(value => value.count))
  const sampleValues = table?.sampleRows.map(row => row[field.name]).filter(value => value !== undefined).slice(0, 4) ?? []
  const timestampRange = field.role === 'time' || field.type.toLowerCase().includes('date') || field.type.toLowerCase().includes('timestamp')

  return (
    <div className="space-y-4 p-4">
      <div className="rounded-md border border-[#2a2a2a] bg-[#181818] p-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-white">
          <Table2 className="h-4 w-4 text-brand-orange" />
          {table?.name}.{field.name}
        </div>
        <div className="mt-3 grid gap-2 text-xs text-[#d6d6d6]">
          <ProfileKV label="Type" value={field.type} />
          <ProfileKV label="Inferred role" value={field.role} />
          <ProfileKV label="Nullable" value={field.nullable ? 'yes' : 'no'} />
          <ProfileKV label="Cardinality" value={`${field.distinctCount.toLocaleString()} distinct`} />
          <ProfileKV label="Min / Max" value={`${field.min ?? '-'} / ${field.max ?? '-'}`} />
          {timestampRange && <ProfileKV label="Timestamp range" value={`${field.min ?? table?.timeRange ?? '-'} to ${field.max ?? table?.timeRange ?? '-'}`} />}
        </div>
      </div>

      <div className="rounded-md border border-[#2a2a2a] bg-[#181818] p-3">
        <SectionTitle>Null Percentage</SectionTitle>
        <div className="mt-3">
          <div className="mb-1 flex justify-between text-xs text-[#bdbdbd]">
            <span>{field.nullRate}% null</span>
            <span>{100 - field.nullRate}% filled</span>
          </div>
          <div className="h-2 rounded bg-[#303030]">
            <div className="h-full rounded bg-amber-400" style={{ width: `${Math.min(100, field.nullRate)}%` }} />
          </div>
        </div>
      </div>

      <div className="rounded-md border border-[#2a2a2a] bg-[#181818] p-3">
        <SectionTitle>Top Values</SectionTitle>
        <div className="mt-3 space-y-2">
          {field.topValues.length > 0 ? field.topValues.map(item => (
            <div key={item.value}>
              <div className="mb-1 flex justify-between text-xs text-[#bdbdbd]">
                <span>{item.value}</span>
                <span>{item.count.toLocaleString()}</span>
              </div>
              <div className="h-1.5 rounded bg-[#303030]">
                <div className="h-full rounded bg-brand-orange" style={{ width: `${Math.min(100, Math.max(8, item.count / topMax * 100))}%` }} />
              </div>
            </div>
          )) : <p className="text-sm text-[#9a9a9a]">No dominant top values in this sample.</p>}
        </div>
      </div>

      {(field.role === 'amount' || field.role === 'measure' || field.type.toLowerCase().includes('number')) && (
        <div className="rounded-md border border-[#2a2a2a] bg-[#181818] p-3">
          <SectionTitle>Numeric Histogram</SectionTitle>
          <div className="mt-3 flex h-24 items-end gap-1">
            {histogram.map((height, index) => (
              <div key={index} className="flex-1 rounded-t bg-brand-orange/75" style={{ height: `${height}%` }} />
            ))}
          </div>
          <div className="mt-2 flex justify-between text-xs text-[#9a9a9a]">
            <span>{field.min ?? 'min'}</span>
            <span>{field.max ?? 'max'}</span>
          </div>
        </div>
      )}

      <div className="rounded-md border border-[#2a2a2a] bg-[#181818] p-3">
        <SectionTitle>Sample Values</SectionTitle>
        <div className="mt-2 flex flex-wrap gap-2">
          {(sampleValues.length ? sampleValues : ['no sample']).map(value => <span key={String(value)} className="rounded border border-[#333] bg-[#151515] px-2 py-1 text-xs text-[#d6d6d6]">{String(value)}</span>)}
        </div>
      </div>

      <div className={`rounded-md border p-3 ${field.pii ? 'border-red-500/30 bg-red-500/10' : 'border-emerald-500/20 bg-emerald-500/5'}`}>
        <div className="flex items-start gap-2">
          {field.pii ? <ShieldAlert className="mt-0.5 h-4 w-4 text-red-300" /> : <Database className="mt-0.5 h-4 w-4 text-emerald-300" />}
          <div>
            <div className="text-sm font-medium text-white">{field.pii ? 'PII policy required' : 'Safe for semantic modeling'}</div>
            <p className="mt-1 text-xs text-[#cfcfcf]">
              {field.pii ? 'This field should be masked and excluded from MCP semantic tools by default.' : 'The generator can use this field for entity mapping, metric logic, or dimensions.'}
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

function ProfileStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-[#2a2a2a] bg-[#181818] p-3">
      <div className="text-xs uppercase text-[#858585]">{label}</div>
      <div className="mt-1 text-lg font-semibold text-white">{value}</div>
    </div>
  )
}

function ProfileKV({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-[#292929] pb-2 last:border-0 last:pb-0">
      <span className="text-[#8d8d8d]">{label}</span>
      <span className="break-words text-right text-[#d6d6d6]">{value}</span>
    </div>
  )
}
