import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ApiService } from '../services/api'
import { showToast } from '../utils/toast'

export const useTeamMembers = () => {
  return useQuery({
    queryKey: ['team-members'],
    queryFn: () => ApiService.getTeamMembers(),
  })
}

export const usePendingInvitations = () => {
  return useQuery({
    queryKey: ['pending-invitations'],
    queryFn: () => ApiService.getPendingInvitations(),
  })
}

export const useInviteTeamMember = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: { email: string; role: 'admin' | 'member'; message?: string }) =>
      ApiService.inviteTeamMember(data),
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: ['pending-invitations'] })
      const message = response?.message || 'Invitation sent successfully'
      showToast.success(message)
      return response
    },
    onError: (error) => {
      console.error('Error inviting team member:', error)
      const errorMessage = error instanceof Error ? error.message : 'Failed to send invitation'
      showToast.error(errorMessage)
    },
  })
}

export const useResendInvitation = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (invitationId: string) => ApiService.resendInvitation(invitationId),
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: ['pending-invitations'] })
      const message = response?.message || 'Invitation resent successfully'
      showToast.success(message)
      return response
    },
    onError: (error) => {
      console.error('Error resending invitation:', error)
      const errorMessage = error instanceof Error ? error.message : 'Failed to resend invitation'
      showToast.error(errorMessage)
    },
  })
}

export const useCancelInvitation = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (invitationId: string) => ApiService.cancelInvitation(invitationId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pending-invitations'] })
      showToast.success('Invitation cancelled successfully')
    },
    onError: (error) => {
      console.error('Error cancelling invitation:', error)
      const errorMessage = error instanceof Error ? error.message : 'Failed to cancel invitation'
      showToast.error(errorMessage)
    },
  })
}

export const useUpdateMemberRole = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ memberId, role }: { memberId: string; role: 'owner' | 'admin' | 'member' | 'viewer' }) =>
      ApiService.updateMemberRole(memberId, role),
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: ['team-members'] })

      const message = response?.message || 'Member role updated successfully'
      showToast.success(message)
    },
    onError: (error) => {
      console.error('Error updating member role:', error)
      const errorMessage = error instanceof Error ? error.message : 'Failed to update member role'
      showToast.error(errorMessage)
    },
  })
}

export const useRemoveMember = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (memberId: string) => ApiService.removeMember(memberId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['team-members'] })
      showToast.success('Member removed successfully')
    },
    onError: (error) => {
      console.error('Error removing member:', error)
      const errorMessage = error instanceof Error ? error.message : 'Failed to remove member'
      showToast.error(errorMessage)
    },
  })
}
