import { getApiBaseUrl, isHostedMode } from '../lib/runtime-config'
import { getBackendUrl, isTauriApp } from '../lib/tauri-api'
import { getAccessToken } from './tokenStore'
import type {
  AdvisorChangeSet,
  AdvisorReview,
  EvaluationCase,
  EvaluationFailureSummary,
  EvaluationRun,
  EvaluationRunComparison,
  EvaluationRunDetail,
  EvaluationSuite,
  EvaluationTargetSnapshotInput,
} from '../types/evaluation'

interface StandardResponse<T> {
  success: boolean
  message: string
  data: T
}

async function getEvaluationApiUrl(): Promise<string> {
  const runtimeBase = getApiBaseUrl()
  if (runtimeBase && runtimeBase !== '/api') {
    return `${runtimeBase}/evaluation`
  }
  if (isHostedMode()) {
    return '/api/evaluation'
  }
  if (isTauriApp()) {
    const backend = await getBackendUrl()
    return `${backend}/api/evaluation`
  }
  return '/api/evaluation'
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

async function evaluationFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const base = await getEvaluationApiUrl()
  const response = await fetch(`${base}${path}`, {
    ...init,
    headers: { ...getHeaders(), ...(init?.headers || {}) },
    credentials: 'include',
  })
  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    const message = payload?.message || payload?.detail || response.statusText || 'Evaluation request failed'
    throw new Error(message)
  }
  if (payload?.success === false) {
    throw new Error(payload.message || 'Evaluation request failed')
  }
  return (payload?.data ?? payload) as T
}

function query(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') {
      search.set(key, String(value))
    }
  })
  const serialized = search.toString()
  return serialized ? `?${serialized}` : ''
}

export const EvaluationService = {
  async listSuites(params: {
    query?: string
    targetKind?: string
    status?: string
    limit?: number
  } = {}): Promise<{ items: EvaluationSuite[]; total: number }> {
    return evaluationFetch<{ items: EvaluationSuite[]; total: number }>(
      `/suites${query({
        query: params.query,
        target_kind: params.targetKind,
        status: params.status,
        limit: params.limit,
      })}`,
    )
  },

  async describeSuite(suiteId: string, includeManifests = true): Promise<{ suite: EvaluationSuite }> {
    return evaluationFetch<{ suite: EvaluationSuite }>(
      `/suites/${suiteId}${query({ include_manifests: includeManifests })}`,
    )
  },

  async listCases(suiteVersionId: string): Promise<{ items: EvaluationCase[]; total: number; has_more: boolean }> {
    return evaluationFetch<{ items: EvaluationCase[]; total: number; has_more: boolean }>(
      `/suite-versions/${suiteVersionId}/cases`,
    )
  },

  async listRuns(suiteVersionId: string): Promise<{ items: EvaluationRun[]; total: number }> {
    return evaluationFetch<{ items: EvaluationRun[]; total: number }>(
      `/suite-versions/${suiteVersionId}/runs`,
    )
  },

  async listAdvisorChangeSets(suiteVersionId: string): Promise<{ items: AdvisorChangeSet[]; total: number }> {
    return evaluationFetch<{ items: AdvisorChangeSet[]; total: number }>(
      `/suite-versions/${suiteVersionId}/advisor-change-sets`,
    )
  },

  async getRun(runId: string): Promise<EvaluationRunDetail> {
    return evaluationFetch<EvaluationRunDetail>(`/runs/${runId}`)
  },

  async getFailures(runId: string): Promise<EvaluationFailureSummary> {
    return evaluationFetch<EvaluationFailureSummary>(`/runs/${runId}/failures`)
  },

  async compareRuns(baselineRunId: string, candidateRunId: string): Promise<{ comparison: EvaluationRunComparison }> {
    return evaluationFetch<{ comparison: EvaluationRunComparison }>(
      `/runs/compare${query({ baseline_run_id: baselineRunId, candidate_run_id: candidateRunId })}`,
    )
  },

  async getAdvisorReview(changeSetId: string): Promise<AdvisorReview> {
    return evaluationFetch<AdvisorReview>(`/advisor-change-sets/${changeSetId}/review`)
  },

  async runAdvisorVerification(changeSetId: string, payload: {
    targetSnapshot: EvaluationTargetSnapshotInput
    idempotencyKey?: string
  }): Promise<{ change_set: AdvisorChangeSet; run: EvaluationRun }> {
    return evaluationFetch<{ change_set: AdvisorChangeSet; run: EvaluationRun }>(
      `/advisor-change-sets/${changeSetId}/verification`,
      {
        method: 'POST',
        body: JSON.stringify({
          target_snapshot: payload.targetSnapshot,
          idempotency_key: payload.idempotencyKey,
        }),
      },
    )
  },

  async runAdvisorRegression(changeSetId: string, payload: {
    targetSnapshot: EvaluationTargetSnapshotInput
    idempotencyKey?: string
  }): Promise<{ change_set: AdvisorChangeSet; run: EvaluationRun }> {
    return evaluationFetch<{ change_set: AdvisorChangeSet; run: EvaluationRun }>(
      `/advisor-change-sets/${changeSetId}/regression`,
      {
        method: 'POST',
        body: JSON.stringify({
          target_snapshot: payload.targetSnapshot,
          idempotency_key: payload.idempotencyKey,
        }),
      },
    )
  },

  async applyAdvisorChangeSet(changeSetId: string): Promise<{ promotion: unknown; review: AdvisorReview }> {
    return evaluationFetch<{ promotion: unknown; review: AdvisorReview }>(
      `/advisor-change-sets/${changeSetId}/apply`,
      { method: 'POST', body: JSON.stringify({}) },
    )
  },
}

export type EvaluationApiResponse<T> = StandardResponse<T>
