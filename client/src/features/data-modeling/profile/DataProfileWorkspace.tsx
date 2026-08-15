import { Bot, ChevronRight, Database, PanelRightClose, ShieldAlert, Table2 } from 'lucide-react'
import { Button } from '../../../components/ui/button'
import { AgentSuggestionList } from '../components/SchemaProfilePanel'
import { MetricTile, Panel, PanelHeader, SectionTitle, StatusPill, Surface, modelingStyles } from '../components/modelingUi'
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
                selectedTable?.name === table.name ? modelingStyles.active : 'border-[#2d3338] bg-[#181b1f] hover:border-[#46505a] hover:bg-[#20252a]'
              }`}
            >
              <div className="flex min-w-0 items-center justify-between gap-2">
                <span className="truncate text-sm font-medium text-[#f3f5f5]">{table.name}</span>
                <span className="text-xs capitalize text-[#9aa4ac]">{table.category}</span>
              </div>
              <div className="mt-2 flex items-center justify-between text-xs text-[#87929b]">
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
          action={<span className="text-xs text-[#9aa4ac]">{selectedTable?.category ?? 'table'}</span>}
        />
        {selectedTable && (
          <div className="p-4">
            <div className="grid gap-3 sm:grid-cols-3">
              <ProfileStat label="Rows" value={selectedTable.rowCount.toLocaleString()} />
              <ProfileStat label="Fields" value={String(selectedTable.fields.length)} />
              <ProfileStat label="PII Fields" value={String(selectedTable.fields.filter(field => field.pii).length)} />
            </div>

            <div className="mt-4 overflow-x-auto rounded-md border border-[#2d3338] custom-scrollbar">
              <table className="min-w-[760px] w-full text-left text-xs">
                <thead className={modelingStyles.tableHead}>
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
                  {selectedTable.fields.map((field, index) => (
                    <tr
                      key={`${field.name}-${index}`}
                      className={`border-t border-[#272d32] ${selectedField?.name === field.name ? 'bg-brand-orange/10' : 'bg-[#191c1f]'}`}
                    >
                      <td className="px-3 py-2">
                        <button
                          type="button"
                          onClick={() => selectProfileField(field.name)}
                          className="font-mono text-[11px] text-[#f3f5f5] underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                        >
                          {field.name}
                        </button>
                      </td>
                      <td className="px-3 py-2 text-[#d6dde2]">{field.type}</td>
                      <td className="px-3 py-2"><StatusPill tone={roleTone[field.role]}>{field.role}</StatusPill></td>
                      <td className="px-3 py-2 tabular-nums text-[#d6dde2]">{field.nullRate}%</td>
                      <td className="px-3 py-2 tabular-nums text-[#d6dde2]">{field.distinctCount.toLocaleString()}</td>
                      <td className="px-3 py-2 text-[#d6dde2]">{field.min ?? '-'} / {field.max ?? '-'}</td>
                      <td className="px-3 py-2 text-[#d6dde2]">{field.topValues.slice(0, 2).map(value => `${value.value} (${value.count})`).join(', ') || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="mt-4">
              <SectionTitle>Sample Rows</SectionTitle>
              <div className="mt-2 overflow-x-auto rounded-md border border-[#2d3338] custom-scrollbar">
                <table className="min-w-[720px] w-full text-left text-xs">
                  <thead className={modelingStyles.tableHead}>
                    <tr>{Object.keys(selectedTable.sampleRows[0] ?? {}).map(key => <th key={key} className="px-3 py-2 font-medium">{key}</th>)}</tr>
                  </thead>
                  <tbody>
                    {selectedTable.sampleRows.map((row, index) => (
                      <tr key={index} className={modelingStyles.tableRow}>
                        {Object.values(row).map((value, cell) => <td key={cell} className="px-3 py-2 text-[#d6dde2]">{String(value)}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {showSuggestions && (
              <Surface className="mt-4 p-3">
                <div className="mb-3 flex items-center gap-2 text-sm font-medium text-[#f3f5f5]">
                  <Bot className="h-4 w-4 text-brand-orange" />
                  Evidence-backed recommendations
                </div>
                <AgentSuggestionList suggestions={model.suggestions} />
              </Surface>
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
      <Surface className="p-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-[#f3f5f5]">
          <Table2 className="h-4 w-4 text-brand-orange" />
          {table?.name}.{field.name}
        </div>
        <div className="mt-3 grid gap-2 text-xs text-[#d6dde2]">
          <ProfileKV label="Type" value={field.type} />
          <ProfileKV label="Inferred role" value={field.role} />
          <ProfileKV label="Nullable" value={field.nullable ? 'yes' : 'no'} />
          <ProfileKV label="Cardinality" value={`${field.distinctCount.toLocaleString()} distinct`} />
          <ProfileKV label="Min / Max" value={`${field.min ?? '-'} / ${field.max ?? '-'}`} />
          {timestampRange && <ProfileKV label="Timestamp range" value={`${field.min ?? table?.timeRange ?? '-'} to ${field.max ?? table?.timeRange ?? '-'}`} />}
        </div>
      </Surface>

      <Surface className="p-3">
        <SectionTitle>Null Percentage</SectionTitle>
        <div className="mt-3">
          <div className="mb-1 flex justify-between text-xs text-[#c4ccd2]">
            <span>{field.nullRate}% null</span>
            <span>{100 - field.nullRate}% filled</span>
          </div>
          <div className="h-2 rounded bg-[#2b3136]">
            <div className="h-full rounded bg-amber-400" style={{ width: `${Math.min(100, field.nullRate)}%` }} />
          </div>
        </div>
      </Surface>

      <Surface className="p-3">
        <SectionTitle>Top Values</SectionTitle>
        <div className="mt-3 space-y-2">
          {field.topValues.length > 0 ? field.topValues.map((item, index) => (
            <div key={`${item.value}-${index}`}>
              <div className="mb-1 flex justify-between text-xs text-[#c4ccd2]">
                <span>{item.value}</span>
                <span>{item.count.toLocaleString()}</span>
              </div>
              <div className="h-1.5 rounded bg-[#2b3136]">
                <div className="h-full rounded bg-brand-orange" style={{ width: `${Math.min(100, Math.max(8, item.count / topMax * 100))}%` }} />
              </div>
            </div>
          )) : <p className="text-sm text-[#9aa4ac]">No dominant top values in this sample.</p>}
        </div>
      </Surface>

      {(field.role === 'amount' || field.role === 'measure' || field.type.toLowerCase().includes('number')) && (
        <Surface className="p-3">
          <SectionTitle>Numeric Histogram</SectionTitle>
          <div className="mt-3 flex h-24 items-end gap-1">
            {histogram.map((height, index) => (
              <div key={index} className="flex-1 rounded-t bg-brand-orange/75" style={{ height: `${height}%` }} />
            ))}
          </div>
          <div className="mt-2 flex justify-between text-xs text-[#9aa4ac]">
            <span>{field.min ?? 'min'}</span>
            <span>{field.max ?? 'max'}</span>
          </div>
        </Surface>
      )}

      <Surface className="p-3">
        <SectionTitle>Sample Values</SectionTitle>
        <div className="mt-2 flex flex-wrap gap-2">
          {(sampleValues.length ? sampleValues : ['no sample']).map((value, index) => <span key={`${String(value)}-${index}`} className="rounded border border-[#343a40] bg-[#111315] px-2 py-1 text-xs text-[#d6dde2]">{String(value)}</span>)}
        </div>
      </Surface>

      <div className={`rounded-md border p-3 ${field.pii ? 'border-red-500/30 bg-red-500/10' : 'border-emerald-500/20 bg-emerald-500/5'}`}>
        <div className="flex items-start gap-2">
          {field.pii ? <ShieldAlert className="mt-0.5 h-4 w-4 text-red-300" /> : <Database className="mt-0.5 h-4 w-4 text-emerald-300" />}
          <div>
            <div className="text-sm font-medium text-[#f3f5f5]">{field.pii ? 'PII policy required' : 'Safe for semantic modeling'}</div>
            <p className="mt-1 text-xs leading-5 text-[#cdd3d8]">
              {field.pii ? 'This field should be masked and excluded from MCP semantic tools by default.' : 'The generator can use this field for entity mapping, metric logic, or dimensions.'}
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

function ProfileStat({ label, value }: { label: string; value: string }) {
  return <MetricTile label={label} value={value} />
}

function ProfileKV({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-[#272d32] pb-2 last:border-0 last:pb-0">
      <span className="text-[#87929b]">{label}</span>
      <span className="break-words text-right text-[#d6dde2]">{value}</span>
    </div>
  )
}
