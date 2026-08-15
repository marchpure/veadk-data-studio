import { useState, useCallback } from 'react'
import { isTauriApp, getBackendUrl } from '../lib/tauri-api'
import { getApiBaseUrl } from '../lib/runtime-config'

export const getCodexOAuthBaseUrl = async (): Promise<string> => {
  if (isTauriApp()) {
    const backendUrl = await getBackendUrl()
    return `${backendUrl}/api`
  }
  return getApiBaseUrl()
}

interface CodexOAuthTokens {
  access_token: string
  refresh_token: string
  expires_at: number
}

interface CodexOAuthStatusState {
  authenticated: boolean
  tokens: CodexOAuthTokens | null
  loading: boolean
  error: string | null
}

export function useCodexOAuthStatus() {
  const [status, setStatus] = useState<CodexOAuthStatusState>({
    authenticated: false,
    tokens: null,
    loading: false,
    error: null
  })

  const setTokens = useCallback((tokens: CodexOAuthTokens) => {
    setStatus({
      authenticated: true,
      tokens,
      loading: false,
      error: null
    })
  }, [])

  const checkStatus = useCallback(async (connectionId: string) => {
    setStatus(prev => ({ ...prev, loading: true, error: null }))
    try {
      const apiBaseUrl = await getCodexOAuthBaseUrl()
      const response = await fetch(`${apiBaseUrl}/codex-oauth/status/${connectionId}`)
      const data = await response.json()
      if (data.success) {
        setStatus(prev => ({
          ...prev,
          authenticated: data.data.authenticated,
          loading: false,
          error: null
        }))
      } else {
        setStatus(prev => ({
          ...prev,
          authenticated: false,
          loading: false,
          error: data.message || 'Failed to check status'
        }))
      }
    } catch (err: unknown) {
      setStatus(prev => ({
        ...prev,
        authenticated: false,
        loading: false,
        error: err instanceof Error ? err.message : 'Failed to check status'
      }))
    }
  }, [])

  const reset = useCallback(() => {
    setStatus({
      authenticated: false,
      tokens: null,
      loading: false,
      error: null
    })
  }, [])

  return { ...status, setTokens, checkStatus, reset }
}
