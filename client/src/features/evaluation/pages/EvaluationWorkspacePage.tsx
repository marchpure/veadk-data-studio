import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowRightLeft,
  Bot,
  CheckCircle2,
  ClipboardCheck,
  Database,
  FileSearch,
  GitBranch,
  Loader2,
  Play,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  XCircle,
} from 'lucide-react'
import { Button } from '../../../components/ui/button'
import { Input } from '../../../components/ui/input'
import { cn } from '../../../lib/utils'
import { EvaluationService } from '../../../services/evaluation'
import type {
  AdvisorChangeSet,
  AdvisorReview,
  EvaluationCase,
  EvaluationCaseRun,
  EvaluationFailureSummary,
  EvaluationRun,
  EvaluationRunComparison,
  EvaluationRunDetail,
  EvaluationSuite,
  EvaluationSuiteVersion,
  EvaluationTargetSnapshotInput,
} from '../../../types/evaluation'

type EvaluationTab = 'cases' | 'runs' | 'advisor' | 'feedback' | 'settings'

const statusTone: Record<string, string> = {
  published: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
  draft: 'border-sky-500/30 bg-sky-500/10 text-sky-200',
  running: 'border-sky-500/30 bg-sky-500/10 text-sky-200',
  queued: 'border-[#3a444d] bg-[#20262b] text-[#cdd3d8]',
  preflight: 'border-[#3a444d] bg-[#20262b] text-[#cdd3d8]',
  verification_queued: 'border-sky-500/30 bg-sky-500/10 text-sky-200',
  regression_queued: 'border-sky-500/30 bg-sky-500/10 text-sky-200',
  passed: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
  promoted: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
  accepted: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
  failed: 'border-red-500/30 bg-red-500/10 text-red-200',
  blocked: 'border-red-500/30 bg-red-500/10 text-red-200',
  rejected: 'border-red-500/30 bg-red-500/10 text-red-200',
  canceled: 'border-amber-500/30 bg-amber-500/10 text-amber-100',
  partial: 'border-amber-500/30 bg-amber-500/10 text-amber-100',
  ready_for_review: 'border-violet-500/30 bg-violet-500/10 text-violet-100',
}

export default function EvaluationWorkspacePage() {
  const { suiteId } = useParams<{ suiteId?: string }>()
  const navigate = useNavigate()
  const [suites, setSuites] = useState<EvaluationSuite[]>([])
  const [suite, setSuite] = useState<EvaluationSuite | null>(null)
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null)
  const [cases, setCases] = useState<EvaluationCase[]>([])
  const [runs, setRuns] = useState<EvaluationRun[]>([])
  const [selectedRun, setSelectedRun] = useState<EvaluationRunDetail | null>(null)
  const [failures, setFailures] = useState<EvaluationFailureSummary | null>(null)
  const [comparison, setComparison] = useState<EvaluationRunComparison | null>(null)
  const [advisorChangeSets, setAdvisorChangeSets] = useState<AdvisorChangeSet[]>([])
  const [advisorReview, setAdvisorReview] = useState<AdvisorReview | null>(null)
  const [query, setQuery] = useState('')
  const [tab, setTab] = useState<EvaluationTab>('cases')
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null)
  const [loadingSuites, setLoadingSuites] = useState(true)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [loadingAction, setLoadingAction] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [actionMessage, setActionMessage] = useState<string | null>(null)

  const selectedVersion = useMemo(() => {
    return suite?.versions?.find(version => version.id === selectedVersionId) ?? suite?.versions?.[0] ?? null
  }, [suite, selectedVersionId])

  const selectedCase = useMemo(() => {
    return cases.find(item => item.id === selectedCaseId) ?? cases[0] ?? null
  }, [cases, selectedCaseId])

  const loadSuites = useCallback(async () => {
    setLoadingSuites(true)
    setError(null)
    try {
      const response = await EvaluationService.listSuites({ query, limit: 100 })
      setSuites(response.items)
      if (!suiteId && response.items.length > 0) {
        navigate(`/evaluation/${response.items[0].id}`, { replace: true })
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load Evaluation suites')
    } finally {
      setLoadingSuites(false)
    }
  }, [navigate, query, suiteId])

  const loadVersionData = useCallback(async (versionId: string) => {
    const [caseResponse, runResponse, advisorResponse] = await Promise.all([
      EvaluationService.listCases(versionId),
      EvaluationService.listRuns(versionId),
      EvaluationService.listAdvisorChangeSets(versionId),
    ])
    setCases(caseResponse.items)
    setRuns(runResponse.items)
    setAdvisorChangeSets(advisorResponse.items)
    setSelectedCaseId(previous => previous && caseResponse.items.some(item => item.id === previous) ? previous : caseResponse.items[0]?.id ?? null)
    const firstRun = runResponse.items[0]
    if (firstRun) {
      const [runDetail, failureDetail] = await Promise.all([
        EvaluationService.getRun(firstRun.id),
        EvaluationService.getFailures(firstRun.id),
      ])
      setSelectedRun(runDetail)
      setFailures(failureDetail)
    } else {
      setSelectedRun(null)
      setFailures(null)
    }
    if (advisorResponse.items[0]) {
      setAdvisorReview(await EvaluationService.getAdvisorReview(advisorResponse.items[0].id))
    } else {
      setAdvisorReview(null)
    }
  }, [])

  const loadSuiteDetail = useCallback(async (id: string) => {
    setLoadingDetail(true)
    setError(null)
    try {
      const response = await EvaluationService.describeSuite(id, true)
      const nextSuite = response.suite
      const version = chooseVersion(nextSuite.versions ?? [], selectedVersionId)
      setSuite(nextSuite)
      setSelectedVersionId(version?.id ?? null)
      if (!version) {
        setCases([])
        setRuns([])
        setAdvisorChangeSets([])
        setSelectedRun(null)
        setFailures(null)
        setAdvisorReview(null)
        return
      }
      await loadVersionData(version.id)
      setComparison(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load Evaluation suite')
    } finally {
      setLoadingDetail(false)
    }
  }, [loadVersionData, selectedVersionId])

  useEffect(() => {
    void loadSuites()
  }, [loadSuites])

  useEffect(() => {
    if (suiteId) {
      void loadSuiteDetail(suiteId)
    }
  }, [suiteId, loadSuiteDetail])

  const filteredSuites = useMemo(() => {
    const lower = query.trim().toLowerCase()
    if (!lower) return suites
    return suites.filter(item => [item.name, item.slug, item.description].some(value => value.toLowerCase().includes(lower)))
  }, [query, suites])

  const loadRun = async (runId: string) => {
    setLoadingAction(true)
    setError(null)
    try {
      const [runDetail, failureDetail] = await Promise.all([
        EvaluationService.getRun(runId),
        EvaluationService.getFailures(runId),
      ])
      setSelectedRun(runDetail)
      setFailures(failureDetail)
      setTab('runs')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load Evaluation run')
    } finally {
      setLoadingAction(false)
    }
  }

  const compareLatestRuns = async () => {
    if (runs.length < 2) return
    setLoadingAction(true)
    setError(null)
    try {
      const response = await EvaluationService.compareRuns(runs[1].id, runs[0].id)
      setComparison(response.comparison)
      setTab('runs')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to compare Evaluation runs')
    } finally {
      setLoadingAction(false)
    }
  }

  const selectAdvisor = async (changeSetId: string) => {
    setLoadingAction(true)
    setError(null)
    try {
      setAdvisorReview(await EvaluationService.getAdvisorReview(changeSetId))
      setTab('advisor')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load Advisor review')
    } finally {
      setLoadingAction(false)
    }
  }

  const runAdvisorGate = async (kind: 'verification' | 'regression') => {
    if (!advisorReview) return
    setLoadingAction(true)
    setActionMessage(null)
    try {
      const snapshot = buildTargetSnapshot(advisorReview.change_set, suite, selectedVersion)
      const response = kind === 'verification'
        ? await EvaluationService.runAdvisorVerification(advisorReview.change_set.id, {
          targetSnapshot: snapshot,
          idempotencyKey: `human-${kind}-${advisorReview.change_set.id}`,
        })
        : await EvaluationService.runAdvisorRegression(advisorReview.change_set.id, {
          targetSnapshot: snapshot,
          idempotencyKey: `human-${kind}-${advisorReview.change_set.id}`,
        })
      setActionMessage(`${kind} run queued: ${shortId(response.run.id)}`)
      setAdvisorReview(await EvaluationService.getAdvisorReview(advisorReview.change_set.id))
      if (suiteId) {
        await loadSuiteDetail(suiteId)
      }
    } catch (err) {
      setActionMessage(err instanceof Error ? err.message : `${kind} failed`)
    } finally {
      setLoadingAction(false)
    }
  }

  const applyAdvisor = async () => {
    if (!advisorReview) return
    setLoadingAction(true)
    setActionMessage(null)
    try {
      const response = await EvaluationService.applyAdvisorChangeSet(advisorReview.change_set.id)
      setAdvisorReview(response.review)
      setActionMessage(`Apply decision: ${formatValue(response.promotion)}`)
      if (suiteId) {
        await loadSuiteDetail(suiteId)
      }
    } catch (err) {
      setActionMessage(err instanceof Error ? err.message : 'Advisor apply failed')
    } finally {
      setLoadingAction(false)
    }
  }

  return (
    <div className="flex min-h-full bg-[#0d0f11] text-[#f3f5f5]">
      <aside className="hidden w-[360px] shrink-0 border-r border-[#293037] bg-[#121518] lg:flex lg:flex-col">
        <div className="border-b border-[#293037] p-4">
          <div className="flex items-center gap-2">
            <ClipboardCheck className="h-5 w-5 text-brand-orange" />
            <h1 className="text-lg font-semibold">Evaluation</h1>
          </div>
          <div className="relative mt-3">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-[#7f8a93]" />
            <Input
              value={query}
              onChange={event => setQuery(event.target.value)}
              placeholder="Search suites"
              className="h-9 border-[#303940] bg-[#0e1114] pl-9 text-sm text-[#eef2f3]"
              aria-label="Search Evaluation suites"
            />
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-3 custom-scrollbar">
          {loadingSuites && <LoadingList />}
          {!loadingSuites && filteredSuites.length === 0 && (
            <EmptyPanel title="No Evaluation suites" body="Published and draft suites will appear here after cases are promoted or authored." />
          )}
          {!loadingSuites && filteredSuites.map(item => (
            <Link
              key={item.id}
              to={`/evaluation/${item.id}`}
              className={cn(
                'mb-2 block rounded-md border p-3 transition-colors',
                item.id === suiteId ? 'border-brand-orange/60 bg-brand-orange/10' : 'border-[#293037] bg-[#171b1f] hover:border-[#4a5660]',
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-[#f3f5f5]">{item.name}</div>
                  <div className="mt-1 truncate text-xs text-[#818c95]">{item.slug}</div>
                </div>
                <StatusPill status={item.lifecycle} />
              </div>
              <div className="mt-3 flex flex-wrap gap-1">
                {item.target_kinds.map(kind => <Badge key={kind}>{kind}</Badge>)}
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] text-[#9aa4ac]">
                <span>Draft {shortId(item.current_draft_version_id)}</span>
                <span>Published {shortId(item.published_version_id)}</span>
              </div>
            </Link>
          ))}
        </div>
      </aside>

      <main className="min-w-0 flex-1">
        <div className="mx-auto flex max-w-[1480px] flex-col gap-4 p-4 md:p-6">
          {error && (
            <div className="flex items-center gap-2 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-100">
              <AlertTriangle className="h-4 w-4" />
              <span>{error}</span>
            </div>
          )}

          {!suite && !loadingDetail && (
            <EmptyPanel title="Open an Evaluation suite" body="Select a suite to inspect cases, run history, Advisor changes, and promotion gates." />
          )}

          {suite && (
            <>
              <header className="grid gap-3 border-b border-[#293037] pb-4 xl:grid-cols-[minmax(0,1fr)_420px]">
                <section className="rounded-md border border-[#293037] bg-[#14181c] p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <h1 className="min-w-0 truncate text-xl font-semibold">{suite.name}</h1>
                    <StatusPill status={suite.lifecycle} />
                    <StatusPill status={selectedVersion?.status} />
                    {selectedVersion?.published_at && <Badge tone="ready">Published</Badge>}
                  </div>
                  <p className="mt-2 max-w-4xl text-sm leading-6 text-[#a4adb5]">{suite.description || 'No suite description'}</p>
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <select
                      value={selectedVersion?.id ?? ''}
                      onChange={event => {
                        const nextVersionId = event.target.value
                        setSelectedVersionId(nextVersionId)
                        void loadVersionData(nextVersionId)
                        setComparison(null)
                      }}
                      className="h-8 rounded border border-[#303940] bg-[#0e1114] px-2 text-xs text-[#eef2f3]"
                      aria-label="Evaluation suite version"
                    >
                      {(suite.versions ?? []).map(version => (
                        <option key={version.id} value={version.id}>
                          v{version.version_num} {version.status}
                        </option>
                      ))}
                    </select>
                    {suite.target_kinds.map(kind => <Badge key={kind}>{kind}</Badge>)}
                  </div>
                  <div className="mt-4 grid gap-2 text-xs text-[#9aa4ac] md:grid-cols-4">
                    <HeaderSignal icon={<FileSearch className="h-4 w-4" />} label="Cases" value={String(cases.length)} />
                    <HeaderSignal icon={<Play className="h-4 w-4" />} label="Runs" value={String(runs.length)} />
                    <HeaderSignal icon={<Bot className="h-4 w-4" />} label="Advisor" value={String(advisorChangeSets.length)} />
                    <HeaderSignal icon={<ShieldCheck className="h-4 w-4" />} label="Gate" value={latestGate(runs)} />
                  </div>
                </section>

                <section className="rounded-md border border-[#293037] bg-[#14181c] p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-xs font-medium uppercase text-[#818c95]">Run compare</div>
                      <div className="mt-1 text-sm text-[#d6dde2]">{runs.length >= 2 ? 'Latest candidate against previous baseline' : 'Needs at least two runs'}</div>
                    </div>
                    <Button variant="secondary" onClick={() => void compareLatestRuns()} disabled={loadingAction || runs.length < 2}>
                      {loadingAction ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRightLeft className="h-4 w-4" />}
                      Compare
                    </Button>
                  </div>
                  {comparison ? (
                    <div className="mt-4 grid grid-cols-3 gap-2 text-center">
                      <Metric label="Regressions" value={comparison.summary.regression_count} tone="bad" />
                      <Metric label="Improvements" value={comparison.summary.improvement_count} tone="good" />
                      <Metric label="Unchanged" value={comparison.summary.unchanged_count} />
                    </div>
                  ) : (
                    <div className="mt-4 rounded-md border border-[#303940] bg-[#0e1114] p-3 text-sm text-[#9aa4ac]">
                      No comparison loaded.
                    </div>
                  )}
                </section>
              </header>

              <section className="rounded-md border border-[#293037] bg-[#14181c]">
                <div className="flex flex-col gap-3 border-b border-[#293037] p-3 xl:flex-row xl:items-center xl:justify-between">
                  <div className="flex flex-wrap gap-1 rounded-md border border-[#303940] bg-[#0e1114] p-1">
                    <TabButton active={tab === 'cases'} onClick={() => setTab('cases')} icon={<FileSearch className="h-4 w-4" />} label="Cases" />
                    <TabButton active={tab === 'runs'} onClick={() => setTab('runs')} icon={<Play className="h-4 w-4" />} label="Runs" />
                    <TabButton active={tab === 'advisor'} onClick={() => setTab('advisor')} icon={<Bot className="h-4 w-4" />} label="Advisor" />
                    <TabButton active={tab === 'feedback'} onClick={() => setTab('feedback')} icon={<ClipboardCheck className="h-4 w-4" />} label="Feedback" />
                    <TabButton active={tab === 'settings'} onClick={() => setTab('settings')} icon={<SlidersHorizontal className="h-4 w-4" />} label="Settings" />
                  </div>
                  {loadingDetail && (
                    <div className="flex items-center gap-2 text-sm text-[#9aa4ac]">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Loading suite
                    </div>
                  )}
                </div>
                <div className="p-3">
                  {tab === 'cases' && <CasesTab cases={cases} selectedCase={selectedCase} onSelectCase={setSelectedCaseId} />}
                  {tab === 'runs' && (
                    <RunsTab
                      runs={runs}
                      selectedRun={selectedRun}
                      failures={failures}
                      comparison={comparison}
                      onSelectRun={runId => void loadRun(runId)}
                    />
                  )}
                  {tab === 'advisor' && (
                    <AdvisorTab
                      changeSets={advisorChangeSets}
                      review={advisorReview}
                      loading={loadingAction}
                      message={actionMessage}
                      onSelect={changeSetId => void selectAdvisor(changeSetId)}
                      onVerify={() => void runAdvisorGate('verification')}
                      onRegress={() => void runAdvisorGate('regression')}
                      onApply={() => void applyAdvisor()}
                    />
                  )}
                  {tab === 'feedback' && <FeedbackTab selectedVersion={selectedVersion} cases={cases} />}
                  {tab === 'settings' && <SettingsTab suite={suite} version={selectedVersion} />}
                </div>
              </section>
            </>
          )}
        </div>
      </main>
    </div>
  )
}

function chooseVersion(versions: EvaluationSuiteVersion[], selectedVersionId: string | null): EvaluationSuiteVersion | null {
  if (selectedVersionId) {
    const selected = versions.find(version => version.id === selectedVersionId)
    if (selected) return selected
  }
  return versions.find(version => version.status === 'published') ?? versions[0] ?? null
}

function CasesTab({ cases, selectedCase, onSelectCase }: {
  cases: EvaluationCase[]
  selectedCase: EvaluationCase | null
  onSelectCase: (caseId: string) => void
}) {
  if (cases.length === 0) {
    return <EmptyPanel title="No cases" body="Promoted feedback and authored contracts will appear in this suite version." />
  }
  return (
    <div className="grid gap-3 xl:grid-cols-[360px_minmax(0,1fr)]">
      <div className="space-y-2">
        {cases.map(item => (
          <button
            key={item.id}
            type="button"
            onClick={() => onSelectCase(item.id)}
            className={cn(
              'w-full rounded-md border p-3 text-left transition-colors',
              selectedCase?.id === item.id ? 'border-brand-orange/60 bg-brand-orange/10' : 'border-[#293037] bg-[#101316] hover:border-[#4a5660]',
            )}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-[#f3f5f5]">{item.title}</div>
                <div className="mt-1 truncate text-xs text-[#818c95]">{item.case_key}</div>
              </div>
              {item.immutable && <Badge tone="ready">Immutable</Badge>}
            </div>
            <div className="mt-3 flex flex-wrap gap-1">
              {item.target_kinds.map(kind => <Badge key={kind}>{kind}</Badge>)}
              {item.tags.slice(0, 3).map(tag => <Badge key={tag}>{tag}</Badge>)}
            </div>
          </button>
        ))}
      </div>
      {selectedCase ? <CaseDetailPanel item={selectedCase} /> : null}
    </div>
  )
}

function CaseDetailPanel({ item }: { item: EvaluationCase }) {
  return (
    <div className="rounded-md border border-[#293037] bg-[#101316] p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-base font-semibold">{item.title}</h2>
        <StatusPill status={item.operation} />
        {item.has_ground_truth_sql && <Badge tone="ready">Ground truth SQL</Badge>}
      </div>
      <p className="mt-3 text-sm leading-6 text-[#d6dde2]">{item.question}</p>
      <div className="mt-4 grid gap-3 xl:grid-cols-2">
        <JsonPanel title="Expected contract" value={item.expected_contract ?? {}} />
        <JsonPanel title="Provenance" value={item.provenance} />
      </div>
    </div>
  )
}

function RunsTab({ runs, selectedRun, failures, comparison, onSelectRun }: {
  runs: EvaluationRun[]
  selectedRun: EvaluationRunDetail | null
  failures: EvaluationFailureSummary | null
  comparison: EvaluationRunComparison | null
  onSelectRun: (runId: string) => void
}) {
  if (runs.length === 0) {
    return <EmptyPanel title="No runs" body="Queued, running, blocked, partial, failed, and completed Evaluation runs will appear here." />
  }
  return (
    <div className="grid gap-3 xl:grid-cols-[360px_minmax(0,1fr)]">
      <div className="space-y-2">
        {runs.map(run => (
          <button
            key={run.id}
            type="button"
            onClick={() => onSelectRun(run.id)}
            className={cn(
              'w-full rounded-md border p-3 text-left transition-colors',
              selectedRun?.run.id === run.id ? 'border-brand-orange/60 bg-brand-orange/10' : 'border-[#293037] bg-[#101316] hover:border-[#4a5660]',
            )}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-semibold">{shortId(run.id)}</span>
              <StatusPill status={run.status} />
            </div>
            <div className="mt-2 grid grid-cols-2 gap-2 text-[11px] text-[#9aa4ac]">
              <span>Gate {formatValue(run.summary.gate_decision ?? run.status)}</span>
              <span>Attempt {run.attempt}</span>
              <span>{formatDate(run.created_at)}</span>
              <span>{run.stop_requested ? 'Stopping' : run.lease_holder ? 'Leased' : 'Idle'}</span>
            </div>
          </button>
        ))}
      </div>
      <div className="space-y-3">
        {comparison && <ComparisonPanel comparison={comparison} />}
        {selectedRun && <RunDetailPanel detail={selectedRun} failures={failures} />}
      </div>
    </div>
  )
}

function RunDetailPanel({ detail, failures }: { detail: EvaluationRunDetail; failures: EvaluationFailureSummary | null }) {
  const run = detail.run
  const caseRuns = detail.case_runs ?? []
  return (
    <div className="rounded-md border border-[#293037] bg-[#101316] p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-base font-semibold">Run {shortId(run.id)}</h2>
        <StatusPill status={run.status} />
        {run.stop_requested && <Badge tone="warning">Stopping</Badge>}
      </div>
      <div className="mt-4 grid gap-2 md:grid-cols-4">
        <HeaderSignal icon={<ShieldCheck className="h-4 w-4" />} label="Gate" value={formatValue(run.summary.gate_decision ?? run.status)} />
        <HeaderSignal icon={<RefreshCw className="h-4 w-4" />} label="Attempt" value={String(run.attempt)} />
        <HeaderSignal icon={<GitBranch className="h-4 w-4" />} label="Lease" value={run.lease_holder ?? 'None'} />
        <HeaderSignal icon={<Database className="h-4 w-4" />} label="Failures" value={String(failures?.total ?? 0)} />
      </div>
      {run.preflight_blockers.length > 0 && (
        <div className="mt-4 rounded-md border border-red-500/30 bg-red-500/10 p-3">
          <div className="mb-2 text-sm font-semibold text-red-100">Preflight blockers</div>
          <ul className="space-y-1 text-sm text-red-100">
            {run.preflight_blockers.map(blocker => <li key={blocker}>{blocker}</li>)}
          </ul>
        </div>
      )}
      <div className="mt-4 space-y-2">
        {caseRuns.map(caseRun => <CaseRunRow key={caseRun.id} item={caseRun} />)}
      </div>
    </div>
  )
}

function CaseRunRow({ item }: { item: EvaluationCaseRun }) {
  return (
    <div className="rounded-md border border-[#293037] bg-[#14181c] p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm font-medium">Case {shortId(item.case_id)}</div>
        <StatusPill status={item.status} />
      </div>
      <div className="mt-2 grid gap-2 md:grid-cols-3">
        {item.assessments.map(assessment => (
          <div key={assessment.id} className="rounded border border-[#303940] bg-[#0e1114] p-2 text-xs">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium text-[#d6dde2]">{assessment.category}</span>
              {assessment.hard_fail ? <XCircle className="h-3.5 w-3.5 text-red-300" /> : <CheckCircle2 className="h-3.5 w-3.5 text-emerald-300" />}
            </div>
            <div className="mt-1 text-[#9aa4ac]">{assessment.status} {assessment.score ?? ''}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

function ComparisonPanel({ comparison }: { comparison: EvaluationRunComparison }) {
  return (
    <div className="rounded-md border border-[#293037] bg-[#101316] p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-base font-semibold">Baseline compare</h2>
        <StatusPill status={comparison.candidate_gate} />
      </div>
      <div className="mt-4 grid grid-cols-3 gap-2 text-center">
        <Metric label="Regressions" value={comparison.summary.regression_count} tone="bad" />
        <Metric label="Improvements" value={comparison.summary.improvement_count} tone="good" />
        <Metric label="Unchanged" value={comparison.summary.unchanged_count} />
      </div>
      {comparison.regressions.length > 0 && (
        <JsonPanel title="Regressions first" value={comparison.regressions} compact />
      )}
    </div>
  )
}

function AdvisorTab({ changeSets, review, loading, message, onSelect, onVerify, onRegress, onApply }: {
  changeSets: AdvisorChangeSet[]
  review: AdvisorReview | null
  loading: boolean
  message: string | null
  onSelect: (changeSetId: string) => void
  onVerify: () => void
  onRegress: () => void
  onApply: () => void
}) {
  if (changeSets.length === 0) {
    return <EmptyPanel title="No Advisor change sets" body="Typed staged patches from feedback and advisor drafts will appear here." />
  }
  return (
    <div className="grid gap-3 xl:grid-cols-[360px_minmax(0,1fr)]">
      <div className="space-y-2">
        {changeSets.map(changeSet => (
          <button
            key={changeSet.id}
            type="button"
            onClick={() => onSelect(changeSet.id)}
            className={cn(
              'w-full rounded-md border p-3 text-left transition-colors',
              review?.change_set.id === changeSet.id ? 'border-brand-orange/60 bg-brand-orange/10' : 'border-[#293037] bg-[#101316] hover:border-[#4a5660]',
            )}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="truncate text-sm font-semibold">{changeSet.target_ref}</span>
              <StatusPill status={changeSet.status} />
            </div>
            <div className="mt-2 text-xs text-[#9aa4ac]">{changeSet.base_version_ref}</div>
          </button>
        ))}
      </div>
      {review && (
        <div className="space-y-3">
          <div className="rounded-md border border-[#293037] bg-[#101316] p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="text-base font-semibold">Advisor staged patch</div>
                <div className="mt-1 text-xs text-[#9aa4ac]">{review.change_set.base_etag}</div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button variant="secondary" onClick={onVerify} disabled={loading}>
                  {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                  Verify
                </Button>
                <Button variant="secondary" onClick={onRegress} disabled={loading}>
                  <RefreshCw className="h-4 w-4" />
                  Regress
                </Button>
                <Button variant="brand-primary" onClick={onApply} disabled={loading || !review.gate_summary.ready_to_apply}>
                  <ShieldCheck className="h-4 w-4" />
                  Apply
                </Button>
              </div>
            </div>
            <div className="mt-4 grid gap-2 md:grid-cols-3">
              <Metric label="Verification" value={review.gate_summary.verification_gate} tone={review.gate_summary.verification_gate === 'passed' ? 'good' : 'bad'} />
              <Metric label="Regression" value={review.gate_summary.regression_gate} tone={review.gate_summary.regression_gate === 'passed' ? 'good' : 'bad'} />
              <Metric label="Ready" value={review.gate_summary.ready_to_apply ? 'yes' : 'no'} tone={review.gate_summary.ready_to_apply ? 'good' : 'bad'} />
            </div>
            {message && <div className="mt-3 text-sm text-[#a4adb5]">{message}</div>}
          </div>
          <div className="grid gap-3 xl:grid-cols-2">
            {review.advisor_suggestions.map(suggestion => (
              <div key={suggestion.id} className="rounded-md border border-[#293037] bg-[#101316] p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-sm font-semibold">{suggestion.suggestion_type}</h3>
                  <StatusPill status={suggestion.status} />
                </div>
                <JsonPanel title="Patch" value={suggestion.patch} compact />
                <div className="mt-3 flex flex-wrap gap-1">
                  {suggestion.affected_case_ids.map(caseId => <Badge key={caseId}>case {shortId(caseId)}</Badge>)}
                </div>
              </div>
            ))}
          </div>
          {review.promotion_decisions.length > 0 && <JsonPanel title="Promotion history" value={review.promotion_decisions} />}
        </div>
      )}
    </div>
  )
}

function FeedbackTab({ selectedVersion, cases }: { selectedVersion: EvaluationSuiteVersion | null; cases: EvaluationCase[] }) {
  const feedbackCases = cases.filter(item => String(item.provenance.source ?? '').includes('feedback') || item.tags.includes('feedback'))
  return (
    <div className="rounded-md border border-[#293037] bg-[#101316] p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-base font-semibold">Feedback review</h2>
        <Badge>{feedbackCases.length} promoted cases</Badge>
        {selectedVersion && <Badge>suite version {selectedVersion.version_num}</Badge>}
      </div>
      <div className="mt-4 grid gap-3 xl:grid-cols-2">
        {feedbackCases.length === 0 ? (
          <EmptyPanel title="No feedback cases" body="Legacy conversation feedback promoted to Evaluation cases will appear here." />
        ) : feedbackCases.map(item => (
          <div key={item.id} className="rounded-md border border-[#293037] bg-[#14181c] p-3">
            <div className="text-sm font-semibold">{item.title}</div>
            <div className="mt-2 text-sm leading-6 text-[#a4adb5]">{item.question}</div>
            <JsonPanel title="Feedback provenance" value={item.provenance} compact />
          </div>
        ))}
      </div>
    </div>
  )
}

function SettingsTab({ suite, version }: { suite: EvaluationSuite; version: EvaluationSuiteVersion | null }) {
  return (
    <div className="grid gap-3 xl:grid-cols-2">
      <JsonPanel title="Suite" value={suite} />
      <JsonPanel title="Gate policy" value={version?.gate_policy ?? {}} />
      <JsonPanel title="Manifest" value={version?.manifest ?? {}} />
    </div>
  )
}

function buildTargetSnapshot(changeSet: AdvisorChangeSet, suite: EvaluationSuite | null, version: EvaluationSuiteVersion | null): EvaluationTargetSnapshotInput {
  const targetKind = changeSet.target_ref.split(':')[0] || suite?.target_kinds[0] || 'semantic_model'
  const now = new Date().toISOString()
  return {
    contract_version: 'evaluation.target_snapshot.v1',
    target_kind: targetKind,
    target_ref: changeSet.target_ref,
    app: {
      git_sha: 'human-ui',
      image_digest: 'sha256:human-ui',
      migration_revision: 'add_evaluation_authoritative_model',
    },
    source: { snapshot_id: 'human-ui-source', snapshot_hash: `sha256:${changeSet.base_etag || changeSet.id}` },
    semantic_model: { version_id: changeSet.base_version_ref, version_hash: changeSet.base_etag || `sha256:${changeSet.id}` },
    dashboard: { version_id: version?.id ?? 'none', manifest_hash: version?.content_hash ?? 'sha256:none' },
    prompt: { registry_version: 'human-ui', tool_registry_hash: 'sha256:human-ui' },
    principal: { tenant_id: changeSet.tenant_id, actor_type: 'human', actor_id: changeSet.created_by, scopes: ['dashboard.query'] },
    dataset: { snapshot_id: 'human-ui-dataset', snapshot_hash: `sha256:${version?.content_hash || changeSet.id}` },
    feature_flags: { evaluation_governance: true },
    time_fixture: { now, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC' },
  }
}

function latestGate(runs: EvaluationRun[]): string {
  const latest = runs[0]
  if (!latest) return 'No run'
  return String(latest.summary.gate_decision ?? latest.status)
}

function TabButton({ active, onClick, icon, label }: { active: boolean; onClick: () => void; icon: ReactNode; label: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'inline-flex h-8 items-center gap-2 rounded px-3 text-xs font-medium transition-colors',
        active ? 'bg-brand-orange text-white' : 'text-[#a4adb5] hover:bg-[#20262b] hover:text-[#f3f5f5]',
      )}
    >
      {icon}
      {label}
    </button>
  )
}

function HeaderSignal({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-md border border-[#293037] bg-[#101316] p-3">
      <div className="flex items-center gap-2 text-[#818c95]">
        {icon}
        <span>{label}</span>
      </div>
      <div className="mt-2 truncate text-sm font-semibold text-[#f3f5f5]">{value}</div>
    </div>
  )
}

function Metric({ label, value, tone }: { label: string; value: string | number; tone?: 'good' | 'bad' }) {
  return (
    <div className={cn(
      'rounded-md border p-3',
      tone === 'good' ? 'border-emerald-500/30 bg-emerald-500/10' : tone === 'bad' ? 'border-red-500/30 bg-red-500/10' : 'border-[#293037] bg-[#101316]',
    )}>
      <div className="text-xs text-[#9aa4ac]">{label}</div>
      <div className="mt-1 truncate text-lg font-semibold">{String(value)}</div>
    </div>
  )
}

function JsonPanel({ title, value, compact = false }: { title: string; value: unknown; compact?: boolean }) {
  return (
    <div className={cn('mt-3 rounded-md border border-[#293037] bg-[#0e1114]', compact ? 'p-3' : 'p-4')}>
      <div className="mb-2 text-xs font-medium uppercase text-[#818c95]">{title}</div>
      <pre className={cn('overflow-auto whitespace-pre-wrap break-words text-xs leading-5 text-[#d6dde2] custom-scrollbar', compact ? 'max-h-48' : 'max-h-80')}>
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  )
}

function StatusPill({ status }: { status?: string | null }) {
  const value = status || 'unknown'
  return (
    <span className={cn('inline-flex h-6 items-center rounded-full border px-2 text-[11px] font-medium', statusTone[value] ?? 'border-[#3a444d] bg-[#20262b] text-[#cdd3d8]')}>
      {value}
    </span>
  )
}

function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'ready' | 'warning' }) {
  return (
    <span className={cn(
      'inline-flex h-6 items-center rounded border px-2 text-[11px] font-medium',
      tone === 'ready' ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200' : tone === 'warning' ? 'border-amber-500/30 bg-amber-500/10 text-amber-100' : 'border-[#303940] bg-[#171b1f] text-[#aeb7bf]',
    )}>
      {children}
    </span>
  )
}

function EmptyPanel({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-md border border-dashed border-[#303940] bg-[#101316] p-6">
      <div className="text-sm font-semibold text-[#f3f5f5]">{title}</div>
      <div className="mt-2 max-w-2xl text-sm leading-6 text-[#9aa4ac]">{body}</div>
    </div>
  )
}

function LoadingList() {
  return (
    <div className="space-y-2">
      {Array.from({ length: 5 }).map((_, index) => (
        <div key={index} className="h-24 animate-pulse rounded-md border border-[#293037] bg-[#171b1f]" />
      ))}
    </div>
  )
}

function shortId(value?: string | null): string {
  return value ? value.slice(0, 8) : 'none'
}

function formatDate(value?: string | null): string {
  if (!value) return 'No date'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return 'None'
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value)
  return JSON.stringify(value)
}
