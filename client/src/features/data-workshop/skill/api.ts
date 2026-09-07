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
export const SKILL_REQUEST_TIMEOUT_MS = 12_000

type Envelope<T> = { success: boolean; message: string; data: T }
export type SkillRequestOptions = {
  signal?: AbortSignal
  timeoutMs?: number
}

export class SkillApiError extends Error {
  status: number
  code?: string

  constructor(message: string, status: number, code?: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

export class SkillApiTimeoutError extends SkillApiError {
  constructor(path: string) {
    super(`请求超时（${path}）`, 408, 'SKILL_REQUEST_TIMEOUT')
    this.name = 'SkillApiTimeoutError'
  }
}

async function request<T>(path: string, init?: RequestInit, options?: SkillRequestOptions): Promise<T> {
  const controller = new AbortController()
  let timedOut = false
  const timeoutId = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, options?.timeoutMs ?? SKILL_REQUEST_TIMEOUT_MS)
  const abortFromCaller = () => controller.abort()
  if (options?.signal) {
    if (options.signal.aborted) controller.abort()
    else options.signal.addEventListener('abort', abortFromCaller, { once: true })
  }
  let response: Response
  try {
    response = await apiFetch(`${API_ROOT}${path}`, {
      credentials: 'include',
      ...init,
      signal: controller.signal,
      headers: {
        ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
        ...init?.headers,
      },
    })
  } catch (reason) {
    if (timedOut) throw new SkillApiTimeoutError(path)
    throw reason
  } finally {
    clearTimeout(timeoutId)
    options?.signal?.removeEventListener('abort', abortFromCaller)
  }
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
  catalog: (options?: SkillRequestOptions) => request<SkillCatalog>('/skill-catalog', undefined, options),
  listSkills: (search = '', options?: SkillRequestOptions) =>
    request<{ items: WorkshopSkill[]; total: number }>(
      `/skills${search ? `?search=${encodeURIComponent(search)}` : ''}`,
      undefined,
      options,
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
  listSessions: (skillId: string, options?: SkillRequestOptions) =>
    request<{ items: SkillSession[]; total: number }>(
      `/skills/${encodeURIComponent(skillId)}/sessions`,
      undefined,
      options,
    ),
  getSession: (sessionId: string, options?: SkillRequestOptions) =>
    request<SkillSession>(`/sessions/${encodeURIComponent(sessionId)}`, undefined, options),
  createSession: (skillId: string) =>
    request<SkillSession>(`/skills/${encodeURIComponent(skillId)}/sessions`, {
      method: 'POST',
      body: JSON.stringify({ title: '新会话' }),
    }),
  updateContext: (sessionId: string, body: {
    mcp_refs: SkillContextRef[]
    knowledge_refs: SkillContextRef[]
  }) =>
    request<SkillSession>(`/sessions/${encodeURIComponent(sessionId)}/context`, {
      method: 'PATCH',
      body: JSON.stringify(body),
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
  revisions: (skillId: string, options?: SkillRequestOptions) =>
    request<{ items: SkillRevision[]; total: number }>(
      `/skills/${encodeURIComponent(skillId)}/revisions`,
      undefined,
      options,
    ),
  revisionDiff: (skillId: string, base: string, target: string) =>
    request<RevisionDiff>(
      `/skills/${encodeURIComponent(skillId)}/revision-diff?base=${encodeURIComponent(base)}&target=${encodeURIComponent(target)}`,
    ),
}
