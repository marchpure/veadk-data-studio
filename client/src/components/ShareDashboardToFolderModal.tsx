import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog'
import {
  Share2,
  Trash2,
  Loader2,
  FolderOpen,
  FolderPlus,
  Globe,
} from 'lucide-react'
import { ApiService } from '../services/api'
import type { DashboardVersion } from '../services/api'
import { useStore } from '../stores/useStore'
import type { Folder, DashboardFolder } from '../types/folder'

interface ShareDashboardToFolderModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  dashboardId: string
  dashboardVersion?: number
  notebookId?: string
  notebookName?: string
}

export default function ShareDashboardToFolderModal({
  open,
  onOpenChange,
  dashboardId,
  dashboardVersion,
  notebookId,
  notebookName,
}: ShareDashboardToFolderModalProps) {
  const navigate = useNavigate()

  // State
  const [sharedFolders, setSharedFolders] = useState<DashboardFolder[]>([])
  const [availableFolders, setAvailableFolders] = useState<Folder[]>([])
  const [availableVersions, setAvailableVersions] = useState<DashboardVersion[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [selectedFolderId, setSelectedFolderId] = useState<string>('')
  const [selectedVersionId, setSelectedVersionId] = useState<string>(dashboardId)
  const [isSharing, setIsSharing] = useState(false)
  const [unsharingFolderId, setUnsharingFolderId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showCreateFolder, setShowCreateFolder] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')
  const [newFolderIsPublic, setNewFolderIsPublic] = useState(false)
  const [isCreatingFolder, setIsCreatingFolder] = useState(false)

  // Get folders from store
  const folders = useStore((state) => state.folders)
  const fetchFolders = useStore((state) => state.fetchFolders)
  const createFolder = useStore((state) => state.createFolder)

  // Load data when modal opens
  useEffect(() => {
    if (open && dashboardId) {
      loadSharedFolders()
      fetchFolders()
      if (notebookId) {
        loadAvailableVersions()
      }
    }
  }, [open, dashboardId, notebookId])

  // Update selected version when dashboardId changes
  useEffect(() => {
    if (dashboardId) {
      setSelectedVersionId(dashboardId)
    }
  }, [dashboardId])

  // Update available folders when folders or sharedFolders change
  useEffect(() => {
    const sharedFolderIds = new Set(sharedFolders.map((sf) => sf.folder_id))
    setAvailableFolders(folders.filter((f) => !sharedFolderIds.has(f.id)))
  }, [folders, sharedFolders])

  // Reset state when modal closes
  useEffect(() => {
    if (!open) {
      setSelectedFolderId('')
      setSelectedVersionId(dashboardId)
      setError(null)
      setShowCreateFolder(false)
      setNewFolderName('')
      setNewFolderIsPublic(false)
    }
  }, [open, dashboardId])

  const loadAvailableVersions = async () => {
    if (!notebookId) return
    try {
      const versions = await ApiService.getNotebookDashboardVersions(notebookId)
      setAvailableVersions(versions.sort((a, b) => b.version_num - a.version_num))
    } catch (err) {
      console.error('Error loading dashboard versions:', err)
    }
  }

  const loadSharedFolders = async () => {
    setIsLoading(true)
    try {
      const response = await ApiService.getDashboardFolders(dashboardId)
      setSharedFolders(response.items)
    } catch (err) {
      console.error('Error loading shared folders:', err)
    } finally {
      setIsLoading(false)
    }
  }

  const handleShareToFolder = async () => {
    if (!selectedFolderId || !selectedVersionId) return

    setIsSharing(true)
    setError(null)
    try {
      await ApiService.shareDashboardToFolder(selectedFolderId, selectedVersionId)
      setSelectedFolderId('')
      setSelectedVersionId(dashboardId)
      await loadSharedFolders()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to share to folder')
      console.error('Error sharing to folder:', err)
    } finally {
      setIsSharing(false)
    }
  }

  const handleUnshareFromFolder = async (folderId: string) => {
    setUnsharingFolderId(folderId)
    setError(null)
    try {
      await ApiService.unshareDashboardFromFolder(folderId, dashboardId)
      setSharedFolders((prev) => prev.filter((sf) => sf.folder_id !== folderId))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to unshare from folder')
      console.error('Error unsharing from folder:', err)
    } finally {
      setUnsharingFolderId(null)
    }
  }

  const handleCreateFolder = async () => {
    if (!newFolderName.trim()) return
    setIsCreatingFolder(true)
    setError(null)
    try {
      const newFolder = await createFolder(newFolderName.trim(), undefined, newFolderIsPublic)
      setNewFolderName('')
      setNewFolderIsPublic(false)
      setShowCreateFolder(false)
      setSelectedFolderId(newFolder.id)
      await fetchFolders()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create folder')
    } finally {
      setIsCreatingFolder(false)
    }
  }

  const formatRelativeTime = (dateStr: string) => {
    const date = new Date(dateStr)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMs / 3600000)
    const diffDays = Math.floor(diffMs / 86400000)

    if (diffMins < 1) return 'just now'
    if (diffMins < 60) return `${diffMins}m ago`
    if (diffHours < 24) return `${diffHours}h ago`
    if (diffDays < 7) return `${diffDays}d ago`
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md bg-[#1a1a1a] border-[#404040] max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="text-white flex items-center gap-2">
            <FolderOpen className="w-4 h-4" />
            Share Dashboard to Folder
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 flex-1 overflow-hidden flex flex-col">
          {/* Description */}
          <p className="text-xs text-gray-500">
            Share this dashboard with folder members.
            {notebookName && <span className="text-gray-400"> ({notebookName})</span>}
            {dashboardVersion && <span className="text-gray-400"> v{dashboardVersion}</span>}
          </p>

          {/* Loading state */}
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-6 h-6 text-gray-400 animate-spin" />
            </div>
          ) : (
            <>
              {/* Share to folder section */}
              <div className="p-4 bg-[#252525] rounded-lg border border-[#333]">
                <h3 className="text-sm font-medium text-white mb-3">Share to Folder</h3>

                {availableFolders.length === 0 ? (
                  folders.length === 0 ? (
                    <div className="space-y-3">
                      <p className="text-sm text-gray-400">No folders available. Create one to get started.</p>

                      {/* Inline folder creation for empty state */}
                      <div className="p-3 bg-[#1a1a1a] rounded-lg border border-[#404040]">
                        <input
                          type="text"
                          placeholder="Folder name"
                          value={newFolderName}
                          onChange={(e) => setNewFolderName(e.target.value)}
                          className="w-full px-3 py-2 text-sm bg-[#252525] border border-[#404040] rounded text-white mb-2 focus:outline-none focus:border-brand-orange"
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' && newFolderName.trim()) {
                              handleCreateFolder()
                            }
                          }}
                        />
                        <label className="flex items-center gap-2 text-xs text-gray-400 mb-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={newFolderIsPublic}
                            onChange={(e) => setNewFolderIsPublic(e.target.checked)}
                            className="rounded border-[#404040] bg-[#252525]"
                          />
                          <Globe className="w-3 h-3" />
                          Public folder (visible to all team members)
                        </label>
                        <button
                          onClick={handleCreateFolder}
                          disabled={!newFolderName.trim() || isCreatingFolder}
                          className="w-full px-3 py-1.5 text-xs bg-brand-orange hover:bg-brand-orange-hover text-white rounded disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-1"
                        >
                          {isCreatingFolder ? (
                            <>
                              <Loader2 className="w-3 h-3 animate-spin" />
                              Creating...
                            </>
                          ) : (
                            <>
                              <FolderPlus className="w-3 h-3" />
                              Create Folder
                            </>
                          )}
                        </button>
                      </div>
                    </div>
                  ) : (
                    <p className="text-sm text-gray-400">This dashboard is already shared to all your folders.</p>
                  )
                ) : (
                  <>
                    {showCreateFolder ? (
                      <>
                        {/* Create new folder form */}
                        <div className="mb-3 p-3 bg-[#1a1a1a] rounded-lg border border-[#404040]">
                          <div className="flex items-center justify-between mb-2">
                            <span className="text-xs text-gray-400">Create New Folder</span>
                            <button
                              onClick={() => {
                                setShowCreateFolder(false)
                                setNewFolderName('')
                                setNewFolderIsPublic(false)
                              }}
                              className="text-xs text-gray-500 hover:text-gray-300"
                            >
                              ← Back to select
                            </button>
                          </div>
                          <input
                            type="text"
                            placeholder="Folder name"
                            value={newFolderName}
                            onChange={(e) => setNewFolderName(e.target.value)}
                            className="w-full px-3 py-2 text-sm bg-[#252525] border border-[#404040] rounded text-white mb-2 focus:outline-none focus:border-brand-orange"
                            autoFocus
                            onKeyDown={(e) => {
                              if (e.key === 'Enter' && newFolderName.trim()) {
                                handleCreateFolder()
                              }
                            }}
                          />
                          <label className="flex items-center gap-2 text-xs text-gray-400 mb-3 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={newFolderIsPublic}
                              onChange={(e) => setNewFolderIsPublic(e.target.checked)}
                              className="rounded border-[#404040] bg-[#252525]"
                            />
                            <Globe className="w-3 h-3" />
                            Public folder (visible to all team members)
                          </label>
                          <button
                            onClick={handleCreateFolder}
                            disabled={!newFolderName.trim() || isCreatingFolder}
                            className="w-full px-3 py-2 text-sm bg-brand-orange hover:bg-brand-orange-hover text-white rounded disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-1"
                          >
                            {isCreatingFolder ? (
                              <>
                                <Loader2 className="w-3 h-3 animate-spin" />
                                Creating...
                              </>
                            ) : (
                              <>
                                <FolderPlus className="w-3 h-3" />
                                Create & Select Folder
                              </>
                            )}
                          </button>
                        </div>
                      </>
                    ) : (
                      <>
                        {/* Folder select */}
                        <div className="mb-3">
                          <label className="text-xs text-gray-400 mb-1 block">Select Folder</label>
                          <select
                            value={selectedFolderId}
                            onChange={(e) => setSelectedFolderId(e.target.value)}
                            className="w-full px-3 py-2 text-sm bg-[#1a1a1a] border border-[#404040] rounded-lg text-white focus:outline-none focus:border-brand-orange"
                            disabled={isSharing}
                          >
                            <option value="">Select a folder</option>
                            {availableFolders.map((folder) => (
                              <option key={folder.id} value={folder.id}>
                                {folder.name} {folder.is_public ? '(Public)' : '(Private)'}
                              </option>
                            ))}
                          </select>
                        </div>

                        {/* Create folder link */}
                        <button
                          onClick={() => setShowCreateFolder(true)}
                          className="text-xs text-brand-orange hover:underline mb-3 flex items-center gap-1"
                        >
                          <FolderPlus className="w-3 h-3" />
                          Create New Folder
                        </button>
                      </>
                    )}

                    {/* Version picker */}
                    {availableVersions.length > 0 && (
                      <div className="mb-3">
                        <label className="text-xs text-gray-400 mb-1 block">Select Version</label>
                        <select
                          value={selectedVersionId}
                          onChange={(e) => setSelectedVersionId(e.target.value)}
                          className="w-full px-3 py-2 text-sm bg-[#1a1a1a] border border-[#404040] rounded-lg text-white focus:outline-none focus:border-brand-orange"
                          disabled={isSharing}
                        >
                          {availableVersions.map((version, index) => (
                            <option key={version.id} value={version.id}>
                              Version {version.version_num}{index === 0 ? ' (Latest)' : ''}
                            </option>
                          ))}
                        </select>
                      </div>
                    )}

                    {/* Share button */}
                    <button
                      onClick={handleShareToFolder}
                      disabled={isSharing || !selectedFolderId || !selectedVersionId}
                      className="w-full px-4 py-2.5 text-sm font-medium bg-brand-orange hover:bg-brand-orange-hover text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                    >
                      {isSharing ? (
                        <>
                          <Loader2 className="w-4 h-4 animate-spin" />
                          Sharing...
                        </>
                      ) : (
                        <>
                          <Share2 className="w-4 h-4" />
                          Share to Folder
                        </>
                      )}
                    </button>
                  </>
                )}
              </div>

              {/* Shared folders list */}
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-medium text-white">Shared to Folders</h3>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-500">
                    {sharedFolders.length} {sharedFolders.length === 1 ? 'folder' : 'folders'}
                  </span>
                  <button
                    onClick={() => {
                      onOpenChange(false)
                      navigate('/folders')
                    }}
                    className="text-xs text-brand-orange hover:underline"
                  >
                    Manage →
                  </button>
                </div>
              </div>

              {sharedFolders.length === 0 ? (
                <div className="text-center py-6 text-gray-500 text-sm">
                  Not shared to any folders yet. Share to a folder above.
                </div>
              ) : (
                <div className="space-y-2 overflow-y-auto flex-1 pr-1 scrollbar-thin scrollbar-thumb-[#404040] scrollbar-track-transparent">
                  {sharedFolders.map((sf) => (
                    <div key={sf.id} className="p-3 bg-[#252525] rounded-lg border border-green-900/30">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 min-w-0 flex-1">
                          <div className="w-6 h-6 rounded-full bg-green-900/30 flex items-center justify-center flex-shrink-0">
                            <FolderOpen className="w-3 h-3 text-green-400" />
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2">
                              <span className="text-sm text-white font-medium truncate">{sf.folder_name}</span>
                              <span className="text-xs text-green-400 bg-green-900/20 px-1.5 py-0.5 rounded flex-shrink-0">
                                Shared
                              </span>
                            </div>
                            <div className="flex items-center gap-1.5 text-xs text-gray-500 mt-0.5">
                              {sf.shared_by_user?.full_name && (
                                <>
                                  <span>by {sf.shared_by_user.full_name}</span>
                                  <span>·</span>
                                </>
                              )}
                              <span>{formatRelativeTime(sf.created_at)}</span>
                            </div>
                          </div>
                        </div>
                        <button
                          onClick={() => handleUnshareFromFolder(sf.folder_id)}
                          disabled={unsharingFolderId === sf.folder_id}
                          className="p-1.5 text-gray-400 hover:text-red-400 hover:bg-[#333] rounded transition-colors disabled:opacity-50 ml-2 flex-shrink-0"
                          title="Unshare from folder"
                        >
                          {unsharingFolderId === sf.folder_id ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                          ) : (
                            <Trash2 className="w-4 h-4" />
                          )}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}

          {/* Error message */}
          {error && (
            <div className="text-red-400 text-sm text-center bg-red-400/10 py-2 px-3 rounded-lg">{error}</div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
