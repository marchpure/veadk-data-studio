import { useState, useEffect } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog'
import { Input } from './ui/input'
import { Label } from './ui/label'
import { Button } from './ui/button'
import { Loader2, Save } from 'lucide-react'

interface SaveQueryDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSave: (name: string, saveAsNew?: boolean) => void
  isLoading: boolean
  mode?: 'save' | 'update'
  currentQueryName?: string
  currentQueryId?: string
}

export function SaveQueryDialog({
  open,
  onOpenChange,
  onSave,
  isLoading,
  mode = 'save',
  currentQueryName = '',
  currentQueryId,
}: SaveQueryDialogProps) {
  const [queryName, setQueryName] = useState('')

  useEffect(() => {
    if (open && mode === 'update' && currentQueryName) {
      setQueryName(currentQueryName)
    } else if (!open) {
      setQueryName('')
    }
  }, [open, mode, currentQueryName])

  const handleSave = (saveAsNew: boolean = false) => {
    if (queryName.trim()) {
      onSave(queryName.trim(), saveAsNew)
      setQueryName('')
    }
  }

  const handleClose = () => {
    if (!isLoading) {
      setQueryName('')
      onOpenChange(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-md bg-[#2a2a2a] border-[#444444]">
        <DialogHeader>
          <DialogTitle className="text-white">
            {mode === 'update' ? 'Update Query' : 'Save Query'}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <Label htmlFor="query-name" className="text-white">
              Query Name <span className="text-red-400">*</span>
            </Label>
            <Input
              id="query-name"
              placeholder="Enter a descriptive name for your query"
              value={queryName}
              onChange={(e) => setQueryName(e.target.value)}
              className="mt-1 bg-[#1a1a1a] border-[#555555] text-white focus:border-brand-orange focus:ring-1 focus:ring-brand-orange/50"
              disabled={isLoading}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey && queryName.trim()) {
                  e.preventDefault()
                  handleSave(false)
                }
              }}
            />
          </div>

          <div className="flex justify-end gap-2 mt-6">
            <Button
              variant="outline"
              onClick={handleClose}
              disabled={isLoading}
              className="border-[#555555] text-white hover:bg-[#3a3a3a]"
            >
              Cancel
            </Button>
            {mode === 'update' && (
              <Button
                variant="outline"
                onClick={() => handleSave(true)}
                disabled={!queryName.trim() || isLoading}
                className="border-[#555555] text-white hover:bg-[#3a3a3a]"
              >
                {isLoading ? (
                  <Loader2 className="w-4 h-4 animate-spin mr-2" />
                ) : (
                  <Save className="w-4 h-4 mr-2" />
                )}
                Save as New
              </Button>
            )}
            <Button
              variant="brand-primary"
              onClick={() => handleSave(false)}
              disabled={!queryName.trim() || isLoading}
            >
              {isLoading ? (
                <Loader2 className="w-4 h-4 animate-spin mr-2" />
              ) : (
                <Save className="w-4 h-4 mr-2" />
              )}
              {isLoading ? 'Saving...' : mode === 'update' ? 'Update' : 'Save Query'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}