import { apiFetch } from '../../services/api'

export type SkillRef = {
  id: string
  kind: 'connection' | 'mcp_action' | 'knowledge_resource'
  name: string
  source: string
  metadata: Record<string, unknown>
}

export type SkillArtifact = {
  name?: string
  mime_type?: string
  files?: string[]
  revision?: string
  content?: string
  download?: { download_url?: string }
  download_url?: string
  preview_url?: string
}

export type SkillSession = {
  id: string
  skill_id: string | null
  target: string
  mcp_refs: SkillRef[]
  knowledge_refs: SkillRef[]
  revision: string | null
  messages: Array<{ role: string; content: string; at: string }>
  events: Array<Record<string, unknown>>
  artifact: SkillArtifact | null
  status: string
  backend: 'REAL AGENT' | 'TEST BACKEND'
  preview_url: string
}

const unwrap = async <T>(response: Response): Promise<T> => {
  const body = await response.json()
  if (!response.ok) throw new Error(body?.message || body?.detail || 'Request failed')
  return body?.data ?? body
}

const request = (path: string, init?: RequestInit) => apiFetch(`/api${path}`, init)

export const skillCreatorApi = {
  async catalog() {
    return unwrap<{ mcp_refs: SkillRef[]; knowledge_refs: SkillRef[]; backend: SkillSession['backend'] }>(
      await request('/skill-agent-bff/catalog'),
    )
  },
  async listSessions() {
    return unwrap<{ items: SkillSession[]; total: number }>(await request('/skill-agent-bff/sessions'))
  },
  async getSession(id: string) {
    return unwrap<SkillSession>(await request(`/skill-agent-bff/sessions/${id}`))
  },
  async createSession(input: { skill_id?: string; target: string; mcp_refs: SkillRef[]; knowledge_refs: SkillRef[] }) {
    return unwrap<SkillSession>(await request('/skill-agent-bff/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    }))
  },
  async invoke(id: string, input: { message: string; client_invocation_id: string; validate?: boolean }) {
    return unwrap<SkillSession>(await request(`/skill-agent-bff/sessions/${id}/invocations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    }))
  },
  async events(id: string, after: number) {
    return unwrap<{ items: Array<Record<string, unknown>>; next: number; done: boolean }>(
      await request(`/skill-agent-bff/sessions/${id}/events?after=${after}`),
    )
  },
  async cancel(id: string) {
    return unwrap<SkillSession>(await request(`/skill-agent-bff/sessions/${id}/cancel`, { method: 'POST' }))
  },
  async retry(id: string) {
    return unwrap<SkillSession>(await request(`/skill-agent-bff/sessions/${id}/retry`, { method: 'POST' }))
  },
}
