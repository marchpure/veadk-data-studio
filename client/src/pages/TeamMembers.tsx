import { useState, useEffect } from 'react'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'
import { Card } from '../components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs'
import { Trash2, Loader2, Search, UserPlus, RefreshCw, X, Shield, User, Crown, Copy, Check, BarChart3 } from 'lucide-react'
import { ApiService } from '../services/api'
import { copyToClipboard } from '../lib/tauri-api'
import type { TenantMember, TenantInvitation, TenantRole, MemberStats, SlackStats } from '../types/team'
import { useScopes } from '../hooks/useScopes'
import { useInviteTeamMember, useResendInvitation, useCancelInvitation, useUpdateMemberRole, useRemoveMember } from '../hooks/useTeamManagement'

export default function TeamMembersPage() {
  const { isOwner, isAdmin, userId } = useScopes()

  // Use mutation hooks
  const inviteMutation = useInviteTeamMember()
  const resendMutation = useResendInvitation()
  const cancelInviteMutation = useCancelInvitation()
  const updateRoleMutation = useUpdateMemberRole()
  const removeMemberMutation = useRemoveMember()
  const [activeTab, setActiveTab] = useState<'members' | 'invitations'>('members')
  const [showInviteDialog, setShowInviteDialog] = useState(false)
  const [showRoleDialog, setShowRoleDialog] = useState(false)
  const [showRemoveDialog, setShowRemoveDialog] = useState(false)
  const [showCancelDialog, setShowCancelDialog] = useState(false)
  const [showLinkDialog, setShowLinkDialog] = useState(false)
  const [generatedLink, setGeneratedLink] = useState('')
  const [linkCopied, setLinkCopied] = useState(false)
  const [linkEmailSent, setLinkEmailSent] = useState<boolean | null>(null)

  // Data state
  const [members, setMembers] = useState<TenantMember[]>([])
  const [invitations, setInvitations] = useState<TenantInvitation[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Form state for invite dialog
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteRole, setInviteRole] = useState<'admin' | 'member'>('member')
  const [inviteMessage, setInviteMessage] = useState('')

  // State for role update
  const [selectedMember, setSelectedMember] = useState<TenantMember | null>(null)
  const [newRole, setNewRole] = useState<TenantRole>('member')

  // State for remove member
  const [memberToRemove, setMemberToRemove] = useState<TenantMember | null>(null)

  // State for cancel invitation
  const [invitationToCancel, setInvitationToCancel] = useState<TenantInvitation | null>(null)

  // State for resend invitation
  const [resending, setResending] = useState<string | null>(null)
  const [copyingLink, setCopyingLink] = useState<string | null>(null)

  // Search state
  const [searchQuery, setSearchQuery] = useState('')

  // Team Stats dialog state
  const [showStatsDialog, setShowStatsDialog] = useState(false)
  const [memberStats, setMemberStats] = useState<MemberStats[]>([])
  const [slackStats, setSlackStats] = useState<SlackStats | null>(null)
  const [statsLoading, setStatsLoading] = useState(false)
  const [statsError, setStatsError] = useState<string | null>(null)
  const [statsSearch, setStatsSearch] = useState('')

  useEffect(() => {
    fetchData()
  }, [])

  const fetchData = async () => {
    try {
      setLoading(true)
      setError(null)
      const [membersData, invitationsData] = await Promise.all([
        ApiService.getTeamMembers(),
        ApiService.getPendingInvitations(),
      ])
      setMembers(membersData)
      setInvitations(invitationsData)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load team data')
    } finally {
      setLoading(false)
    }
  }

  const handleOpenStats = async () => {
    setShowStatsDialog(true)
    setStatsSearch('')
    setStatsError(null)
    setStatsLoading(true)
    try {
      const data = await ApiService.getTeamMemberStats()
      setMemberStats(data.items || [])
      setSlackStats(data.slack || null)
    } catch (err) {
      setStatsError(err instanceof Error ? err.message : 'Failed to load team stats')
    } finally {
      setStatsLoading(false)
    }
  }

  const handleInviteMember = () => {
    if (!inviteEmail.trim()) return

    inviteMutation.mutate(
      {
        email: inviteEmail,
        role: inviteRole,
        message: inviteMessage || undefined,
      },
      {
        onSuccess: (response) => {
          setShowInviteDialog(false)
          resetInviteForm()
          fetchData()
          const link = response?.data?.invitation_link
          if (link) {
            setGeneratedLink(link)
            setLinkCopied(false)
            setLinkEmailSent(response?.data?.email_sent ?? null)
            setShowLinkDialog(true)
          }
        },
      }
    )
  }

  const resetInviteForm = () => {
    setInviteEmail('')
    setInviteRole('member')
    setInviteMessage('')
  }

  const handleChangeRoleClick = (member: TenantMember) => {
    setSelectedMember(member)
    setNewRole(member.role)
    setShowRoleDialog(true)
  }

  const handleUpdateRole = () => {
    if (!selectedMember) return

    updateRoleMutation.mutate(
      { memberId: selectedMember.id, role: newRole },
      {
        onSuccess: () => {
          setShowRoleDialog(false)
          setSelectedMember(null)
          fetchData()
        },
      }
    )
  }

  const handleRemoveClick = (member: TenantMember) => {
    setMemberToRemove(member)
    setShowRemoveDialog(true)
  }

  const handleRemoveMember = () => {
    if (!memberToRemove) return

    removeMemberMutation.mutate(memberToRemove.id, {
      onSuccess: () => {
        setShowRemoveDialog(false)
        setMemberToRemove(null)
        fetchData()
      },
    })
  }

  const handleCancelInvitationClick = (invitation: TenantInvitation) => {
    setInvitationToCancel(invitation)
    setShowCancelDialog(true)
  }

  const handleCancelInvitation = () => {
    if (!invitationToCancel) return

    cancelInviteMutation.mutate(invitationToCancel.id, {
      onSuccess: () => {
        setShowCancelDialog(false)
        setInvitationToCancel(null)
        fetchData()
      },
    })
  }

  const handleResendInvitation = (invitationId: string) => {
    setResending(invitationId)
    resendMutation.mutate(invitationId, {
      onSuccess: (response) => {
        fetchData()
        const link = response?.data?.invitation_link
        if (link) {
          setGeneratedLink(link)
          setLinkCopied(false)
          setLinkEmailSent(response?.data?.email_sent ?? null)
          setShowLinkDialog(true)
        }
      },
      onSettled: () => {
        setResending(null)
      },
    })
  }

  const handleCopyInvitationLink = async (invitationId: string) => {
    setCopyingLink(invitationId)
    try {
      const response = await ApiService.getInvitationLink(invitationId)
      const link = response?.data?.invitation_link
      if (link) {
        setGeneratedLink(link)
        setLinkCopied(false)
        setLinkEmailSent(response?.data?.email_sent ?? null)
        setShowLinkDialog(true)
      }
    } catch (err) {
      console.error('Error getting invitation link:', err)
    } finally {
      setCopyingLink(null)
    }
  }

  const handleCopyLink = async () => {
    await copyToClipboard(generatedLink)
    setLinkCopied(true)
    setTimeout(() => setLinkCopied(false), 2000)
  }

  const getRoleBadgeVariant = (role: TenantRole): "default" | "secondary" | "destructive" | "outline" => {
    switch (role) {
      case 'owner':
        return 'default'
      case 'admin':
        return 'secondary'
      case 'member':
        return 'outline'
      default:
        return 'outline'
    }
  }

  const getRoleIcon = (role: TenantRole) => {
    switch (role) {
      case 'owner':
        return <Crown className="w-3 h-3" />
      case 'admin':
        return <Shield className="w-3 h-3" />
      case 'member':
        return <User className="w-3 h-3" />
      default:
        return <User className="w-3 h-3" />
    }
  }

  const formatTimeAgo = (dateString: string): string => {
    const date = new Date(dateString)
    const now = new Date()
    const diffInMs = now.getTime() - date.getTime()
    const diffInMinutes = Math.floor(diffInMs / (1000 * 60))
    const diffInHours = Math.floor(diffInMs / (1000 * 60 * 60))
    const diffInDays = Math.floor(diffInMs / (1000 * 60 * 60 * 24))

    if (diffInMinutes < 1) return 'just now'
    if (diffInMinutes < 60) return `${diffInMinutes} minute${diffInMinutes > 1 ? 's' : ''} ago`
    if (diffInHours < 24) return `${diffInHours} hour${diffInHours > 1 ? 's' : ''} ago`
    return `${diffInDays} day${diffInDays > 1 ? 's' : ''} ago`
  }

  const formatExpiresIn = (dateString: string): string => {
    const date = new Date(dateString)
    const now = new Date()
    const diffInMs = date.getTime() - now.getTime()
    const diffInDays = Math.ceil(diffInMs / (1000 * 60 * 60 * 24))

    if (diffInDays < 0) return 'Expired'
    if (diffInDays === 0) return 'Expires today'
    if (diffInDays === 1) return 'Expires tomorrow'
    return `Expires in ${diffInDays} days`
  }

  const getMemberName = (member: TenantMember): string => {
    if (member.user?.full_name) {
      return member.user.full_name
    }
    return member.user?.email || 'Unknown'
  }

  const getInviterName = (invitation: TenantInvitation): string => {
    if (invitation.invited_by?.full_name) {
      return invitation.invited_by.full_name
    }
    return invitation.invited_by?.email || 'Unknown'
  }

  const canChangeRole = (member: TenantMember): boolean => {
    // Owner's role cannot be changed by anyone (including owner himself)
    if (member.role === 'owner') {
      return false
    }

    // Users cannot change their own role
    if (member.user_id === userId) {
      return false
    }

    // Owner and Admin can change other admin/member roles
    if (isOwner || isAdmin) {
      return true
    }

    // Members cannot change roles
    return false
  }

  const canRemoveMember = (member: TenantMember): boolean => {
    // Owner cannot be removed by anyone
    if (member.role === 'owner') {
      return false
    }

    // Admins and Owners cannot remove themselves
    if (member.user_id === userId) {
      return false
    }

    // Owner can remove other admins and members
    if (isOwner) {
      return true
    }

    // Admin can remove other admins and members
    if (isAdmin) {
      return true
    }

    return false
  }

  const filteredMembers = members.filter(member => {
    if (!searchQuery) return true
    const query = searchQuery.toLowerCase()
    const name = getMemberName(member).toLowerCase()
    const email = member.user?.email.toLowerCase() || ''
    return name.includes(query) || email.includes(query) || member.role.includes(query)
  })

  const filteredInvitations = invitations.filter(invitation => {
    if (!searchQuery) return true
    const query = searchQuery.toLowerCase()
    return invitation.email.toLowerCase().includes(query) || invitation.role.includes(query)
  })

  return (
    <div className="bg-[#0d0d0d] w-full h-full flex flex-col">
      {/* Header Section */}
      <div className="w-full px-8 pt-[50px] pb-8">
        <div className="max-w-[850px] mx-auto">
          {/* Title and Button */}
          <div className="flex items-center justify-between mb-8">
            <h1 className="text-2xl font-bold text-white tracking-tight">Team</h1>
            <div className="flex items-center gap-2">
              <Button
                onClick={handleOpenStats}
                variant="outline"
                className="font-medium px-5 py-2.5 rounded-md text-sm border-[#555555] text-white hover:bg-[#3a3a3a]"
              >
                <BarChart3 className="w-4 h-4 mr-2" />
                Team Stats
              </Button>
              <Button
                onClick={() => setShowInviteDialog(true)}
                variant="brand-primary"
                disabled={inviteMutation.isPending || updateRoleMutation.isPending || removeMemberMutation.isPending || cancelInviteMutation.isPending}
                className="font-medium px-5 py-2.5 rounded-md text-sm"
              >
                <UserPlus className="w-4 h-4 mr-2" />
                Invite Member
              </Button>
            </div>
          </div>

          {/* Search Bar */}
          <div className="relative mb-6">
            <Search className="absolute left-4 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-500" />
            <Input
              type="text"
              placeholder="Search team members..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-12 pr-4 py-6 bg-transparent border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-gray-600 focus:ring-0"
            />
          </div>

          {/* Tabs */}
          <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as 'members' | 'invitations')}>
            <TabsList className="bg-[#1a1a1a] border-b border-gray-800 w-full grid grid-cols-2">
              <TabsTrigger value="members" className="data-[state=active]:bg-brand-orange/10 data-[state=active]:text-brand-orange">
                Active Members ({filteredMembers.length})
              </TabsTrigger>
              <TabsTrigger value="invitations" className="data-[state=active]:bg-brand-orange/10 data-[state=active]:text-brand-orange">
                Pending Invitations ({filteredInvitations.length})
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </div>
      </div>

      {/* Scrollable Content Section */}
      <div className="flex-1 overflow-y-auto custom-scrollbar min-h-0">
        <div className="w-full px-8 pb-6">
          {/* Error Message */}
          {error && (
            <div className="max-w-[850px] mx-auto mb-6">
              <div className="bg-red-900/20 border border-red-500 text-red-400 px-4 py-3 rounded-md flex items-center justify-between">
                <span>{error}</span>
                <button onClick={() => setError(null)} className="text-red-400 hover:text-red-300">
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}

          {/* Loading State */}
          {loading ? (
            <div className="text-center py-12">
              <div className="animate-spin w-8 h-8 border-2 border-brand-orange border-t-transparent rounded-full mx-auto mb-4"></div>
              <p className="text-gray-400">Loading team members...</p>
            </div>
          ) : (
            <div className="max-w-[850px] mx-auto">
              <Tabs value={activeTab}>
                {/* Active Members Tab */}
                <TabsContent value="members">
                  {filteredMembers.length === 0 ? (
                    <Card className="p-12 text-center bg-[#1a1a1a] border-gray-800">
                      <div className="max-w-md mx-auto">
                        <div className="w-16 h-16 bg-brand-orange/10 rounded-full flex items-center justify-center mx-auto mb-4">
                          <UserPlus className="w-8 h-8 text-brand-orange" />
                        </div>
                        <h3 className="text-xl font-semibold text-white mb-2">No Team Members</h3>
                        <p className="text-gray-400 mb-6">
                          Invite your first team member to start collaborating.
                        </p>
                      </div>
                    </Card>
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      {filteredMembers.map(member => (
                        <Card key={member.id} className="p-6 bg-[#1a1a1a] border-gray-800 hover:border-gray-700 transition-colors">
                          <div className="flex items-start justify-between mb-3">
                            <div className="flex-1 min-w-0 pr-2">
                              {/* Member Name and Role Badge */}
                              <div className="flex items-center gap-3 mb-2">
                                <h3 className="text-lg font-normal text-white truncate" title={getMemberName(member)}>
                                  {getMemberName(member).length > 15
                                    ? `${getMemberName(member).substring(0, 15)}...`
                                    : getMemberName(member)}
                                </h3>
                                <Badge variant={getRoleBadgeVariant(member.role)} className="flex items-center gap-1 flex-shrink-0">
                                  {getRoleIcon(member.role)}
                                  {member.role.charAt(0).toUpperCase() + member.role.slice(1)}
                                </Badge>
                              </div>

                              {/* Email */}
                              <p className="text-sm text-gray-400 mb-3 truncate" title={member.user?.email}>
                                {member.user?.email && member.user.email.length > 35
                                  ? `${member.user.email.substring(0, 35)}...`
                                  : member.user?.email}
                              </p>

                              {/* Timestamp */}
                              <p className="text-xs text-gray-500">
                                Joined {formatTimeAgo(member.joined_at || member.created_at)}
                              </p>
                            </div>

                            {/* Action Buttons */}
                            <div className="flex gap-2 flex-shrink-0">
                              {/* Owners and admins can change roles (with restrictions) */}
                              {canChangeRole(member) && (
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  onClick={() => handleChangeRoleClick(member)}
                                  disabled={updateRoleMutation.isPending || removeMemberMutation.isPending}
                                  className="text-gray-400 hover:text-white hover:bg-gray-800"
                                  title="Change role"
                                >
                                  <Shield className="w-4 h-4" />
                                </Button>
                              )}
                              {/* Show delete button based on role hierarchy */}
                              {canRemoveMember(member) && (
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  onClick={() => handleRemoveClick(member)}
                                  disabled={updateRoleMutation.isPending || removeMemberMutation.isPending}
                                  className="text-gray-400 hover:text-red-400 hover:bg-gray-800"
                                  title="Remove member"
                                >
                                  <Trash2 className="w-4 h-4" />
                                </Button>
                              )}
                            </div>
                          </div>
                        </Card>
                      ))}
                    </div>
                  )}
                </TabsContent>

                {/* Pending Invitations Tab */}
                <TabsContent value="invitations">
                  {filteredInvitations.length === 0 ? (
                    <Card className="p-12 text-center bg-[#1a1a1a] border-gray-800">
                      <div className="max-w-md mx-auto">
                        <div className="w-16 h-16 bg-brand-orange/10 rounded-full flex items-center justify-center mx-auto mb-4">
                          <UserPlus className="w-8 h-8 text-brand-orange" />
                        </div>
                        <h3 className="text-xl font-semibold text-white mb-2">No Pending Invitations</h3>
                        <p className="text-gray-400">
                          All invitations have been accepted or there are no pending invites.
                        </p>
                      </div>
                    </Card>
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      {filteredInvitations.map(invitation => (
                        <Card key={invitation.id} className="p-6 bg-[#1a1a1a] border-gray-800 hover:border-gray-700 transition-colors">
                          {/* Row 1: Email and Cancel button */}
                          <div className="flex items-center justify-between mb-2">
                            <h3 className="text-lg font-normal text-white truncate pr-2" title={invitation.email}>
                              {invitation.email.length > 25
                                ? `${invitation.email.substring(0, 25)}...`
                                : invitation.email}
                            </h3>
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => handleCancelInvitationClick(invitation)}
                              disabled={resending !== null || cancelInviteMutation.isPending}
                              className="text-gray-400 hover:text-red-400 hover:bg-gray-800 flex-shrink-0"
                              title="Cancel invitation"
                            >
                              <X className="w-4 h-4" />
                            </Button>
                          </div>

                          {/* Row 2: Invited by */}
                          <p className="text-sm text-gray-400 mb-1">
                            Invited by {getInviterName(invitation)}
                          </p>

                          {/* Row 3: Sent date */}
                          <p className="text-xs text-gray-500 mb-2">
                            Sent {formatTimeAgo(invitation.created_at)}
                          </p>

                          {/* Row 4: Expiration, Role badge and Resend button */}
                          <div className="flex items-center justify-between">
                            <p className="text-xs text-yellow-500">
                              {formatExpiresIn(invitation.expires_at)}
                            </p>
                            <div className="flex items-center gap-2">
                              <Badge variant={getRoleBadgeVariant(invitation.role)} className="flex items-center gap-1">
                                {getRoleIcon(invitation.role)}
                                {invitation.role.charAt(0).toUpperCase() + invitation.role.slice(1)}
                              </Badge>
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => handleCopyInvitationLink(invitation.id)}
                                disabled={copyingLink === invitation.id || resending === invitation.id || cancelInviteMutation.isPending}
                                className="text-gray-400 hover:text-white hover:bg-gray-800"
                                title="Copy invitation link"
                              >
                                {copyingLink === invitation.id ? (
                                  <Loader2 className="w-4 h-4 animate-spin" />
                                ) : (
                                  <Copy className="w-4 h-4" />
                                )}
                              </Button>
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => handleResendInvitation(invitation.id)}
                                disabled={resending === invitation.id || cancelInviteMutation.isPending}
                                className="text-gray-400 hover:text-white hover:bg-gray-800"
                                title="Resend invitation"
                              >
                                {resending === invitation.id ? (
                                  <Loader2 className="w-4 h-4 animate-spin" />
                                ) : (
                                  <RefreshCw className="w-4 h-4" />
                                )}
                              </Button>
                            </div>
                          </div>
                        </Card>
                      ))}
                    </div>
                  )}
                </TabsContent>
              </Tabs>
            </div>
          )}
        </div>
      </div>

      {/* Invite Member Dialog */}
      <Dialog open={showInviteDialog} onOpenChange={(open) => {
        if (!open && inviteMutation.isPending) return
        if (!open) resetInviteForm()
        setShowInviteDialog(open)
      }}>
        <DialogContent className="max-w-lg bg-[#2a2a2a] border-[#444444]">
          <DialogHeader>
            <DialogTitle className="text-white">Invite Team Member</DialogTitle>
          </DialogHeader>

          <div className="space-y-4">
            <div>
              <Label htmlFor="invite-email" className="text-white">
                Email Address <span className="text-red-400">*</span>
              </Label>
              <Input
                id="invite-email"
                type="email"
                placeholder="colleague@example.com"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                className="mt-1 bg-[#1a1a1a] border-[#555555] text-white"
              />
            </div>

            <div>
              <Label htmlFor="invite-role" className="text-white">
                Role <span className="text-red-400">*</span>
              </Label>
              <Select value={inviteRole} onValueChange={(value) => setInviteRole(value as 'admin' | 'member')}>
                <SelectTrigger className="mt-1 bg-[#1a1a1a] border-[#555555] text-white">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-[#2a2a2a] border-[#555555]">
                  <SelectItem value="viewer">Viewer</SelectItem>
                  <SelectItem value="member">Member</SelectItem>
                  <SelectItem value="admin">Admin</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-gray-400 mt-1">
                {inviteRole === 'admin'
                  ? 'Can invite, remove members, and manage roles'
                  : 'Can view and collaborate on team content'}
              </p>
            </div>

            <div>
              <Label htmlFor="invite-message" className="text-white">
                Personal Message (Optional)
              </Label>
              <Input
                id="invite-message"
                type="text"
                placeholder="Looking forward to working with you!"
                value={inviteMessage}
                onChange={(e) => setInviteMessage(e.target.value)}
                className="mt-1 bg-[#1a1a1a] border-[#555555] text-white"
              />
            </div>

            <div className="flex justify-end gap-2 pt-4">
              <Button
                variant="outline"
                onClick={() => {
                  setShowInviteDialog(false)
                  resetInviteForm()
                }}
                disabled={inviteMutation.isPending}
                className="border-[#555555] text-white hover:bg-[#3a3a3a]"
              >
                Cancel
              </Button>
              <Button
                onClick={handleInviteMember}
                disabled={inviteMutation.isPending || !inviteEmail.trim()}
                className={`${
                  inviteMutation.isPending || !inviteEmail.trim()
                    ? 'bg-gray-500 cursor-not-allowed'
                    : 'bg-brand-orange hover:bg-brand-orange/90'
                } flex items-center gap-2`}
              >
                {inviteMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
                Send Invitation
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Change Role Dialog */}
      <Dialog open={showRoleDialog} onOpenChange={(open) => {
        if (!open && updateRoleMutation.isPending) return
        if (!open) setSelectedMember(null)
        setShowRoleDialog(open)
      }}>
        <DialogContent className="max-w-md bg-[#2a2a2a] border-[#444444]">
          <DialogHeader>
            <DialogTitle className="text-white">Change Member Role</DialogTitle>
          </DialogHeader>

          <div className="space-y-4">
            <p className="text-sm text-[#aaaaaa]">
              Update the role for <span className="font-semibold text-white">{selectedMember && getMemberName(selectedMember)}</span>
            </p>

            <div>
              <Label htmlFor="new-role" className="text-white">
                New Role
              </Label>
              <Select value={newRole} onValueChange={(value) => setNewRole(value as TenantRole)}>
                <SelectTrigger className="mt-1 bg-[#1a1a1a] border-[#555555] text-white">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-[#2a2a2a] border-[#555555]">
                  <SelectItem value="viewer">Viewer</SelectItem>
                  <SelectItem value="member">Member</SelectItem>
                  <SelectItem value="admin">Admin</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-gray-400 mt-2">
                {newRole === 'owner'
                  ? 'Full control over workspace and team'
                  : newRole === 'admin'
                  ? 'Can invite, remove members, and manage roles'
                  : newRole === 'viewer'
                  ? 'Can only view shared dashboards'
                  : 'Can view and collaborate on team content'}
              </p>
            </div>

            <div className="flex justify-end gap-2 pt-4">
              <Button
                variant="outline"
                onClick={() => {
                  setShowRoleDialog(false)
                  setSelectedMember(null)
                }}
                disabled={updateRoleMutation.isPending}
                className="border-[#555555] text-white hover:bg-[#3a3a3a]"
              >
                Cancel
              </Button>
              <Button
                onClick={handleUpdateRole}
                disabled={updateRoleMutation.isPending}
                className={`${
                  updateRoleMutation.isPending
                    ? 'bg-gray-500 cursor-not-allowed'
                    : 'bg-brand-orange hover:bg-brand-orange/90'
                } flex items-center gap-2`}
              >
                {updateRoleMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
                Update Role
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Remove Member Dialog */}
      <Dialog open={showRemoveDialog} onOpenChange={(open) => {
        if (!open && removeMemberMutation.isPending) return
        if (!open) setMemberToRemove(null)
        setShowRemoveDialog(open)
      }}>
        <DialogContent className="max-w-md bg-[#2a2a2a] border-[#444444]">
          <DialogHeader>
            <DialogTitle className="text-white">Remove Team Member?</DialogTitle>
          </DialogHeader>

          <div className="space-y-4">
            <p className="text-sm text-[#aaaaaa]">
              Are you sure you want to remove <span className="font-semibold text-white">{memberToRemove && getMemberName(memberToRemove)}</span> from the team? They will immediately lose access to all team resources.
            </p>

            <div className="flex justify-end gap-2 pt-4">
              <Button
                variant="outline"
                onClick={() => {
                  setShowRemoveDialog(false)
                  setMemberToRemove(null)
                }}
                disabled={removeMemberMutation.isPending}
                className="border-[#555555] text-white hover:bg-[#3a3a3a]"
              >
                Cancel
              </Button>
              <Button
                onClick={handleRemoveMember}
                disabled={removeMemberMutation.isPending}
                className={`${
                  removeMemberMutation.isPending
                    ? 'bg-gray-500 cursor-not-allowed'
                    : 'bg-red-800 hover:bg-red-900'
                } text-white flex items-center gap-2`}
              >
                {removeMemberMutation.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Trash2 className="mr-2 h-4 w-4" />
                )}
                {removeMemberMutation.isPending ? 'Removing...' : 'Remove Member'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Cancel Invitation Dialog */}
      <Dialog open={showCancelDialog} onOpenChange={(open) => {
        if (!open && cancelInviteMutation.isPending) return
        if (!open) setInvitationToCancel(null)
        setShowCancelDialog(open)
      }}>
        <DialogContent className="max-w-md bg-[#2a2a2a] border-[#444444]">
          <DialogHeader>
            <DialogTitle className="text-white">Cancel Invitation?</DialogTitle>
          </DialogHeader>

          <div className="space-y-4">
            <p className="text-sm text-[#aaaaaa]">
              Are you sure you want to cancel the invitation to <span className="font-semibold text-white">{invitationToCancel?.email}</span>? The invitation link will become invalid.
            </p>

            <div className="flex justify-end gap-2 pt-4">
              <Button
                variant="outline"
                onClick={() => {
                  setShowCancelDialog(false)
                  setInvitationToCancel(null)
                }}
                disabled={cancelInviteMutation.isPending}
                className="border-[#555555] text-white hover:bg-[#3a3a3a]"
              >
                Keep Invitation
              </Button>
              <Button
                onClick={handleCancelInvitation}
                disabled={cancelInviteMutation.isPending}
                className={`${
                  cancelInviteMutation.isPending
                    ? 'bg-gray-500 cursor-not-allowed'
                    : 'bg-red-800 hover:bg-red-900'
                } text-white flex items-center gap-2`}
              >
                {cancelInviteMutation.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <X className="mr-2 h-4 w-4" />
                )}
                {cancelInviteMutation.isPending ? 'Canceling...' : 'Cancel Invitation'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Invitation Link Dialog */}
      <Dialog open={showLinkDialog} onOpenChange={setShowLinkDialog}>
        <DialogContent className="max-w-lg bg-[#2a2a2a] border-[#444444]">
          <DialogHeader>
            <DialogTitle className="text-white">Invitation Link</DialogTitle>
          </DialogHeader>

          <div className="space-y-4">
            <p className="text-sm text-[#aaaaaa]">
              Share this link with the invitee. Expires in 7 days.
            </p>

            {linkEmailSent === false && (
              <div className="rounded-md border border-yellow-700/40 bg-yellow-900/20 px-3 py-2 text-xs text-yellow-300">
                Email was not sent — SMTP isn't configured on this server. Copy the link below
                and share it directly with your teammate.
              </div>
            )}
            {linkEmailSent === true && (
              <div className="rounded-md border border-emerald-700/40 bg-emerald-900/20 px-3 py-2 text-xs text-emerald-300">
                Invite email sent. You can also copy the link below.
              </div>
            )}

            <div className="flex gap-2">
              <Input
                readOnly
                value={generatedLink}
                className="bg-[#1a1a1a] border-[#555555] text-white text-sm"
              />
              <Button
                onClick={handleCopyLink}
                variant="outline"
                className="border-[#555555] text-white hover:bg-[#3a3a3a] flex-shrink-0"
              >
                {linkCopied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
              </Button>
            </div>

            <div className="flex justify-end pt-2">
              <Button
                onClick={() => setShowLinkDialog(false)}
                className="bg-brand-orange hover:bg-brand-orange/90"
              >
                Done
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Team Stats Dialog */}
      <Dialog open={showStatsDialog} onOpenChange={setShowStatsDialog}>
        <DialogContent className="max-w-4xl bg-[#2a2a2a] border-[#444444]">
          <DialogHeader>
            <DialogTitle className="text-white">Team Stats</DialogTitle>
          </DialogHeader>

          <div className="space-y-4">
            {statsError && (
              <div className="bg-red-900/20 border border-red-500 text-red-400 px-4 py-3 rounded-md text-sm">
                {statsError}
              </div>
            )}

            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-500" />
              <Input
                type="text"
                placeholder="Search members..."
                value={statsSearch}
                onChange={(e) => setStatsSearch(e.target.value)}
                className="w-full pl-9 pr-4 py-2 bg-[#1a1a1a] border-[#555555] text-white placeholder-gray-500"
              />
            </div>

            {statsLoading ? (
              <div className="text-center py-12">
                <Loader2 className="w-8 h-8 animate-spin text-brand-orange mx-auto" />
              </div>
            ) : (
              (() => {
                const roleOrder: Record<string, number> = { owner: 0, admin: 1, member: 2, viewer: 3 }
                const filtered = memberStats.filter((m) => {
                  if (!statsSearch) return true
                  const q = statsSearch.toLowerCase()
                  return (
                    (m.full_name?.toLowerCase().includes(q) ?? false) ||
                    (m.email?.toLowerCase().includes(q) ?? false)
                  )
                })
                const sorted = [...filtered].sort((a, b) => {
                  const ra = roleOrder[a.role] ?? 99
                  const rb = roleOrder[b.role] ?? 99
                  if (ra !== rb) return ra - rb
                  return b.notebooks_count - a.notebooks_count
                })
                const totals = sorted.reduce(
                  (acc, m) => ({
                    notebooks: acc.notebooks + m.notebooks_count,
                    dashboards: acc.dashboards + m.dashboards_count,
                    datasources: acc.datasources + m.datasources_count,
                    queries: acc.queries + m.queries_count,
                  }),
                  { notebooks: 0, dashboards: 0, datasources: 0, queries: 0 }
                )
                const formatRole = (r: string) => r.charAt(0).toUpperCase() + r.slice(1)

                if (sorted.length === 0) {
                  return (
                    <div className="text-center py-12 text-gray-400 text-sm">
                      No members found
                    </div>
                  )
                }

                return (
                  <>
                    <div className="overflow-x-auto max-h-[50vh] overflow-y-auto custom-scrollbar">
                      <table className="w-full text-sm table-fixed">
                        <colgroup>
                          <col style={{ width: '28%' }} />
                          <col style={{ width: '12%' }} />
                          <col style={{ width: '14%' }} />
                          <col style={{ width: '12%' }} />
                          <col style={{ width: '12%' }} />
                          <col style={{ width: '12%' }} />
                          <col style={{ width: '10%' }} />
                        </colgroup>
                        <thead className="sticky top-0 bg-[#2a2a2a]">
                          <tr className="border-b border-[#444444] text-brand-orange text-left">
                            <th className="py-3 px-3 font-medium">Name</th>
                            <th className="py-3 px-3 font-medium">Role</th>
                            <th className="py-3 px-3 font-medium">Joined</th>
                            <th className="py-3 px-3 font-medium text-right">Notebooks</th>
                            <th className="py-3 px-3 font-medium text-right">Dashboards</th>
                            <th className="py-3 px-3 font-medium text-right">Datasources</th>
                            <th className="py-3 px-3 font-medium text-right">Queries</th>
                          </tr>
                        </thead>
                        <tbody>
                          {sorted.map((m) => (
                            <tr key={m.member_id} className="border-b border-[#3a3a3a] text-gray-200">
                              <td className="py-3 px-3">
                                <div className="text-white truncate" title={m.full_name || m.email || ''}>
                                  {m.full_name || m.email || 'Unknown'}
                                </div>
                                {m.full_name && m.email && (
                                  <div className="text-xs text-gray-500 truncate" title={m.email}>
                                    {m.email}
                                  </div>
                                )}
                              </td>
                              <td className="py-3 px-3">{formatRole(m.role)}</td>
                              <td className="py-3 px-3 text-gray-400">
                                {m.joined_at ? formatTimeAgo(m.joined_at) : '—'}
                              </td>
                              <td className="py-3 px-3 text-right tabular-nums">{m.notebooks_count.toLocaleString()}</td>
                              <td className="py-3 px-3 text-right tabular-nums">{m.dashboards_count.toLocaleString()}</td>
                              <td className="py-3 px-3 text-right tabular-nums">{m.datasources_count.toLocaleString()}</td>
                              <td className="py-3 px-3 text-right tabular-nums">{m.queries_count.toLocaleString()}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <table className="w-full text-sm table-fixed border-t-2 border-[#555555]">
                      <colgroup>
                        <col style={{ width: '28%' }} />
                        <col style={{ width: '12%' }} />
                        <col style={{ width: '14%' }} />
                        <col style={{ width: '12%' }} />
                        <col style={{ width: '12%' }} />
                        <col style={{ width: '12%' }} />
                        <col style={{ width: '10%' }} />
                      </colgroup>
                      <tbody>
                        <tr className="text-white font-medium">
                          <td className="py-3 px-3" colSpan={3}>Team total</td>
                          <td className="py-3 px-3 text-right tabular-nums">{totals.notebooks.toLocaleString()}</td>
                          <td className="py-3 px-3 text-right tabular-nums">{totals.dashboards.toLocaleString()}</td>
                          <td className="py-3 px-3 text-right tabular-nums">{totals.datasources.toLocaleString()}</td>
                          <td className="py-3 px-3 text-right tabular-nums">{totals.queries.toLocaleString()}</td>
                        </tr>
                      </tbody>
                    </table>
                  </>
                )
              })()
            )}

            {!statsLoading && slackStats && (
              <div className="border-t border-[#444444] pt-4 mt-2">
                <div className="text-brand-orange text-sm font-medium mb-2">Slack Stats</div>
                <div className="grid grid-cols-3 gap-4 text-sm text-gray-300">
                  <span>Notebooks: <span className="text-white tabular-nums">{slackStats.notebooks_count.toLocaleString()}</span></span>
                  <span>Dashboards: <span className="text-white tabular-nums">{slackStats.dashboards_count.toLocaleString()}</span></span>
                  <span>Queries: <span className="text-white tabular-nums">{slackStats.queries_count.toLocaleString()}</span></span>
                </div>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
