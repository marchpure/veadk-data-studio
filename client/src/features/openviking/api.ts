import { apiFetch } from '../../services/api'
import type { OpenVikingProfile } from './hooks/use-app-connection'
import { getActiveOpenVikingProfileId } from './hooks/use-app-connection'
import { getOpenVikingResourceRef } from './lib/ov-client/client'

const ROOT = '/api/knowledge/openviking'

type Envelope<T> = { data: T; meta?: { request_id: string } }
export type ConnectionResource = {
  resource_id: string
  kind: string
  display_name: string
  status: string
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body) headers.set('Content-Type', 'application/json')
  const response = await apiFetch(`${ROOT}${path}`, { ...init, headers })
  if (!response.ok) {
    const contentType = response.headers.get('content-type') || ''
    const payload = contentType.includes('application/json')
      ? await response.json().catch(() => null)
      : null
    const fallback = payload
      ? null
      : response.status === 405
        ? 'OpenViking BFF is unavailable on this server. Restart Studio with secure profile keys configured.'
        : `OpenViking request failed (${response.status})`
    throw new Error(
      payload?.error?.message ??
        payload?.detail?.message ??
        fallback,
    )
  }
  if (response.status === 204) return undefined as T
  const envelope = (await response.json()) as Envelope<T>
  return envelope.data
}

async function knowledgeRequest<T>(path: string): Promise<T> {
  const response = await apiFetch(`/api${path}`)
  if (!response.ok) throw new Error(`Knowledge request failed (${response.status})`)
  return ((await response.json()) as Envelope<T>).data
}

function activeProfilePath(suffix: string): string {
  const profileId = getActiveOpenVikingProfileId()
  if (!profileId) throw new Error('Select an OpenViking profile first')
  return `/profiles/${encodeURIComponent(profileId)}${suffix}`
}

function parentRef(uri: string): string {
  const ref = getOpenVikingResourceRef(uri)
  if (!ref) throw new Error('Refresh the OpenViking directory before importing')
  return ref
}

export function selectConnectionResources(
  items: Array<Record<string, unknown>>,
): ConnectionResource[] {
  return items
    .filter((item) => item.source_type === 'source_resource')
    .map((item) => ({
      resource_id: String(item.id ?? ''),
      kind: String(item.resource_type ?? ''),
      display_name: String(item.name ?? item.id ?? ''),
      status: String(item.status ?? ''),
    }))
}

type CreateOpenVikingProfile = {
  api_key: string
  base_url: string
  display_name: string
  workspace_uri: string
}

export const openVikingApi = {
  listProfiles: (signal?: AbortSignal) =>
    request<OpenVikingProfile[]>('/profiles', { signal }),
  createProfile: (input: CreateOpenVikingProfile) =>
    request<OpenVikingProfile>('/profiles', {
      method: 'POST',
      body: JSON.stringify(input),
    }),
  validateProfile: (profileId: string) =>
    request<OpenVikingProfile>(
      `/profiles/${encodeURIComponent(profileId)}/validate`,
      { method: 'POST' },
    ),
  updateProfile: (
    profileId: string,
    input: Partial<CreateOpenVikingProfile>,
  ) =>
    request<OpenVikingProfile>(`/profiles/${encodeURIComponent(profileId)}`, {
      method: 'PATCH',
      body: JSON.stringify(input),
    }),
  revokeProfile: (profileId: string) =>
    request<void>(`/profiles/${encodeURIComponent(profileId)}`, {
      method: 'DELETE',
    }),
  importText: (input: { parent_uri: string; filename: string; content: string }) =>
    request<unknown>(activeProfilePath('/text'), {
      method: 'POST',
      body: JSON.stringify({
        parent_ref: parentRef(input.parent_uri),
        filename: input.filename,
        content: input.content,
      }),
    }),
  importConnectionResource: (input: {
    parent_uri: string
    filename: string
    resource_id: string
  }) =>
    request<unknown>(activeProfilePath('/connection-resource'), {
      method: 'POST',
      body: JSON.stringify({
        parent_ref: parentRef(input.parent_uri),
        filename: input.filename,
        resource_id: input.resource_id,
      }),
    }),
  listConnectionResources: () =>
    knowledgeRequest<{ items: Array<Record<string, unknown>> }>('/datasources')
      .then(({ items }) => selectConnectionResources(items)),
  authorizeSkillContext: (profileId: string, resourceRef: string) =>
    request<{
      provider: 'openviking'
      profile_ref: string
      resource_ref: string
      display_name: string
      resource_type: string
      summary: string
      profile_name: string
      version: 'v1'
    }>(`/profiles/${encodeURIComponent(profileId)}/skill-context`, {
      method: 'POST',
      body: JSON.stringify({ resource_ref: resourceRef }),
    }),
  resolveResource: (profileId: string, resourceRef: string) =>
    request<{
      resource_ref: string
      display_name: string
      resource_type: string
      summary: string
      profile_name: string
    }>(`/profiles/${encodeURIComponent(profileId)}/resource/resolve`, {
      method: 'POST',
      body: JSON.stringify({ resource_ref: resourceRef }),
    }),
}
