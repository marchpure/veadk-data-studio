import { getBackendUrl } from '../lib/tauri-api'
import { getAccessToken } from './tokenStore'
import type { ConnectedRepo } from './github'

async function getApiUrl(): Promise<string> {
  const base = await getBackendUrl()
  return `${base}/api/local-repos`
}

function getHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = getAccessToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  const tenantId = localStorage.getItem('byaan_active_tenant')
  if (tenantId) {
    headers['X-Tenant-ID'] = tenantId
  }
  return headers
}

async function apiFetch(path: string, init?: RequestInit) {
  const base = await getApiUrl()
  const response = await fetch(`${base}${path}`, {
    ...init,
    headers: { ...getHeaders(), ...(init?.headers || {}) },
    credentials: 'include',
  })
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(error.detail || error.message || 'Request failed')
  }
  return response.json()
}

export const LocalRepoService = {
  async connectRepo(path: string, name?: string) {
    const res = await apiFetch('/connect', {
      method: 'POST',
      body: JSON.stringify({ path, name: name || undefined }),
    })
    return res.data as ConnectedRepo
  },

  async getConnectedRepos() {
    const res = await apiFetch('/connected')
    return res.data as ConnectedRepo[]
  },

  async deleteRepo(id: string) {
    return apiFetch(`/${id}`, { method: 'DELETE' })
  },

  async analyzeRepo(id: string, llmConnectionId: string) {
    const res = await apiFetch(`/${id}/analyze`, {
      method: 'POST',
      body: JSON.stringify({ llm_connection_id: llmConnectionId }),
    })
    return res.data as { status: string }
  },

  async cancelAnalysis(id: string) {
    return apiFetch(`/${id}/analyze/cancel`, { method: 'POST' })
  },

  async getRepoStatus(id: string) {
    const res = await apiFetch(`/${id}/status`)
    return res.data as { status: string; progress_message: string | null; files_analyzed: number | null; total_files: number | null; error: string | null }
  },
}
