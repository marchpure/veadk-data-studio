import { type ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useScopes } from '../hooks/useScopes'

interface RoleGuardProps {
  children: ReactNode
  allowedRoles?: Array<'owner' | 'admin' | 'member' | 'viewer'>
  requireOwnerOrAdmin?: boolean
}


export function RoleGuard({ children, allowedRoles, requireOwnerOrAdmin }: RoleGuardProps) {
  const { role, isOwner, isAdmin } = useScopes()

  // If requireOwnerOrAdmin is true, check if user is owner or admin
  if (requireOwnerOrAdmin) {
    if (!isOwner && !isAdmin) {
      return <Navigate to="/" replace />
    }
    return <>{children}</>
  }

  // If allowedRoles is specified, check if user's role is in the list
  if (allowedRoles && allowedRoles.length > 0) {
    if (!role || !allowedRoles.includes(role)) {
      return <Navigate to="/" replace />
    }
    return <>{children}</>
  }

  // If no restrictions specified, allow access
  return <>{children}</>
}
