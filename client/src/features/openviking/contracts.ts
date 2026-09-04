export type KnowledgeSourceCapability = {
  id: string
  enabled: boolean
}

export type KnowledgeSourceRef = {
  provider: 'openviking'
  profile_ref?: string
  resource_ref?: string
}

export type KnowledgeSourceOption = {
  id: string
  provider: string
  displayName: string
  type: string
  scope: string
  status: string
  ready: boolean
  category: string
  refs: KnowledgeSourceRef[]
  selected?: boolean
}

export type KnowledgeSourceDataToolSlot = {
  id: string
  listOptions: (signal?: AbortSignal) => Promise<KnowledgeSourceOption[]>
}

export type KnowledgeSourceExtension = {
  provider: string
  displayName: string
  capabilities: KnowledgeSourceCapability[]
  slots: {
    createKnowledgeBase: {
      id: string
      label: string
      description: string
      run: () => void
    }
    dataTools: KnowledgeSourceDataToolSlot
  }
}
