import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog'
import { Button } from '../ui/button'
import { Badge } from '../ui/badge'
import { Card } from '../ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../ui/tabs'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Loader2, UserPlus, BookOpen, Trash2, X, Copy, Pencil, RefreshCw, Camera, Radio, LayoutDashboard, Eye, Globe } from 'lucide-react'
import { Switch } from '../ui/switch'
import { useStore } from '../../stores/useStore'
import { useScopes } from '../../hooks/useScopes'
import { AddMemberModal } from './AddMemberModal'
import { ShareNotebookModal } from './ShareNotebookModal'
import { ApiService } from '../../services/api'
import { showToast } from '../../utils/toast'
import type { Folder, FolderDashboard } from '../../types/folder'
import { rewriteDashboardHtmlForBackend, ensureBaseHref, getBackendUrlForHtmlProcessing, injectViewerConfig } from '../../utils/dashboardHtml'

interface FolderDetailProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  folder: Folder | null
}

export function FolderDetail({ open, onOpenChange, folder }: FolderDetailProps) {
  const navigate = useNavigate()
  const { userId, canManageFolderMembers, canShareNotebookToFolder } = useScopes()
  const {
    folderMembers,
    folderNotebooks,
    folderDashboards,
    fetchFolderMembers,
    fetchFolderNotebooks,
    fetchFolderDashboards,
    removeFolderMember,
    unshareNotebookFromFolder,
    unshareDashboardFromFolder,
    cloneNotebook,
    updateFolder,
    updateSnapshot,
  } = useStore()

  const [activeTab, setActiveTab] = useState<'notebooks' | 'dashboards' | 'members'>('notebooks')
  const [showAddMemberModal, setShowAddMemberModal] = useState(false)
  const [showShareNotebookModal, setShowShareNotebookModal] = useState(false)
  const [loading, setLoading] = useState(false)
  const [removingMember, setRemovingMember] = useState<string | null>(null)
  const [unsharingNotebook, setUnsharingNotebook] = useState<string | null>(null)
  const [unsharingDashboard, setUnsharingDashboard] = useState<string | null>(null)
  const [cloningNotebook, setCloningNotebook] = useState<string | null>(null)
  const [updatingSnapshot, setUpdatingSnapshot] = useState<string | null>(null)
  const [showEditDialog, setShowEditDialog] = useState(false)
  const [editName, setEditName] = useState('')
  const [editDescription, setEditDescription] = useState('')
  const [editIsPublic, setEditIsPublic] = useState(false)
  const [updating, setUpdating] = useState(false)
  // Dashboard preview state
  const [selectedDashboard, setSelectedDashboard] = useState<FolderDashboard | null>(null)
  const [dashboardHtml, setDashboardHtml] = useState<string>('')
  const [loadingDashboardPreview, setLoadingDashboardPreview] = useState(false)

  const loadFolderData = useCallback(async (folderId: string) => {
    setLoading(true)
    try {
      await Promise.all([
        fetchFolderMembers(folderId),
        fetchFolderNotebooks(folderId),
        fetchFolderDashboards(folderId),
      ])
    } finally {
      setLoading(false)
    }
  }, [fetchFolderMembers, fetchFolderNotebooks, fetchFolderDashboards])

  useEffect(() => {
    if (open && folder) {
      loadFolderData(folder.id)
    }
  }, [open, folder, loadFolderData])

  const handleRemoveMember = async (memberId: string) => {
    if (!folder) return
    try {
      setRemovingMember(memberId)
      await removeFolderMember(folder.id, memberId)
    } catch (err) {
      console.error('Failed to remove member:', err)
    } finally {
      setRemovingMember(null)
    }
  }

  const handleUnshareNotebook = async (notebookId: string) => {
    if (!folder) return
    try {
      setUnsharingNotebook(notebookId)
      await unshareNotebookFromFolder(folder.id, notebookId)
    } catch (err) {
      console.error('Failed to unshare notebook:', err)
    } finally {
      setUnsharingNotebook(null)
    }
  }

  const handleCloneNotebook = async (notebookId: string, notebookName: string) => {
    if (!folder) return
    try {
      setCloningNotebook(notebookId)
      const result = await cloneNotebook(folder.id, notebookId, `${notebookName} (Copy)`)
      // Navigate to the cloned notebook
      onOpenChange(false)
      navigate(`/notebook/${result.notebook_id}`)
    } catch (err) {
      console.error('Failed to clone notebook:', err)
    } finally {
      setCloningNotebook(null)
    }
  }

  const handleUpdateSnapshot = async (notebookId: string) => {
    if (!folder) return
    try {
      setUpdatingSnapshot(notebookId)
      await updateSnapshot(folder.id, notebookId)
      showToast.success('Snapshot updated with latest notebook data')
    } catch (err) {
      console.error('Failed to update snapshot:', err)
      showToast.error('Failed to update snapshot')
    } finally {
      setUpdatingSnapshot(null)
    }
  }

  const handleUnshareDashboard = async (dashboardId: string) => {
    if (!folder) return
    try {
      setUnsharingDashboard(dashboardId)
      await unshareDashboardFromFolder(folder.id, dashboardId)
    } catch (err) {
      console.error('Failed to unshare dashboard:', err)
    } finally {
      setUnsharingDashboard(null)
    }
  }

  const handleViewDashboard = async (dashboard: FolderDashboard) => {
    if (!dashboard.dashboard_notebook_id || !dashboard.dashboard_version) {
      console.error('Dashboard is missing notebook_id or version')
      return
    }
    try {
      setSelectedDashboard(dashboard)
      setLoadingDashboardPreview(true)
      setDashboardHtml('')
      const html = await ApiService.getNotebookHtmlVersion(
        dashboard.dashboard_notebook_id,
        dashboard.dashboard_version
      )

      const backendUrl = await getBackendUrlForHtmlProcessing()
      const rewritten = rewriteDashboardHtmlForBackend(html, backendUrl)
      const withViewer = injectViewerConfig(rewritten, dashboard.dashboard_id)
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

  const handleEditClick = () => {
    if (!folder) return
    setEditName(folder.name)
    setEditDescription(folder.description || '')
    setEditIsPublic(folder.is_public)
    setShowEditDialog(true)
  }

  const handleUpdateFolder = async () => {
    if (!folder || !editName.trim()) return
    try {
      setUpdating(true)
      await updateFolder(folder.id, editName.trim(), editDescription.trim() || undefined, editIsPublic)
      setShowEditDialog(false)
    } catch (err) {
      console.error('Failed to update folder:', err)
    } finally {
      setUpdating(false)
    }
  }

  // Check if current user can manage members (folder creator or admin/owner)
  const canManageMembers = canManageFolderMembers || folder?.created_by === userId

  const formatTimeAgo = (dateString: string): string => {
    const date = new Date(dateString)
    const now = new Date()
    const diffInMs = now.getTime() - date.getTime()
    const diffInDays = Math.floor(diffInMs / (1000 * 60 * 60 * 24))
    if (diffInDays === 0) return 'today'
    if (diffInDays === 1) return 'yesterday'
    return `${diffInDays} days ago`
  }

  if (!folder) return null

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-2xl max-h-[80vh] bg-[#2a2a2a] border-[#444444] overflow-hidden flex flex-col">
          <DialogHeader className="flex-shrink-0">
            <div className="flex items-center justify-between pr-8">
              <div className="flex items-center gap-3">
                <DialogTitle className="text-white">{folder.name}</DialogTitle>
                {(canManageFolderMembers || folder.created_by === userId) && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={handleEditClick}
                    className="text-gray-400 hover:text-white hover:bg-gray-800 h-7 w-7 p-0"
                  >
                    <Pencil className="w-4 h-4" />
                  </Button>
                )}
              </div>
            </div>
            {folder.description && (
              <p className="text-sm text-gray-400 mt-1">{folder.description}</p>
            )}
          </DialogHeader>

          <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as 'notebooks' | 'dashboards' | 'members')} className="flex-1 flex flex-col overflow-hidden">
            <TabsList className="bg-[#1a1a1a] border-b border-gray-800 w-full grid grid-cols-3 flex-shrink-0">
              <TabsTrigger value="notebooks" className="data-[state=active]:bg-brand-orange/10 data-[state=active]:text-brand-orange">
                Notebooks ({folderNotebooks.length})
              </TabsTrigger>
              <TabsTrigger value="dashboards" className="data-[state=active]:bg-brand-orange/10 data-[state=active]:text-brand-orange">
                Dashboards ({folderDashboards.length})
              </TabsTrigger>
              <TabsTrigger value="members" className="data-[state=active]:bg-brand-orange/10 data-[state=active]:text-brand-orange">
                Members ({folderMembers.length})
              </TabsTrigger>
            </TabsList>

            <div className="flex-1 overflow-y-auto custom-scrollbar">
              {loading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
                </div>
              ) : (
                <>
                  {/* Notebooks Tab */}
                  <TabsContent value="notebooks" className="mt-0 p-4 space-y-4">
                    {canShareNotebookToFolder && (
                      <div className="flex justify-end">
                        <Button
                          variant="brand-primary"
                          size="sm"
                          onClick={() => setShowShareNotebookModal(true)}
                        >
                          <BookOpen className="w-4 h-4 mr-2" />
                          Share Notebook
                        </Button>
                      </div>
                    )}

                    {folderNotebooks.length === 0 ? (
                      <Card className="p-8 text-center bg-[#1a1a1a] border-gray-800">
                        <div className="w-12 h-12 bg-brand-orange/10 rounded-full flex items-center justify-center mx-auto mb-3">
                          <BookOpen className="w-6 h-6 text-brand-orange" />
                        </div>
                        <h3 className="text-lg font-medium text-white mb-2">No Notebooks Shared</h3>
                        <p className="text-sm text-gray-400">
                          Share a notebook to this folder for members to view and clone.
                        </p>
                      </Card>
                    ) : (
                      <div className="space-y-3">
                        {folderNotebooks.map((notebook) => (
                          <Card
                            key={notebook.id}
                            className="p-4 bg-[#1a1a1a] border-gray-800 hover:border-gray-700 transition-colors"
                          >
                            <div className="flex items-center justify-between">
                              <div className="flex-1">
                                <div className="flex items-center gap-2">
                                  <h4 className="text-white font-medium">
                                    {notebook.notebook_name || 'Untitled Notebook'}
                                  </h4>
                                  {notebook.is_snapshot ? (
                                    <Badge variant="secondary" className="text-xs bg-purple-900/30 text-purple-400 border-purple-700">
                                      <Camera className="w-3 h-3 mr-1" />
                                      Snapshot
                                    </Badge>
                                  ) : (
                                    <Badge variant="secondary" className="text-xs bg-green-900/30 text-green-400 border-green-700">
                                      <Radio className="w-3 h-3 mr-1" />
                                      Live
                                    </Badge>
                                  )}
                                </div>
                                <p className="text-xs text-gray-500 mt-1">
                                  Shared by {notebook.shared_by_user?.full_name || notebook.shared_by_user?.email || 'Unknown'} {formatTimeAgo(notebook.created_at)}
                                  {notebook.is_snapshot && notebook.snapshot_updated_at && (
                                    <span className="ml-2">• Updated {formatTimeAgo(notebook.snapshot_updated_at)}</span>
                                  )}
                                </p>
                              </div>
                              <div className="flex items-center gap-2 ml-4">
                                {/* Update Snapshot button - only for owner of snapshot shares */}
                                {notebook.is_snapshot && notebook.shared_by === userId && (
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    onClick={() => handleUpdateSnapshot(notebook.notebook_id)}
                                    disabled={updatingSnapshot === notebook.notebook_id}
                                    className="text-gray-400 hover:text-purple-400 hover:bg-gray-800"
                                    title="Update snapshot to current notebook state"
                                  >
                                    {updatingSnapshot === notebook.notebook_id ? (
                                      <Loader2 className="w-4 h-4 animate-spin" />
                                    ) : (
                                      <RefreshCw className="w-4 h-4" />
                                    )}
                                  </Button>
                                )}
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  onClick={() => handleCloneNotebook(notebook.notebook_id, notebook.notebook_name || 'Untitled')}
                                  disabled={cloningNotebook === notebook.notebook_id}
                                  className="text-gray-400 hover:text-white hover:bg-gray-800"
                                  title="Clone notebook"
                                >
                                  {cloningNotebook === notebook.notebook_id ? (
                                    <Loader2 className="w-4 h-4 animate-spin" />
                                  ) : (
                                    <Copy className="w-4 h-4" />
                                  )}
                                </Button>
                                {notebook.shared_by === userId && (
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    onClick={() => handleUnshareNotebook(notebook.notebook_id)}
                                    disabled={unsharingNotebook === notebook.notebook_id}
                                    className="text-gray-400 hover:text-red-400 hover:bg-gray-800"
                                    title="Unshare notebook"
                                  >
                                    {unsharingNotebook === notebook.notebook_id ? (
                                      <Loader2 className="w-4 h-4 animate-spin" />
                                    ) : (
                                      <X className="w-4 h-4" />
                                    )}
                                  </Button>
                                )}
                              </div>
                            </div>
                          </Card>
                        ))}
                      </div>
                    )}
                  </TabsContent>

                  {/* Dashboards Tab */}
                  <TabsContent value="dashboards" className="mt-0 p-4 space-y-4">
                    {folderDashboards.length === 0 ? (
                      <Card className="p-8 text-center bg-[#1a1a1a] border-gray-800">
                        <div className="w-12 h-12 bg-brand-orange/10 rounded-full flex items-center justify-center mx-auto mb-3">
                          <LayoutDashboard className="w-6 h-6 text-brand-orange" />
                        </div>
                        <h3 className="text-lg font-medium text-white mb-2">No Dashboards Shared</h3>
                        <p className="text-sm text-gray-400">
                          Share a dashboard to this folder for members to view.
                        </p>
                      </Card>
                    ) : (
                      <div className="space-y-3">
                        {folderDashboards.map((dashboard) => (
                          <Card
                            key={dashboard.id}
                            className="p-4 bg-[#1a1a1a] border-gray-800 hover:border-gray-700 transition-colors"
                          >
                            <div className="flex items-center justify-between">
                              <div className="flex-1">
                                <div className="flex items-center gap-2">
                                  <h4 className="text-white font-medium">
                                    {dashboard.dashboard_notebook_name || `Dashboard v${dashboard.dashboard_version || 1}`}
                                  </h4>
                                  {dashboard.is_snapshot ? (
                                    <Badge variant="secondary" className="text-xs bg-purple-900/30 text-purple-400 border-purple-700">
                                      <Camera className="w-3 h-3 mr-1" />
                                      Snapshot
                                    </Badge>
                                  ) : (
                                    <Badge variant="secondary" className="text-xs bg-green-900/30 text-green-400 border-green-700">
                                      <Radio className="w-3 h-3 mr-1" />
                                      Live
                                    </Badge>
                                  )}
                                </div>
                                <p className="text-xs text-gray-500 mt-1">
                                  Shared by {dashboard.shared_by_user?.full_name || dashboard.shared_by_user?.email || 'Unknown'} {formatTimeAgo(dashboard.created_at)}
                                  {dashboard.is_snapshot && dashboard.snapshot_updated_at && (
                                    <span className="ml-2">• Updated {formatTimeAgo(dashboard.snapshot_updated_at)}</span>
                                  )}
                                </p>
                              </div>
                              <div className="flex items-center gap-2 ml-4">
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  onClick={() => handleViewDashboard(dashboard)}
                                  className="text-gray-400 hover:text-white hover:bg-gray-800"
                                  title="View dashboard"
                                >
                                  <Eye className="w-4 h-4" />
                                </Button>
                                {dashboard.shared_by === userId && (
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    onClick={() => handleUnshareDashboard(dashboard.dashboard_id)}
                                    disabled={unsharingDashboard === dashboard.dashboard_id}
                                    className="text-gray-400 hover:text-red-400 hover:bg-gray-800"
                                    title="Unshare dashboard"
                                  >
                                    {unsharingDashboard === dashboard.dashboard_id ? (
                                      <Loader2 className="w-4 h-4 animate-spin" />
                                    ) : (
                                      <X className="w-4 h-4" />
                                    )}
                                  </Button>
                                )}
                              </div>
                            </div>
                          </Card>
                        ))}
                      </div>
                    )}
                  </TabsContent>

                  {/* Members Tab */}
                  <TabsContent value="members" className="mt-0 p-4 space-y-4">
                    {canManageMembers && (
                      <div className="flex justify-end">
                        <Button
                          variant="brand-primary"
                          size="sm"
                          onClick={() => setShowAddMemberModal(true)}
                        >
                          <UserPlus className="w-4 h-4 mr-2" />
                          Add Member
                        </Button>
                      </div>
                    )}

                    {folderMembers.length === 0 ? (
                      <Card className="p-8 text-center bg-[#1a1a1a] border-gray-800">
                        <div className="w-12 h-12 bg-brand-orange/10 rounded-full flex items-center justify-center mx-auto mb-3">
                          <UserPlus className="w-6 h-6 text-brand-orange" />
                        </div>
                        <h3 className="text-lg font-medium text-white mb-2">No Members</h3>
                        <p className="text-sm text-gray-400">
                          Add team members to give them access to this folder.
                        </p>
                      </Card>
                    ) : (
                      <div className="space-y-3">
                        {folderMembers.map((member) => (
                          <Card
                            key={member.id}
                            className="p-4 bg-[#1a1a1a] border-gray-800"
                          >
                            <div className="flex items-center justify-between">
                              <div className="flex-1">
                                <h4 className="text-white font-medium">
                                  {member.user?.full_name || member.user?.email || 'Unknown User'}
                                  {member.user_id === folder.created_by && (
                                    <span className="ml-2 text-xs text-brand-orange">(Creator)</span>
                                  )}
                                </h4>
                                <p className="text-sm text-gray-400">
                                  {member.user?.email}
                                </p>
                                <p className="text-xs text-gray-500 mt-1">
                                  Added {formatTimeAgo(member.created_at)}
                                </p>
                              </div>
                              {canManageMembers && member.user_id !== folder.created_by && (
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  onClick={() => handleRemoveMember(member.id)}
                                  disabled={removingMember === member.id}
                                  className="text-gray-400 hover:text-red-400 hover:bg-gray-800 ml-4"
                                  title="Remove member"
                                >
                                  {removingMember === member.id ? (
                                    <Loader2 className="w-4 h-4 animate-spin" />
                                  ) : (
                                    <Trash2 className="w-4 h-4" />
                                  )}
                                </Button>
                              )}
                            </div>
                          </Card>
                        ))}
                      </div>
                    )}
                  </TabsContent>
                </>
              )}
            </div>
          </Tabs>
        </DialogContent>
      </Dialog>

      {/* Add Member Modal */}
      <AddMemberModal
        open={showAddMemberModal}
        onOpenChange={setShowAddMemberModal}
        folderId={folder.id}
        existingMembers={folderMembers}
      />

      {/* Share Notebook Modal */}
      <ShareNotebookModal
        open={showShareNotebookModal}
        onOpenChange={setShowShareNotebookModal}
        folderId={folder.id}
        existingNotebooks={folderNotebooks}
      />

      {/* Edit Folder Dialog */}
      <Dialog open={showEditDialog} onOpenChange={(open) => {
        if (!open && updating) return
        setShowEditDialog(open)
      }}>
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
                  <Label htmlFor="edit-folder-public-modal" className="text-white cursor-pointer">
                    Public folder
                  </Label>
                  <p className="text-xs text-gray-400">Everyone in your team can view this folder</p>
                </div>
              </div>
              <Switch id="edit-folder-public-modal" checked={editIsPublic} onCheckedChange={setEditIsPublic} />
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

      {/* Dashboard Loading Overlay */}
      {loadingDashboardPreview && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="flex items-center gap-3 bg-[#1a1a1a] px-6 py-4 rounded-lg">
            <Loader2 className="w-5 h-5 text-brand-orange animate-spin" />
            <span className="text-white">Loading dashboard...</span>
          </div>
        </div>
      )}

      {/* Dashboard Preview Modal - Full Screen */}
      <Dialog open={!!selectedDashboard && !!dashboardHtml} onOpenChange={(open) => !open && handleCloseDashboardPreview()}>
        <DialogContent className="max-w-[95vw] w-[95vw] h-[90vh] p-0 bg-white overflow-hidden">
          <div className="relative w-full h-full">
            <button
              onClick={handleCloseDashboardPreview}
              className="absolute top-4 right-4 z-10 w-10 h-10 bg-gray-900/80 hover:bg-gray-900 rounded-full flex items-center justify-center transition-colors"
            >
              <X className="w-5 h-5 text-white" />
            </button>
            {dashboardHtml && (
              <iframe
                srcDoc={dashboardHtml}
                className="w-full h-full border-0"
                title="Dashboard Preview"
                sandbox="allow-scripts allow-same-origin"
              />
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
