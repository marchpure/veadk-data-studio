import { getApiBaseUrl, isHostedMode } from '../lib/runtime-config'
import { getBackendUrl, isTauriApp } from '../lib/tauri-api'
import { getAccessToken } from './tokenStore'
import type {
  AdvisorChangeSet,
  AdvisorReview,
  EvaluationCase,
  EvaluationCaseDraftInput,
  EvaluationFailureSummary,
  EvaluationRun,
  EvaluationRunComparison,
  EvaluationRunDetail,
  EvaluationSuiteCreateInput,
  EvaluationSuiteVersion,
  EvaluationTargetSnapshotInput,
  EvaluationSuite,
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

  async createSuite(payload: EvaluationSuiteCreateInput): Promise<{ suite: EvaluationSuite }> {
    return evaluationFetch<{ suite: EvaluationSuite }>('/suites', {
      method: 'POST',
      body: JSON.stringify({
        slug: payload.slug,
        name: payload.name,
        description: payload.description,
        target_kinds: payload.targetKinds,
        gate_policy: payload.gatePolicy ?? {},
      }),
    })
  },

  async createDraftVersion(suiteId: string, copyFromVersionId?: string | null): Promise<{ version: EvaluationSuiteVersion }> {
    return evaluationFetch<{ version: EvaluationSuiteVersion }>(`/suites/${suiteId}/draft-version`, {
      method: 'POST',
      body: JSON.stringify({ copy_from_version_id: copyFromVersionId ?? null }),
    })
  },

  async listCases(suiteVersionId: string): Promise<{ items: EvaluationCase[]; total: number; has_more: boolean }> {
    return evaluationFetch<{ items: EvaluationCase[]; total: number; has_more: boolean }>(
      `/suite-versions/${suiteVersionId}/cases`,
    )
  },

  async createCase(suiteVersionId: string, payload: EvaluationCaseDraftInput): Promise<{ case: EvaluationCase; created: boolean }> {
    return evaluationFetch<{ case: EvaluationCase; created: boolean }>(`/suite-versions/${suiteVersionId}/cases`, {
      method: 'POST',
      body: JSON.stringify(toCasePayload(payload)),
    })
  },

  async importCases(suiteVersionId: string, cases: EvaluationCaseDraftInput[]): Promise<{
    created: EvaluationCase[]
    existing: EvaluationCase[]
    created_count: number
    existing_count: number
    total: number
  }> {
    return evaluationFetch<{
      created: EvaluationCase[]
      existing: EvaluationCase[]
      created_count: number
      existing_count: number
      total: number
    }>(`/suite-versions/${suiteVersionId}/cases/import`, {
      method: 'POST',
      body: JSON.stringify({ format: 'json', cases: cases.map(toCasePayload) }),
    })
  },

  async publishSuiteVersion(suiteVersionId: string): Promise<{ version: EvaluationSuiteVersion }> {
    return evaluationFetch<{ version: EvaluationSuiteVersion }>(`/suite-versions/${suiteVersionId}/publish`, {
      method: 'POST',
      body: JSON.stringify({}),
    })
  },

  async listRuns(suiteVersionId: string): Promise<{ items: EvaluationRun[]; total: number }> {
    return evaluationFetch<{ items: EvaluationRun[]; total: number }>(
      `/suite-versions/${suiteVersionId}/runs`,
    )
  },

  async createPreflightRun(payload: {
    suiteVersionId: string
    targetSnapshot: EvaluationTargetSnapshotInput
    idempotencyKey?: string
    actorType?: 'human' | 'agent' | 'service'
    actorId?: string
  }): Promise<EvaluationRun> {
    return evaluationFetch<EvaluationRun>('/runs/preflight', {
      method: 'POST',
      body: JSON.stringify({
        suite_version_id: payload.suiteVersionId,
        target_snapshot: payload.targetSnapshot,
        idempotency_key: payload.idempotencyKey,
        actor_type: payload.actorType ?? 'agent',
        actor_id: payload.actorId,
      }),
    })
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

function toCasePayload(payload: EvaluationCaseDraftInput): Record<string, unknown> {
  return {
    case_key: payload.caseKey,
    title: payload.title,
    target_kinds: payload.targetKinds,
    operation: payload.operation,
    question: payload.question,
    expected_contract: payload.expectedContract,
    provenance: payload.provenance,
    tags: payload.tags,
  }
}
