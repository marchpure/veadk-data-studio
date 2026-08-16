export interface EvaluationSuite {
  id: string
  tenant_id: string
  slug: string
  name: string
  description: string
  owner_id: string | null
  target_kinds: string[]
  lifecycle: string
  current_draft_version_id: string | null
  published_version_id: string | null
  versions?: EvaluationSuiteVersion[]
  created_at: string | null
  updated_at: string | null
}

export interface EvaluationSuiteCreateInput {
  slug: string
  name: string
  description: string
  targetKinds: string[]
  gatePolicy?: Record<string, unknown>
}

export interface EvaluationCaseDraftInput {
  caseKey: string
  title: string
  targetKinds: string[]
  operation: string
  question: string
  expectedContract: Record<string, unknown>
  provenance: Record<string, unknown>
  tags: string[]
}

export interface EvaluationSuiteVersion {
  id: string
  tenant_id: string
  suite_id: string
  version_num: number
  status: string
  contract_version: string
  case_count: number
  content_hash: string
  gate_policy: Record<string, unknown>
  manifest?: Record<string, unknown>
  created_by: string | null
  published_at: string | null
  created_at: string | null
}

export interface EvaluationCase {
  id: string
  tenant_id: string
  suite_version_id: string
  case_key: string
  title: string
  target_kinds: string[]
  operation: string
  question: string
  expected_contract?: Record<string, unknown>
  provenance: Record<string, unknown>
  tags: string[]
  content_hash: string
  immutable: boolean
  has_ground_truth_sql: boolean
  created_at: string | null
}

export interface EvaluationRun {
  id: string
  tenant_id: string
  suite_version_id: string
  target_snapshot_id: string
  status: string
  actor_type: string
  actor_id: string
  baseline_run_id: string | null
  candidate_label: string | null
  idempotency_key: string | null
  attempt: number
  lease_holder: string | null
  lease_expires_at: string | null
  heartbeat_at: string | null
  stop_requested: boolean
  preflight_blockers: string[]
  summary: Record<string, unknown>
  started_at: string | null
  completed_at: string | null
  created_at: string | null
}

export interface EvaluationAssessment {
  id: string
  tenant_id: string
  case_run_id: string
  category: string
  status: string
  score: string | null
  hard_fail: boolean
  details: Record<string, unknown>
  immutable: boolean
  created_at: string | null
}

export interface EvaluationCaseRun {
  id: string
  tenant_id: string
  run_id: string
  case_id: string
  status: string
  attempt: number
  input_digest: string
  output_digest: string
  result: Record<string, unknown>
  error: Record<string, unknown>
  immutable: boolean
  started_at: string | null
  completed_at: string | null
  created_at: string | null
  assessments: EvaluationAssessment[]
}

export interface EvaluationRunDetail {
  run: EvaluationRun
  case_runs?: EvaluationCaseRun[]
  total_case_runs?: number
  has_more_case_runs?: boolean
}

export interface EvaluationFailureSummary {
  run: EvaluationRun
  failures: EvaluationCaseRun[]
  total: number
  has_more: boolean
}

export interface EvaluationRunComparison {
  baseline_run_id: string
  candidate_run_id: string
  baseline_gate: string
  candidate_gate: string
  regressions: Array<Record<string, unknown>>
  improvements: Array<Record<string, unknown>>
  unchanged: Array<Record<string, unknown>>
  summary: {
    regression_count: number
    improvement_count: number
    unchanged_count: number
  }
}

export interface AdvisorChangeSet {
  id: string
  tenant_id: string
  suite_version_id: string | null
  target_ref: string
  base_version_ref: string
  base_etag: string
  status: string
  evidence: Record<string, unknown>
  verification_run_id: string | null
  regression_run_id: string | null
  created_by: string
  created_at: string | null
}

export interface AdvisorSuggestion {
  id: string
  tenant_id: string
  change_set_id: string
  suggestion_type: string
  patch: Record<string, unknown>
  affected_case_ids: string[]
  status: string
  created_at: string | null
}

export interface PromotionDecision {
  id: string
  tenant_id: string
  change_set_id: string | null
  verification_run_id: string | null
  regression_run_id: string | null
  decision: string
  decided_by: string | null
  rationale: string
  audit: Record<string, unknown>
  created_at: string | null
}

export interface AdvisorReview {
  change_set: AdvisorChangeSet
  advisor_suggestions: AdvisorSuggestion[]
  verification_run: EvaluationRun | null
  regression_run: EvaluationRun | null
  promotion_decisions: PromotionDecision[]
  gate_summary: {
    verification_gate: string
    regression_gate: string
    ready_to_apply: boolean
  }
}

export interface EvaluationTargetSnapshotInput {
  contract_version: string
  target_kind: string
  target_ref: string
  app: Record<string, unknown>
  source?: Record<string, unknown>
  semantic_model?: Record<string, unknown>
  dashboard?: Record<string, unknown>
  prompt?: Record<string, unknown>
  tool_registry_hash?: string | null
  skill_registry_hash?: string | null
  llm?: Record<string, unknown>
  principal: Record<string, unknown>
  dataset?: Record<string, unknown>
  feature_flags: Record<string, unknown>
  time_fixture: Record<string, unknown>
}
