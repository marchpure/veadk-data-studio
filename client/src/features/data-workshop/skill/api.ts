import { apiFetch } from '../../../services/api'
import type {
  SkillCatalog,
  SkillContextRef,
  SkillEvent,
  RevisionDiff,
  SkillRevision,
  SkillSession,
  WorkshopSkill,
} from './types'

const API_ROOT = '/api/v1'

type Envelope<T> = { success: boolean; message: string; data: T }

export class SkillApiError extends Error {
  status: number
  code?: string

  constructor(message: string, status: number, code?: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await apiFetch(`${API_ROOT}${path}`, {
    credentials: 'include',
    ...init,
    headers: {
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...init?.headers,
    },
  })
  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = payload?.detail
    throw new SkillApiError(
      detail?.message || payload?.message || detail || '请求失败，请稍后重试',
      response.status,
      detail?.code || payload?.code,
    )
  }
  return (payload as Envelope<T>).data
}

export const skillApi = {
  catalog: () => request<SkillCatalog>('/skill-catalog'),
  listSkills: (search = '') =>
    request<{ items: WorkshopSkill[]; total: number }>(
      `/skills${search ? `?search=${encodeURIComponent(search)}` : ''}`,
    ),
  getSkill: (skillId: string) => request<WorkshopSkill>(`/skills/${encodeURIComponent(skillId)}`),
  createSkill: (body: {
    title: string
    target_skill: string
    description: string
    mcp_refs: SkillContextRef[]
    knowledge_refs: SkillContextRef[]
  }) =>
    request<{ skill: WorkshopSkill; session: SkillSession }>('/skills', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  listSessions: (skillId: string) =>
    request<{ items: SkillSession[]; total: number }>(
      `/skills/${encodeURIComponent(skillId)}/sessions`,
    ),
  getSession: (sessionId: string) =>
    request<SkillSession>(`/sessions/${encodeURIComponent(sessionId)}`),
  createSession: (skillId: string) =>
    request<SkillSession>(`/skills/${encodeURIComponent(skillId)}/sessions`, {
      method: 'POST',
      body: JSON.stringify({ title: '新会话' }),
    }),
  invoke: (sessionId: string, message: string, clientInvocationId: string) =>
    request<SkillSession>(`/sessions/${encodeURIComponent(sessionId)}/invocations`, {
      method: 'POST',
      body: JSON.stringify({
        message,
        client_invocation_id: clientInvocationId,
        validate: true,
      }),
    }),
  events: (sessionId: string, after: number) =>
    request<{ items: SkillEvent[]; next: number; done: boolean; status: SkillSession['status'] }>(
      `/sessions/${encodeURIComponent(sessionId)}/events?after=${after}`,
    ),
  cancel: (sessionId: string) =>
    request<SkillSession>(`/sessions/${encodeURIComponent(sessionId)}/cancel`, {
      method: 'POST',
    }),
  retry: (sessionId: string) =>
    request<SkillSession>(`/sessions/${encodeURIComponent(sessionId)}/retry`, {
      method: 'POST',
      body: JSON.stringify({}),
    }),
  revisions: (skillId: string) =>
    request<{ items: SkillRevision[]; total: number }>(
      `/skills/${encodeURIComponent(skillId)}/revisions`,
    ),
  revisionDiff: (skillId: string, base: string, target: string) =>
    request<RevisionDiff>(
      `/skills/${encodeURIComponent(skillId)}/revision-diff?base=${encodeURIComponent(base)}&target=${encodeURIComponent(target)}`,
    ),
}
