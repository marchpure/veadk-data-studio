import { Calculator, LineChart, ShieldCheck } from 'lucide-react'
import { Button } from '../../../components/ui/button'
import { useDataModelingStore } from '../store/useDataModelingStore'
import { Panel, PanelHeader, SectionTitle, StatusPill, Surface, modelingStyles } from '../components/modelingUi'
import type { CertificationStatus, Metric, TimeGrain } from '../types'

export function MetricEditor({ metric }: { metric: Metric }) {
  const updateMetric = useDataModelingStore(state => state.updateMetric)
  const setMetricCertification = useDataModelingStore(state => state.setMetricCertification)

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
      <Panel>
        <PanelHeader title="Metric Editor" subtitle="Formal KPI definition, governance, dimensions, and lineage." action={<StatusPill tone={metric.certification === 'certified' ? 'ready' : 'warning'}>{metric.certification}</StatusPill>} />
        <div className="grid gap-4 p-4">
          <Surface className="p-4">
            <div className="mb-4 flex items-center gap-2">
              <Calculator className="h-4 w-4 text-brand-orange" />
              <SectionTitle>Business Definition</SectionTitle>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Business name"><input value={metric.businessName} onChange={event => updateMetric(metric.id, { businessName: event.target.value })} className={`mt-1 h-9 w-full rounded-md px-3 text-sm focus-visible:outline-none focus-visible:ring-1 ${modelingStyles.input}`} /></Field>
              <Field label="Owner"><input value={metric.owner} onChange={event => updateMetric(metric.id, { owner: event.target.value })} className={`mt-1 h-9 w-full rounded-md px-3 text-sm focus-visible:outline-none focus-visible:ring-1 ${modelingStyles.input}`} /></Field>
              <Field label="Business definition" className="md:col-span-2"><textarea value={metric.definition} onChange={event => updateMetric(metric.id, { definition: event.target.value })} className={`mt-1 min-h-20 w-full rounded-md p-3 text-sm focus-visible:outline-none focus-visible:ring-1 ${modelingStyles.input}`} /></Field>
            </div>
          </Surface>

          <Surface className="p-4">
            <div className="mb-4 flex items-center gap-2">
              <LineChart className="h-4 w-4 text-brand-orange" />
              <SectionTitle>Calculation Contract</SectionTitle>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Metric type">
                <select value={metric.kind} onChange={event => updateMetric(metric.id, { kind: event.target.value as Metric['kind'] })} className={`mt-1 h-9 w-full rounded-md px-3 text-sm focus-visible:outline-none focus-visible:ring-1 ${modelingStyles.input}`}>
                  <option value="measure">Measure</option>
                  <option value="derived_metric">Derived Metric</option>
                </select>
              </Field>
              <Field label="Unit"><input value={metric.unit} onChange={event => updateMetric(metric.id, { unit: event.target.value })} className={`mt-1 h-9 w-full rounded-md px-3 text-sm focus-visible:outline-none focus-visible:ring-1 ${modelingStyles.input}`} /></Field>
              <Field label="Formula" className="md:col-span-2"><input value={metric.formula} onChange={event => updateMetric(metric.id, { formula: event.target.value })} className={`mt-1 h-9 w-full rounded-md px-3 font-mono text-xs focus-visible:outline-none focus-visible:ring-1 ${modelingStyles.input}`} /></Field>
              <Field label="Filter" className="md:col-span-2"><input value={metric.filter} onChange={event => updateMetric(metric.id, { filter: event.target.value })} className={`mt-1 h-9 w-full rounded-md px-3 font-mono text-xs focus-visible:outline-none focus-visible:ring-1 ${modelingStyles.input}`} /></Field>
              <Field label="Time field"><input value={metric.timeField} onChange={event => updateMetric(metric.id, { timeField: event.target.value })} className={`mt-1 h-9 w-full rounded-md px-3 font-mono text-xs focus-visible:outline-none focus-visible:ring-1 ${modelingStyles.input}`} /></Field>
              <Field label="Default grain">
                <select value={metric.defaultGrain} onChange={event => updateMetric(metric.id, { defaultGrain: event.target.value as TimeGrain })} className={`mt-1 h-9 w-full rounded-md px-3 text-sm focus-visible:outline-none focus-visible:ring-1 ${modelingStyles.input}`}>
                  <option value="day">Day</option>
                  <option value="week">Week</option>
                  <option value="month">Month</option>
                  <option value="quarter">Quarter</option>
                </select>
              </Field>
            </div>
          </Surface>

          <div className="grid gap-4 md:grid-cols-2">
            <Surface className="p-4">
              <SectionTitle>Available Dimensions</SectionTitle>
              <div className="mt-3 flex flex-wrap gap-2">
                {metric.dimensions.map((item, index) => <StatusPill key={`${item}-${index}`}>{item}</StatusPill>)}
              </div>
            </Surface>
            <Surface className="p-4">
              <SectionTitle>Certification</SectionTitle>
              <div className="mt-3 flex flex-wrap gap-2">
                {(['draft', 'reviewed', 'certified'] as CertificationStatus[]).map(status => (
                  <Button key={status} size="sm" variant={metric.certification === status ? 'brand-primary' : 'secondary'} onClick={() => setMetricCertification(metric.id, status)}>
                    {status === 'certified' && <ShieldCheck className="h-4 w-4" />}
                    {status}
                  </Button>
                ))}
              </div>
            </Surface>
          </div>
        </div>
      </Panel>

      <Panel>
        <PanelHeader title="Metric Preview" subtitle="Saved draft definition plus the latest semantic query evidence." />
        <div className="space-y-4 p-4">
          <PreviewKV label="Current value" value={metric.preview.currentValue} />
          <PreviewKV label="Trend" value={metric.preview.trend} />
          <div>
            <SectionTitle>Breakdown</SectionTitle>
            <div className="mt-2 space-y-2">
              {metric.preview.breakdown.map((row, index) => (
                <div key={`${row.label}-${index}`} className="flex items-center justify-between rounded-md border border-[#2d3338] bg-[#15181b] px-3 py-2 text-sm">
                  <span className="text-[#f3f5f5]">{row.label}</span>
                  <span className="text-[#d6dde2]">{row.value} · {row.delta}</span>
                </div>
              ))}
            </div>
          </div>
          <PreviewKV label="Why this calculation" value={metric.preview.explanation} />
          <div>
            <SectionTitle>Compiled SQL</SectionTitle>
            <pre className="mt-2 max-h-44 overflow-auto rounded-md border border-[#343a40] bg-[#101214] p-3 text-xs text-[#cdd3d8] custom-scrollbar">{metric.preview.sql}</pre>
          </div>
          <PreviewKV label="Validation result" value={metric.preview.validation} />
          <div>
            <SectionTitle>Lineage</SectionTitle>
            <div className="mt-2 flex flex-wrap gap-2">{metric.lineage.map((item, index) => <StatusPill key={`${item}-${index}`}>{item}</StatusPill>)}</div>
          </div>
        </div>
      </Panel>
    </div>
  )
}

function PreviewKV({ label, value }: { label: string; value: string }) {
  return (
    <Surface className="p-3">
      <div className="text-[11px] font-medium uppercase text-[#7e8992]">{label}</div>
      <div className="mt-1 break-words text-sm leading-6 text-[#d6dde2]">{value}</div>
    </Surface>
  )
}

function Field({ label, className = '', children }: { label: string; className?: string; children: React.ReactNode }) {
  return (
    <label className={`block text-xs text-[#818c95] ${className}`}>
      {label}
      {children}
    </label>
  )
}
