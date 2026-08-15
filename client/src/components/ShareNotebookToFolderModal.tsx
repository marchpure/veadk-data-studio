import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog'
import {
  Share2,
  Trash2,
  Loader2,
  FolderOpen,
  FolderPlus,
  Camera,
  Radio,
  Globe,
} from 'lucide-react'
import { ApiService } from '../services/api'
import { useStore } from '../stores/useStore'
import type { Folder, NotebookFolder } from '../types/folder'

interface ShareNotebookToFolderModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  notebookId: string
  notebookName?: string
}

export default function ShareNotebookToFolderModal({
  open,
  onOpenChange,
  notebookId,
  notebookName,
}: ShareNotebookToFolderModalProps) {
  const navigate = useNavigate()

  // State
  const [sharedFolders, setSharedFolders] = useState<NotebookFolder[]>([])
  const [availableFolders, setAvailableFolders] = useState<Folder[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [selectedFolderId, setSelectedFolderId] = useState<string>('')
  const [isSnapshot, setIsSnapshot] = useState(false)
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
  const shareNotebookToFolder = useStore((state) => state.shareNotebookToFolder)
  const unshareNotebookFromFolder = useStore((state) => state.unshareNotebookFromFolder)
  const createFolder = useStore((state) => state.createFolder)

  // Load data when modal opens
  useEffect(() => {
    if (open && notebookId) {
      loadSharedFolders()
      fetchFolders()
    }
  }, [open, notebookId])

  // Update available folders when folders or sharedFolders change
  useEffect(() => {
    const sharedFolderIds = new Set(sharedFolders.map((sf) => sf.folder_id))
    setAvailableFolders(folders.filter((f) => !sharedFolderIds.has(f.id)))
  }, [folders, sharedFolders])

  // Reset state when modal closes
  useEffect(() => {
    if (!open) {
      setSelectedFolderId('')
      setIsSnapshot(false)
      setError(null)
      setShowCreateFolder(false)
      setNewFolderName('')
      setNewFolderIsPublic(false)
    }
  }, [open])

  const loadSharedFolders = async () => {
    setIsLoading(true)
    try {
      const response = await ApiService.getNotebookFolders(notebookId)
      setSharedFolders(response.items)
    } catch (err) {
      console.error('Error loading shared folders:', err)
    } finally {
      setIsLoading(false)
    }
  }

  const handleShareToFolder = async () => {
    if (!selectedFolderId) return

    setIsSharing(true)
    setError(null)
    try {
      await shareNotebookToFolder(selectedFolderId, notebookId, isSnapshot)
      setSelectedFolderId('')
      setIsSnapshot(false)
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
      await unshareNotebookFromFolder(folderId, notebookId)
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
            Share Notebook to Folder
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 flex-1 overflow-hidden flex flex-col">
          {/* Description */}
          <p className="text-xs text-gray-500">
            Share this notebook with folder members.
            {notebookName && <span className="text-gray-400"> ({notebookName})</span>}
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
                    <p className="text-sm text-gray-400">This notebook is already shared to all your folders.</p>
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

                    {/* Live/Snapshot toggle */}
                    <div className="flex items-center justify-between mb-3 py-2">
                      <div>
                        <label className="text-sm text-white flex items-center gap-2">
                          {isSnapshot ? <Camera className="w-4 h-4" /> : <Radio className="w-4 h-4" />}
                          {isSnapshot ? 'Share as snapshot' : 'Share live'}
                        </label>
                        <p className="text-xs text-gray-500 mt-0.5">
                          {isSnapshot
                            ? 'Members will see a frozen copy. You can update it later.'
                            : 'Members will see live changes to the notebook.'}
                        </p>
                      </div>
                      <button
                        onClick={() => setIsSnapshot(!isSnapshot)}
                        className={`relative w-10 h-5 rounded-full transition-colors ${
                          isSnapshot ? 'bg-brand-orange' : 'bg-[#404040]'
                        }`}
                        disabled={isSharing}
                      >
                        <span
                          className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-transform ${
                            isSnapshot ? 'translate-x-5' : ''
                          }`}
                        />
                      </button>
                    </div>

                    {/* Share button */}
                    <button
                      onClick={handleShareToFolder}
                      disabled={isSharing || !selectedFolderId}
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
                    <div
                      key={sf.id}
                      className={`p-3 bg-[#252525] rounded-lg border ${
                        sf.is_snapshot ? 'border-purple-900/30' : 'border-green-900/30'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 min-w-0 flex-1">
                          <div
                            className={`w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 ${
                              sf.is_snapshot ? 'bg-purple-900/30' : 'bg-green-900/30'
                            }`}
                          >
                            <FolderOpen className={`w-3 h-3 ${sf.is_snapshot ? 'text-purple-400' : 'text-green-400'}`} />
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2">
                              <span className="text-sm text-white font-medium truncate">{sf.folder_name}</span>
                              {sf.is_snapshot ? (
                                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-xs bg-purple-900/20 text-purple-400 rounded flex-shrink-0">
                                  <Camera className="w-2.5 h-2.5" />
                                  Snapshot
                                </span>
                              ) : (
                                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-xs bg-green-900/20 text-green-400 rounded flex-shrink-0">
                                  <Radio className="w-2.5 h-2.5" />
                                  Live
                                </span>
                              )}
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
