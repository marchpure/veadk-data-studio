import { useState, useEffect } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog'
import { Button } from '../ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'
import { Label } from '../ui/label'
import { Loader2 } from 'lucide-react'
import { useStore } from '../../stores/useStore'
import { ApiService } from '../../services/api'
import type { TenantMember } from '../../types/team'
import type { FolderMember } from '../../types/folder'

interface AddMemberModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  folderId: string
  existingMembers: FolderMember[]
}

export function AddMemberModal({ open, onOpenChange, folderId, existingMembers }: AddMemberModalProps) {
  const addFolderMember = useStore((state) => state.addFolderMember)
  const [selectedUserId, setSelectedUserId] = useState<string>('')
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [tenantMembers, setTenantMembers] = useState<TenantMember[]>([])
  const [loadingMembers, setLoadingMembers] = useState(false)

  // Fetch tenant members when modal opens
  useEffect(() => {
    if (open) {
      fetchTenantMembers()
    }
  }, [open])

  const fetchTenantMembers = async () => {
    try {
      setLoadingMembers(true)
      const members = await ApiService.getTeamMembers()
      setTenantMembers(members)
    } catch (err) {
      console.error('Failed to fetch tenant members:', err)
    } finally {
      setLoadingMembers(false)
    }
  }

  // Filter out users who are already folder members
  const existingMemberUserIds = new Set(existingMembers.map((m) => m.user_id))
  const availableMembers = tenantMembers.filter((m) => !existingMemberUserIds.has(m.user_id))

  const resetForm = () => {
    setSelectedUserId('')
    setError(null)
  }

  const handleClose = () => {
    if (adding) return
    resetForm()
    onOpenChange(false)
  }

  const handleAdd = async () => {
    if (!selectedUserId) return

    try {
      setAdding(true)
      setError(null)
      await addFolderMember(folderId, selectedUserId)
      resetForm()
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add member')
    } finally {
      setAdding(false)
    }
  }

  const getMemberDisplayName = (member: TenantMember): string => {
    if (member.user?.full_name) {
      return `${member.user.full_name} (${member.user.email})`
    }
    return member.user?.email || 'Unknown'
  }

  const truncateMemberName = (name: string, maxLength: number = 40) => {
    if (name.length <= maxLength) return name
    return name.substring(0, maxLength) + '...'
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-md bg-[#2a2a2a] border-[#444444]">
        <DialogHeader>
          <DialogTitle className="text-white">Add Member to Folder</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {error && (
            <div className="bg-red-900/20 border border-red-500 text-red-400 px-3 py-2 rounded-md text-sm">
              {error}
            </div>
          )}

          <div>
            <Label htmlFor="member-select" className="text-white">
              Select Team Member <span className="text-red-400">*</span>
            </Label>
            {loadingMembers ? (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
              </div>
            ) : availableMembers.length === 0 ? (
              <p className="text-sm text-gray-400 mt-2">
                No team members available to add. All team members are already in this folder.
              </p>
            ) : (
              <Select value={selectedUserId} onValueChange={setSelectedUserId}>
                <SelectTrigger className="mt-1 bg-[#1a1a1a] border-[#555555] text-white w-full">
                  <SelectValue placeholder="Select a team member" className="truncate block">
                    {selectedUserId && (
                      <span className="truncate block" title={getMemberDisplayName(tenantMembers.find(m => m.user_id === selectedUserId)!)}>
                        {truncateMemberName(
                          getMemberDisplayName(tenantMembers.find(m => m.user_id === selectedUserId)!)
                        )}
                      </span>
                    )}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent className="bg-[#2a2a2a] border-[#555555] w-[--radix-select-trigger-width] max-h-[300px]">
                  {availableMembers.map((member) => {
                    const displayName = getMemberDisplayName(member)
                    return (
                      <SelectItem
                        key={member.user_id}
                        value={member.user_id}
                        title={displayName}
                        className="truncate"
                      >
                        <span className="truncate block" title={displayName}>
                          {truncateMemberName(displayName)}
                        </span>
                      </SelectItem>
                    )
                  })}
                </SelectContent>
              </Select>
            )}
          </div>

          <div className="flex justify-end gap-2 pt-4">
            <Button
              variant="outline"
              onClick={handleClose}
              disabled={adding}
              className="border-[#555555] text-white hover:bg-[#3a3a3a]"
            >
              Cancel
            </Button>
            <Button
              variant="brand-primary"
              onClick={handleAdd}
              disabled={adding || !selectedUserId || availableMembers.length === 0}
            >
              {adding && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              {adding ? 'Adding...' : 'Add Member'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
