import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useStore } from '../../stores/useStore'
import { ApiService } from '../../services/api'
import { useAppConfig } from '../../hooks/useAppConfig'

export default function SetupWorkspace() {
  const navigate = useNavigate()
  const { fetchTenants, user, tenants, logout } = useStore()
  const { isSelfHosted, isLoading: isConfigLoading } = useAppConfig()

  const [workspaceName, setWorkspaceName] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // If user already has tenants (e.g., via invitation), redirect to home
  useEffect(() => {
    if (tenants && tenants.length > 0) {
      navigate('/', { replace: true })
    }
  }, [tenants, navigate])

  // In self-hosted mode, this page should NEVER be shown
  // Clear localStorage, logout, and redirect to login
  useEffect(() => {
    if (isSelfHosted && !isConfigLoading) {
      // Clear any pending invitation tokens
      localStorage.removeItem('pendingInvitationToken')
      localStorage.removeItem('pendingInvitationTenantName')
      // Logout and redirect to login
      logout()
      navigate('/login', { replace: true })
    }
  }, [isSelfHosted, isConfigLoading, logout, navigate])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    if (!workspaceName.trim()) {
      setError('Please enter a workspace name')
      return
    }

    setIsLoading(true)
    try {
      // Create personal workspace
      await ApiService.createTenant(workspaceName.trim())
      await fetchTenants()

      // Navigate to home
      navigate('/', { replace: true })
    } catch (err: any) {
      // Check for 403 (workspace creation disabled in self-hosted mode)
      const errorMessage = err?.message || ''
      if (err?.response?.status === 403 || errorMessage.includes('disabled') || errorMessage.includes('403')) {
        setError('Workspace creation is disabled in this environment. If you were invited to a workspace, please contact your administrator.')
      } else {
        setError(err instanceof Error ? err.message : 'Failed to create workspace')
      }
    } finally {
      setIsLoading(false)
    }
  }

  // Show loading state while config is loading or redirecting in self-hosted mode
  if (isConfigLoading || isSelfHosted) {
    return (
      <div className="flex min-h-screen w-full items-center justify-center bg-white">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-gray-300 border-t-brand-orange"></div>
      </div>
    )
  }

  // Normal workspace creation flow (non-self-hosted only)
  return (
    <div className="flex min-h-screen w-full">
        {/* Left side - Form */}
        <div className="flex-1 flex items-center justify-center p-8 bg-white">
        <div className="w-full max-w-[380px]">
          {/* Logo */}
          <div className="mb-10">
            <span className="text-3xl font-bold text-gray-900 tracking-tight">Byaan</span>
          </div>

          {/* Header */}
          <h1 className="text-2xl font-semibold text-gray-900 mb-2">Create your workspace</h1>
          <p className="text-gray-500 mb-8">
            {user?.full_name ? `Welcome, ${user.full_name}! ` : ''}
            Give your workspace a name to get started.
          </p>

          {/* Error message */}
          {error && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md">
              <p className="text-sm text-red-600">{error}</p>
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit}>
            {/* Workspace name field */}
            <div className="mb-6">
              <label htmlFor="workspaceName" className="block text-sm font-medium text-gray-700 mb-1.5">
                Workspace name
              </label>
              <div className="flex items-center gap-3 py-3 px-4 border border-gray-200 rounded-md transition-all focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-500/10">
                <svg
                  className="flex-shrink-0 text-gray-400 w-5 h-5"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z" />
                  <polyline points="9 22 9 12 15 12 15 22" />
                </svg>
                <input
                  id="workspaceName"
                  type="text"
                  placeholder="My Workspace"
                  value={workspaceName}
                  onChange={(e) => setWorkspaceName(e.target.value)}
                  required
                  disabled={isLoading}
                  autoFocus
                  className="flex-1 border-none outline-none text-[15px] text-gray-900 bg-transparent placeholder:text-gray-400"
                />
              </div>
              <p className="mt-2 text-xs text-gray-500">
                This is where you'll organize your notebooks and data connections.
              </p>
            </div>

            {/* Submit button */}
            <button
              type="submit"
              disabled={isLoading || !workspaceName.trim()}
              className="flex items-center justify-center gap-2 w-full py-3 px-6 bg-brand-orange border-none rounded-md text-base font-semibold text-white cursor-pointer transition-all hover:bg-brand-orange-hover disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? (
                <>
                  <div className="h-5 w-5 animate-spin rounded-full border-2 border-white/30 border-t-white"></div>
                  Creating...
                </>
              ) : (
                <>
                  Create workspace
                  <svg
                    className="flex-shrink-0"
                    viewBox="0 0 24 24"
                    width="20"
                    height="20"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                  >
                    <path d="M9 18l6-6-6-6" />
                  </svg>
                </>
              )}
            </button>
          </form>
        </div>
      </div>

      {/* Right side - Branding */}
      <div className="flex-1 hidden md:flex items-center justify-center p-8 bg-[#0f0f0f]">
        <div className="max-w-[500px] text-center">
          <p className="text-xs font-semibold tracking-[0.15em] text-brand-orange mb-6">
            ALMOST THERE
          </p>
          <h1 className="text-5xl font-bold text-white leading-tight tracking-tight">
            Set up your workspace
            <br />
            to start exploring
          </h1>
        </div>
      </div>
    </div>
  )
}
