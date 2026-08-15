import { useState, useMemo, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { BookOpen, Search, Pencil, Trash2, Share2 } from 'lucide-react'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog'
import { Input } from '../ui/input'
import { useNotebooks, useRenameNotebook, useDeleteNotebook } from '../../hooks/useNotebooks'
import { ApiService, type Notebook } from '../../services/api'
import { useScopes } from '../../hooks/useScopes'
import { useAppConfig } from '../../hooks/useAppConfig'
import ShareModal from '../ShareModal'
import ShareNotebookToFolderModal from '../ShareNotebookToFolderModal'
import ShareDashboardToFolderModal from '../ShareDashboardToFolderModal'

interface MyNotebooksSectionProps {
  onError?: (error: string | null) => void
}

interface NotebookCardProps {
  notebook: Notebook
  onClick: () => void
  onShare?: (e: React.MouseEvent) => void
  onEdit: (e: React.MouseEvent) => void
  onDelete: (e: React.MouseEvent) => void
  canEdit: boolean
  canDelete: boolean
  formatTimeAgo: (dateString: string) => string
}

function NotebookCard({ notebook, onClick, onShare, onEdit, onDelete, canEdit, canDelete, formatTimeAgo }: NotebookCardProps) {
  const notebookName = notebook.notebook_name || 'Untitled Notebook'

  return (
    <div
      onClick={onClick}
      className="group p-5 bg-[#1a1a1a] border border-gray-800 rounded-xl cursor-pointer hover:border-gray-700 transition-all"
    >
      <div className="flex items-start justify-between gap-3 mb-2">
        <p className="text-white text-sm flex-1 min-w-0 truncate" title={notebookName}>
          {notebookName}
        </p>
        <div className="flex items-center gap-1 flex-shrink-0">
          {onShare && (
            <button
              onClick={onShare}
              className="p-2 text-gray-500 hover:text-white transition-colors"
              title="Share notebook"
            >
              <Share2 className="w-4 h-4" />
            </button>
          )}
          {canEdit && (
            <button
              onClick={onEdit}
              className="p-2 text-gray-500 hover:text-white transition-colors"
              title="Rename notebook"
            >
              <Pencil className="w-4 h-4" />
            </button>
          )}
          {canDelete && (
            <button
              onClick={onDelete}
              className="p-2 text-gray-500 hover:text-red-400 transition-colors"
              title="Delete notebook"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
      <p className="text-gray-500 text-xs">
        Updated {formatTimeAgo(notebook.updated_at)}
      </p>
    </div>
  )
}

export default function MyNotebooksSection({ onError }: MyNotebooksSectionProps) {
  const navigate = useNavigate()
  const { canEditNotebook, canDeleteNotebook, canShareExternally } = useScopes()
  const { isSelfHosted } = useAppConfig()

  const [searchQuery, setSearchQuery] = useState('')

  const [editingNotebook, setEditingNotebook] = useState<Notebook | null>(null)
  const [editingName, setEditingName] = useState('')
  const [showEditDialog, setShowEditDialog] = useState(false)

  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [notebookToDelete, setNotebookToDelete] = useState<Notebook | null>(null)

  const [shareModalOpen, setShareModalOpen] = useState(false)
  const [shareNotebookToFolderOpen, setShareNotebookToFolderOpen] = useState(false)
  const [shareDashboardToFolderOpen, setShareDashboardToFolderOpen] = useState(false)
  const [notebookToShare, setNotebookToShare] = useState<Notebook | null>(null)
  const [latestDashboardVersion, setLatestDashboardVersion] = useState<number>(1)
  const [latestDashboardId, setLatestDashboardId] = useState<string | undefined>(undefined)
  const [pendingShareNotebook, setPendingShareNotebook] = useState<Notebook | null>(null)

  const { data: notebooks = [], isLoading, error } = useNotebooks()
  const renameMutation = useRenameNotebook()
  const deleteMutation = useDeleteNotebook()

  const onErrorRef = useRef(onError)
  onErrorRef.current = onError

  useEffect(() => {
    if (error) {
      onErrorRef.current?.('Failed to load notebooks')
    }
  }, [error])

  useEffect(() => {
    if (pendingShareNotebook) {
      setNotebookToShare(pendingShareNotebook)
      setShareModalOpen(true)
      setPendingShareNotebook(null)
    }
  }, [pendingShareNotebook, latestDashboardVersion])

  const displayNotebooks = useMemo(() => {
    let filtered = notebooks
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase()
      filtered = notebooks.filter(nb =>
        nb.notebook_name.toLowerCase().includes(query) ||
        (nb.description && nb.description.toLowerCase().includes(query))
      )
    }
    return filtered.sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
  }, [notebooks, searchQuery])

  const formatTimeAgo = (dateString: string): string => {
    const date = new Date(dateString)
    const now = new Date()
    const diffInMs = now.getTime() - date.getTime()
    const diffInMinutes = Math.floor(diffInMs / (1000 * 60))
    const diffInHours = Math.floor(diffInMs / (1000 * 60 * 60))
    const diffInDays = Math.floor(diffInMs / (1000 * 60 * 60 * 24))

    if (diffInMinutes < 1) return 'just now'
    if (diffInMinutes < 60) return `${diffInMinutes}m ago`
    if (diffInHours < 24) return `${diffInHours}h ago`
    if (diffInDays < 30) return `${diffInDays}d ago`
    return date.toLocaleDateString()
  }

  const handleNotebookClick = (notebookId: string) => {
    navigate(`/notebook/${notebookId}`)
  }

  const handleShareClick = async (notebook: Notebook, e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      const versions = await ApiService.getNotebookDashboardVersions(notebook.id)
      if (versions.length > 0) {
        const sortedVersions = versions.sort((a, b) => b.version_num - a.version_num)
        setLatestDashboardVersion(sortedVersions[0].version_num)
        setLatestDashboardId(sortedVersions[0].id)
      } else {
        setLatestDashboardVersion(1)
        setLatestDashboardId(undefined)
      }
    } catch (err) {
      console.error('Error loading dashboard versions:', err)
      setLatestDashboardVersion(1)
      setLatestDashboardId(undefined)
    }
    setPendingShareNotebook(notebook)
  }

  const handleEditClick = (notebook: Notebook, e: React.MouseEvent) => {
    e.stopPropagation()
    setEditingNotebook(notebook)
    setEditingName(notebook.notebook_name)
    setShowEditDialog(true)
  }

  const handleDeleteClick = (notebook: Notebook, e: React.MouseEvent) => {
    e.stopPropagation()
    setNotebookToDelete(notebook)
    setDeleteDialogOpen(true)
  }

  const handleRenameSubmit = () => {
    if (!editingNotebook || !editingName.trim()) return
    renameMutation.mutate(
      { notebookId: editingNotebook.id, newName: editingName.trim() },
      {
        onSuccess: () => {
          setShowEditDialog(false)
          setEditingNotebook(null)
          setEditingName('')
        }
      }
    )
  }

  const confirmDelete = () => {
    if (!notebookToDelete) return
    deleteMutation.mutate(notebookToDelete.id, {
      onSuccess: () => {
        setDeleteDialogOpen(false)
        setNotebookToDelete(null)
      },
    })
  }

  if (isLoading) {
    return (
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white">My Notebooks</h2>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="p-5 bg-[#1a1a1a] border border-gray-800 rounded-xl animate-pulse">
              <div className="h-4 bg-gray-800/50 rounded w-3/4 mb-2" />
              <div className="h-3 bg-gray-800/30 rounded w-1/3" />
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (notebooks.length === 0) {
    return (
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white">My Notebooks</h2>
        </div>
        <div className="text-center py-12 bg-[#1a1a1a] border border-gray-800 rounded-lg">
          <div className="w-16 h-16 bg-brand-orange/10 rounded-full flex items-center justify-center mx-auto mb-4">
            <BookOpen className="w-8 h-8 text-brand-orange" />
          </div>
          <h3 className="text-lg font-medium text-white mb-2">No Notebooks Yet</h3>
          <p className="text-gray-400 text-sm">Create your first notebook to get started</p>
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-white">My Notebooks</h2>
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-500" />
          <input
            type="text"
            placeholder="Search notebooks..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Escape') {
                setSearchQuery('')
              }
            }}
            className="w-56 pl-8 pr-3 py-1.5 bg-transparent border border-gray-700/50 hover:border-gray-600 focus:border-brand-orange/50 focus:bg-[#1a1a1a] rounded-md text-sm text-white placeholder-gray-500 focus:outline-none transition-colors"
          />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {displayNotebooks.map((notebook) => (
          <NotebookCard
            key={notebook.id}
            notebook={notebook}
            onClick={() => handleNotebookClick(notebook.id)}
            onShare={isSelfHosted ? (e) => handleShareClick(notebook, e) : undefined}
            onEdit={(e) => handleEditClick(notebook, e)}
            onDelete={(e) => handleDeleteClick(notebook, e)}
            canEdit={canEditNotebook(notebook.created_by)}
            canDelete={canDeleteNotebook(notebook.created_by)}
            formatTimeAgo={formatTimeAgo}
          />
        ))}
      </div>

      {/* Edit/Rename Dialog */}
      <Dialog open={showEditDialog} onOpenChange={(open) => {
        if (!open && renameMutation.isPending) return
        setShowEditDialog(open)
        if (!open) {
          setEditingNotebook(null)
          setEditingName('')
        }
      }}>
        <DialogContent className="max-w-md bg-[#2a2a2a] border-[#444444]">
          <DialogHeader>
            <DialogTitle className="text-white">Rename Notebook</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label htmlFor="notebook-name" className="block text-sm font-medium text-white mb-2">
                Notebook Name
              </label>
              <Input
                id="notebook-name"
                value={editingName}
                onChange={(e) => setEditingName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleRenameSubmit()
                }}
                placeholder="Enter notebook name"
                className="bg-[#1a1a1a] border-[#555555] text-white focus:border-brand-orange focus:ring-1 focus:ring-brand-orange/50"
                autoFocus
              />
            </div>
            <div className="flex justify-end gap-2">
              <Button
                variant="outline"
                onClick={() => {
                  setShowEditDialog(false)
                  setEditingNotebook(null)
                  setEditingName('')
                }}
                disabled={renameMutation.isPending}
                className="border-[#555555] text-white hover:bg-[#3a3a3a]"
              >
                Cancel
              </Button>
              <Button
                variant="brand-primary"
                onClick={handleRenameSubmit}
                disabled={renameMutation.isPending || !editingName.trim()}
              >
                {renameMutation.isPending ? 'Renaming...' : 'Rename'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={(open) => {
        if (!open && deleteMutation.isPending) return
        setDeleteDialogOpen(open)
      }}>
        <DialogContent className="max-w-md bg-[#2a2a2a] border-[#444444]">
          <DialogHeader>
            <DialogTitle className="text-white">Delete Notebook?</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <p className="text-sm text-[#aaaaaa]">
              This action will permanently delete <span className="font-semibold text-white">"{notebookToDelete?.notebook_name && notebookToDelete.notebook_name.length > 40 ? notebookToDelete.notebook_name.slice(0, 40) + '...' : notebookToDelete?.notebook_name}"</span> notebook and all its contents.
            </p>
            <div className="flex justify-end gap-2 mt-6">
              <Button
                variant="outline"
                onClick={() => {
                  setDeleteDialogOpen(false)
                  setNotebookToDelete(null)
                }}
                disabled={deleteMutation.isPending}
                className="border-[#555555] text-white hover:bg-[#3a3a3a]"
              >
                Cancel
              </Button>
              <Button
                onClick={confirmDelete}
                disabled={deleteMutation.isPending}
                className="bg-red-800 hover:bg-red-900 text-white"
              >
                <Trash2 className="mr-2 h-4 w-4" />
                {deleteMutation.isPending ? 'Deleting...' : 'Delete'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Share Modal */}
      {notebookToShare && (
        <>
          <ShareModal
            open={shareModalOpen}
            onOpenChange={setShareModalOpen}
            notebookId={notebookToShare.id}
            dashboardId={latestDashboardId}
            version={latestDashboardVersion}
            onShareNotebookToFolder={isSelfHosted ? () => {
              setShareModalOpen(false)
              setShareNotebookToFolderOpen(true)
            } : undefined}
            onShareDashboardToFolder={isSelfHosted ? () => {
              setShareModalOpen(false)
              setShareDashboardToFolderOpen(true)
            } : undefined}
            canShareExternally={canShareExternally}
          />
          <ShareNotebookToFolderModal
            open={shareNotebookToFolderOpen}
            onOpenChange={setShareNotebookToFolderOpen}
            notebookId={notebookToShare.id}
            notebookName={notebookToShare.notebook_name}
          />
          {latestDashboardId && (
            <ShareDashboardToFolderModal
              open={shareDashboardToFolderOpen}
              onOpenChange={setShareDashboardToFolderOpen}
              dashboardId={latestDashboardId}
              dashboardVersion={latestDashboardVersion}
              notebookId={notebookToShare.id}
              notebookName={notebookToShare.notebook_name}
            />
          )}
        </>
      )}
    </div>
  )
}
