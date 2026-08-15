import { useState } from 'react'
import { Button } from '../ui/button'
import { Card } from '../ui/card'
import { X, UserPlus, Trash2, Loader2 } from 'lucide-react'
import { useStore } from '../../stores/useStore'
import { useScopes } from '../../hooks/useScopes'
import { AddMemberModal } from './AddMemberModal'
import type { FolderMember } from '../../types/folder'

interface MembersPanelProps {
  open: boolean
  onClose: () => void
  folderId: string
  folderCreatedBy: string
  members: FolderMember[]
}

export function MembersPanel({
  open,
  onClose,
  folderId,
  folderCreatedBy,
  members,
}: MembersPanelProps) {
  const { userId, canManageFolderMembers } = useScopes()
  const { removeFolderMember } = useStore()
  const [showAddModal, setShowAddModal] = useState(false)
  const [removingMember, setRemovingMember] = useState<string | null>(null)

  const canManageMembers = canManageFolderMembers || folderCreatedBy === userId

  const handleRemoveMember = async (memberId: string) => {
    try {
      setRemovingMember(memberId)
      await removeFolderMember(folderId, memberId)
    } catch (err) {
      console.error('Failed to remove member:', err)
    } finally {
      setRemovingMember(null)
    }
  }

  const formatTimeAgo = (dateString: string): string => {
    const date = new Date(dateString)
    const now = new Date()
    const diffInMs = now.getTime() - date.getTime()
    const diffInDays = Math.floor(diffInMs / (1000 * 60 * 60 * 24))
    if (diffInDays === 0) return 'today'
    if (diffInDays === 1) return 'yesterday'
    return `${diffInDays} days ago`
  }

  return (
    <>
      {/* Backdrop */}
      {open && (
        <div
          className="fixed inset-0 bg-black/50 z-40 transition-opacity"
          onClick={onClose}
        />
      )}

      {/* Panel */}
      <div
        className={`fixed right-0 top-0 h-full w-96 bg-[#1a1a1a] border-l border-gray-800 z-50 transform transition-transform duration-300 ease-in-out ${
          open ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <div className="flex flex-col h-full">
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b border-gray-800">
            <h2 className="text-lg font-semibold text-white">Folder Members</h2>
            <Button
              variant="ghost"
              size="sm"
              onClick={onClose}
              className="h-8 w-8 p-0 text-gray-400 hover:text-white hover:bg-gray-800"
            >
              <X className="w-5 h-5" />
            </Button>
          </div>

          {/* Add Member Button */}
          {canManageMembers && (
            <div className="p-4 border-b border-gray-800">
              <Button
                variant="brand-primary"
                className="w-full"
                onClick={() => setShowAddModal(true)}
              >
                <UserPlus className="w-4 h-4 mr-2" />
                Add Member
              </Button>
            </div>
          )}

          {/* Members List */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3 custom-scrollbar">
            {members.length === 0 ? (
              <Card className="p-6 text-center bg-[#2a2a2a] border-gray-800">
                <div className="w-12 h-12 bg-brand-orange/10 rounded-full flex items-center justify-center mx-auto mb-3">
                  <UserPlus className="w-6 h-6 text-brand-orange" />
                </div>
                <h3 className="text-sm font-medium text-white mb-1">No Members</h3>
                <p className="text-xs text-gray-400">
                  Add team members to give them access to this folder.
                </p>
              </Card>
            ) : (
              members.map((member) => (
                <Card
                  key={member.id}
                  className="p-4 bg-[#2a2a2a] border-gray-800"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex-1 min-w-0">
                      <h4 className="text-white font-medium truncate">
                        {member.user?.full_name || member.user?.email || 'Unknown User'}
                        {member.user_id === folderCreatedBy && (
                          <span className="ml-2 text-xs text-brand-orange">(Creator)</span>
                        )}
                      </h4>
                      <p className="text-sm text-gray-400 truncate">
                        {member.user?.email}
                      </p>
                      <p className="text-xs text-gray-500 mt-1">
                        Added {formatTimeAgo(member.created_at)}
                      </p>
                    </div>
                    {canManageMembers && member.user_id !== folderCreatedBy && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => handleRemoveMember(member.id)}
                        disabled={removingMember === member.id}
                        className="text-gray-400 hover:text-red-400 hover:bg-gray-800 ml-2 h-8 w-8 p-0"
                        title="Remove member"
                      >
                        {removingMember === member.id ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                          <Trash2 className="w-4 h-4" />
                        )}
                      </Button>
                    )}
                  </div>
                </Card>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Add Member Modal */}
      <AddMemberModal
        open={showAddModal}
        onOpenChange={setShowAddModal}
        folderId={folderId}
        existingMembers={members}
      />
    </>
  )
}
