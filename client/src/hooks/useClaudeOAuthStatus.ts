import { useState, useCallback } from 'react'
import { isTauriApp, getBackendUrl } from '../lib/tauri-api'
import { getApiBaseUrl } from '../lib/runtime-config'

export const getClaudeOAuthBaseUrl = async (): Promise<string> => {
  if (isTauriApp()) {
    const backendUrl = await getBackendUrl()
    return `${backendUrl}/api`
  }
  return getApiBaseUrl()
}

export type ClaudeAuthMethod = 'oauth' | 'token' | null

interface ClaudeOAuthStatusState {
  authenticated: boolean
  authMethod: ClaudeAuthMethod
  loading: boolean
  error: string | null
  savingToken: boolean
}

export function useClaudeOAuthStatus() {
  const [status, setStatus] = useState<ClaudeOAuthStatusState>({
    authenticated: false,
    authMethod: null,
    loading: true,
    error: null,
    savingToken: false
  })

  const checkStatus = useCallback(async () => {
    setStatus(prev => ({ ...prev, loading: true, error: null }))
    try {
      const apiBaseUrl = await getClaudeOAuthBaseUrl()
      const response = await fetch(`${apiBaseUrl}/claude-oauth/status`)
      const data = await response.json()
      if (data.success) {
        setStatus(prev => ({
          ...prev,
          authenticated: data.data.authenticated,
          authMethod: data.data.auth_method || null,
          loading: false,
          error: null
        }))
      } else {
        setStatus(prev => ({
          ...prev,
          authenticated: false,
          authMethod: null,
          loading: false,
          error: data.message || 'Failed to check status'
        }))
      }
    } catch (err: unknown) {
      setStatus(prev => ({
        ...prev,
        authenticated: false,
        authMethod: null,
        loading: false,
        error: err instanceof Error ? err.message : 'Failed to check status'
      }))
    }
  }, [])

  const saveToken = useCallback(async (token: string): Promise<{ success: boolean; error?: string }> => {
    setStatus(prev => ({ ...prev, savingToken: true, error: null }))
    try {
      const apiBaseUrl = await getClaudeOAuthBaseUrl()
      const response = await fetch(`${apiBaseUrl}/claude-oauth/save-token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token })
      })
      const data = await response.json()
      if (data.success) {
        setStatus(prev => ({
          ...prev,
          authenticated: true,
          authMethod: 'token',
          savingToken: false,
          error: null
        }))
        return { success: true }
      } else {
        const errorMsg = data.message || 'Failed to save token'
        setStatus(prev => ({ ...prev, savingToken: false, error: errorMsg }))
        return { success: false, error: errorMsg }
      }
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to save token'
      setStatus(prev => ({ ...prev, savingToken: false, error: errorMsg }))
      return { success: false, error: errorMsg }
    }
  }, [])

  const deleteToken = useCallback(async () => {
    try {
      const apiBaseUrl = await getClaudeOAuthBaseUrl()
      await fetch(`${apiBaseUrl}/claude-oauth/delete-token`, { method: 'POST' })
      setStatus(prev => ({ ...prev, authenticated: false, authMethod: null }))
    } catch {
      // Ignore delete errors
    }
  }, [])

  const logout = useCallback(async () => {
    try {
      const apiBaseUrl = await getClaudeOAuthBaseUrl()
      await fetch(`${apiBaseUrl}/claude-oauth/logout`, { method: 'POST' })
      setStatus(prev => ({ ...prev, authenticated: false, authMethod: null }))
    } catch {
      // Ignore logout errors
    }
  }, [])

  return { ...status, checkStatus, saveToken, deleteToken, logout }
}
