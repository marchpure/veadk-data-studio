import type {
  AccessGrant,
  AccessPreview,
  Action,
  AuditEvent,
  Connection,
  DocsConfig,
  DocsStatus,
  Provider,
  Subject,
} from './types'
import { apiFetch } from '../../services/api'

const API_ROOT = '/api/v1'

interface Envelope<T> {
  success: boolean
  message: string
  data: T
}

export class WorkshopApiError extends Error {
  status: number
  code?: string

  constructor(message: string, status: number, code?: string) {
    super(message)
    this.name = 'WorkshopApiError'
    this.status = status
    this.code = code
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await apiFetch(`${API_ROOT}${path}`, {
    credentials: 'include',
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  })
  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = payload?.detail
    throw new WorkshopApiError(
      detail?.message || detail || '请求失败，请稍后重试',
      response.status,
      detail?.code,
    )
  }
  return (payload as Envelope<T>).data
}

function asItems<T>(value: T[] | { items: T[] }): T[] {
  return Array.isArray(value) ? value : value.items
}

export const workshopApi = {
  listProviders: async () => asItems(await request<Provider[] | { items: Provider[] }>('/providers')),
  listConnections: async () => asItems(await request<Connection[] | { items: Connection[] }>('/connections')),
  getConnection: (connectionId: string) => request<Connection>(`/connections/${connectionId}`),
  getActions: async (connectionId: string) =>
    asItems(await request<Action[] | { items: Action[] }>(`/connections/${connectionId}/actions`)),
  getGrants: async (connectionId: string) =>
    asItems(await request<AccessGrant[] | { items: AccessGrant[] }>(`/connections/${connectionId}/access`)),
  searchSubjects: async (query: string, subjectType: 'user' | 'group' | 'all' = 'all') =>
    asItems(
      await request<Subject[] | { items: Subject[] }>(
        `/identity/subjects?query=${encodeURIComponent(query)}&subject_type=${subjectType}`,
      ),
    ),
  createGrant: (grant: Omit<AccessGrant, 'id' | 'status' | 'updated_at' | 'updated_by'>) =>
    request<AccessGrant>('/access-grants', { method: 'POST', body: JSON.stringify(grant) }),
  updateGrant: (grantId: string, grant: Omit<AccessGrant, 'id' | 'status' | 'updated_at' | 'updated_by'>) =>
    request<AccessGrant>(`/access-grants/${grantId}`, { method: 'PATCH', body: JSON.stringify(grant) }),
  revokeGrant: (grantId: string) =>
    request<AccessGrant>(`/access-grants/${grantId}:revoke`, { method: 'POST' }),
  previewAccess: (subjectId: string, connectionId?: string) =>
    request<AccessPreview>('/access:preview', {
      method: 'POST',
      body: JSON.stringify({ subject_id: subjectId, connection_id: connectionId }),
    }),
  getDocsConfig: () => request<DocsConfig>('/connection-docs/config'),
  getDocsStatus: () => request<DocsStatus>('/connection-docs/status'),
  getAudit: async (connectionId?: string) =>
    asItems(
      await request<AuditEvent[] | { items: AuditEvent[] }>(
        `/access/audit${connectionId ? `?connection_id=${encodeURIComponent(connectionId)}` : ''}`,
      ),
    ),
  createLaunchSession: () =>
    request<{ launch_url: string; expires_at: number }>('/openconnector/launch-sessions', { method: 'POST' }),
  runReadOnlyTest: (operation: 'health' | 'identity' | 'tools_list' | 'list_connections') =>
    request<unknown>('/connection-docs/read-only-tests', {
      method: 'POST',
      body: JSON.stringify({ operation, arguments: {} }),
    }),
}
