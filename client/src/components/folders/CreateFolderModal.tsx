import { useState } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Switch } from '../ui/switch'
import { Loader2, Globe } from 'lucide-react'
import { useStore } from '../../stores/useStore'

interface CreateFolderModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSuccess?: () => void
}

export function CreateFolderModal({ open, onOpenChange, onSuccess }: CreateFolderModalProps) {
  const createFolder = useStore((state) => state.createFolder)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [isPublic, setIsPublic] = useState(false)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const resetForm = () => {
    setName('')
    setDescription('')
    setIsPublic(false)
    setError(null)
  }

  const handleClose = () => {
    if (creating) return
    resetForm()
    onOpenChange(false)
  }

  const handleCreate = async () => {
    if (!name.trim()) return

    try {
      setCreating(true)
      setError(null)
      await createFolder(name.trim(), description.trim() || undefined, isPublic)
      resetForm()
      onOpenChange(false)
      onSuccess?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create folder')
    } finally {
      setCreating(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-md bg-[#2a2a2a] border-[#444444]">
        <DialogHeader>
          <DialogTitle className="text-white">Create Folder</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {error && (
            <div className="bg-red-900/20 border border-red-500 text-red-400 px-3 py-2 rounded-md text-sm">
              {error}
            </div>
          )}

          <div>
            <Label htmlFor="folder-name" className="text-white">
              Name <span className="text-red-400">*</span>
            </Label>
            <Input
              id="folder-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && name.trim()) {
                  handleCreate()
                }
              }}
              placeholder="Enter folder name"
              className="mt-1 bg-[#1a1a1a] border-[#555555] text-white focus:border-brand-orange focus:ring-1 focus:ring-brand-orange/50"
              autoFocus
            />
          </div>

          <div>
            <Label htmlFor="folder-description" className="text-white">
              Description
            </Label>
            <Input
              id="folder-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional description"
              className="mt-1 bg-[#1a1a1a] border-[#555555] text-white focus:border-brand-orange focus:ring-1 focus:ring-brand-orange/50"
            />
          </div>

          <div className="flex items-center justify-between py-2">
            <div className="flex items-center gap-2">
              <Globe className="w-4 h-4 text-gray-400" />
              <div>
                <Label htmlFor="folder-public" className="text-white cursor-pointer">
                  Public folder
                </Label>
                <p className="text-xs text-gray-400">Everyone in your team can view this folder</p>
              </div>
            </div>
            <Switch id="folder-public" checked={isPublic} onCheckedChange={setIsPublic} />
          </div>

          <div className="flex justify-end gap-2 pt-4">
            <Button
              variant="outline"
              onClick={handleClose}
              disabled={creating}
              className="border-[#555555] text-white hover:bg-[#3a3a3a]"
            >
              Cancel
            </Button>
            <Button
              variant="brand-primary"
              onClick={handleCreate}
              disabled={creating || !name.trim()}
            >
              {creating && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              {creating ? 'Creating...' : 'Create Folder'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
