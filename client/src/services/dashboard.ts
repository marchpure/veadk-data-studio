import { getApiBaseUrl, isHostedMode } from '../lib/runtime-config'
import { getBackendUrl, isTauriApp } from '../lib/tauri-api'
import type {
  DashboardAsset,
  DashboardAssetDetail,
  DashboardAuditEvent,
  DashboardFolderShare,
  DashboardRun,
  DashboardSemanticDiff,
  DashboardState,
  DashboardVersion,
} from '../types/dashboard'
import { getAccessToken } from './tokenStore'

interface StandardResponse<T> {
  success: boolean
  message: string
  data: T
}

async function getDashboardApiUrl(): Promise<string> {
  const runtimeBase = getApiBaseUrl()
  if (runtimeBase && runtimeBase !== '/api') {
    return `${runtimeBase}/dashboard-assets`
  }
  if (isHostedMode()) {
    return '/api/dashboard-assets'
  }
  if (isTauriApp()) {
    const backend = await getBackendUrl()
    return `${backend}/api/dashboard-assets`
  }
  return '/api/dashboard-assets'
}

function getHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = getAccessToken()
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }
  const tenantId = localStorage.getItem('byaan_active_tenant')
  if (tenantId) {
    headers['X-Tenant-ID'] = tenantId
  }
  return headers
}

async function dashboardFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const base = await getDashboardApiUrl()
  const response = await fetch(`${base}${path}`, {
    ...init,
    headers: { ...getHeaders(), ...(init?.headers || {}) },
    credentials: 'include',
  })
  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    const message = payload?.message || payload?.detail || response.statusText || 'Dashboard request failed'
    throw new Error(message)
  }
  if (payload?.success === false) {
    throw new Error(payload.message || 'Dashboard request failed')
  }
  return (payload?.data ?? payload) as T
}

export const DashboardService = {
  async listAssets(): Promise<{ items: DashboardAsset[]; total: number }> {
    return dashboardFetch<{ items: DashboardAsset[]; total: number }>('')
  },

  async getAsset(assetId: string): Promise<DashboardAssetDetail> {
    return dashboardFetch<DashboardAssetDetail>(`/${assetId}`)
  },

  async getVersion(assetId: string, versionNum: number): Promise<DashboardVersion> {
    return dashboardFetch<DashboardVersion>(`/${assetId}/versions/${versionNum}`)
  },

  async query(assetId: string, payload: {
    filters?: Record<string, unknown>
    data_view_ids?: string[]
    correlation_id?: string
  }): Promise<DashboardRun> {
    return dashboardFetch<DashboardRun>(`/${assetId}/query`, {
      method: 'POST',
      body: JSON.stringify({
        filters: payload.filters ?? {},
        data_view_ids: payload.data_view_ids,
        correlation_id: payload.correlation_id,
      }),
    })
  },

  async preview(assetId: string, payload: {
    filters?: Record<string, unknown>
    data_view_ids?: string[]
    correlation_id?: string
  }): Promise<DashboardRun> {
    return dashboardFetch<DashboardRun>(`/${assetId}/preview`, {
      method: 'POST',
      body: JSON.stringify({
        filters: payload.filters ?? {},
        data_view_ids: payload.data_view_ids,
        correlation_id: payload.correlation_id,
      }),
    })
  },

  async validate(assetId: string): Promise<{ validation: DashboardVersion['validation_result']; manifest: DashboardVersion['manifest'] }> {
    return dashboardFetch<{ validation: DashboardVersion['validation_result']; manifest: DashboardVersion['manifest'] }>(
      `/${assetId}/validate`,
      {
        method: 'POST',
        body: JSON.stringify({}),
      },
    )
  },

  async patchDraft(assetId: string, payload: {
    base_etag: string
    json_patch: Array<Record<string, unknown>>
    change_summary: string
  }): Promise<DashboardVersion> {
    return dashboardFetch<DashboardVersion>(`/${assetId}/draft`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    })
  },

  async publish(assetId: string, payload: {
    base_etag: string
    change_summary: string
  }): Promise<DashboardVersion> {
    return dashboardFetch<DashboardVersion>(`/${assetId}/publish`, {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },

  async reload(assetId: string, payload: {
    base_etag: string
    semantic_model_versions?: Record<string, string>
    source_snapshot_ids?: string[] | null
    change_summary: string
  }): Promise<{ draft: DashboardVersion; semantic_diff: DashboardSemanticDiff }> {
    return dashboardFetch<{ draft: DashboardVersion; semantic_diff: DashboardSemanticDiff }>(`/${assetId}/reload`, {
      method: 'POST',
      body: JSON.stringify({
        base_etag: payload.base_etag,
        semantic_model_versions: payload.semantic_model_versions ?? {},
        source_snapshot_ids: payload.source_snapshot_ids ?? null,
        change_summary: payload.change_summary,
      }),
    })
  },

  async getState(assetId: string): Promise<DashboardState> {
    return dashboardFetch<DashboardState>(`/${assetId}/state`)
  },

  async getAudit(assetId: string): Promise<{ items: DashboardAuditEvent[]; total: number }> {
    return dashboardFetch<{ items: DashboardAuditEvent[]; total: number }>(`/${assetId}/audit`)
  },

  async exportHtml(assetId: string, versionNum?: number): Promise<{ blob: Blob; filename: string }> {
    const base = await getDashboardApiUrl()
    const params = new URLSearchParams()
    if (versionNum !== undefined) params.set('version_num', String(versionNum))
    const response = await fetch(`${base}/${assetId}/export/html${params.toString() ? `?${params.toString()}` : ''}`, {
      headers: getHeaders(),
      credentials: 'include',
    })
    if (!response.ok) {
      const payload = await response.json().catch(() => null)
      const message = payload?.message || payload?.detail || response.statusText || 'Dashboard export failed'
      throw new Error(message)
    }
    const disposition = response.headers.get('content-disposition') || ''
    const filename = disposition.match(/filename="([^"]+)"/)?.[1] ?? `dashboard-${assetId}.html`
    return { blob: await response.blob(), filename }
  },

  async sharePublishedVersionToFolder(folderId: string, dashboardVersionId: string): Promise<DashboardFolderShare> {
    const runtimeBase = getApiBaseUrl()
    const apiBase = runtimeBase && runtimeBase !== '/api'
      ? runtimeBase
      : isHostedMode()
        ? '/api'
        : isTauriApp()
          ? `${await getBackendUrl()}/api`
          : '/api'
    const response = await fetch(`${apiBase}/folders/${folderId}/dashboards`, {
      method: 'POST',
      headers: getHeaders(),
      credentials: 'include',
      body: JSON.stringify({ dashboard_id: dashboardVersionId }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok) {
      const message = payload?.message || payload?.detail || response.statusText || 'Dashboard folder share failed'
      throw new Error(message)
    }
    return (payload?.data ?? payload) as DashboardFolderShare
  },
}

export type DashboardApiResponse<T> = StandardResponse<T>
