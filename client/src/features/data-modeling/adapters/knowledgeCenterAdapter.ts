import type { ConsumptionEntry, KnowledgeCenterGateState, SemanticModel } from '../types'

export interface KnowledgeCenterAdapter {
  evaluateGate(model: SemanticModel): Promise<KnowledgeCenterGateState>
  publishAsset(model: SemanticModel): Promise<{
    publishedVersion: string
    publishedAt: string
    consumers: SemanticModel['consumers']
    entries: ConsumptionEntry[]
  }>
}

export async function loadMockKnowledgeCenterAdapter(): Promise<KnowledgeCenterAdapter> {
  const module = await import('./knowledgeCenterMockAdapter')
  return module.knowledgeCenterMockAdapter
}
