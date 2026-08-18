import { useState, useEffect, useCallback, useMemo } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { Button } from '../components/ui/button'
import { Card } from '../components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import {
  ChevronRight,
  FolderOpen,
  Settings,
  Plus,
  Pencil,
  Loader2,
  BookOpen,
  LayoutDashboard,
  X,
  Globe,
} from 'lucide-react'
import { Switch } from '../components/ui/switch'
import { useStore } from '../stores/useStore'
import { useScopes } from '../hooks/useScopes'
import { ApiService } from '../services/api'
import type { DashboardVersion } from '../services/api'
import { showToast } from '../utils/toast'
import { FolderContentRow } from '../components/folders/FolderContentRow'
import { MembersPanel } from '../components/folders/MembersPanel'
import { ShareNotebookModal } from '../components/folders/ShareNotebookModal'
import { useKnowledgeCenterPath } from '../contexts/EmbeddedModeContext'
import type { Folder, FolderContentItem, FolderDashboard } from '../types/folder'
import { rewriteDashboardHtmlForBackend, ensureBaseHref, getBackendUrlForHtmlProcessing, injectViewerConfig } from '../utils/dashboardHtml'

export default function FolderDetailPage() {
  const { id: folderId } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const kcPath = useKnowledgeCenterPath()
  const { userId, isViewer, canManageFolderMembers, canShareNotebookToFolder } = useScopes()

  // Store
  const {
    folders,
    folderMembers,
    folderNotebooks,
    folderDashboards,
    fetchFolders,
    fetchFolderMembers,
    fetchFolderNotebooks,
    fetchFolderDashboards,
    unshareNotebookFromFolder,
    unshareDashboardFromFolder,
    cloneNotebook,
    updateFolder,
    updateSnapshot,
  } = useStore()

  // Local state
  const [folder, setFolder] = useState<Folder | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Modal states
  const [showMembersPanel, setShowMembersPanel] = useState(false)
  const [showShareNotebookModal, setShowShareNotebookModal] = useState(false)
  const [showEditDialog, setShowEditDialog] = useState(false)

  // Edit folder state
  const [editName, setEditName] = useState('')
  const [editDescription, setEditDescription] = useState('')
  const [editIsPublic, setEditIsPublic] = useState(false)
  const [updating, setUpdating] = useState(false)

  // Action loading states
  const [cloningNotebook, setCloningNotebook] = useState<string | null>(null)
  const [unsharingNotebook, setUnsharingNotebook] = useState<string | null>(null)
  const [unsharingDashboard, setUnsharingDashboard] = useState<string | null>(null)
  const [updatingSnapshot, setUpdatingSnapshot] = useState<string | null>(null)

  // Dashboard preview state
  const [selectedDashboard, setSelectedDashboard] = useState<FolderDashboard | null>(null)
  const [dashboardHtml, setDashboardHtml] = useState<string>('')
  const [loadingDashboardPreview, setLoadingDashboardPreview] = useState(false)

  // Dashboard version update state
  const [showUpdateVersionDialog, setShowUpdateVersionDialog] = useState(false)
  const [dashboardToUpdate, setDashboardToUpdate] = useState<FolderContentItem | null>(null)
  const [availableVersionsForUpdate, setAvailableVersionsForUpdate] = useState<DashboardVersion[]>([])
  const [selectedNewVersionId, setSelectedNewVersionId] = useState<string>('')
  const [updatingDashboardVersion, setUpdatingDashboardVersion] = useState<string | null>(null)
  const [loadingVersions, setLoadingVersions] = useState(false)

  // Load folder data
  const loadFolderData = useCallback(async () => {
    if (!folderId) return

    setLoading(true)
    setError(null)

    try {
      // Fetch folders if not already loaded
      if (folders.length === 0) {
        await fetchFolders()
      }

      // Fetch folder content in parallel
      // Viewers only get dashboards, not members or notebooks
      const fetchPromises = [fetchFolderDashboards(folderId)]
      if (!isViewer) {
        fetchPromises.push(fetchFolderMembers(folderId))
        fetchPromises.push(fetchFolderNotebooks(folderId))
      }
      await Promise.all(fetchPromises)
    } catch (err) {
      console.error('Failed to load folder data:', err)
      setError('Failed to load folder data')
    } finally {
      setLoading(false)
    }
  }, [folderId, folders.length, fetchFolders, fetchFolderMembers, fetchFolderNotebooks, fetchFolderDashboards, isViewer])

  // Initial load
  useEffect(() => {
    loadFolderData()
  }, [loadFolderData])

  // Find folder from store
  useEffect(() => {
    if (folderId && folders.length > 0) {
      const found = folders.find((f) => f.id === folderId)
      if (found) {
        setFolder(found)
      } else {
        setError('Folder not found')
      }
    }
  }, [folderId, folders])

  // Merge and sort content items
  const contentItems = useMemo((): FolderContentItem[] => {
    // Viewers only see dashboards, not notebooks
    const notebooks: FolderContentItem[] = isViewer ? [] : folderNotebooks.map((n) => ({
      id: n.id,
      type: 'notebook' as const,
      name: n.notebook_name || 'Untitled Notebook',
      description: n.notebook_description || null,
      isSnapshot: n.is_snapshot,
      sharedBy: n.shared_by,
      sharedByUser: n.shared_by_user || null,
      createdAt: n.created_at,
      snapshotUpdatedAt: n.snapshot_updated_at,
      notebookId: n.notebook_id,
    }))

    const dashboards: FolderContentItem[] = folderDashboards.map((d) => ({
      id: d.id,
      type: 'dashboard' as const,
      name: d.dashboard_notebook_name || `Dashboard v${d.dashboard_version || 1}`,
      description: null,
      isSnapshot: d.is_snapshot,
      sharedBy: d.shared_by,
      sharedByUser: d.shared_by_user || null,
      createdAt: d.created_at,
      snapshotUpdatedAt: d.snapshot_updated_at,
      dashboardId: d.dashboard_id,
      dashboardVersion: d.dashboard_version || undefined,
      dashboardNotebookId: d.dashboard_notebook_id || undefined,
    }))

    // Sort by created_at descending (most recent first)
    return [...notebooks, ...dashboards].sort(
      (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
    )
  }, [folderNotebooks, folderDashboards, isViewer])

  // Handlers
  const handleClone = async (item: FolderContentItem) => {
    if (!folder || !item.notebookId) return

    try {
      setCloningNotebook(item.notebookId)
      const result = await cloneNotebook(folder.id, item.notebookId, `${item.name} (Copy)`)
      navigate(`/notebook/${result.notebook_id}`)
    } catch (err) {
      console.error('Failed to clone notebook:', err)
      showToast.error('Failed to clone notebook')
    } finally {
      setCloningNotebook(null)
    }
  }

  const handleUnshare = async (item: FolderContentItem) => {
    if (!folder) return

    try {
      if (item.type === 'notebook' && item.notebookId) {
        setUnsharingNotebook(item.notebookId)
        await unshareNotebookFromFolder(folder.id, item.notebookId)
      } else if (item.type === 'dashboard' && item.dashboardId) {
        setUnsharingDashboard(item.dashboardId)
        await unshareDashboardFromFolder(folder.id, item.dashboardId)
      }
    } catch (err) {
      console.error('Failed to unshare:', err)
      showToast.error('Failed to unshare')
    } finally {
      setUnsharingNotebook(null)
      setUnsharingDashboard(null)
    }
  }

  const handlePreview = async (item: FolderContentItem) => {
    if (!item.dashboardId) {
      console.error('Dashboard is missing dashboard_id')
      return
    }

    const dashboard = folderDashboards.find((d) => d.id === item.id)
    if (!dashboard) return

    try {
      setSelectedDashboard(dashboard)
      setLoadingDashboardPreview(true)
      setDashboardHtml('')
      const detail = await ApiService.getViewerDashboard(item.dashboardId)

      const backendUrl = await getBackendUrlForHtmlProcessing()
      const rewritten = rewriteDashboardHtmlForBackend(detail.html_content, backendUrl)
      const withViewer = injectViewerConfig(rewritten, item.dashboardId)
      const withBase = ensureBaseHref(withViewer, backendUrl)
      setDashboardHtml(withBase)
    } catch (err) {
      console.error('Failed to load dashboard preview:', err)
      setSelectedDashboard(null)
    } finally {
      setLoadingDashboardPreview(false)
    }
  }

  const handleCloseDashboardPreview = () => {
    setSelectedDashboard(null)
    setDashboardHtml('')
  }

  const handleUpdateSnapshot = async (item: FolderContentItem) => {
    if (!folder || !item.notebookId) return

    try {
      setUpdatingSnapshot(item.notebookId)
      await updateSnapshot(folder.id, item.notebookId)
      showToast.success('Snapshot updated with latest notebook data')
    } catch (err) {
      console.error('Failed to update snapshot:', err)
      showToast.error('Failed to update snapshot')
    } finally {
      setUpdatingSnapshot(null)
    }
  }

  const handleEditClick = () => {
    if (!folder) return
    setEditName(folder.name)
    setEditDescription(folder.description || '')
    setEditIsPublic(folder.is_public)
    setShowEditDialog(true)
  }

  const handleUpdateDashboardVersion = async (item: FolderContentItem) => {
    if (!item.dashboardNotebookId) {
      showToast.error('Unable to find dashboard source notebook')
      return
    }

    setDashboardToUpdate(item)
    setShowUpdateVersionDialog(true)
    setLoadingVersions(true)

    try {
      const versions = await ApiService.getNotebookDashboardVersions(item.dashboardNotebookId)
      setAvailableVersionsForUpdate(versions.sort((a, b) => b.version_num - a.version_num))
      // Pre-select current version
      const currentVersion = versions.find((v) => v.id === item.dashboardId)
      if (currentVersion) {
        setSelectedNewVersionId(currentVersion.id)
      } else if (versions.length > 0) {
        setSelectedNewVersionId(versions[0].id)
      }
    } catch (err) {
      console.error('Failed to load dashboard versions:', err)
      showToast.error('Failed to load available versions')
      setShowUpdateVersionDialog(false)
      setDashboardToUpdate(null)
    } finally {
      setLoadingVersions(false)
    }
  }

  const handleConfirmVersionUpdate = async () => {
    if (!folder || !dashboardToUpdate?.dashboardId || !selectedNewVersionId) return

    // Don't update if same version
    if (selectedNewVersionId === dashboardToUpdate.dashboardId) {
      setShowUpdateVersionDialog(false)
      setDashboardToUpdate(null)
      return
    }

    try {
      setUpdatingDashboardVersion(dashboardToUpdate.dashboardId)
      await ApiService.updateFolderDashboardVersion(folder.id, dashboardToUpdate.dashboardId, selectedNewVersionId)
      showToast.success('Dashboard version updated')
      // Refresh dashboards
      await fetchFolderDashboards(folder.id)
    } catch (err) {
      console.error('Failed to update dashboard version:', err)
      showToast.error('Failed to update dashboard version')
    } finally {
      setUpdatingDashboardVersion(null)
      setShowUpdateVersionDialog(false)
      setDashboardToUpdate(null)
      setSelectedNewVersionId('')
      setAvailableVersionsForUpdate([])
    }
  }

  const handleCloseVersionDialog = () => {
    if (updatingDashboardVersion) return
    setShowUpdateVersionDialog(false)
    setDashboardToUpdate(null)
    setSelectedNewVersionId('')
    setAvailableVersionsForUpdate([])
  }

  const handleUpdateFolder = async () => {
    if (!folder || !editName.trim()) return

    try {
      setUpdating(true)
      await updateFolder(folder.id, editName.trim(), editDescription.trim() || undefined, editIsPublic)
      setShowEditDialog(false)
      // Update local folder state
      setFolder((prev) =>
        prev
          ? { ...prev, name: editName.trim(), description: editDescription.trim() || null, is_public: editIsPublic }
          : null
      )
    } catch (err) {
      console.error('Failed to update folder:', err)
      showToast.error('Failed to update folder')
    } finally {
      setUpdating(false)
    }
  }

  // Permissions
  const canEditFolder = canManageFolderMembers || folder?.created_by === userId

  if (loading) {
    return (
      <div className="bg-[#0d0d0d] w-full h-full flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="w-8 h-8 animate-spin text-brand-orange mx-auto mb-4" />
          <p className="text-gray-400">Loading folder...</p>
        </div>
      </div>
    )
  }

  if (error || !folder) {
    return (
      <div className="bg-[#0d0d0d] w-full h-full flex items-center justify-center">
        <Card className="p-8 text-center bg-[#1a1a1a] border-gray-800 max-w-md">
          <div className="w-16 h-16 bg-red-900/20 rounded-full flex items-center justify-center mx-auto mb-4">
            <FolderOpen className="w-8 h-8 text-red-400" />
          </div>
          <h3 className="text-xl font-semibold text-white mb-2">Folder Not Found</h3>
          <p className="text-gray-400 mb-6">
            {error || 'The folder you are looking for does not exist or you do not have access.'}
          </p>
          <Button variant="brand-primary" onClick={() => navigate(kcPath('/folders'))}>
            Back to Folders
          </Button>
        </Card>
      </div>
    )
  }

  return (
    <div className="bg-[#0d0d0d] w-full h-full flex flex-col">
      {/* Header Section */}
      <div className="w-full px-8 pt-[50px] pb-6 border-b border-gray-800">
        <div className="max-w-[1000px] mx-auto">
          {/* Breadcrumb */}
          <nav className="flex items-center text-sm text-gray-400 mb-4">
            <Link
              to={kcPath('/folders')}
              className="hover:text-white transition-colors"
            >
              Folders
            </Link>
            <ChevronRight className="w-4 h-4 mx-2" />
            <span className="text-white">{folder.name}</span>
          </nav>

          {/* Title Row */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <FolderOpen className="w-6 h-6 text-brand-orange" />
              <div>
                <h1 className="text-2xl font-bold text-white">{folder.name}</h1>
                {folder.description && (
                  <p className="text-sm text-gray-400 mt-1">{folder.description}</p>
                )}
              </div>
              {canEditFolder && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleEditClick}
                  className="text-gray-400 hover:text-white hover:bg-gray-800 h-8 w-8 p-0"
                >
                  <Pencil className="w-4 h-4" />
                </Button>
              )}
            </div>

            {/* Right Actions */}
            <div className="flex items-center gap-3">
              {/* Members button with count badge - hidden for viewers */}
              {!isViewer && (
                <Button
                  variant="outline"
                  onClick={() => setShowMembersPanel(true)}
                  className="border-gray-700 text-gray-300 hover:bg-gray-800"
                >
                  <Settings className="w-4 h-4 mr-2" />
                  Members ({folderMembers.length})
                </Button>
              )}

              {/* Share Content button */}
              {canShareNotebookToFolder && (
                <Button
                  variant="brand-primary"
                  onClick={() => setShowShareNotebookModal(true)}
                >
                  <Plus className="w-4 h-4 mr-2" />
                  Share Notebook
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Content List */}
      <div className="flex-1 overflow-y-auto custom-scrollbar">
        <div className="max-w-[1000px] mx-auto px-8 py-6">
          {contentItems.length === 0 ? (
            <Card className="p-12 text-center bg-[#1a1a1a] border-gray-800">
              <div className="max-w-md mx-auto">
                <div className="w-16 h-16 bg-brand-orange/10 rounded-full flex items-center justify-center mx-auto mb-4">
                  {isViewer ? (
                    <LayoutDashboard className="w-8 h-8 text-brand-orange" />
                  ) : (
                    <BookOpen className="w-8 h-8 text-brand-orange" />
                  )}
                </div>
                <h3 className="text-xl font-semibold text-white mb-2">
                  {isViewer ? 'No Dashboards Available' : 'No Content Shared'}
                </h3>
                <p className="text-gray-400 mb-6">
                  {isViewer
                    ? 'No dashboards have been shared to this folder yet.'
                    : 'Share notebooks and dashboards to this folder for team members to access.'}
                </p>
                {canShareNotebookToFolder && (
                  <Button
                    variant="brand-primary"
                    onClick={() => setShowShareNotebookModal(true)}
                  >
                    <Plus className="w-4 h-4 mr-2" />
                    Share Notebook
                  </Button>
                )}
              </div>
            </Card>
          ) : (
            <div className="bg-[#1a1a1a] rounded-lg border border-gray-800">
              {/* List Header */}
              <div className="grid grid-cols-12 gap-4 px-4 py-3 border-b border-gray-800 text-xs text-gray-500 uppercase tracking-wider">
                <div className="col-span-5">Name</div>
                <div className="col-span-2">Type</div>
                <div className="col-span-2">Shared By</div>
                <div className="col-span-2">Modified</div>
                <div className="col-span-1 text-right">Actions</div>
              </div>

              {/* List Items */}
              {contentItems.map((item) => (
                <FolderContentRow
                  key={item.id}
                  item={item}
                  userId={userId ?? null}
                  onClone={handleClone}
                  onUnshare={handleUnshare}
                  onPreview={handlePreview}
                  onUpdateSnapshot={handleUpdateSnapshot}
                  onUpdateDashboardVersion={handleUpdateDashboardVersion}
                  cloningId={cloningNotebook}
                  unsharingId={item.type === 'notebook' ? unsharingNotebook : unsharingDashboard}
                  updatingSnapshotId={updatingSnapshot}
                  updatingDashboardVersionId={updatingDashboardVersion}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Members Panel (Slide-over) */}
      <MembersPanel
        open={showMembersPanel}
        onClose={() => setShowMembersPanel(false)}
        folderId={folder.id}
        folderCreatedBy={folder.created_by}
        members={folderMembers}
      />

      {/* Share Notebook Modal */}
      {!isViewer && (
        <ShareNotebookModal
          open={showShareNotebookModal}
          onOpenChange={setShowShareNotebookModal}
          folderId={folder.id}
          existingNotebooks={folderNotebooks}
        />
      )}

      {/* Edit Folder Dialog */}
      <Dialog
        open={showEditDialog}
        onOpenChange={(open) => {
          if (!open && updating) return
          setShowEditDialog(open)
        }}
      >
        <DialogContent className="max-w-md bg-[#2a2a2a] border-[#444444]">
          <DialogHeader>
            <DialogTitle className="text-white">Edit Folder</DialogTitle>
          </DialogHeader>

          <div className="space-y-4">
            <div>
              <Label htmlFor="edit-folder-name" className="text-white">
                Name <span className="text-red-400">*</span>
              </Label>
              <Input
                id="edit-folder-name"
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                placeholder="Folder name"
                className="mt-1 bg-[#1a1a1a] border-[#555555] text-white focus:border-brand-orange focus:ring-1 focus:ring-brand-orange/50"
              />
            </div>

            <div>
              <Label htmlFor="edit-folder-description" className="text-white">
                Description
              </Label>
              <Input
                id="edit-folder-description"
                value={editDescription}
                onChange={(e) => setEditDescription(e.target.value)}
                placeholder="Optional description"
                className="mt-1 bg-[#1a1a1a] border-[#555555] text-white focus:border-brand-orange focus:ring-1 focus:ring-brand-orange/50"
              />
            </div>

            <div className="flex items-center justify-between py-2">
              <div className="flex items-center gap-2">
                <Globe className="w-4 h-4 text-gray-400" />
                <div>
                  <Label htmlFor="edit-folder-public" className="text-white cursor-pointer">
                    Public folder
                  </Label>
                  <p className="text-xs text-gray-400">Everyone in your team can view this folder</p>
                </div>
              </div>
              <Switch id="edit-folder-public" checked={editIsPublic} onCheckedChange={setEditIsPublic} />
            </div>

            <div className="flex justify-end gap-2 pt-4">
              <Button
                variant="outline"
                onClick={() => setShowEditDialog(false)}
                disabled={updating}
                className="border-[#555555] text-white hover:bg-[#3a3a3a]"
              >
                Cancel
              </Button>
              <Button
                variant="brand-primary"
                onClick={handleUpdateFolder}
                disabled={updating || !editName.trim()}
              >
                {updating && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                {updating ? 'Saving...' : 'Save Changes'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Update Dashboard Version Dialog */}
      <Dialog open={showUpdateVersionDialog} onOpenChange={handleCloseVersionDialog}>
        <DialogContent className="max-w-sm bg-[#2a2a2a] border-[#444444]">
          <DialogHeader>
            <DialogTitle className="text-white flex items-center gap-2">
              <LayoutDashboard className="w-4 h-4" />
              Update Dashboard Version
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-4">
            {dashboardToUpdate && (
              <p className="text-sm text-gray-400">
                Update the shared version of{' '}
                <span className="text-white font-medium">{dashboardToUpdate.name}</span>
              </p>
            )}

            {loadingVersions ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
              </div>
            ) : availableVersionsForUpdate.length === 0 ? (
              <p className="text-sm text-gray-500 text-center py-4">No versions available</p>
            ) : (
              <div>
                <Label htmlFor="version-select" className="text-white text-sm">
                  Select Version
                </Label>
                <select
                  id="version-select"
                  value={selectedNewVersionId}
                  onChange={(e) => setSelectedNewVersionId(e.target.value)}
                  disabled={!!updatingDashboardVersion}
                  className="w-full mt-2 px-3 py-2 text-sm bg-[#1a1a1a] border border-[#555555] rounded-lg text-white focus:outline-none focus:border-brand-orange"
                >
                  {availableVersionsForUpdate.map((version, index) => (
                    <option key={version.id} value={version.id}>
                      Version {version.version_num}
                      {index === 0 ? ' (Latest)' : ''}
                      {version.id === dashboardToUpdate?.dashboardId ? ' (Current)' : ''}
                    </option>
                  ))}
                </select>
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <Button
                variant="outline"
                onClick={handleCloseVersionDialog}
                disabled={!!updatingDashboardVersion}
                className="border-[#555555] text-white hover:bg-[#3a3a3a]"
              >
                Cancel
              </Button>
              <Button
                variant="brand-primary"
                onClick={handleConfirmVersionUpdate}
                disabled={
                  !!updatingDashboardVersion ||
                  !selectedNewVersionId ||
                  selectedNewVersionId === dashboardToUpdate?.dashboardId
                }
              >
                {updatingDashboardVersion && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                {updatingDashboardVersion ? 'Updating...' : 'Update Version'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Dashboard Preview Fullscreen */}
      {selectedDashboard && (
        <div className="fixed inset-0 z-50 bg-[#0d0d0d] flex flex-col">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800 bg-[#1a1a1a]">
            <div className="flex items-center gap-3">
              <LayoutDashboard className="w-5 h-5 text-brand-orange" />
              <h2 className="text-lg font-semibold text-white">
                {selectedDashboard.dashboard_notebook_name ||
                  `Dashboard v${selectedDashboard.dashboard_version || 1}`}
              </h2>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleCloseDashboardPreview}
              className="text-gray-400 hover:text-white hover:bg-gray-800"
            >
              <X className="w-5 h-5" />
            </Button>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-hidden">
            {loadingDashboardPreview ? (
              <div className="flex items-center justify-center h-full">
                <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
              </div>
            ) : dashboardHtml ? (
              <iframe
                srcDoc={dashboardHtml}
                className="w-full h-full border-0"
                title="Dashboard Preview"
                sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals"
              />
            ) : (
              <div className="flex items-center justify-center h-full text-gray-500">
                <div className="text-center">
                  <LayoutDashboard className="w-8 h-8 mx-auto mb-2 opacity-60" />
                  <p className="text-sm">Unable to load dashboard preview</p>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
