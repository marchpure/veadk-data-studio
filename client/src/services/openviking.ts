import { apiFetch } from './api'

export type OpenVikingProfile = {
  profile_id: string
  display_name: string
  workspace_uri: string
  root_resource_ref: string
  status: 'pending' | 'ready' | 'error'
  api_key_masked: string
}

const unwrap = async <T>(response: Response): Promise<T> => {
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload?.detail?.message || payload?.message || `OpenViking request failed (${response.status})`)
  return (payload.data ?? payload) as T
}

const request = <T>(path: string, init?: RequestInit) =>
  apiFetch(`/api/knowledge/openviking${path}`, init).then(unwrap<T>)

export const openVikingApi = {
  listProfiles: () => request<OpenVikingProfile[]>('/profiles'),
  createProfile: (body: { display_name: string; base_url: string; api_key: string; workspace_uri: string }) =>
    request<OpenVikingProfile>('/profiles', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  updateProfile: (id: string, body: Partial<{ display_name: string; base_url: string; api_key: string; workspace_uri: string }>) =>
    request<OpenVikingProfile>(`/profiles/${encodeURIComponent(id)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  validateProfile: (id: string) => request<OpenVikingProfile>(`/profiles/${encodeURIComponent(id)}/validate`, { method: 'POST' }),
  deleteProfile: (id: string) => apiFetch(`/api/knowledge/openviking/profiles/${encodeURIComponent(id)}`, { method: 'DELETE' }).then(unwrap<void>),
  operation: (id: string, operation: string, payload: Record<string, unknown>) =>
    request<unknown>(`/profiles/${encodeURIComponent(id)}/operations/${operation}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ payload }) }),
  importText: (id: string, body: { parent_ref: string; filename: string; content: string }) =>
    request<unknown>(`/profiles/${encodeURIComponent(id)}/text`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  upload: (id: string, parentRef: string, file: File) => {
    const form = new FormData()
    form.append('parent_ref', parentRef)
    form.append('file', file)
    return request<unknown>(`/profiles/${encodeURIComponent(id)}/upload`, { method: 'POST', body: form })
  },
  deleteResource: (id: string, resourceRef: string) =>
    request<unknown>(`/profiles/${encodeURIComponent(id)}/resource`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ payload: { resource_ref: resourceRef, recursive: true, wait: true } }) }),
  authorizeSkillContext: (id: string, resourceRef: string) =>
    request<{ provider: string; profile_ref: string; resource_ref: string }>(`/profiles/${encodeURIComponent(id)}/skill-context`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ resource_ref: resourceRef }) }),
  itemOperation: (id: string, operation: string, itemId: string, payload: Record<string, unknown>) =>
    request<unknown>(`/profiles/${encodeURIComponent(id)}/operations/${operation}/${encodeURIComponent(itemId)}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ payload }) }),
}
