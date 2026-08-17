import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  BarChart3,
  Braces,
  CheckCircle2,
  Database,
  ExternalLink,
  Filter,
  GitBranch,
  LayoutDashboard,
  LineChart,
  Loader2,
  Plus,
  RefreshCw,
  Save,
  Search,
  ShieldCheck,
  Table2,
  Trash2,
} from 'lucide-react'
import { Button } from '../../../components/ui/button'
import { Input } from '../../../components/ui/input'
import { DashboardApiError, DashboardService } from '../../../services/dashboard'
import type {
  DashboardAsset,
  DashboardAssetDetail,
  DashboardAuditEvent,
  DashboardDataView,
  DashboardFilter,
  DashboardLineageRef,
  DashboardManifest,
  DashboardRun,
  DashboardRunView,
  DashboardSemanticDiff,
  DashboardTile,
  DashboardVersion,
  DashboardVersionSummary,
} from '../../../types/dashboard'
import { cn } from '../../../lib/utils'

type WorkspaceTab = 'dashboard' | 'data' | 'lineage'
type EditorSelection = { kind: 'tile'; id: string } | { kind: 'filter'; id: string }
type JsonPatchOperation = { op: 'add' | 'replace' | 'remove'; path: string; value?: unknown }
type ConflictState = { currentEtag?: string; message: string }
type LastDraftPatch = { jsonPatch: JsonPatchOperation[]; changeSummary: string; successMessage: string }

const filterOperatorOptions = ['eq', 'ne', 'gt', 'lt', 'gte', 'lte', 'in', 'between', 'contains', 'like']

const statusTone: Record<string, string> = {
  published: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
  draft: 'border-sky-500/30 bg-sky-500/10 text-sky-200',
  in_review: 'border-sky-500/30 bg-sky-500/10 text-sky-200',
  legacy_unstructured: 'border-amber-500/30 bg-amber-500/10 text-amber-200',
  stale: 'border-amber-500/30 bg-amber-500/10 text-amber-200',
  blocked: 'border-red-500/30 bg-red-500/10 text-red-200',
  partial: 'border-amber-500/30 bg-amber-500/10 text-amber-200',
  success: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
  pending: 'border-[#3a444d] bg-[#20262b] text-[#cdd3d8]',
  running: 'border-sky-500/30 bg-sky-500/10 text-sky-200',
}

export default function DashboardWorkspacePage() {
  const { assetId } = useParams<{ assetId?: string }>()
  const navigate = useNavigate()
  const [assets, setAssets] = useState<DashboardAsset[]>([])
  const [selectedAsset, setSelectedAsset] = useState<DashboardAssetDetail | null>(null)
  const [selectedVersion, setSelectedVersion] = useState<DashboardVersion | null>(null)
  const [run, setRun] = useState<DashboardRun | null>(null)
  const [filters, setFilters] = useState<Record<string, unknown>>({})
  const [tab, setTab] = useState<WorkspaceTab>('dashboard')
  const [versionNum, setVersionNum] = useState<number | null>(null)
  const [query, setQuery] = useState('')
  const [loadingAssets, setLoadingAssets] = useState(true)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [loadingRun, setLoadingRun] = useState(false)
  const [loadingWorkflow, setLoadingWorkflow] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [validationMessage, setValidationMessage] = useState<string | null>(null)
  const [editingTitle, setEditingTitle] = useState('')
  const [editorSelection, setEditorSelection] = useState<EditorSelection | null>(null)
  const [conflict, setConflict] = useState<ConflictState | null>(null)
  const [lastDraftPatch, setLastDraftPatch] = useState<LastDraftPatch | null>(null)
  const [semanticDiff, setSemanticDiff] = useState<DashboardSemanticDiff | null>(null)
  const [auditEvents, setAuditEvents] = useState<DashboardAuditEvent[]>([])
  const [shareFolderId, setShareFolderId] = useState('')

  const loadAssets = useCallback(async () => {
    setLoadingAssets(true)
    setError(null)
    try {
      const response = await DashboardService.listAssets()
      setAssets(response.items)
      if (!assetId && response.items.length > 0) {
        navigate(`/dashboard-assets/${response.items[0].id}`, { replace: true })
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load Dashboard assets')
    } finally {
      setLoadingAssets(false)
    }
  }, [assetId, navigate])

  const loadAudit = useCallback(async (id: string) => {
    try {
      const response = await DashboardService.getAudit(id)
      setAuditEvents(response.items)
    } catch {
      setAuditEvents([])
    }
  }, [])

  const loadDetail = useCallback(async (id: string, requestedVersionNum?: number | null) => {
    setLoadingDetail(true)
    setError(null)
    setValidationMessage(null)
    try {
      const asset = await DashboardService.getAsset(id)
      setSelectedAsset(asset)
      setEditingTitle(asset.name)
      setConflict(null)
      const versionSummary = chooseVersion(asset.versions, requestedVersionNum)
      if (!versionSummary) {
        setSelectedVersion(null)
        setRun(null)
        setVersionNum(null)
        return
      }
      const version = await DashboardService.getVersion(id, versionSummary.version_num)
      setSelectedVersion(version)
      setVersionNum(version.version_num)
      setRun(null)
      setEditorSelection(previous => {
        if (!isStructuredDashboardManifest(version.manifest)) return null
        return normalizeEditorSelection(version.manifest, previous)
      })
      const diff = extractSemanticDiff(version)
      setSemanticDiff(diff ?? extractSemanticDiff(asset))
      void loadAudit(id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load Dashboard')
    } finally {
      setLoadingDetail(false)
    }
  }, [loadAudit])

  const executeRun = useCallback(async (asset: DashboardAssetDetail, version: DashboardVersion, nextFilters: Record<string, unknown>) => {
    if (!isStructuredDashboardManifest(version.manifest)) {
      setRun(null)
      return
    }
    setLoadingRun(true)
    try {
      const payload = {
        filters: nextFilters,
        data_view_ids: version.manifest.data_views.map(view => view.id),
        correlation_id: 'human-dashboard-workspace',
      }
      const response = version.status === 'published'
        ? await DashboardService.query(asset.id, payload)
        : await DashboardService.preview(asset.id, payload)
      setRun(response)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to execute Dashboard')
      setRun(null)
    } finally {
      setLoadingRun(false)
    }
  }, [])

  useEffect(() => {
    void loadAssets()
  }, [loadAssets])

  useEffect(() => {
    if (assetId) {
      setVersionNum(null)
      setSemanticDiff(null)
      setAuditEvents([])
      void loadDetail(assetId, null)
    }
  }, [assetId, loadDetail])

  useEffect(() => {
    if (selectedAsset && selectedVersion && isStructuredDashboardManifest(selectedVersion.manifest)) {
      void executeRun(selectedAsset, selectedVersion, filters)
    } else {
      setRun(null)
    }
  }, [selectedAsset, selectedVersion, executeRun, filters])

  const filteredAssets = useMemo(() => {
    const lower = query.trim().toLowerCase()
    if (!lower) return assets
    return assets.filter(asset => [asset.name, asset.slug, asset.description].some(value => value.toLowerCase().includes(lower)))
  }, [assets, query])

  const manifest = isStructuredDashboardManifest(selectedVersion?.manifest) ? selectedVersion.manifest : null
  const isLegacyAsset = selectedAsset?.lifecycle === 'legacy_unstructured' || selectedVersion?.migration_state === 'legacy_unstructured'
  const blockers = selectedVersion?.validation_result.blockers ?? manifest?.migration.blockers ?? []
  const semanticWarnings = semanticDiff?.warnings ?? []
  const semanticBlockers = semanticDiff?.blockers ?? []
  const pinnedSnapshotBlocked = Boolean(run?.mode === 'pinned_snapshot' && selectedVersion && !selectedVersion.is_published_immutable)
  const allBlockers = [
    ...blockers,
    ...semanticBlockers,
    ...(pinnedSnapshotBlocked ? ['Pinned snapshot run is blocked because this version has no immutable artifact.'] : []),
  ]
  const warnings = [...(selectedVersion?.validation_result.warnings ?? []), ...semanticWarnings, ...(run?.warnings ?? [])]
  const canPublish = Boolean(selectedAsset && manifest && selectedVersion?.status === 'draft' && allBlockers.length === 0)

  const handleFilterChange = (filter: DashboardFilter, value: string) => {
    setFilters(previous => {
      const next = { ...previous }
      if (!value) {
        delete next[filter.field]
      } else {
        next[filter.field] = coerceFilterValue(filter, value)
      }
      return next
    })
  }

  const validateDraft = async () => {
    if (!selectedAsset) return
    setLoadingWorkflow(true)
    setValidationMessage(null)
    try {
      const response = await DashboardService.validate(selectedAsset.id)
      const blockerCount = response.validation.blockers?.length ?? 0
      const warningCount = response.validation.warnings?.length ?? 0
      setValidationMessage(`${blockerCount} blockers, ${warningCount} warnings`)
      await loadDetail(selectedAsset.id, versionNum)
    } catch (err) {
      setValidationMessage(err instanceof Error ? err.message : 'Validation failed')
    } finally {
      setLoadingWorkflow(false)
    }
  }

  const applyDraftPatch = async (jsonPatch: JsonPatchOperation[], changeSummary: string, successMessage: string, baseEtag?: string) => {
    if (!selectedAsset || !selectedVersion || jsonPatch.length === 0) return false
    setLoadingWorkflow(true)
    setValidationMessage(null)
    setConflict(null)
    setLastDraftPatch({ jsonPatch, changeSummary, successMessage })
    try {
      await DashboardService.patchDraft(selectedAsset.id, {
        base_etag: baseEtag ?? selectedAsset.etag,
        json_patch: jsonPatch,
        change_summary: changeSummary,
      })
      await loadDetail(selectedAsset.id, null)
      await loadAssets()
      setValidationMessage(successMessage)
      setLastDraftPatch(null)
      return true
    } catch (err) {
      const conflictState = getConflictState(err)
      if (conflictState) {
        setConflict(conflictState)
        setValidationMessage('Draft conflict detected')
      } else {
        setValidationMessage(err instanceof Error ? err.message : 'Draft update failed')
      }
      return false
    } finally {
      setLoadingWorkflow(false)
    }
  }

  const refreshAfterConflict = async () => {
    if (!selectedAsset) return
    await loadDetail(selectedAsset.id, null)
    await loadAssets()
    setValidationMessage('Draft refreshed after conflict')
  }

  const retryLastDraftPatch = async () => {
    if (!selectedAsset || !lastDraftPatch) return
    const latest = await DashboardService.getAsset(selectedAsset.id)
    await applyDraftPatch(lastDraftPatch.jsonPatch, lastDraftPatch.changeSummary, lastDraftPatch.successMessage, latest.etag)
  }

  const patchTitle = async () => {
    if (!manifest || !editingTitle.trim()) return
    await applyDraftPatch(
      [{ op: 'replace', path: '/title', value: editingTitle.trim() }],
      'Update Dashboard title from workspace',
      'Draft title updated',
    )
  }

  const createReloadDraft = async () => {
    if (!selectedAsset || !selectedVersion || !manifest) return
    setLoadingWorkflow(true)
    setValidationMessage(null)
    try {
      const nextModelVersions = Object.fromEntries(
        manifest.semantic_bindings.map(binding => [binding.id, binding.model_version]),
      )
      const response = await DashboardService.reload(selectedAsset.id, {
        base_etag: selectedAsset.etag,
        semantic_model_versions: nextModelVersions,
        source_snapshot_ids: selectedVersion.pinned_source_snapshots,
        change_summary: 'Reload Dashboard from workspace review',
      })
      setSemanticDiff(response.semantic_diff)
      await loadDetail(selectedAsset.id, response.draft.version_num)
      await loadAssets()
      setValidationMessage('Reload draft ready for review')
    } catch (err) {
      setValidationMessage(err instanceof Error ? err.message : 'Reload draft failed')
    } finally {
      setLoadingWorkflow(false)
    }
  }

  const publishDraft = async () => {
    if (!selectedAsset || !selectedVersion || !canPublish) return
    setLoadingWorkflow(true)
    setValidationMessage(null)
    try {
      const version = await DashboardService.publish(selectedAsset.id, {
        base_etag: selectedAsset.etag,
        change_summary: 'Publish reviewed Dashboard from workspace',
      })
      await loadDetail(selectedAsset.id, version.version_num)
      await loadAssets()
      setValidationMessage(`Published v${version.version_num}`)
    } catch (err) {
      setValidationMessage(err instanceof Error ? err.message : 'Publish failed')
    } finally {
      setLoadingWorkflow(false)
    }
  }

  const selectVersion = async (nextVersionNum: number) => {
    if (!selectedAsset) return
    setVersionNum(nextVersionNum)
    await loadDetail(selectedAsset.id, nextVersionNum)
  }

  const executeSelectedVersion = async () => {
    if (!selectedAsset || !selectedVersion || !manifest) return
    await executeRun(selectedAsset, selectedVersion, filters)
    if (selectedVersion.status !== 'published') {
      setValidationMessage('Preview executed against draft version')
    }
  }

  const exportHtml = async () => {
    if (!selectedAsset || !selectedVersion || !manifest) return
    setLoadingWorkflow(true)
    setValidationMessage(null)
    try {
      const response = await DashboardService.exportHtml(selectedAsset.id, selectedVersion.version_num)
      const url = URL.createObjectURL(response.blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = response.filename
      anchor.click()
      URL.revokeObjectURL(url)
      await loadAudit(selectedAsset.id)
      setValidationMessage('Exported structured HTML')
    } catch (err) {
      setValidationMessage(err instanceof Error ? err.message : 'Export failed')
    } finally {
      setLoadingWorkflow(false)
    }
  }

  const shareToFolder = async () => {
    if (!selectedAsset || !selectedVersion || !shareFolderId.trim()) return
    setLoadingWorkflow(true)
    setValidationMessage(null)
    try {
      await DashboardService.sharePublishedVersionToFolder(shareFolderId.trim(), selectedVersion.id)
      setShareFolderId('')
      setValidationMessage('Published version shared to folder')
    } catch (err) {
      setValidationMessage(err instanceof Error ? err.message : 'Folder share failed')
    } finally {
      setLoadingWorkflow(false)
    }
  }

  return (
    <div data-dashboard-workspace="true" className="flex min-h-full bg-[#0d0f11] text-[#f3f5f5]">
      <aside className="hidden w-[360px] shrink-0 border-r border-[#293037] bg-[#121518] lg:flex lg:flex-col">
        <div className="border-b border-[#293037] p-4">
          <div className="flex items-center gap-2">
            <LayoutDashboard className="h-5 w-5 text-brand-orange" />
            <h1 className="text-lg font-semibold">Dashboards</h1>
          </div>
          <div className="relative mt-3">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-[#7f8a93]" />
            <Input
              value={query}
              onChange={event => setQuery(event.target.value)}
              placeholder="Search governed assets"
              className="h-9 border-[#303940] bg-[#0e1114] pl-9 text-sm text-[#eef2f3]"
              aria-label="Search Dashboards"
            />
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-3 custom-scrollbar">
          {loadingAssets && <LoadingList />}
          {!loadingAssets && filteredAssets.length === 0 && <EmptyPanel title="No governed Dashboards" body="Structured Dashboard assets will appear here after draft creation or migration review." />}
          {!loadingAssets && filteredAssets.map(asset => (
            <Link
              key={asset.id}
              to={`/dashboard-assets/${asset.id}`}
              className={cn(
                'mb-2 block rounded-md border p-3 transition-colors',
                asset.id === assetId ? 'border-brand-orange/60 bg-brand-orange/10' : 'border-[#293037] bg-[#171b1f] hover:border-[#4a5660]',
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-[#f3f5f5]">{asset.name}</div>
                  <div className="mt-1 truncate text-xs text-[#818c95]">{asset.slug}</div>
                </div>
                <StatusPill status={asset.lifecycle} />
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] text-[#9aa4ac]">
                <span>Draft {shortId(asset.current_draft_version_id)}</span>
                <span>Published {shortId(asset.published_version_id)}</span>
              </div>
              {asset.lifecycle === 'legacy_unstructured' && (
                <div className="mt-2 rounded border border-amber-500/20 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-100">
                  Needs structured review
                </div>
              )}
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

          {conflict && (
            <ConflictBanner
              conflict={conflict}
              loading={loadingWorkflow}
              onRefresh={() => void refreshAfterConflict()}
              onRetry={() => void retryLastDraftPatch()}
            />
          )}

          <section className="lg:hidden">
            <div className="rounded-md border border-[#293037] bg-[#14181c] p-3">
              <div className="flex items-center gap-2">
                <LayoutDashboard className="h-4 w-4 text-brand-orange" />
                <h1 className="text-sm font-semibold">Dashboards</h1>
              </div>
              <div className="relative mt-3">
                <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-[#7f8a93]" />
                <Input
                  value={query}
                  onChange={event => setQuery(event.target.value)}
                  placeholder="Search governed assets"
                  className="h-9 border-[#303940] bg-[#0e1114] pl-9 text-sm text-[#eef2f3]"
                  aria-label="Search Dashboards"
                />
              </div>
              <div className="mt-3 flex gap-2 overflow-x-auto custom-scrollbar">
                {filteredAssets.map(asset => (
                  <Link
                    key={asset.id}
                    to={`/dashboard-assets/${asset.id}`}
                    className={cn(
                      'min-w-[240px] rounded-md border p-3',
                      asset.id === assetId ? 'border-brand-orange/60 bg-brand-orange/10' : 'border-[#293037] bg-[#101316]',
                    )}
                  >
                    <div className="truncate text-sm font-semibold">{asset.name}</div>
                    <div className="mt-1 truncate text-xs text-[#818c95]">{asset.slug}</div>
                    <div className="mt-2 flex flex-wrap gap-1">
                      <StatusPill status={asset.lifecycle} />
                      <Badge>{formatInventoryFreshness(asset)}</Badge>
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          </section>

          <InventoryEvidenceTable assets={filteredAssets} selectedAssetId={assetId} />

          {!selectedAsset && !loadingDetail && (
            <EmptyPanel title="Open a governed Dashboard" body="Select a structured Dashboard asset from the inventory to inspect manifest-bound tiles, data, freshness, evidence, and lineage." />
          )}

          {selectedAsset && (
            <>
              <header className="grid gap-3 border-b border-[#293037] pb-4 xl:grid-cols-[minmax(0,1fr)_420px]">
                <section className="rounded-md border border-[#293037] bg-[#14181c] p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <h1 className="min-w-0 truncate text-xl font-semibold">{manifest?.title || selectedAsset.name}</h1>
                    <StatusPill status={selectedAsset.lifecycle} />
                    <StatusPill status={selectedVersion?.status} />
                    {selectedVersion?.is_published_immutable && <Badge tone="ready">Immutable</Badge>}
                  </div>
                  <p className="mt-2 max-w-4xl text-sm leading-6 text-[#a4adb5]">{manifest?.description || selectedAsset.description || 'No description'}</p>
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <select
                      value={versionNum ?? ''}
                      onChange={event => void selectVersion(Number(event.target.value))}
                      className="h-8 rounded border border-[#303940] bg-[#0e1114] px-2 text-xs text-[#eef2f3]"
                      aria-label="Dashboard version"
                    >
                      {selectedAsset.versions.map(version => (
                        <option key={version.id} value={version.version_num}>
                          v{version.version_num} {version.status}
                        </option>
                      ))}
                    </select>
                    {run?.preview && <Badge tone="warning">Preview run</Badge>}
                  </div>
                  <div className="mt-4 grid gap-2 text-xs text-[#9aa4ac] md:grid-cols-4">
                    <HeaderSignal icon={<ShieldCheck className="h-4 w-4" />} label="Version" value={selectedVersion ? `v${selectedVersion.version_num} ${selectedVersion.status}` : 'None'} />
                    <HeaderSignal icon={<GitBranch className="h-4 w-4" />} label="Filter Digest" value={run?.filter_digest ? shortHash(run.filter_digest) : 'Not run'} />
                    <HeaderSignal icon={<Database className="h-4 w-4" />} label="Freshness" value={run?.overall_freshness ?? formatValue(selectedAsset.health_summary.freshness ?? 'unknown')} />
                    <HeaderSignal icon={<Braces className="h-4 w-4" />} label="Manifest" value={selectedVersion?.content_hash ? shortHash(selectedVersion.content_hash) : 'draft'} />
                  </div>
                </section>

                <section className="rounded-md border border-[#293037] bg-[#14181c] p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-xs font-medium uppercase text-[#818c95]">Review state</div>
                      <div className="mt-1 text-sm text-[#d6dde2]">{allBlockers.length} blockers, {warnings.length} warnings</div>
                    </div>
                    <Button variant="secondary" onClick={() => void executeSelectedVersion()} disabled={loadingRun || !manifest}>
                      {loadingRun ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                      {selectedVersion?.status === 'published' ? 'Run' : 'Preview'}
                    </Button>
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <Button variant="secondary" onClick={() => void validateDraft()} disabled={loadingWorkflow || !manifest}>Validate</Button>
                    <Button variant="secondary" onClick={() => void patchTitle()} disabled={loadingWorkflow || !manifest || !selectedVersion || selectedVersion.status === 'published'}>Patch Title</Button>
                    <Button variant="secondary" onClick={() => void createReloadDraft()} disabled={loadingWorkflow || !manifest || !selectedAsset.published_version_id}>Reload Draft</Button>
                    <Button variant="secondary" onClick={() => void publishDraft()} disabled={loadingWorkflow || !canPublish}>Publish</Button>
                    <Button variant="secondary" onClick={() => void exportHtml()} disabled={loadingWorkflow || !manifest || selectedVersion?.status !== 'published'}>Export</Button>
                  </div>
                  <div className="mt-3 flex gap-2">
                    <Input
                      value={shareFolderId}
                      onChange={event => setShareFolderId(event.target.value)}
                      className="h-9 border-[#303940] bg-[#0e1114] text-sm text-[#eef2f3]"
                      placeholder="Folder ID"
                      aria-label="Folder ID"
                    />
                    <Button variant="secondary" onClick={() => void shareToFolder()} disabled={loadingWorkflow || !manifest || selectedVersion?.status !== 'published' || !shareFolderId.trim()}>Share</Button>
                  </div>
                  <Input
                    value={editingTitle}
                    onChange={event => setEditingTitle(event.target.value)}
                    className="mt-3 h-9 border-[#303940] bg-[#0e1114] text-sm text-[#eef2f3]"
                    aria-label="Draft title"
                  />
                  {validationMessage && <div className="mt-2 text-xs text-[#a4adb5]">{validationMessage}</div>}
                </section>
              </header>

              <section className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_360px]">
                <SemanticDiffPanel diff={semanticDiff} blockers={allBlockers} warnings={warnings} />
                <AuditTrail events={auditEvents} />
              </section>

              {manifest && (
                <ManifestEditor
                  manifest={manifest}
                  selection={editorSelection}
                  loading={loadingWorkflow}
                  disabled={selectedVersion?.status === 'published'}
                  onSelect={setEditorSelection}
                  onPatch={(patch, summary, message) => void applyDraftPatch(patch, summary, message)}
                />
              )}

              {pinnedSnapshotBlocked && (
                <section className="rounded-md border border-red-500/30 bg-red-500/10 p-4 text-red-100" role="alert">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                    <div>
                      <h2 className="text-sm font-semibold">Pinned snapshot blocked</h2>
                      <p className="mt-1 text-sm leading-6 text-red-100/80">
                        The current run requested pinned_snapshot mode, but this Dashboard version is not marked immutable. Publish an immutable version before sharing or replaying the pinned artifact.
                      </p>
                    </div>
                  </div>
                </section>
              )}

              {isLegacyAsset && (
                <LegacyMigrationReviewPanel
                  asset={selectedAsset}
                  version={selectedVersion}
                  manifest={manifest}
                  run={run}
                  blockers={allBlockers}
                  warnings={warnings}
                  loading={loadingWorkflow}
                  onGenerateDraft={() => void createReloadDraft()}
                  onStartReview={() => void validateDraft()}
                  onRefresh={() => void loadDetail(selectedAsset.id, versionNum)}
                />
              )}

              {manifest && (
                <section className="rounded-md border border-[#293037] bg-[#14181c]">
                  <div className="flex flex-col gap-3 border-b border-[#293037] p-3 xl:flex-row xl:items-center xl:justify-between">
                    <FilterBar filters={manifest.filters} values={filters} onChange={handleFilterChange} />
                    <div className="flex shrink-0 gap-1 rounded-md border border-[#303940] bg-[#0e1114] p-1">
                      <TabButton active={tab === 'dashboard'} onClick={() => setTab('dashboard')} icon={<LayoutDashboard className="h-4 w-4" />} label="Dashboard" />
                      <TabButton active={tab === 'data'} onClick={() => setTab('data')} icon={<Table2 className="h-4 w-4" />} label="Data" />
                      <TabButton active={tab === 'lineage'} onClick={() => setTab('lineage')} icon={<GitBranch className="h-4 w-4" />} label="Lineage" />
                    </div>
                  </div>

                  <div className="p-3">
                    {tab === 'dashboard' && <DashboardCanvas manifest={manifest} run={run} loadingRun={loadingRun} />}
                    {tab === 'data' && <DataTab manifest={manifest} run={run} />}
                    {tab === 'lineage' && <LineageTab manifest={manifest} run={run} version={selectedVersion} />}
                  </div>
                </section>
              )}
            </>
          )}
        </div>
      </main>
    </div>
  )
}

function chooseVersion(versions: DashboardVersionSummary[], requestedVersionNum?: number | null): DashboardVersionSummary | null {
  if (requestedVersionNum) {
    const requested = versions.find(version => version.version_num === requestedVersionNum)
    if (requested) return requested
  }
  return versions.find(version => version.status === 'published') ?? versions[0] ?? null
}

function extractSemanticDiff(source: DashboardVersion | DashboardAssetDetail | null): DashboardSemanticDiff | null {
  if (!source) return null
  if ('validation_result' in source) {
    const diff = source.validation_result.semantic_diff
    return isRecord(diff) ? diff as DashboardSemanticDiff : null
  }
  const diff = source.health_summary.semantic_diff
  return isRecord(diff) ? diff as DashboardSemanticDiff : null
}

function isStructuredDashboardManifest(value: unknown): value is DashboardManifest {
  if (!isRecord(value)) return false
  if (value.schema_version !== 'dashboard.manifest.v1') return false
  return Array.isArray(value.semantic_bindings)
    && Array.isArray(value.data_views)
    && Array.isArray(value.filters)
    && isRecord(value.layout)
    && Array.isArray(value.layout.sections)
    && Array.isArray(value.tiles)
    && Array.isArray(value.actions)
    && isRecord(value.freshness_policy)
    && isRecord(value.access_policy)
    && isRecord(value.provenance)
    && isRecord(value.migration)
}

function normalizeEditorSelection(manifest: DashboardManifest, selection: EditorSelection | null): EditorSelection | null {
  if (selection?.kind === 'tile' && manifest.tiles.some(tile => tile.id === selection.id)) return selection
  if (selection?.kind === 'filter' && manifest.filters.some(filter => filter.id === selection.id)) return selection
  const firstTile = manifest.tiles[0]
  if (firstTile) return { kind: 'tile', id: firstTile.id }
  const firstFilter = manifest.filters[0]
  if (firstFilter) return { kind: 'filter', id: firstFilter.id }
  return null
}

function uniqueManifestId(prefix: string, existingIds: string[]): string {
  const existing = new Set(existingIds)
  for (let index = 1; index < 1000; index += 1) {
    const candidate = `${prefix}-${index}`
    if (!existing.has(candidate)) return candidate
  }
  return `${prefix}-${Date.now()}`
}

function getConflictState(error: unknown): ConflictState | null {
  if (!(error instanceof DashboardApiError) || error.status !== 409) return null
  const data = isRecord(error.data) ? error.data : {}
  const currentEtag = typeof data.current_etag === 'string' ? data.current_etag : undefined
  return {
    currentEtag,
    message: 'The draft changed on the server. Refresh the latest draft before retrying this JSON Patch.',
  }
}

function InventoryEvidenceTable({ assets, selectedAssetId }: { assets: DashboardAsset[]; selectedAssetId?: string }) {
  if (assets.length === 0) return null
  return (
    <section className="rounded-md border border-[#293037] bg-[#14181c]">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#293037] px-3 py-2">
        <div>
          <h2 className="text-sm font-semibold">Inventory</h2>
          <p className="mt-0.5 text-xs text-[#818c95]">Governed asset readiness, versions, model pins, freshness, owner, and update state.</p>
        </div>
        <Badge>{assets.length} assets</Badge>
      </div>
      <div className="overflow-x-auto custom-scrollbar">
        <table className="min-w-[980px] text-left text-xs">
          <thead className="bg-[#101316] text-[#9aa4ac]">
            <tr>
              <th className="px-3 py-2 font-medium">Asset</th>
              <th className="px-3 py-2 font-medium">Owner</th>
              <th className="px-3 py-2 font-medium">Published / Draft Version</th>
              <th className="px-3 py-2 font-medium">Model / Version</th>
              <th className="px-3 py-2 font-medium">Freshness</th>
              <th className="px-3 py-2 font-medium">Readiness / Warnings</th>
              <th className="px-3 py-2 font-medium">Last Update</th>
            </tr>
          </thead>
          <tbody>
            {assets.map(asset => (
              <tr key={asset.id} className={cn('border-t border-[#242b31]', asset.id === selectedAssetId ? 'bg-brand-orange/5' : '')}>
                <td className="max-w-[220px] px-3 py-2">
                  <Link to={`/dashboard-assets/${asset.id}`} className="font-medium text-[#f3f5f5] hover:text-brand-orange">
                    {asset.name}
                  </Link>
                  <div className="truncate text-[#818c95]">{asset.slug}</div>
                </td>
                <td className="px-3 py-2 text-[#d6dde2]">{shortId(asset.owner_id)}</td>
                <td className="px-3 py-2 text-[#d6dde2]">
                  <div>Published {shortId(asset.published_version_id)}</div>
                  <div className="text-[#818c95]">Draft {shortId(asset.current_draft_version_id)}</div>
                </td>
                <td className="px-3 py-2 text-[#d6dde2]">{formatInventoryModel(asset)}</td>
                <td className="px-3 py-2 text-[#d6dde2]">{formatInventoryFreshness(asset)}</td>
                <td className="px-3 py-2">
                  <div className="flex flex-wrap gap-1">
                    <StatusPill status={asset.lifecycle} />
                    <Badge tone={asset.lifecycle === 'legacy_unstructured' ? 'warning' : 'ready'}>{formatInventoryWarnings(asset)}</Badge>
                  </div>
                </td>
                <td className="px-3 py-2 text-[#d6dde2]">{asset.updated_at ? formatDate(asset.updated_at) : 'No timestamp'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function ConflictBanner({
  conflict,
  loading,
  onRefresh,
  onRetry,
}: {
  conflict: ConflictState
  loading: boolean
  onRefresh: () => void
  onRetry: () => void
}) {
  return (
    <section className="rounded-md border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-100" role="alert">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2 font-semibold">
            <AlertTriangle className="h-4 w-4" />
            <span>Draft conflict (409)</span>
          </div>
          <p className="mt-1 break-words text-xs text-red-100/80">
            {conflict.message}
            {conflict.currentEtag ? ` Current ETag ${conflict.currentEtag}.` : ''}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <Button variant="secondary" size="sm" onClick={onRefresh} disabled={loading}>
            <RefreshCw className="h-4 w-4" />
            Refresh Draft
          </Button>
          <Button variant="secondary" size="sm" onClick={onRetry} disabled={loading}>
            <Save className="h-4 w-4" />
            Retry Patch
          </Button>
        </div>
      </div>
    </section>
  )
}

function ManifestEditor({
  manifest,
  selection,
  loading,
  disabled,
  onSelect,
  onPatch,
}: {
  manifest: DashboardManifest
  selection: EditorSelection | null
  loading: boolean
  disabled: boolean
  onSelect: (selection: EditorSelection) => void
  onPatch: (patch: JsonPatchOperation[], summary: string, message: string) => void
}) {
  const activeSelection = normalizeEditorSelection(manifest, selection)
  const selectedTile = activeSelection?.kind === 'tile' ? manifest.tiles.find(tile => tile.id === activeSelection.id) ?? null : null
  const selectedFilter = activeSelection?.kind === 'filter' ? manifest.filters.find(filter => filter.id === activeSelection.id) ?? null : null

  const moveTile = (tileId: string, direction: -1 | 1) => {
    const sectionIndex = manifest.layout.sections.findIndex(section => section.tile_ids.includes(tileId))
    if (sectionIndex < 0) return
    const section = manifest.layout.sections[sectionIndex]
    const currentIndex = section.tile_ids.indexOf(tileId)
    const nextIndex = currentIndex + direction
    if (nextIndex < 0 || nextIndex >= section.tile_ids.length) return
    const tileIds = [...section.tile_ids]
    const [tile] = tileIds.splice(currentIndex, 1)
    tileIds.splice(nextIndex, 0, tile)
    onPatch(
      [{ op: 'replace', path: `/layout/sections/${sectionIndex}/tile_ids`, value: tileIds }],
      'Reorder Dashboard tile layout from workspace',
      'Tile order updated',
    )
  }

  const addFilter = () => {
    const firstViewId = manifest.data_views[0]?.id
    const id = uniqueManifestId('filter', manifest.filters.map(filter => filter.id))
    const filter: DashboardFilter = {
      id,
      label: 'New Filter',
      source: 'saved_query_contract',
      field: manifest.filters[0]?.field ?? 'region',
      filter_type: 'enum',
      operators: ['eq'],
      affected_data_view_ids: firstViewId ? [firstViewId] : [],
      default_value: '',
      required: false,
      domain: manifest.filters[0]?.domain ?? [],
      timezone: null,
    }
    onPatch(
      [{ op: 'add', path: '/filters/-', value: filter }],
      'Add Dashboard filter from workspace',
      'Filter added',
    )
    onSelect({ kind: 'filter', id })
  }

  return (
    <section className="rounded-md border border-[#293037] bg-[#14181c]" aria-label="Manifest editor">
      <div className="flex flex-col gap-3 border-b border-[#293037] p-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="text-sm font-semibold">Manifest editor</h2>
          <p className="mt-1 text-xs text-[#818c95]">Tile, filter, and layout edits use JSON Patch with the current draft ETag.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge>{disabled ? 'Published view' : 'Draft editable'}</Badge>
          <Badge>json_patch</Badge>
          <Badge>base_etag</Badge>
        </div>
      </div>
      <div className="grid min-w-0 gap-0 xl:grid-cols-[260px_minmax(0,1fr)_360px]">
        <ManifestOutline
          manifest={manifest}
          selection={activeSelection}
          disabled={disabled || loading}
          onSelect={onSelect}
          onMoveTile={moveTile}
          onAddFilter={addFilter}
        />
        <div className="min-w-0 border-t border-[#293037] p-3 xl:border-l xl:border-t-0">
          <DashboardCanvas manifest={manifest} run={null} loadingRun={false} selectedTileId={selectedTile?.id ?? null} onSelectTile={tileId => onSelect({ kind: 'tile', id: tileId })} />
        </div>
        <ManifestInspector
          manifest={manifest}
          selection={activeSelection}
          tile={selectedTile}
          filter={selectedFilter}
          loading={loading}
          disabled={disabled}
          onPatch={onPatch}
        />
      </div>
    </section>
  )
}

function ManifestOutline({
  manifest,
  selection,
  disabled,
  onSelect,
  onMoveTile,
  onAddFilter,
}: {
  manifest: DashboardManifest
  selection: EditorSelection | null
  disabled: boolean
  onSelect: (selection: EditorSelection) => void
  onMoveTile: (tileId: string, direction: -1 | 1) => void
  onAddFilter: () => void
}) {
  const orderedTileIds = manifest.layout.sections.flatMap(section => section.tile_ids)
  const tileOrder = new Map(orderedTileIds.map((tileId, index) => [tileId, index]))
  return (
    <aside className="min-w-0 p-3" aria-label="Manifest outline">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-xs font-medium uppercase text-[#818c95]">Outline</h3>
        <Button variant="secondary" size="sm" onClick={onAddFilter} disabled={disabled}>
          <Plus className="h-4 w-4" />
          Filter
        </Button>
      </div>
      <div className="mt-3 space-y-4">
        <div>
          <div className="mb-2 flex items-center gap-2 text-xs text-[#9aa4ac]">
            <LayoutDashboard className="h-4 w-4 text-brand-orange" />
            Tiles
          </div>
          <div className="space-y-2">
            {manifest.tiles.map(tile => {
              const index = tileOrder.get(tile.id) ?? -1
              const active = selection?.kind === 'tile' && selection.id === tile.id
              return (
                <div key={tile.id} className={cn('rounded border p-2', active ? 'border-brand-orange/60 bg-brand-orange/10' : 'border-[#303940] bg-[#101316]')}>
                  <button
                    type="button"
                    onClick={() => onSelect({ kind: 'tile', id: tile.id })}
                    className="block w-full min-w-0 text-left"
                    aria-label={`Select tile ${tile.title}`}
                  >
                    <div className="truncate text-sm text-[#f3f5f5]">{tile.title}</div>
                    <div className="mt-1 truncate text-xs text-[#818c95]">{tile.tile_type} · {tile.id}</div>
                  </button>
                  <div className="mt-2 flex gap-1">
                    <IconButton label={`Move ${tile.title} up`} disabled={disabled || index <= 0} onClick={() => onMoveTile(tile.id, -1)}>
                      <ArrowUp className="h-4 w-4" />
                    </IconButton>
                    <IconButton label={`Move ${tile.title} down`} disabled={disabled || index < 0 || index >= orderedTileIds.length - 1} onClick={() => onMoveTile(tile.id, 1)}>
                      <ArrowDown className="h-4 w-4" />
                    </IconButton>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
        <div>
          <div className="mb-2 flex items-center gap-2 text-xs text-[#9aa4ac]">
            <Filter className="h-4 w-4 text-brand-orange" />
            Filters
          </div>
          <div className="space-y-2">
            {manifest.filters.map(filter => {
              const active = selection?.kind === 'filter' && selection.id === filter.id
              return (
                <button
                  key={filter.id}
                  type="button"
                  onClick={() => onSelect({ kind: 'filter', id: filter.id })}
                  className={cn(
                    'block w-full min-w-0 rounded border p-2 text-left',
                    active ? 'border-brand-orange/60 bg-brand-orange/10' : 'border-[#303940] bg-[#101316]',
                  )}
                >
                  <div className="truncate text-sm text-[#f3f5f5]">{filter.label}</div>
                  <div className="mt-1 truncate text-xs text-[#818c95]">{filter.field} · {filter.operators.join(', ')}</div>
                </button>
              )
            })}
          </div>
        </div>
      </div>
    </aside>
  )
}

function ManifestInspector({
  manifest,
  selection,
  tile,
  filter,
  loading,
  disabled,
  onPatch,
}: {
  manifest: DashboardManifest
  selection: EditorSelection | null
  tile: DashboardTile | null
  filter: DashboardFilter | null
  loading: boolean
  disabled: boolean
  onPatch: (patch: JsonPatchOperation[], summary: string, message: string) => void
}) {
  return (
    <aside className="min-w-0 border-t border-[#293037] p-3 xl:border-l xl:border-t-0" aria-label="Manifest inspector">
      <h3 className="text-xs font-medium uppercase text-[#818c95]">Inspector</h3>
      {!selection && <div className="mt-3 text-sm text-[#818c95]">Select a tile or filter.</div>}
      {tile && (
        <TileInspector
          manifest={manifest}
          tile={tile}
          loading={loading}
          disabled={disabled}
          onPatch={onPatch}
        />
      )}
      {filter && (
        <FilterInspector
          manifest={manifest}
          filter={filter}
          loading={loading}
          disabled={disabled}
          onPatch={onPatch}
        />
      )}
    </aside>
  )
}

function TileInspector({
  manifest,
  tile,
  loading,
  disabled,
  onPatch,
}: {
  manifest: DashboardManifest
  tile: DashboardTile
  loading: boolean
  disabled: boolean
  onPatch: (patch: JsonPatchOperation[], summary: string, message: string) => void
}) {
  const [title, setTitle] = useState(tile.title)
  const [question, setQuestion] = useState(tile.business_question)
  const [encodingText, setEncodingText] = useState(JSON.stringify(tile.encoding ?? {}, null, 2))
  const [encodingError, setEncodingError] = useState<string | null>(null)

  useEffect(() => {
    setTitle(tile.title)
    setQuestion(tile.business_question)
    setEncodingText(JSON.stringify(tile.encoding ?? {}, null, 2))
    setEncodingError(null)
  }, [tile])

  const tileIndex = manifest.tiles.findIndex(item => item.id === tile.id)
  const save = () => {
    if (tileIndex < 0 || !title.trim() || !question.trim()) return
    let encoding: Record<string, unknown>
    try {
      const parsed = JSON.parse(encodingText || '{}') as unknown
      if (!isRecord(parsed)) throw new Error('Encoding must be a JSON object')
      encoding = parsed
      setEncodingError(null)
    } catch (err) {
      setEncodingError(err instanceof Error ? err.message : 'Encoding must be valid JSON')
      return
    }
    const patch: JsonPatchOperation[] = [
      { op: 'replace', path: `/tiles/${tileIndex}/title`, value: title.trim() },
      { op: 'replace', path: `/tiles/${tileIndex}/business_question`, value: question.trim() },
      { op: 'replace', path: `/tiles/${tileIndex}/encoding`, value: encoding },
    ]
    onPatch(patch, `Edit Dashboard tile ${tile.id} from workspace`, 'Tile inspector saved')
  }

  return (
    <div className="mt-3 space-y-3">
      <InspectorField label="Tile title">
        <Input value={title} onChange={event => setTitle(event.target.value)} disabled={disabled || loading} aria-label="Tile title" className="border-[#303940] bg-[#0e1114] text-sm text-[#eef2f3]" />
      </InspectorField>
      <InspectorField label="Business question">
        <textarea
          value={question}
          onChange={event => setQuestion(event.target.value)}
          disabled={disabled || loading}
          aria-label="Tile business question"
          className="min-h-[84px] w-full resize-y rounded-md border border-[#303940] bg-[#0e1114] px-3 py-2 text-sm text-[#eef2f3] outline-none focus:ring-1 focus:ring-ring disabled:opacity-50"
        />
      </InspectorField>
      <InspectorField label="Encoding JSON">
        <textarea
          value={encodingText}
          onChange={event => setEncodingText(event.target.value)}
          disabled={disabled || loading}
          aria-label="Tile encoding JSON"
          className="min-h-[112px] w-full resize-y rounded-md border border-[#303940] bg-[#0e1114] px-3 py-2 font-mono text-xs text-[#eef2f3] outline-none focus:ring-1 focus:ring-ring disabled:opacity-50"
        />
        {encodingError && <div className="mt-1 text-xs text-red-100">{encodingError}</div>}
      </InspectorField>
      <Button variant="secondary" onClick={save} disabled={disabled || loading || !title.trim() || !question.trim()}>
        <Save className="h-4 w-4" />
        Save Tile
      </Button>
    </div>
  )
}

function FilterInspector({
  manifest,
  filter,
  loading,
  disabled,
  onPatch,
}: {
  manifest: DashboardManifest
  filter: DashboardFilter
  loading: boolean
  disabled: boolean
  onPatch: (patch: JsonPatchOperation[], summary: string, message: string) => void
}) {
  const [label, setLabel] = useState(filter.label)
  const [operator, setOperator] = useState(filter.operators[0] ?? 'eq')
  const [defaultValue, setDefaultValue] = useState(filter.default_value === null || filter.default_value === undefined ? '' : String(filter.default_value))

  useEffect(() => {
    setLabel(filter.label)
    setOperator(filter.operators[0] ?? 'eq')
    setDefaultValue(filter.default_value === null || filter.default_value === undefined ? '' : String(filter.default_value))
  }, [filter])

  const filterIndex = manifest.filters.findIndex(item => item.id === filter.id)
  const save = () => {
    if (filterIndex < 0 || !label.trim()) return
    onPatch(
      [
        { op: 'replace', path: `/filters/${filterIndex}/label`, value: label.trim() },
        { op: 'replace', path: `/filters/${filterIndex}/operators`, value: [operator] },
        { op: 'replace', path: `/filters/${filterIndex}/default_value`, value: coerceFilterValue(filter, defaultValue) },
      ],
      `Edit Dashboard filter ${filter.id} from workspace`,
      'Filter inspector saved',
    )
  }
  const remove = () => {
    if (filterIndex < 0) return
    onPatch([{ op: 'remove', path: `/filters/${filterIndex}` }], `Remove Dashboard filter ${filter.id} from workspace`, 'Filter removed')
  }

  return (
    <div className="mt-3 space-y-3">
      <InspectorField label="Filter label">
        <Input value={label} onChange={event => setLabel(event.target.value)} disabled={disabled || loading} aria-label="Filter label" className="border-[#303940] bg-[#0e1114] text-sm text-[#eef2f3]" />
      </InspectorField>
      <InspectorField label="Operator">
        <select
          value={operator}
          onChange={event => setOperator(event.target.value)}
          disabled={disabled || loading}
          aria-label="Filter operator"
          className="h-9 w-full rounded border border-[#303940] bg-[#0e1114] px-2 text-sm text-[#eef2f3] disabled:opacity-50"
        >
          {filterOperatorOptions.map(value => <option key={value} value={value}>{value}</option>)}
        </select>
      </InspectorField>
      <InspectorField label="Default value">
        <Input value={defaultValue} onChange={event => setDefaultValue(event.target.value)} disabled={disabled || loading} aria-label="Filter default value" className="border-[#303940] bg-[#0e1114] text-sm text-[#eef2f3]" />
      </InspectorField>
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" onClick={save} disabled={disabled || loading || !label.trim()}>
          <Save className="h-4 w-4" />
          Save Filter
        </Button>
        <Button variant="secondary" onClick={remove} disabled={disabled || loading || manifest.filters.length <= 1}>
          <Trash2 className="h-4 w-4" />
          Remove Filter
        </Button>
      </div>
    </div>
  )
}

function InspectorField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-xs font-medium text-[#9aa4ac]">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  )
}

function IconButton({
  label,
  disabled,
  onClick,
  children,
}: {
  label: string
  disabled?: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      disabled={disabled}
      onClick={event => {
        event.preventDefault()
        event.stopPropagation()
        onClick()
      }}
      className="inline-flex h-8 w-8 items-center justify-center rounded border border-[#303940] bg-[#151a1f] text-[#cdd3d8] transition-colors hover:border-brand-orange/50 disabled:cursor-not-allowed disabled:opacity-40"
    >
      {children}
    </button>
  )
}

function FilterBar({ filters, values, onChange }: { filters: DashboardFilter[]; values: Record<string, unknown>; onChange: (filter: DashboardFilter, value: string) => void }) {
  if (filters.length === 0) {
    return <div className="text-sm text-[#818c95]">No global filters</div>
  }
  return (
    <div className="flex min-w-0 flex-wrap gap-2">
      {filters.map(filter => (
        <label key={filter.id} className="flex items-center gap-2 rounded-md border border-[#303940] bg-[#0e1114] px-2 py-1.5 text-sm">
          <span className="text-xs text-[#9aa4ac]">{filter.label}</span>
          {filter.domain && filter.domain.length > 0 ? (
            <select
              value={String(values[filter.field] ?? '')}
              onChange={event => onChange(filter, event.target.value)}
              className="h-7 rounded border border-[#303940] bg-[#151a1f] px-2 text-xs text-[#eef2f3]"
              aria-label={filter.label}
            >
              <option value="">All</option>
              {filter.domain.map((value, index) => <option key={index} value={String(value)}>{String(value)}</option>)}
            </select>
          ) : (
            <input
              value={String(values[filter.field] ?? '')}
              onChange={event => onChange(filter, event.target.value)}
              className="h-7 w-32 rounded border border-[#303940] bg-[#151a1f] px-2 text-xs text-[#eef2f3]"
              aria-label={filter.label}
            />
          )}
        </label>
      ))}
    </div>
  )
}

function DashboardCanvas({
  manifest,
  run,
  loadingRun,
  selectedTileId,
  onSelectTile,
}: {
  manifest: DashboardManifest
  run: DashboardRun | null
  loadingRun: boolean
  selectedTileId?: string | null
  onSelectTile?: (tileId: string) => void
}) {
  const viewsById = useMemo(() => new Map((run?.views ?? []).map(view => [view.data_view_id, view])), [run])
  const tilesById = useMemo(() => new Map(manifest.tiles.map(tile => [tile.id, tile])), [manifest.tiles])
  return (
    <div className="space-y-4">
      {manifest.layout.sections.map(section => (
        <section key={section.id}>
          {section.title && <h2 className="mb-2 text-sm font-semibold text-[#d6dde2]">{section.title}</h2>}
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {section.tile_ids.map(tileId => {
              const tile = tilesById.get(tileId)
              if (!tile) return null
              const view = tile.data_view_id ? viewsById.get(tile.data_view_id) : undefined
              const dataView = manifest.data_views.find(item => item.id === tile.data_view_id)
              return (
                <DashboardTileCard
                  key={tile.id}
                  tile={tile}
                  view={view}
                  dataView={dataView}
                  loading={loadingRun}
                  selected={selectedTileId === tile.id}
                  onSelect={onSelectTile ? () => onSelectTile(tile.id) : undefined}
                />
              )
            })}
          </div>
        </section>
      ))}
    </div>
  )
}

function DashboardTileCard({
  tile,
  view,
  dataView,
  loading,
  selected,
  onSelect,
}: {
  tile: DashboardTile
  view?: DashboardRunView
  dataView?: DashboardDataView
  loading: boolean
  selected?: boolean
  onSelect?: () => void
}) {
  const rows = Array.isArray(view?.result) ? view.result : view?.result ? [view.result] : []
  const first = rows[0] ?? {}
  const firstField = view?.schema?.[0]?.name ?? dataView?.output_schema?.[0]?.name
  const primaryValue = firstField ? first[firstField] : tile.tile_type === 'text' ? tile.business_question : null
  const unit = view?.schema?.[0]?.unit ?? dataView?.output_schema?.[0]?.unit
  const status = loading ? 'running' : view?.status ?? (tile.tile_type === 'text' ? 'success' : 'pending')
  const Component = onSelect ? 'button' : 'article'
  return (
    <Component
      type={onSelect ? 'button' : undefined}
      onClick={onSelect}
      className={cn(
        'block min-h-[210px] w-full rounded-md border bg-[#101316] p-4 text-left',
        selected ? 'border-brand-orange/70 ring-1 ring-brand-orange/40' : 'border-[#2d3338]',
        onSelect ? 'transition-colors hover:border-brand-orange/50' : '',
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            {tileIcon(tile.tile_type)}
            <h3 className="truncate text-sm font-semibold text-[#f3f5f5]">{tile.title}</h3>
          </div>
          <p className="mt-1 line-clamp-2 text-xs leading-5 text-[#8f9aa3]">{tile.business_question}</p>
        </div>
        <StatusPill status={status} />
      </div>

      <div className="mt-5">
        {loading ? (
          <div className="h-11 w-32 animate-pulse rounded bg-[#20262b]" />
        ) : status === 'error' || status === 'blocked' || status === 'permission_denied' ? (
          <div className="rounded border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-100">
            <div>{view?.error?.message || 'Dashboard view is blocked'}</div>
            <div className="mt-2 text-xs text-red-100/80">{view?.as_of ? `as of ${formatDate(view.as_of)}` : 'No run timestamp'}</div>
          </div>
        ) : rows.length === 0 && tile.tile_type !== 'text' ? (
          <div className="rounded border border-[#303940] bg-[#151a1f] p-3 text-sm text-[#a4adb5]">No rows returned</div>
        ) : tile.tile_type === 'table' ? (
          <MiniTable rows={rows} fields={view?.schema ?? dataView?.output_schema ?? []} />
        ) : (
          <div>
            <div className="text-3xl font-semibold tabular-nums text-[#f3f5f5]">{formatValue(primaryValue)}{unit ? <span className="ml-2 text-sm text-[#9aa4ac]">{unit}</span> : null}</div>
            <div className="mt-2 text-xs text-[#818c95]">{view?.as_of ? `as of ${formatDate(view.as_of)}` : 'No run timestamp'}</div>
          </div>
        )}
      </div>

      <div className="mt-4 flex flex-wrap gap-2 text-[11px] text-[#8f9aa3]">
        {view?.cached && <Badge>Cached</Badge>}
        {view?.stale && <Badge tone="warning">Stale data</Badge>}
        {runStateIsPartial(status) && <Badge tone="warning">Partial failure</Badge>}
        {dataView?.sensitivity && <Badge>{dataView.sensitivity}</Badge>}
        {view?.row_count !== undefined && <Badge>{view.row_count} rows</Badge>}
      </div>
    </Component>
  )
}

function DataTab({ manifest, run }: { manifest: DashboardManifest; run: DashboardRun | null }) {
  if (!run) return <EmptyPanel title="No run data" body="Publish and run the Dashboard to inspect canonical data-view results." />
  return (
    <div className="space-y-4">
      {manifest.data_views.map(dataView => {
        const view = run.views.find(item => item.data_view_id === dataView.id)
        const rows = Array.isArray(view?.result) ? view.result : view?.result ? [view.result] : []
        return (
          <section key={dataView.id} className="rounded-md border border-[#2d3338] bg-[#101316]">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#2d3338] p-3">
              <div>
                <h3 className="text-sm font-semibold text-[#f3f5f5]">{dataView.id}</h3>
                <p className="mt-1 text-xs text-[#8f9aa3]">{dataView.question}</p>
              </div>
              <StatusPill status={view?.status ?? 'pending'} />
            </div>
            <div className="p-3">
              <MiniTable rows={rows} fields={view?.schema ?? dataView.output_schema ?? []} />
            </div>
          </section>
        )
      })}
    </div>
  )
}

function LineageTab({ manifest, run, version }: { manifest: DashboardManifest; run: DashboardRun | null; version: DashboardVersion | null }) {
  const runViews = new Map((run?.views ?? []).map(view => [view.data_view_id, view]))
  return (
    <div className="grid gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
      <section className="rounded-md border border-[#2d3338] bg-[#101316] p-4">
        <h3 className="text-sm font-semibold">Pinned versions</h3>
        <div className="mt-3 space-y-2 text-sm">
          {manifest.semantic_bindings.map(binding => (
            <div key={binding.id} className="rounded border border-[#303940] bg-[#151a1f] p-3">
              <div className="font-medium text-[#f3f5f5]">{binding.model_slug}</div>
              <div className="mt-1 text-xs text-[#8f9aa3]">{binding.model_version}</div>
              <div className="mt-2 flex flex-wrap gap-1">
                {(binding.source_snapshot_ids ?? []).map(snapshot => <Badge key={snapshot}>{snapshot}</Badge>)}
              </div>
            </div>
          ))}
          {version?.pinned_source_snapshots?.length ? <div className="text-xs text-[#8f9aa3]">{version.pinned_source_snapshots.length} source snapshots pinned</div> : null}
        </div>
      </section>
      <section className="space-y-3">
        {manifest.data_views.map(dataView => {
          const view = runViews.get(dataView.id)
          const lineage = uniqueBy(
            [...(dataView.lineage ?? []), ...(dataView.saved_query?.lineage ?? []), ...(view?.lineage ?? [])],
            lineageKey,
          )
          const evidence = uniqueBy([...(dataView.evidence ?? []), ...(view?.evidence ?? [])], evidenceKey)
          return (
            <div key={dataView.id} className="rounded-md border border-[#2d3338] bg-[#101316] p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h3 className="text-sm font-semibold">{dataView.id}</h3>
                  <p className="mt-1 text-xs text-[#8f9aa3]">{dataView.question}</p>
                </div>
                <Badge>{dataView.kind}</Badge>
              </div>
              <LineageList title="Lineage" items={lineage} />
              <EvidenceList evidence={evidence} />
            </div>
          )
        })}
      </section>
    </div>
  )
}

function uniqueBy<T>(items: T[], getKey: (item: T) => string): T[] {
  const seen = new Set<string>()
  return items.filter(item => {
    const key = getKey(item)
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function lineageKey(item: DashboardLineageRef): string {
  return `${item.kind}-${item.ref}-${item.id}`
}

function evidenceKey(item: { id: string; title: string; kind: string }): string {
  return `${item.kind}-${item.id}-${item.title}`
}

function MiniTable({ rows, fields }: { rows: Record<string, unknown>[]; fields: Array<{ name: string; data_type?: string }> }) {
  if (rows.length === 0) return <div className="text-sm text-[#818c95]">No table rows</div>
  const columns = fields.length > 0 ? fields.map(field => field.name) : Object.keys(rows[0] ?? {})
  return (
    <div className="overflow-x-auto rounded border border-[#2d3338] custom-scrollbar">
      <table className="min-w-full text-left text-xs">
        <thead className="bg-[#171c21] text-[#9aa4ac]">
          <tr>{columns.map(column => <th key={column} className="px-3 py-2 font-medium">{column}</th>)}</tr>
        </thead>
        <tbody>
          {rows.slice(0, 8).map((row, index) => (
            <tr key={index} className="border-t border-[#242b31]">
              {columns.map(column => <td key={column} className="max-w-[220px] truncate px-3 py-2 text-[#d6dde2]">{formatValue(row[column])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function LineageList({ title, items }: { title: string; items: DashboardLineageRef[] }) {
  return (
    <div className="mt-4">
      <div className="text-xs font-medium uppercase text-[#818c95]">{title}</div>
      {items.length === 0 ? <div className="mt-2 text-sm text-[#7f8a93]">No lineage locators</div> : (
        <div className="mt-2 grid gap-2 md:grid-cols-2">
          {items.map(item => (
            <div key={`${item.kind}-${item.ref}-${item.id}`} className="rounded border border-[#303940] bg-[#151a1f] p-3 text-xs">
              <div className="font-medium text-[#f3f5f5]">{item.name}</div>
              <div className="mt-1 text-[#8f9aa3]">{item.kind} · {item.ref}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function EvidenceList({ evidence }: { evidence: Array<{ id: string; title: string; kind: string; confidence?: number | null }> }) {
  return (
    <div className="mt-4">
      <div className="text-xs font-medium uppercase text-[#818c95]">Evidence</div>
      {evidence.length === 0 ? <div className="mt-2 text-sm text-[#7f8a93]">No evidence locators</div> : (
        <div className="mt-2 flex flex-wrap gap-2">
          {evidence.map(item => <Badge key={item.id}>{item.title} · {item.kind}{item.confidence ? ` · ${Math.round(item.confidence * 100)}%` : ''}</Badge>)}
        </div>
      )}
    </div>
  )
}

function SemanticDiffPanel({ diff, blockers, warnings }: { diff: DashboardSemanticDiff | null; blockers: string[]; warnings: string[] }) {
  const modelChanges = diff?.model_version_changes ?? []
  const sourceChanges = diff?.source_snapshot_changes ?? []
  const hasChanges = modelChanges.length > 0 || sourceChanges.length > 0
  return (
    <section className="rounded-md border border-[#293037] bg-[#14181c] p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-[#f3f5f5]">Review diff</h2>
        <StatusPill status={blockers.length > 0 ? 'blocked' : hasChanges ? 'in_review' : 'pending'} />
      </div>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <DiffList title="Model pins" items={modelChanges.map(item => `${item.model_slug}: ${item.from} -> ${item.to}`)} />
        <DiffList title="Source snapshots" items={sourceChanges.map(item => `${item.model_slug}: ${item.from.join(', ') || 'none'} -> ${item.to.join(', ') || 'none'}`)} />
      </div>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <DiffList title="Blockers" items={blockers} tone="blocked" />
        <DiffList title="Warnings" items={warnings} tone="warning" />
      </div>
    </section>
  )
}

function DiffList({ title, items, tone = 'neutral' }: { title: string; items: string[]; tone?: 'neutral' | 'warning' | 'blocked' }) {
  const textClass = tone === 'blocked' ? 'text-red-100' : tone === 'warning' ? 'text-amber-100' : 'text-[#d6dde2]'
  return (
    <div className="rounded border border-[#303940] bg-[#101316] p-3">
      <div className="text-xs font-medium uppercase text-[#818c95]">{title}</div>
      {items.length === 0 ? (
        <div className="mt-2 text-sm text-[#7f8a93]">No changes</div>
      ) : (
        <div className="mt-2 space-y-1">
          {items.slice(0, 4).map((item, index) => <div key={`${title}-${index}`} className={cn('truncate text-sm', textClass)}>{item}</div>)}
        </div>
      )}
    </div>
  )
}

function AuditTrail({ events }: { events: DashboardAuditEvent[] }) {
  return (
    <section className="rounded-md border border-[#293037] bg-[#14181c] p-4">
      <h2 className="text-sm font-semibold text-[#f3f5f5]">Audit</h2>
      <div className="mt-3 space-y-2">
        {events.length === 0 ? (
          <div className="text-sm text-[#7f8a93]">No audit events</div>
        ) : events.slice(0, 5).map(event => (
          <div key={event.id} className="rounded border border-[#303940] bg-[#101316] p-3">
            <div className="flex items-center justify-between gap-2">
              <div className="truncate text-sm text-[#d6dde2]">{event.action}</div>
              <StatusPill status={event.outcome} />
            </div>
            <div className="mt-1 truncate text-xs text-[#818c95]">{event.created_at ? formatDate(event.created_at) : 'No timestamp'}</div>
          </div>
        ))}
      </div>
    </section>
  )
}

function LegacyMigrationReviewPanel({
  asset,
  version,
  manifest,
  run,
  blockers,
  warnings,
  loading,
  onGenerateDraft,
  onStartReview,
  onRefresh,
}: {
  asset: DashboardAssetDetail
  version: DashboardVersion | null
  manifest: DashboardManifest | null
  run: DashboardRun | null
  blockers: string[]
  warnings: string[]
  loading: boolean
  onGenerateDraft: () => void
  onStartReview: () => void
  onRefresh: () => void
}) {
  const migrationSummary = isRecord(asset.health_summary.migration) ? asset.health_summary.migration : {}
  const migrationState = manifest?.migration.state
    ?? version?.migration_state
    ?? stringValue(migrationSummary.state)
    ?? asset.lifecycle
  const sourceIds = uniqueStrings([
    ...(version?.pinned_source_snapshots ?? []),
    ...(manifest?.semantic_bindings.flatMap(binding => binding.source_snapshot_ids ?? []) ?? []),
  ])
  const latestLegacyVersionId = stringValue(migrationSummary.latest_dashboard_version_id)
  const legacySourceId = manifest?.migration.legacy_dashboard_id ?? asset.notebook_id ?? latestLegacyVersionId ?? version?.id ?? null
  const permissionSummary = summarizeAccessPolicy(manifest?.access_policy ?? asset.access_policy)
  const readOnlyRows = legacyPreviewRows(manifest, run, asset)
  const previewPath = asset.notebook_id ? `/notebook/${asset.notebook_id}/preview` : null
  return (
    <section className="rounded-md border border-amber-500/30 bg-amber-500/10 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-sm font-semibold text-amber-100">Legacy migration review</h2>
            <StatusPill status={migrationState} />
            {version && <Badge>v{version.version_num} {version.status}</Badge>}
          </div>
          <p className="mt-1 text-sm text-amber-100/80">
            This legacy_unstructured asset stays read-only until a reviewer generates and validates a structured draft. It is not converted to a generic error state.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={onGenerateDraft} disabled={loading || !manifest || !asset.published_version_id}>
            <GitBranch className="h-4 w-4" />
            Generate structured draft
          </Button>
          <Button variant="secondary" onClick={onStartReview} disabled={loading || !manifest || !version}>
            <ShieldCheck className="h-4 w-4" />
            Start review
          </Button>
          <Button variant="secondary" onClick={onRefresh} disabled={loading}>
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
          <Button asChild variant="secondary">
            <Link to="/dashboard-assets">Back to list</Link>
          </Button>
          {asset.notebook_id && (
            <Button asChild variant="secondary">
              <Link to={`/notebook/${asset.notebook_id}`}>Open Notebook</Link>
            </Button>
          )}
          {previewPath && (
            <Button asChild variant="secondary">
              <Link to={previewPath}>
                <ExternalLink className="h-4 w-4" />
                Open legacy preview
              </Link>
            </Button>
          )}
        </div>
      </div>

      <div className="mt-4 grid gap-3 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-3">
          <div className="grid gap-2 md:grid-cols-3">
            <LegacyKV label="Asset" value={`${asset.name} / ${asset.slug}`} />
            <LegacyKV label="Version" value={version ? `v${version.version_num} ${version.status}` : 'No structured version'} />
            <LegacyKV label="Freshness" value={run?.overall_freshness ?? formatInventoryFreshness(asset)} />
            <LegacyKV label="Source" value={sourceIds.length ? sourceIds.join(', ') : legacySourceId ?? 'No source snapshot'} />
            <LegacyKV label="Permission" value={permissionSummary} />
            <LegacyKV label="Audit" value={manifest?.migration.reviewed_at ? `Reviewed ${formatDate(manifest.migration.reviewed_at)}` : 'Review not started'} />
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <DiffList title="Blockers" items={blockers} tone="blocked" />
            <DiffList title="Warnings" items={warnings} tone="warning" />
          </div>
        </div>

        <div className="rounded-md border border-amber-500/25 bg-[#101316] p-3">
          <div className="flex items-center justify-between gap-2">
            <div className="text-xs font-medium uppercase text-amber-100/70">Read-only preview</div>
            <Badge tone="warning">locked</Badge>
          </div>
          <div className="mt-3 space-y-2">
            {readOnlyRows.map(row => (
              <div key={row.label} className="rounded border border-[#303940] bg-[#151a1f] p-2">
                <div className="truncate text-xs text-[#818c95]">{row.label}</div>
                <div className="mt-1 line-clamp-2 text-sm text-[#d6dde2]">{row.value}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

function LegacyKV({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded border border-amber-500/20 bg-[#101316] p-3">
      <div className="text-[11px] font-medium uppercase text-amber-100/60">{label}</div>
      <div className="mt-1 break-words text-sm text-amber-50">{value}</div>
    </div>
  )
}

function summarizeAccessPolicy(policy: Record<string, unknown>): string {
  const scopes = policy.required_scopes
  const rows = policy.row_policy_refs
  const columns = policy.column_policy_refs
  const redactions = policy.redaction_policy_refs
  const parts = [
    Array.isArray(scopes) && scopes.length ? `${scopes.length} scopes` : null,
    Array.isArray(rows) && rows.length ? `${rows.length} row policies` : null,
    Array.isArray(columns) && columns.length ? `${columns.length} column policies` : null,
    Array.isArray(redactions) && redactions.length ? `${redactions.length} redactions` : null,
  ].filter(Boolean)
  return parts.length ? parts.join(', ') : 'Workspace policy inherited'
}

function legacyPreviewRows(manifest: DashboardManifest | null, run: DashboardRun | null, asset: DashboardAssetDetail): Array<{ label: string; value: string }> {
  const runRows = run?.views.flatMap(view => {
    const rows = Array.isArray(view.result) ? view.result : view.result ? [view.result] : []
    return rows.slice(0, 1).map(row => ({ label: view.data_view_id, value: formatValue(row) }))
  }) ?? []
  if (runRows.length > 0) return runRows.slice(0, 4)
  const tileRows = manifest?.tiles.slice(0, 4).map(tile => ({
    label: tile.title,
    value: tile.accessible_fallback?.summary || tile.business_question || tile.tile_type,
  })) ?? []
  if (tileRows.length > 0) return tileRows
  return [
    { label: 'Name', value: asset.name },
    { label: 'Description', value: asset.description || 'No description' },
    { label: 'Notebook', value: asset.notebook_id ?? 'No notebook' },
    { label: 'Lifecycle', value: asset.lifecycle },
  ]
}

function uniqueStrings(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean)))
}

function TabButton({ active, onClick, icon, label }: { active: boolean; onClick: () => void; icon: React.ReactNode; label: string }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'flex h-8 items-center gap-2 rounded px-3 text-sm transition-colors',
        active ? 'bg-brand-orange text-white' : 'text-[#9aa4ac] hover:bg-[#1b2127] hover:text-white',
      )}
    >
      {icon}
      <span>{label}</span>
    </button>
  )
}

function StatusPill({ status }: { status?: string }) {
  const value = status || 'unknown'
  return <span className={cn('inline-flex h-6 items-center rounded-full border px-2 text-[11px] font-medium', statusTone[value] ?? 'border-[#3a444d] bg-[#20262b] text-[#cdd3d8]')}>{value}</span>
}

function Badge({ children, tone = 'neutral' }: { children: React.ReactNode; tone?: 'neutral' | 'ready' | 'warning' }) {
  const cls = tone === 'ready'
    ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
    : tone === 'warning'
      ? 'border-amber-500/30 bg-amber-500/10 text-amber-200'
      : 'border-[#3a444d] bg-[#20262b] text-[#cdd3d8]'
  return <span className={cn('inline-flex h-6 items-center rounded border px-2 text-[11px]', cls)}>{children}</span>
}

function HeaderSignal({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-md border border-[#2a3136] bg-[#101316] p-3">
      <div className="flex items-center gap-2 text-[#cdd3d8]">
        <span className="text-brand-orange">{icon}</span>
        <span className="font-medium">{label}</span>
      </div>
      <div className="mt-1 truncate text-[#818c95]">{value}</div>
    </div>
  )
}

function EmptyPanel({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-md border border-[#293037] bg-[#14181c] p-6 text-center">
      <CheckCircle2 className="mx-auto h-8 w-8 text-[#5f6d78]" />
      <h2 className="mt-3 text-sm font-semibold text-[#f3f5f5]">{title}</h2>
      <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-[#8f9aa3]">{body}</p>
    </div>
  )
}

function LoadingList() {
  return <div className="space-y-2">{Array.from({ length: 6 }).map((_, index) => <div key={index} className="h-24 animate-pulse rounded-md bg-[#1a2025]" />)}</div>
}

function tileIcon(type: string) {
  if (type === 'line' || type === 'area') return <LineChart className="h-4 w-4 text-brand-orange" />
  if (type === 'bar' || type === 'kpi') return <BarChart3 className="h-4 w-4 text-brand-orange" />
  if (type === 'table') return <Table2 className="h-4 w-4 text-brand-orange" />
  return <LayoutDashboard className="h-4 w-4 text-brand-orange" />
}

function runStateIsPartial(status: string): boolean {
  return status === 'error' || status === 'partial'
}

function coerceFilterValue(filter: DashboardFilter, value: string): unknown {
  if (filter.filter_type === 'number' || filter.filter_type === 'integer') return Number(value)
  if (filter.filter_type === 'boolean') return value === 'true'
  return value
}

function shortId(value?: string | null) {
  if (!value) return 'none'
  return value.slice(0, 8)
}

function shortHash(value: string) {
  return value.replace('sha256:', '').slice(0, 10)
}

function stringValue(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

function formatInventoryModel(asset: DashboardAsset): string {
  const modelVersions = asset.health_summary.model_versions ?? asset.health_summary.semantic_models
  if (isRecord(modelVersions)) {
    const first = Object.entries(modelVersions)[0]
    if (first) return `${first[0]} / ${String(first[1])}`
  }
  const model = asset.health_summary.model_slug ?? asset.health_summary.model
  const version = asset.health_summary.model_version ?? asset.health_summary.version
  if (model || version) return `${String(model ?? 'model')} / ${String(version ?? 'version pending')}`
  return 'Model pending / version pending'
}

function formatInventoryFreshness(asset: DashboardAsset): string {
  const freshness = asset.health_summary.freshness ?? asset.health_summary.overall_freshness
  if (freshness) return String(freshness)
  return asset.lifecycle === 'published' ? 'Freshness ready' : 'Freshness pending'
}

function formatInventoryWarnings(asset: DashboardAsset): string {
  const warnings = asset.health_summary.warnings
  if (Array.isArray(warnings) && warnings.length > 0) return `${warnings.length} warnings`
  if (asset.lifecycle === 'legacy_unstructured') return 'Needs structured review'
  return 'Ready'
}

function formatDate(value: string) {
  return new Date(value).toLocaleString()
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'number') return new Intl.NumberFormat().format(value)
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}
