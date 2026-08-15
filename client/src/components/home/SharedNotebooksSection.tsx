import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, ChevronDown, ChevronRight, Copy, Loader2 } from 'lucide-react'
import { ApiService } from '../../services/api'
import { useStore } from '../../stores/useStore'
import type { NotebooksByFolder, NotebookListItem, FolderWithNotebooks } from '../../types/folder'

interface SharedNotebooksSectionProps {
  onLoadingChange?: (loading: boolean) => void
  onError?: (error: string | null) => void
}

interface NotebookCardProps {
  notebook: NotebookListItem
  onClick: () => void
  onClone: () => void
  isCloning: boolean
  formatTimeAgo: (dateString: string | null) => string
  currentUserId: string | undefined
}

function NotebookCard({ notebook, onClick, onClone, isCloning, formatTimeAgo, currentUserId }: NotebookCardProps) {
  const isOwner = notebook.shared_by === currentUserId

  const truncateText = (text: string, maxLength: number = 75) => {
    if (text.length <= maxLength) return text
    return text.substring(0, maxLength) + '...'
  }

  const notebookName = notebook.notebook_name || 'Untitled Notebook'

  return (
    <div
      onClick={isOwner ? onClick : undefined}
      className={`group p-5 bg-[#1a1a1a] border border-gray-800 rounded-xl transition-all ${
        isOwner ? 'cursor-pointer hover:border-gray-700' : ''
      }`}
    >
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex-1">
          <p className="text-white text-sm" title={notebookName}>
            {truncateText(notebookName)}
          </p>
          {notebook.is_snapshot && (
            <span className="inline-block mt-1 px-2 py-0.5 bg-transparent border border-brand-orange text-brand-orange text-xs font-medium rounded-full">
              Snapshot
            </span>
          )}
        </div>
        <button
          onClick={(e) => {
            e.stopPropagation()
            onClone()
          }}
          disabled={isCloning}
          className="p-2 text-gray-500 hover:text-white transition-colors disabled:opacity-50 flex-shrink-0"
          title="Clone notebook"
        >
          {isCloning ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Copy className="w-4 h-4" />
          )}
        </button>
      </div>
      <div className="flex items-center justify-between gap-2">
        <p className="text-gray-500 text-xs">
          Shared {formatTimeAgo(notebook.shared_at)}
        </p>
        {!isOwner && (
          <p className="text-gray-400 text-xs italic">
            Clone this notebook to view/edit
          </p>
        )}
      </div>
    </div>
  )
}

interface FolderAccordionProps {
  folder: FolderWithNotebooks
  isExpanded: boolean
  onToggle: () => void
  onNotebookClick: (id: string) => void
  onCloneNotebook: (folderId: string, notebookId: string, notebookName: string) => void
  cloningNotebook: string | null
  formatTimeAgo: (dateString: string | null) => string
  currentUserId: string | undefined
}

function FolderAccordion({ folder, isExpanded, onToggle, onNotebookClick, onCloneNotebook, cloningNotebook, formatTimeAgo, currentUserId }: FolderAccordionProps) {
  return (
    <div className="mb-4">
      <button
        onClick={onToggle}
        className="flex items-center gap-2 w-full text-left py-2 px-1 hover:bg-gray-800/30 rounded-lg transition-colors"
      >
        {isExpanded ? (
          <ChevronDown className="w-4 h-4 text-gray-400" />
        ) : (
          <ChevronRight className="w-4 h-4 text-gray-400" />
        )}
        <span className="text-sm font-medium text-white">{folder.folder_name}</span>
        <span className="text-xs text-gray-500">({folder.notebooks.length})</span>
      </button>

      {isExpanded && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-3 pl-6">
          {folder.notebooks.map((notebook) => (
            <NotebookCard
              key={notebook.id}
              notebook={notebook}
              onClick={() => onNotebookClick(notebook.id)}
              onClone={() => onCloneNotebook(folder.folder_id, notebook.id, notebook.notebook_name || 'Untitled')}
              isCloning={cloningNotebook === notebook.id}
              formatTimeAgo={formatTimeAgo}
              currentUserId={currentUserId}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export default function SharedNotebooksSection({ onLoadingChange, onError }: SharedNotebooksSectionProps) {
  const navigate = useNavigate()
  const cloneNotebook = useStore(state => state.cloneNotebook)
  const currentUserId = useStore(state => state.user?.id)
  const [notebookData, setNotebookData] = useState<NotebooksByFolder | null>(null)
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set())
  const [cloningNotebook, setCloningNotebook] = useState<string | null>(null)

  const onLoadingChangeRef = useRef(onLoadingChange)
  const onErrorRef = useRef(onError)
  onLoadingChangeRef.current = onLoadingChange
  onErrorRef.current = onError

  const fetchNotebooks = useCallback(async () => {
    try {
      setLoading(true)
      onLoadingChangeRef.current?.(true)
      const response = await ApiService.getAllSharedNotebooks()
      setNotebookData(response)
      if (response?.folders) {
        setExpandedFolders(new Set(response.folders.map(f => f.folder_id)))
      }
    } catch (err) {
      console.error('Failed to fetch notebooks:', err)
      onErrorRef.current?.('Failed to load notebooks')
    } finally {
      setLoading(false)
      onLoadingChangeRef.current?.(false)
    }
  }, [])

  useEffect(() => {
    fetchNotebooks()
  }, [fetchNotebooks])

  const allNotebooks = useMemo(() => {
    if (!notebookData?.folders) return []
    return notebookData.folders.flatMap(folder =>
      folder.notebooks.map(nb => ({ ...nb, folderName: folder.folder_name, folderId: folder.folder_id }))
    )
  }, [notebookData])

  const filteredNotebooks = useMemo(() => {
    if (!searchQuery.trim()) return []
    const query = searchQuery.toLowerCase()
    return allNotebooks.filter(nb =>
      (nb.notebook_name || '').toLowerCase().includes(query)
    )
  }, [allNotebooks, searchQuery])

  const toggleFolder = (folderId: string) => {
    setExpandedFolders(prev => {
      const next = new Set(prev)
      if (next.has(folderId)) {
        next.delete(folderId)
      } else {
        next.add(folderId)
      }
      return next
    })
  }

  const formatTimeAgo = (dateString: string | null): string => {
    if (!dateString) return 'Unknown'
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
    navigate(`/notebook/${notebookId}/preview`)
  }

  const handleCloneNotebook = async (folderId: string, notebookId: string, notebookName: string) => {
    try {
      setCloningNotebook(notebookId)
      const result = await cloneNotebook(folderId, notebookId, `${notebookName} (Copy)`)
      navigate(`/notebook/${result.notebook_id}`)
    } catch (err) {
      console.error('Failed to clone notebook:', err)
      onError?.('Failed to clone notebook')
    } finally {
      setCloningNotebook(null)
    }
  }

  if (loading) {
    return (
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white">Shared Notebooks</h2>
        </div>
        <div className="space-y-4">
          {[1, 2].map((i) => (
            <div key={i} className="animate-pulse">
              <div className="h-6 w-32 bg-gray-800/50 rounded mb-3" />
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 pl-6">
                {[1, 2].map((j) => (
                  <div key={j} className="p-5 bg-[#1a1a1a] border border-gray-800 rounded-xl">
                    <div className="h-4 bg-gray-800/50 rounded w-3/4 mb-2" />
                    <div className="h-3 bg-gray-800/30 rounded w-1/3" />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (!notebookData || allNotebooks.length === 0) {
    return null
  }

  const isSearching = searchQuery.trim().length > 0

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-white">Shared Notebooks</h2>
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

      <div className="flex items-center gap-2 mb-4 px-3 py-2 bg-[#1a1a1a] border border-gray-800 rounded-lg text-sm text-gray-400">
        <Copy className="w-4 h-4 flex-shrink-0" />
        <span>Click the clone icon on any notebook to create your own copy and start editing.</span>
      </div>

      {isSearching ? (
        filteredNotebooks.length === 0 ? (
          <div className="text-center py-8 text-gray-500 text-sm">
            No notebooks found matching "{searchQuery}"
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {filteredNotebooks.map((notebook) => (
              <NotebookCard
                key={notebook.id}
                notebook={notebook}
                onClick={() => handleNotebookClick(notebook.id)}
                onClone={() => handleCloneNotebook(notebook.folderId, notebook.id, notebook.notebook_name || 'Untitled')}
                isCloning={cloningNotebook === notebook.id}
                formatTimeAgo={formatTimeAgo}
                currentUserId={currentUserId}
              />
            ))}
          </div>
        )
      ) : (
        notebookData.folders.map((folder) => (
          <FolderAccordion
            key={folder.folder_id}
            folder={folder}
            isExpanded={expandedFolders.has(folder.folder_id)}
            onToggle={() => toggleFolder(folder.folder_id)}
            onNotebookClick={handleNotebookClick}
            onCloneNotebook={handleCloneNotebook}
            cloningNotebook={cloningNotebook}
            formatTimeAgo={formatTimeAgo}
            currentUserId={currentUserId}
          />
        ))
      )}
    </div>
  )
}
