export type LoadState = 'loading' | 'ready' | 'empty' | 'error'

export interface Connection {
  id: string
  name: string
  provider: string
  description?: string
  status: 'ready' | 'pending' | 'error' | 'disabled'
  action_count?: number
  updated_at?: string
}

export interface Provider {
  id: string
  name: string
  category: string
  description: string
  color?: string
  available: boolean
}

export interface Action {
  id: string
  name: string
  description?: string
  risk: 'low' | 'medium' | 'high'
  read_only: boolean
}

export interface Subject {
  id: string
  type: 'user' | 'group'
  display_name: string
  secondary_text?: string
}

export interface AccessGrant {
  id: string
  connection_id: string
  subject_type: 'user' | 'group'
  subject_id: string
  subject_display_snapshot: string
  role_id: 'reader' | 'operator' | 'custom'
  effect: 'allow' | 'deny'
  action_scope: string[]
  status: 'active' | 'revoked' | 'conflict'
  updated_at?: string
  updated_by?: string
  version?: number
}

export interface AccessPreview {
  subject: Subject
  connections: Array<{
    connection_id: string
    connection_name: string
    actions: Action[]
    reasons: Array<{ grant_id: string; source: string; effect: 'allow' | 'deny' }>
  }>
}

export interface DocsConfig {
  mcp: {
    endpoint: string
    protocol?: string
    workbuddy_config?: Record<string, unknown>
    generic_config?: Record<string, unknown>
    api_reference_url?: string
    openapi_url?: string
    sdk_languages?: string[]
  }
  identity: {
    status: 'ready' | 'unconfigured' | 'error'
    issuer?: string
    audience?: string[]
    user_pool_ref?: string
    jwks_status?: string
  }
}

export interface DocsStatus {
  status: 'healthy' | 'degraded' | 'unavailable'
  protocol?: string
  checked_at?: string
}

export interface AuditEvent {
  id: string
  event_type: string
  subject_display?: string
  action_name?: string
  decision?: 'allow' | 'deny'
  created_at: string
  request_id?: string
}
