import { ShieldCheck } from 'lucide-react'
import { Button } from '../../../components/ui/button'
import { useDataModelingStore } from '../store/useDataModelingStore'
import { Panel, PanelHeader, SectionTitle, StatusPill } from '../components/modelingUi'
import type { CertificationStatus, Metric, TimeGrain } from '../types'

export function MetricEditor({ metric }: { metric: Metric }) {
  const updateMetric = useDataModelingStore(state => state.updateMetric)
  const setMetricCertification = useDataModelingStore(state => state.setMetricCertification)

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
      <Panel>
        <PanelHeader title="Metric Editor" subtitle="Formal KPI definition, governance, dimensions, and lineage." action={<StatusPill tone={metric.certification === 'certified' ? 'ready' : 'warning'}>{metric.certification}</StatusPill>} />
        <div className="grid gap-4 p-4 md:grid-cols-2">
          <label className="block text-xs text-[#9a9a9a]">
            Business name
            <input value={metric.businessName} onChange={event => updateMetric(metric.id, { businessName: event.target.value })} className="mt-1 h-9 w-full rounded-md border border-[#333] bg-[#151515] px-3 text-sm text-white focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring" />
          </label>
          <label className="block text-xs text-[#9a9a9a]">
            Owner
            <input value={metric.owner} onChange={event => updateMetric(metric.id, { owner: event.target.value })} className="mt-1 h-9 w-full rounded-md border border-[#333] bg-[#151515] px-3 text-sm text-white focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring" />
          </label>
          <label className="block text-xs text-[#9a9a9a] md:col-span-2">
            Business definition
            <textarea value={metric.definition} onChange={event => updateMetric(metric.id, { definition: event.target.value })} className="mt-1 min-h-20 w-full rounded-md border border-[#333] bg-[#151515] p-3 text-sm text-white focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring" />
          </label>
          <label className="block text-xs text-[#9a9a9a]">
            Metric type
            <select value={metric.kind} onChange={event => updateMetric(metric.id, { kind: event.target.value as Metric['kind'] })} className="mt-1 h-9 w-full rounded-md border border-[#333] bg-[#151515] px-3 text-sm text-white focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring">
              <option value="measure">Measure</option>
              <option value="derived_metric">Derived Metric</option>
            </select>
          </label>
          <label className="block text-xs text-[#9a9a9a]">
            Unit
            <input value={metric.unit} onChange={event => updateMetric(metric.id, { unit: event.target.value })} className="mt-1 h-9 w-full rounded-md border border-[#333] bg-[#151515] px-3 text-sm text-white focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring" />
          </label>
          <label className="block text-xs text-[#9a9a9a] md:col-span-2">
            Formula
            <input value={metric.formula} onChange={event => updateMetric(metric.id, { formula: event.target.value })} className="mt-1 h-9 w-full rounded-md border border-[#333] bg-[#151515] px-3 font-mono text-xs text-white focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring" />
          </label>
          <label className="block text-xs text-[#9a9a9a] md:col-span-2">
            Filter
            <input value={metric.filter} onChange={event => updateMetric(metric.id, { filter: event.target.value })} className="mt-1 h-9 w-full rounded-md border border-[#333] bg-[#151515] px-3 font-mono text-xs text-white focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring" />
          </label>
          <label className="block text-xs text-[#9a9a9a]">
            Time field
            <input value={metric.timeField} onChange={event => updateMetric(metric.id, { timeField: event.target.value })} className="mt-1 h-9 w-full rounded-md border border-[#333] bg-[#151515] px-3 font-mono text-xs text-white focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring" />
          </label>
          <label className="block text-xs text-[#9a9a9a]">
            Default grain
            <select value={metric.defaultGrain} onChange={event => updateMetric(metric.id, { defaultGrain: event.target.value as TimeGrain })} className="mt-1 h-9 w-full rounded-md border border-[#333] bg-[#151515] px-3 text-sm text-white focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring">
              <option value="day">Day</option>
              <option value="week">Week</option>
              <option value="month">Month</option>
              <option value="quarter">Quarter</option>
            </select>
          </label>
          <div className="md:col-span-2">
            <SectionTitle>Available Dimensions</SectionTitle>
            <div className="mt-2 flex flex-wrap gap-2">
              {metric.dimensions.map(item => <StatusPill key={item}>{item}</StatusPill>)}
            </div>
          </div>
          <div className="md:col-span-2">
            <SectionTitle>Certification</SectionTitle>
            <div className="mt-2 flex flex-wrap gap-2">
              {(['draft', 'reviewed', 'certified'] as CertificationStatus[]).map(status => (
                <Button key={status} size="sm" variant={metric.certification === status ? 'brand-primary' : 'secondary'} onClick={() => setMetricCertification(metric.id, status)}>
                  {status === 'certified' && <ShieldCheck className="h-4 w-4" />}
                  {status}
                </Button>
              ))}
            </div>
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
              {metric.preview.breakdown.map(row => (
                <div key={row.label} className="flex items-center justify-between rounded-md border border-[#2a2a2a] bg-[#181818] px-3 py-2 text-sm">
                  <span className="text-white">{row.label}</span>
                  <span className="text-[#d6d6d6]">{row.value} · {row.delta}</span>
                </div>
              ))}
            </div>
          </div>
          <PreviewKV label="Why this calculation" value={metric.preview.explanation} />
          <div>
            <SectionTitle>Compiled SQL</SectionTitle>
            <pre className="mt-2 max-h-44 overflow-auto rounded-md border border-[#333] bg-[#101010] p-3 text-xs text-[#cfcfcf] custom-scrollbar">{metric.preview.sql}</pre>
          </div>
          <PreviewKV label="Validation result" value={metric.preview.validation} />
          <div>
            <SectionTitle>Lineage</SectionTitle>
            <div className="mt-2 flex flex-wrap gap-2">{metric.lineage.map(item => <StatusPill key={item}>{item}</StatusPill>)}</div>
          </div>
        </div>
      </Panel>
    </div>
  )
}

function PreviewKV({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-[#2a2a2a] bg-[#181818] p-3">
      <div className="text-xs uppercase text-[#858585]">{label}</div>
      <div className="mt-1 break-words text-sm text-[#d6d6d6]">{value}</div>
    </div>
  )
}
