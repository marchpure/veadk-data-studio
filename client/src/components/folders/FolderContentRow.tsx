import { Button } from '../ui/button'
import { Badge } from '../ui/badge'
import {
  BookOpen,
  LayoutDashboard,
  Copy,
  Eye,
  RefreshCw,
  X,
  Loader2,
  Camera,
  Radio,
} from 'lucide-react'
import type { FolderContentItem } from '../../types/folder'

interface FolderContentRowProps {
  item: FolderContentItem
  userId: string | null
  onClone: (item: FolderContentItem) => void
  onUnshare: (item: FolderContentItem) => void
  onPreview: (item: FolderContentItem) => void
  onUpdateSnapshot: (item: FolderContentItem) => void
  onUpdateDashboardVersion?: (item: FolderContentItem) => void
  cloningId: string | null
  unsharingId: string | null
  updatingSnapshotId: string | null
  updatingDashboardVersionId?: string | null
}

export function FolderContentRow({
  item,
  userId,
  onClone,
  onUnshare,
  onPreview,
  onUpdateSnapshot,
  onUpdateDashboardVersion,
  cloningId,
  unsharingId,
  updatingSnapshotId,
  updatingDashboardVersionId,
}: FolderContentRowProps) {
  const isOwner = item.sharedBy === userId
  const itemId = item.type === 'notebook' ? item.notebookId : item.dashboardId

  const formatTimeAgo = (dateString: string): string => {
    const date = new Date(dateString)
    const now = new Date()
    const diffInMs = now.getTime() - date.getTime()
    const diffInMinutes = Math.floor(diffInMs / (1000 * 60))
    const diffInHours = Math.floor(diffInMs / (1000 * 60 * 60))
    const diffInDays = Math.floor(diffInMs / (1000 * 60 * 60 * 24))
    const diffInMonths = Math.floor(diffInDays / 30)

    if (diffInMinutes < 1) return 'just now'
    if (diffInMinutes < 60) return `${diffInMinutes}m ago`
    if (diffInHours < 24) return `${diffInHours}h ago`
    if (diffInDays < 30) return `${diffInDays}d ago`
    return `${diffInMonths}mo ago`
  }

  return (
    <div className="grid grid-cols-12 gap-4 px-4 py-3 border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors items-center">
      {/* Name Column with Icon */}
      <div className="col-span-5 flex items-center gap-3 min-w-0">
        {item.type === 'notebook' ? (
          <BookOpen className="w-5 h-5 text-blue-400 flex-shrink-0" />
        ) : (
          <LayoutDashboard className="w-5 h-5 text-purple-400 flex-shrink-0" />
        )}
        <span
          className="text-white truncate"
          title={item.name}
        >
          {item.name}
        </span>
      </div>

      {/* Type Badge */}
      <div className="col-span-2">
        <div className="flex items-center gap-2">
          {item.type === 'dashboard' ? (
            // Dashboards show version
            <Badge className="bg-purple-900/30 text-purple-400 border-purple-700 text-xs">
              v{item.dashboardVersion || 1}
            </Badge>
          ) : item.isSnapshot ? (
            // Notebooks show Live/Snapshot
            <Badge className="bg-purple-900/30 text-purple-400 border-purple-700 text-xs">
              <Camera className="w-3 h-3 mr-1" />
              Snapshot
            </Badge>
          ) : (
            <Badge className="bg-green-900/30 text-green-400 border-green-700 text-xs">
              <Radio className="w-3 h-3 mr-1" />
              Live
            </Badge>
          )}
        </div>
      </div>

      {/* Shared By */}
      <div className="col-span-2 text-sm text-gray-400 truncate" title={item.sharedByUser?.email || ''}>
        {item.sharedByUser?.full_name || item.sharedByUser?.email || 'Unknown'}
      </div>

      {/* Modified Date */}
      <div className="col-span-2 text-sm text-gray-500">
        {formatTimeAgo(item.snapshotUpdatedAt || item.createdAt)}
      </div>

      {/* Actions */}
      <div className="col-span-1 flex items-center justify-end gap-1">
        {/* Preview for dashboards */}
        {item.type === 'dashboard' && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onPreview(item)}
            className="h-8 w-8 p-0 text-gray-400 hover:text-white hover:bg-gray-700"
            title="Preview dashboard"
          >
            <Eye className="w-4 h-4" />
          </Button>
        )}

        {/* Clone for notebooks */}
        {item.type === 'notebook' && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onClone(item)}
            disabled={cloningId === item.notebookId}
            className="h-8 w-8 p-0 text-gray-400 hover:text-white hover:bg-gray-700"
            title="Clone notebook"
          >
            {cloningId === item.notebookId ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Copy className="w-4 h-4" />
            )}
          </Button>
        )}

        {/* Update snapshot - only for owner of notebook snapshots */}
        {item.type === 'notebook' && item.isSnapshot && isOwner && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onUpdateSnapshot(item)}
            disabled={updatingSnapshotId === itemId}
            className="h-8 w-8 p-0 text-gray-400 hover:text-purple-400 hover:bg-gray-700"
            title="Update snapshot"
          >
            {updatingSnapshotId === itemId ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4" />
            )}
          </Button>
        )}

        {/* Update version - only for owner of dashboards */}
        {item.type === 'dashboard' && isOwner && onUpdateDashboardVersion && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onUpdateDashboardVersion(item)}
            disabled={updatingDashboardVersionId === item.dashboardId}
            className="h-8 w-8 p-0 text-gray-400 hover:text-purple-400 hover:bg-gray-700"
            title="Update version"
          >
            {updatingDashboardVersionId === item.dashboardId ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4" />
            )}
          </Button>
        )}

        {/* Unshare - only for sharer */}
        {isOwner && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onUnshare(item)}
            disabled={unsharingId === itemId}
            className="h-8 w-8 p-0 text-gray-400 hover:text-red-400 hover:bg-gray-700"
            title="Unshare"
          >
            {unsharingId === itemId ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <X className="w-4 h-4" />
            )}
          </Button>
        )}
      </div>
    </div>
  )
}
