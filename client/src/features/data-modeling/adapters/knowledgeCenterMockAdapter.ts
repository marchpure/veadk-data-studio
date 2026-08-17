import type { ConsumptionEntry, GateCheck, KnowledgeCenterGateState, SemanticModel } from '../types'

export interface KnowledgeCenterAdapter {
  evaluateGate(model: SemanticModel): Promise<KnowledgeCenterGateState>
  publishAsset(model: SemanticModel): Promise<{
    publishedVersion: string
    publishedAt: string
    consumers: SemanticModel['consumers']
    entries: ConsumptionEntry[]
  }>
}

const gateChecks: GateCheck[] = [
  {
    id: 'metric-contract',
    title: 'Paid Revenue contract matches dashboard KPI',
    status: 'failed',
    reason: 'Failed: Dashboard KPI still references gross_amount while the semantic model exposes paid_revenue after refunds.',
    passedReason: 'Passed: Dashboard KPI and semantic model both resolve Paid Revenue from paid order lines net of refunds.',
    evidence: {
      sql: 'select sum(paid_amount - refunded_amount) as paid_revenue from marts.order_revenue_daily',
      doc: 'Revenue Playbook / Section 2.1 Paid Revenue',
      policy: 'Metric consumers may use certified revenue only after refund fanout is resolved.',
    },
  },
  {
    id: 'fanout',
    title: 'Refund relationship fanout guard',
    status: 'failed',
    reason: 'Failed: Refunds can duplicate order lines unless refunds are pre-aggregated by order_id.',
    passedReason: 'Passed: Refund evidence is aggregated by order_id before joining to order facts.',
    evidence: {
      sql: 'with refund_by_order as (select order_id, sum(amount) refund_amount from refunds group by 1)',
      doc: 'Modeling Notes / Section 3.4 Refund Join Pattern',
      policy: 'Fanout risk must be medium or lower for published revenue metrics.',
    },
  },
  {
    id: 'pii-policy',
    title: 'PII is masked from semantic consumers',
    status: 'passed',
    reason: 'Passed: Customer email and phone fields are excluded from Agent, dashboard, and MCP exposure.',
    passedReason: 'Passed: Customer email and phone fields are excluded from Agent, dashboard, and MCP exposure.',
    evidence: {
      sql: 'select customer_id, customer_segment from dim_customers',
      doc: 'Privacy Rules / Section 5 Customer Contact Fields',
      policy: 'MCP allowlist excludes customers.email and customers.phone.',
    },
  },
  {
    id: 'freshness',
    title: 'Freshness is inside operational SLA',
    status: 'passed',
    reason: 'Passed: Source profile and dashboard snapshot were refreshed inside the 4 hour SLA.',
    passedReason: 'Passed: Source profile and dashboard snapshot were refreshed inside the 4 hour SLA.',
    evidence: {
      sql: 'select max(updated_at) from marts.order_revenue_daily',
      doc: 'Operations Runbook / Section 1.2 Data Freshness',
      policy: 'Revenue assets require freshness under 4 hours for publish.',
    },
  },
]

export const knowledgeCenterMockAdapter: KnowledgeCenterAdapter = {
  async evaluateGate(model) {
    await delay(180)
    const repairedFanout = model.readinessLevel === 'ready'
      || !model.relationships.some(relationship => relationship.fanoutRisk === 'high' && relationship.status !== 'rejected')
    const certifiedRevenue = model.readinessLevel === 'ready'
      || model.metrics.some(metric => metric.id === 'paid_revenue' && metric.certification === 'certified')
    const checks = gateChecks.map(check => {
      const passed = check.id === 'fanout'
        ? repairedFanout
        : check.id === 'metric-contract'
          ? certifiedRevenue
          : true
      return {
        ...check,
        status: passed ? 'passed' as const : 'failed' as const,
        reason: passed ? check.passedReason : check.reason,
      }
    })
    const passed = checks.filter(check => check.status === 'passed').length
    const total = checks.length
    return {
      score: Math.round((passed / total) * 100),
      passed,
      total,
      blockers: checks.filter(check => check.status === 'failed').map(check => check.reason),
      checks,
      evaluated: true,
    }
  },

  async publishAsset(model) {
    await delay(180)
    const current = Number(model.publishedVersion.replace(/^v/, '')) || 0
    const publishedVersion = `v${Math.max(1, current + 1)}`
    return {
      publishedVersion,
      publishedAt: new Date().toISOString(),
      consumers: {
        ...model.consumers,
        agents: Math.max(model.consumers.agents, 3),
        mcp: Math.max(model.consumers.mcp, 2),
        dashboards: Math.max(model.consumers.dashboards, 1),
        savedQueries: Math.max(model.consumers.savedQueries, 4),
      },
      entries: [
        { id: 'agent', label: 'Agent', before: 'Waiting for gate pass', after: `Serving ${publishedVersion} with certified metric answers` },
        { id: 'dashboard', label: 'Dashboard', before: 'Bound to draft semantic version', after: `Bound to ${publishedVersion} semantic contract` },
        { id: 'mcp_api', label: 'MCP API', before: 'query_metric blocked for draft', after: `query_metric exposes ${publishedVersion}` },
        { id: 'share_link', label: 'Share link', before: 'Internal preview only', after: 'Share link enabled with policy banner' },
      ],
    }
  },
}

function delay(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms))
}
