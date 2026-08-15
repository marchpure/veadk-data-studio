import { useState, useEffect } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog'
import { Button } from '../ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'
import { Label } from '../ui/label'
import { Switch } from '../ui/switch'
import { Loader2 } from 'lucide-react'
import { useStore } from '../../stores/useStore'
import { useNotebooks } from '../../hooks/useNotebooks'
import type { FolderNotebook } from '../../types/folder'

interface ShareNotebookModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  folderId: string
  existingNotebooks: FolderNotebook[]
}

export function ShareNotebookModal({ open, onOpenChange, folderId, existingNotebooks }: ShareNotebookModalProps) {
  const shareNotebookToFolder = useStore((state) => state.shareNotebookToFolder)
  const [selectedNotebookId, setSelectedNotebookId] = useState<string>('')
  const [isSnapshot, setIsSnapshot] = useState(false)
  const [sharing, setSharing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Fetch user's notebooks
  const { data: notebooks = [], isLoading: loadingNotebooks } = useNotebooks()

  const truncateNotebookName = (name: string, maxLength: number = 50) => {
    if (name.length <= maxLength) return name
    return name.substring(0, maxLength) + '...'
  }

  // Reset form when modal opens
  useEffect(() => {
    if (open) {
      setSelectedNotebookId('')
      setIsSnapshot(false)
      setError(null)
    }
  }, [open])

  // Filter out notebooks that are already shared to this folder
  const existingNotebookIds = new Set(existingNotebooks.map((n) => n.notebook_id))
  const availableNotebooks = notebooks.filter((n) => !existingNotebookIds.has(n.id))

  const resetForm = () => {
    setSelectedNotebookId('')
    setIsSnapshot(false)
    setError(null)
  }

  const handleClose = () => {
    if (sharing) return
    resetForm()
    onOpenChange(false)
  }

  const handleShare = async () => {
    if (!selectedNotebookId) return

    try {
      setSharing(true)
      setError(null)
      await shareNotebookToFolder(folderId, selectedNotebookId, isSnapshot)
      resetForm()
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to share notebook')
    } finally {
      setSharing(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-md bg-[#2a2a2a] border-[#444444]">
        <DialogHeader>
          <DialogTitle className="text-white">Share Notebook to Folder</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {error && (
            <div className="bg-red-900/20 border border-red-500 text-red-400 px-3 py-2 rounded-md text-sm">
              {error}
            </div>
          )}

          <div>
            <Label htmlFor="notebook-select" className="text-white">
              Select Notebook <span className="text-red-400">*</span>
            </Label>
            {loadingNotebooks ? (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
              </div>
            ) : availableNotebooks.length === 0 ? (
              <p className="text-sm text-gray-400 mt-2">
                No notebooks available to share. All your notebooks are already shared to this folder.
              </p>
            ) : (
              <Select value={selectedNotebookId} onValueChange={setSelectedNotebookId}>
                <SelectTrigger className="mt-1 bg-[#1a1a1a] border-[#555555] text-white w-full">
                  <SelectValue placeholder="Select a notebook" className="truncate block">
                    {selectedNotebookId && (
                      <span className="truncate block" title={notebooks.find(n => n.id === selectedNotebookId)?.notebook_name}>
                        {truncateNotebookName(
                          notebooks.find(n => n.id === selectedNotebookId)?.notebook_name || ''
                        )}
                      </span>
                    )}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent className="bg-[#2a2a2a] border-[#555555] w-[--radix-select-trigger-width] max-h-[300px]">
                  {availableNotebooks.map((notebook) => (
                    <SelectItem
                      key={notebook.id}
                      value={notebook.id}
                      title={notebook.notebook_name}
                      className="truncate"
                    >
                      <span className="truncate block" title={notebook.notebook_name}>
                        {truncateNotebookName(notebook.notebook_name)}
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>

          <div className="flex items-center justify-between py-2">
            <div>
              <Label htmlFor="snapshot-toggle" className="text-white">
                Share as snapshot
              </Label>
              <p className="text-xs text-gray-400 mt-0.5">
                {isSnapshot
                  ? 'Members will see a frozen copy. You can update it later.'
                  : 'Members will see live changes to the notebook.'}
              </p>
            </div>
            <Switch
              id="snapshot-toggle"
              checked={isSnapshot}
              onCheckedChange={setIsSnapshot}
            />
          </div>

          <p className="text-xs text-gray-400">
            Shared notebooks can be viewed by all folder members. Only you can unshare this notebook.
          </p>

          <div className="flex justify-end gap-2 pt-4">
            <Button
              variant="outline"
              onClick={handleClose}
              disabled={sharing}
              className="border-[#555555] text-white hover:bg-[#3a3a3a]"
            >
              Cancel
            </Button>
            <Button
              variant="brand-primary"
              onClick={handleShare}
              disabled={sharing || !selectedNotebookId || availableNotebooks.length === 0}
            >
              {sharing && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              {sharing ? 'Sharing...' : 'Share Notebook'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
