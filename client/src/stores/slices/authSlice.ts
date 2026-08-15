import type { StateCreator } from 'zustand'
import type { StoreState } from '../useStore'
import posthog from 'posthog-js'
import { ApiService } from '../../services/api'
import { queryClient } from '../../lib/queryClient'
import { clearAccessToken, clearRefreshToken, getAccessToken, getRefreshToken, setAccessToken, setRefreshToken } from '../../services/tokenStore'
import { isTauriApp } from '../../lib/tauri-api'

export interface AuthUser {
  id: string
  email: string
  full_name: string | null
  avatar_url: string | null
  is_verified: boolean
  is_active: boolean
  is_superuser: boolean
}

export interface AuthSlice {
  user: AuthUser | null
  token: string | null
  isAuthenticated: boolean
  isLoading: boolean
  authError: string | null

  login: (email: string, password: string) => Promise<void>
  googleLogin: (credential: string) => Promise<void>
  register: (email: string, password: string, fullName?: string) => Promise<void>
  logout: () => void

  fetchUser: () => Promise<void>
  forgotPassword: (email: string) => Promise<void>
  resetPassword: (token: string, password: string) => Promise<void>
  setAuthError: (error: string | null) => void
  initAuth: () => Promise<void>
  refreshAccessToken: () => Promise<boolean>
  setLocalUser: (userData: { id: string; email: string; fullName?: string | null }) => void
}

const initialState = {
  user: null,
  token: getAccessToken(),
  isAuthenticated: false,
  isLoading: true,
  authError: null,
}

export const createAuthSlice: StateCreator<
  StoreState,
  [],
  [],
  AuthSlice
> = (set, get) => ({
  ...initialState,

  initAuth: async () => {
    const token = getAccessToken()

    if (token && isTauriApp()) {
      set({ token, isLoading: true })
      try {
        await get().fetchUser()
        try {
          await get().fetchTenants()
        } catch (e) {
          console.warn('Failed to fetch tenants during init:', e)
        }
        set({ isLoading: false })
        return
      } catch {
        set({ token: null, user: null, isAuthenticated: false })
        clearAccessToken()
      }
    }

    // Browser builds store refresh state in httpOnly cookies. If there is no
    // session hint at all, skip the expected unauthenticated refresh request so
    // the login page does not emit a noisy 401 console error on first load.
    if (!isTauriApp() && !document.cookie.includes('csrf_token=') && !getRefreshToken()) {
      set({ isAuthenticated: false, isLoading: false })
      return
    }

    set({ isLoading: true })
    try {
      const refreshed = await get().refreshAccessToken()
      if (!refreshed) {
        set({ isAuthenticated: false, isLoading: false })
        return
      }

      await get().fetchUser()
      await get().fetchTenants()
    } catch {
      set({ token: null, user: null, isAuthenticated: false })
      clearAccessToken()
    } finally {
      set({ isLoading: false })
    }
  },

  login: async (email: string, password: string) => {
    set({ isLoading: true, authError: null })
    try {
      const response = await ApiService.authLogin(email, password)
      const { access_token, refresh_token } = response
      setAccessToken(access_token)
      set({ token: access_token, isAuthenticated: true })
      if (refresh_token) {
        setRefreshToken(refresh_token)
      }

      try {
        await get().fetchUser()
      } catch (e) {
        console.warn('Failed to fetch user profile after login:', e)
      }

      const hasPendingInvitation = localStorage.getItem('pendingInvitationToken')
      if (!hasPendingInvitation) {
        try {
          await get().fetchTenants()
        } catch (e) {
          console.warn('Failed to fetch tenants after login:', e)
        }
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Login failed'
      set({ authError: message, isAuthenticated: false })
      throw error
    } finally {
      set({ isLoading: false })
    }
  },

  googleLogin: async (credential: string) => {
    set({ isLoading: true, authError: null })
    try {
      const response = await ApiService.authGoogleLogin(credential)
      const { access_token, refresh_token } = response
      setAccessToken(access_token)
      set({ token: access_token, isAuthenticated: true })
      if (refresh_token) {
        setRefreshToken(refresh_token)
      }

      try {
        await get().fetchUser()
      } catch (e) {
        console.warn('Failed to fetch user profile after Google login:', e)
      }

      const hasPendingInvitation = localStorage.getItem('pendingInvitationToken')
      if (!hasPendingInvitation) {
        try {
          await get().fetchTenants()
        } catch (e) {
          console.warn('Failed to fetch tenants after Google login:', e)
        }
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Google login failed'
      set({ authError: message, isAuthenticated: false })
      throw error
    } finally {
      set({ isLoading: false })
    }
  },

  register: async (email: string, password: string, fullName?: string) => {
    set({ isLoading: true, authError: null })
    try {
      await ApiService.authRegister(email, password, fullName)
      await get().login(email, password)
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Registration failed'
      set({ authError: message })
      throw error
    } finally {
      set({ isLoading: false })
    }
  },

  logout: () => {
    void ApiService.authLogout()
    set({ user: null, token: null, isAuthenticated: false, authError: null })
    clearAccessToken()
    clearRefreshToken()
    posthog.reset()
    // Clear React Query cache - CRITICAL for preventing data leakage
    queryClient.clear()

    // Clear all localStorage items related to user session
    if (typeof window !== 'undefined') {
      localStorage.removeItem('byaan_auth_token')
      localStorage.removeItem('byaan_refresh_token')
      localStorage.removeItem('byaan_switching_tenant')
      localStorage.removeItem('pendingInvitationToken')
      localStorage.removeItem('pendingInvitationTenantName')
    }

    // Clear all Zustand slices to prevent data leakage between users
    get().clearTenants()
    get().setNotebooks([])
    get().setCurrentNotebook(null)
    get().setConnections([])
    get().setSelectedConnection(null)
    get().clearMessages()
    get().setLLMConnections([])
    get().setSelectedLLMConnection(null)
    get().clearFolders()
    get().setActiveFolder(null)

    // Clear additional slices that were missing
    get().clearSchema()
    get().clearDownloads()
    get().resetTableMentions()
    get().clearContext()
  },

  fetchUser: async () => {
    const { token } = get()
    if (!token) {
      set({ isAuthenticated: false })
      return
    }

    try {
      const user = await ApiService.authGetMe()
      set({ user, isAuthenticated: true })

      if (user) {
        posthog.identify(user.id, {
          email: user.email,
          name: user.full_name,
        })
        const { syncAnalyticsPreferenceFromServer } = await import('@/lib/analyticsPreference')
        void syncAnalyticsPreferenceFromServer()
      }
    } catch (error) {
      set({ user: null, token: null, isAuthenticated: false })
      clearAccessToken()
      throw error
    }
  },

  forgotPassword: async (email: string) => {
    set({ isLoading: true, authError: null })
    try {
      await ApiService.authForgotPassword(email)
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to send reset email'
      set({ authError: message })
      throw error
    } finally {
      set({ isLoading: false })
    }
  },

  resetPassword: async (token: string, password: string) => {
    set({ isLoading: true, authError: null })
    try {
      await ApiService.authResetPassword(token, password)
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to reset password'
      set({ authError: message })
      throw error
    } finally {
      set({ isLoading: false })
    }
  },

  setAuthError: (error) => set({ authError: error }),

  refreshAccessToken: async () => {
    try {
      const refreshToken = getRefreshToken()
      const response = await ApiService.authRefreshToken(refreshToken || undefined)
      const { access_token, refresh_token } = response
      setAccessToken(access_token)
      set({ token: access_token })
      if (refresh_token) {
        setRefreshToken(refresh_token)
      }
      return true
    } catch {
      set({ user: null, token: null, isAuthenticated: false })
      clearAccessToken()
      clearRefreshToken()
      return false
    }
  },

  setLocalUser: (userData: { id: string; email: string; fullName?: string | null }) => {
    // Set user for local mode (no JWT tokens needed)
    const user: AuthUser = {
      id: userData.id,
      email: userData.email,
      full_name: userData.fullName || null,
      avatar_url: null,
      is_verified: true,
      is_active: true,
      is_superuser: false,
    }
    set({ user, isAuthenticated: true, isLoading: false })
  },
})
