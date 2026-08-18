import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useStore } from '../stores/useStore'
import { Button } from '../components/ui/button'
import { Card } from '../components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog'
import { Input } from '../components/ui/input'
import { Search, FolderOpen, Trash2, Users, BookOpen, Loader2, LayoutDashboard, ArrowLeft, FolderPlus } from 'lucide-react'
import { useScopes } from '../hooks/useScopes'
import { CreateFolderModal } from '../components/folders/CreateFolderModal'
import { useKnowledgeCenterPath } from '../contexts/EmbeddedModeContext'
import type { Folder } from '../types/folder'

export default function FoldersPage() {
  const navigate = useNavigate()
  const kcPath = useKnowledgeCenterPath()
  const { isViewer, canDeleteFolder, canCreateFolder } = useScopes()
  const folders = useStore(state => state.folders)
  const isLoadingFolders = useStore(state => state.isLoadingFolders)
  const folderError = useStore(state => state.folderError)
  const fetchFolders = useStore(state => state.fetchFolders)
  const deleteFolder = useStore(state => state.deleteFolder)

  const [searchQuery, setSearchQuery] = useState('')
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const [folderToDelete, setFolderToDelete] = useState<Folder | null>(null)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => {
    fetchFolders()
  }, [fetchFolders])

  const formatTimeAgo = (dateString: string): string => {
    const date = new Date(dateString)
    const now = new Date()
    const diffInMs = now.getTime() - date.getTime()
    const diffInMinutes = Math.floor(diffInMs / (1000 * 60))
    const diffInHours = Math.floor(diffInMs / (1000 * 60 * 60))
    const diffInDays = Math.floor(diffInMs / (1000 * 60 * 60 * 24))
    const diffInMonths = Math.floor(diffInDays / 30)
    const diffInYears = Math.floor(diffInDays / 365)

    if (diffInMinutes < 1) return 'just now'
    if (diffInMinutes < 60) return `${diffInMinutes} minute${diffInMinutes > 1 ? 's' : ''} ago`
    if (diffInHours < 24) return `${diffInHours} hour${diffInHours > 1 ? 's' : ''} ago`
    if (diffInDays < 30) return `${diffInDays} day${diffInDays > 1 ? 's' : ''} ago`
    if (diffInMonths < 12) return `${diffInMonths} month${diffInMonths > 1 ? 's' : ''} ago`
    return `${diffInYears} year${diffInYears > 1 ? 's' : ''} ago`
  }

  // Filter and sort folders
  const displayFolders = folders
    .filter((folder) => {
      if (!searchQuery) return true
      const query = searchQuery.toLowerCase()
      return (
        folder.name.toLowerCase().includes(query) ||
        (folder.description && folder.description.toLowerCase().includes(query))
      )
    })
    .sort((a, b) => {
      // Sort by most recent updated_at
      return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
    })

  const handleFolderClick = (folder: Folder) => {
    navigate(kcPath(`/folders/${folder.id}`))
  }

  const handleDeleteClick = (folder: Folder, event: React.MouseEvent) => {
    event.stopPropagation()
    setFolderToDelete(folder)
    setShowDeleteDialog(true)
  }

  const confirmDelete = async () => {
    if (!folderToDelete) return

    try {
      setDeleting(true)
      await deleteFolder(folderToDelete.id)
      setShowDeleteDialog(false)
      setFolderToDelete(null)
    } catch (error) {
      console.error('Failed to delete folder:', error)
    } finally {
      setDeleting(false)
    }
  }

  const cancelDelete = () => {
    setShowDeleteDialog(false)
    setFolderToDelete(null)
  }

  return (
    <div className="bg-[#0d0d0d] w-full h-full flex flex-col">
      {/* Header Section */}
      <div className="w-full px-8 pt-[50px] pb-8">
        <div className="max-w-[850px] mx-auto">
          {/* Title */}
          <div className="mb-8 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <button
                onClick={() => navigate(kcPath('/data-models'))}
                className="p-1.5 text-gray-400 hover:text-white transition-colors rounded hover:bg-gray-800"
                title="Back to home"
              >
                <ArrowLeft className="w-5 h-5" />
              </button>
              <h1 className="text-2xl font-bold text-white tracking-tight">
                {isViewer ? 'Dashboards' : 'Folders'}
              </h1>
            </div>
            {canCreateFolder && (
              <button
                onClick={() => setShowCreateModal(true)}
                className="flex items-center gap-2 bg-brand-orange hover:bg-brand-orange/90 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
              >
                <FolderPlus className="w-4 h-4" />
                New Folder
              </button>
            )}
          </div>

          {/* Search Bar */}
          <div className="relative">
            <Search className="absolute left-4 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-500" />
            <Input
              type="text"
              placeholder={isViewer ? "Search dashboards..." : "Search folders..."}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-12 pr-4 py-6 bg-transparent border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-brand-orange focus:ring-1 focus:ring-brand-orange/50"
            />
          </div>
        </div>
      </div>

      {/* Scrollable Content Section */}
      <div className="flex-1 overflow-y-auto custom-scrollbar min-h-0">
        <div className="w-full px-8 pb-6">
          {/* Error Message */}
          {folderError && (
            <div className="max-w-[850px] mx-auto mb-6">
              <div className="bg-red-900/20 border border-red-500 text-red-400 px-4 py-3 rounded-md">
                {folderError}
              </div>
            </div>
          )}

          {/* Loading State */}
          {isLoadingFolders ? (
            <div className="text-center py-12">
              <div className="animate-spin w-8 h-8 border-2 border-brand-orange border-t-transparent rounded-full mx-auto mb-4"></div>
              <p className="text-gray-400">{isViewer ? 'Loading dashboards...' : 'Loading folders...'}</p>
            </div>
          ) : (
            <>
              {/* Empty State */}
              {displayFolders.length === 0 ? (
                <div className="max-w-[850px] mx-auto">
                  <Card className="p-12 text-center bg-[#1a1a1a] border-gray-800">
                    <div className="max-w-md mx-auto">
                      <div className="w-16 h-16 bg-brand-orange/10 rounded-full flex items-center justify-center mx-auto mb-4">
                        {isViewer ? (
                          <LayoutDashboard className="w-8 h-8 text-brand-orange" />
                        ) : (
                          <FolderOpen className="w-8 h-8 text-brand-orange" />
                        )}
                      </div>
                      <h3 className="text-xl font-semibold text-white mb-2">
                        {isViewer ? 'No Dashboards' : 'No Folders'}
                      </h3>
                      <p className="text-gray-400 mb-6">
                        {searchQuery
                          ? isViewer ? 'No dashboards match your search.' : 'No folders match your search.'
                          : isViewer
                            ? 'No dashboards have been shared with you yet.'
                            : 'Create folders to organize and share notebooks with team members.'}
                      </p>
                    </div>
                  </Card>
                </div>
              ) : (
                <>
                  {/* Folder Cards */}
                  <div className="max-w-[850px] mx-auto grid grid-cols-1 md:grid-cols-2 gap-6">
                    {displayFolders.map((folder) => {
                      const timeAgo = formatTimeAgo(folder.updated_at)
                      return (
                        <Card
                          key={folder.id}
                          className="p-6 bg-[#1a1a1a] border-gray-800 hover:border-gray-700 transition-colors cursor-pointer"
                          onClick={() => handleFolderClick(folder)}
                        >
                          <div className="flex items-start justify-between mb-3">
                            <div className="flex-1">
                              {/* Folder Name */}
                              <div className="flex items-center gap-2 mb-2">
                                <FolderOpen className="w-5 h-5 text-brand-orange" />
                                <h3
                                  className="text-lg font-normal text-white"
                                  title={folder.name.length > 30 ? folder.name : undefined}
                                >
                                  {folder.name.length > 30
                                    ? `${folder.name.substring(0, 30)}...`
                                    : folder.name}
                                </h3>
                              </div>

                              {/* Description */}
                              <p className="text-sm text-gray-400 mb-3">
                                {folder.description || 'No description'}
                              </p>

                              {/* Stats */}
                              <div className="flex items-center gap-4 text-xs text-gray-500">
                                <div className="flex items-center gap-1">
                                  <Users className="w-3.5 h-3.5" />
                                  <span>{folder.member_count ?? 0} members</span>
                                </div>
                                <div className="flex items-center gap-1">
                                  <BookOpen className="w-3.5 h-3.5" />
                                  <span>{folder.notebook_count ?? 0} notebooks</span>
                                </div>
                              </div>

                              {/* Timestamp */}
                              <p className="text-xs text-gray-500 mt-2">
                                Updated {timeAgo}
                              </p>
                            </div>

                            {/* Action Buttons */}
                            <div className="flex gap-2 ml-4">
                              {canDeleteFolder(folder.created_by) && (
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  onClick={(e) => handleDeleteClick(folder, e)}
                                  disabled={deleting}
                                  className="text-gray-400 hover:text-red-400 hover:bg-gray-800"
                                >
                                  <Trash2 className="w-4 h-4" />
                                </Button>
                              )}
                            </div>
                          </div>
                        </Card>
                      )
                    })}
                  </div>
                </>
              )}
            </>
          )}
        </div>
      </div>

      {/* Delete Confirmation Dialog */}
      <Dialog open={showDeleteDialog} onOpenChange={(open) => {
        if (!open && deleting) return
        setShowDeleteDialog(open)
      }}>
        <DialogContent className="max-w-md bg-[#2a2a2a] border-[#444444]">
          <DialogHeader>
            <DialogTitle className="text-white">Delete Folder?</DialogTitle>
          </DialogHeader>

          <div className="space-y-4">
            <p className="text-sm text-[#aaaaaa]">
              This action will permanently delete <span className="font-semibold text-white">"{folderToDelete?.name}"</span> folder. Shared notebooks will be unshared but not deleted.
            </p>

            <div className="flex justify-end gap-2 mt-6">
              <Button
                variant="outline"
                onClick={cancelDelete}
                disabled={deleting}
                className="border-[#555555] text-white hover:bg-[#3a3a3a]"
              >
                Cancel
              </Button>
              <Button
                onClick={confirmDelete}
                disabled={deleting}
                className="bg-red-800 hover:bg-red-900 text-white"
              >
                {deleting ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Trash2 className="mr-2 h-4 w-4" />
                )}
                {deleting ? 'Deleting...' : 'Delete'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Create Folder Modal */}
      <CreateFolderModal
        open={showCreateModal}
        onOpenChange={setShowCreateModal}
      />
    </div>
  )
}
