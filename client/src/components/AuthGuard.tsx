/**
 * AuthGuard - Route protection component for hosted mode
 *
 * Modes:
 * - Default: Protects routes from unauthenticated users (redirects to /login)
 * - guestOnly: Protects routes from authenticated users (redirects to /)
 */

import { Navigate, useLocation } from 'react-router-dom'
import { useAppConfig } from '../hooks/useAppConfig'
import { useStore } from '../stores/useStore'
import { isEmbeddedKnowledgeCenterLocation } from '../contexts/EmbeddedModeContext'

interface AuthGuardProps {
  children: React.ReactNode
  guestOnly?: boolean // If true, redirect authenticated users to home
  skipOnboarding?: boolean // Used for the setup-workspace route itself
}

export function AuthGuard({
  children,
  guestOnly = false,
  skipOnboarding = false
}: AuthGuardProps) {
  const location = useLocation()
  const isAuthenticated = useStore(state => state.isAuthenticated)
  const isLoading = useStore(state => state.isLoading)
  const tenants = useStore(state => state.tenants)
  const isLoadingTenants = useStore(state => state.isLoadingTenants)
  const tenantsFetched = useStore(state => state.tenantsFetched)
  const { isSelfHosted, isLoading: isConfigLoading } = useAppConfig()
  const embeddedKnowledgeCenter = isEmbeddedKnowledgeCenterLocation(location)
  const loginTarget = embeddedKnowledgeCenter ? '/login?embedded=veadk-studio' : '/login'

  // Check if we're in an invitation acceptance flow
  const hasPendingInvitation = typeof window !== 'undefined' && localStorage.getItem('pendingInvitationToken') !== null

  // Loading state - show spinner
  // For guestOnly routes, only check isLoading (no tenant loading needed)
  // For protected routes, wait for tenants to be fetched to avoid rendering with incomplete data
  const needsTenantsLoaded = isAuthenticated && !tenantsFetched && !guestOnly
  const isLoadingState = guestOnly
    ? isLoading
    : (isLoading || isLoadingTenants || isConfigLoading || needsTenantsLoaded || (isAuthenticated && hasPendingInvitation))

  if (isLoadingState) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#0f0f0f]">
        <div className="flex flex-col items-center gap-4">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-gray-600 border-t-brand-orange"></div>
          <p className="text-sm text-gray-400">Loading...</p>
        </div>
      </div>
    )
  }

  // Guest-only mode: redirect authenticated users to home
  // BUT if they came from noAccess redirect, let them see the login page
  if (guestOnly) {
    if (isAuthenticated && !location.state?.noAccess) {
      const from = location.state?.from?.pathname || '/'
      return <Navigate to={from} replace />
    }
    return <>{children}</>
  }

  // Protected mode: redirect unauthenticated users to login
  if (!isAuthenticated) {
    return <Navigate to={loginTarget} state={{ from: location }} replace />
  }

  // No tenants = needs onboarding (first login)
  // Skip this check for the setup-workspace route itself to avoid redirect loop
  if (!skipOnboarding && tenants.length === 0) {
    // In self-hosted mode with no tenants, redirect to login
    if (isSelfHosted) {
      return <Navigate to={loginTarget} state={{ noAccess: true, from: location }} replace />
    }
    return <Navigate to="/setup-workspace" replace />
  }

  // Authenticated - render children
  return <>{children}</>
}
