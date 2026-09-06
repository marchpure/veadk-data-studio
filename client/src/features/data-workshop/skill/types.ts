export type SkillStatus =
  | 'draft'
  | 'idle'
  | 'running'
  | 'ready'
  | 'blocked_auth'
  | 'blocked_config'
  | 'validation_failed'
  | 'cancelled'
  | 'retryable'
  | 'error'

export interface SkillContextRef {
  id: string
  kind: 'mcp_action' | 'knowledge_resource'
  name: string
  source: 'OpenConnector' | 'OpenViking ResourceRef'
  connection_id?: string | null
  metadata: Record<string, unknown>
}

export interface SkillArtifact {
  revision: string
  name?: string
  files?: string[]
  mime_type?: string
  validation?: {
    ok?: boolean
    code?: string
    errors?: string[]
    checks?: Record<string, boolean> | Array<{ name?: string; ok?: boolean; message?: string }>
  }
  preview_url: string
  download_url: string
}

export interface WorkshopSkill {
  id: string
  target_skill: string
  title: string
  description: string
  status: SkillStatus
  context_refs: {
    mcp_refs: SkillContextRef[]
    knowledge_refs: SkillContextRef[]
  }
  active_revision?: string | null
  artifact?: SkillArtifact | null
  created_at?: string | null
  updated_at?: string | null
}

export interface SkillMessage {
  role: 'user' | 'assistant'
  content: string
  at: string
}

export interface SkillEvent {
  id: string
  type: string
  message?: string
  text?: string
  code?: string
  status?: string
  name?: string
  at?: string
  [key: string]: unknown
}

export interface SkillSession {
  id: string
  skill_id: string
  title: string
  status: SkillStatus
  context_refs: {
    mcp_refs: SkillContextRef[]
    knowledge_refs: SkillContextRef[]
  }
  messages: SkillMessage[]
  events: SkillEvent[]
  current_invocation_id?: string | null
  active_revision?: string | null
  artifact?: SkillArtifact | null
  created_at?: string | null
  updated_at?: string | null
}

export interface SkillCatalog {
  backend: 'REAL' | 'TEST BACKEND'
  w5_configured: boolean
  connections: Array<{
    id: string
    name: string
    provider: string
    actions: SkillContextRef[]
  }>
  knowledge_refs: SkillContextRef[]
}

export interface SkillRevision {
  revision: string
  artifact: SkillArtifact
  validation?: SkillArtifact['validation'] | null
  created_at?: string | null
}

export interface RevisionDiff {
  base: string
  target: string
  files_added: string[]
  files_removed: string[]
  metadata_changed: string[]
  validation_changed: boolean
  text_diff: string[]
}
