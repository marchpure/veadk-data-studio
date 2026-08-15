/**
 * WaitlistGate - Hard gate component that blocks app until user is registered.
 * One-shot flow: collect email + name, save, drop into app.
 */

import { useState, useEffect } from 'react'
import { usePostHog } from 'posthog-js/react'
import { listen } from '@tauri-apps/api/event'
import { invoke } from '@tauri-apps/api/core'
import { useStore } from '../stores/useStore'
import { ApiService } from '../services/api'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { Label } from './ui/label'
import '../styles/waitlist.css'

interface WaitlistGateProps {
  children: React.ReactNode
}

export function WaitlistGate({ children }: WaitlistGateProps) {
  const posthog = usePostHog()
  const {
    accessStatus,
    isLoading,
    error,
    setAccessStatus,
    setIsLoading,
    setError,
    setLocalUser,
    fetchTenants,
    loadPreferencesFromBackend,
  } = useStore()

  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  useEffect(() => {
    const initializeUser = async () => {
      try {
        setIsLoading(true)

        const credentialsResponse = await ApiService.getStoredCredentials()
        const credentials = credentialsResponse.data

        if (credentials) {
          if (credentials.tenantId) {
            localStorage.setItem('byaan_active_tenant', credentials.tenantId)
          }

          if (credentials.userId && credentials.email) {
            setLocalUser({
              id: String(credentials.userId),
              email: credentials.email,
              fullName: credentials.userName,
            })
          }

          await fetchTenants()
          await loadPreferencesFromBackend()

          setAccessStatus({
            hasAccess: true,
            onboarded: true,
            apiKey: credentials.apiKey,
          })

          if (posthog && credentials.userId) {
            posthog.identify(String(credentials.userId))
            posthog.people.set({
              email: credentials.email,
              name: credentials.userName,
            })
            const { syncAnalyticsPreferenceFromServer } = await import('@/lib/analyticsPreference')
            void syncAnalyticsPreferenceFromServer()
          }
        }
      } catch (err) {
        console.error('Error initializing user:', err)
        setError(err instanceof Error ? err.message : 'Failed to initialize')
      } finally {
        setIsLoading(false)
      }
    }

    initializeUser()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Deep link: only handle notebook share imports
  useEffect(() => {
    const handleDeepLink = (url: string) => {
      try {
        const urlObj = new URL(url)
        if (urlObj.protocol !== 'byaan:') return

        const host = urlObj.host || urlObj.pathname.replace('//', '')
        if (host === 'import') {
          const params = new URLSearchParams(urlObj.search)
          const shareId = params.get('share_id')
          if (shareId) {
            useStore.getState().setImportShareId(shareId)
          }
        }
      } catch (err) {
        console.error('Error handling deep link:', err)
      }
    }

    const unlisten = listen<string>('deep-link-received', (event) => {
      handleDeepLink(event.payload)
    })

    const checkInitialDeepLink = async () => {
      try {
        const initialUrl = await invoke<string | null>('get_initial_deep_link')
        if (initialUrl) {
          handleDeepLink(initialUrl)
        }
      } catch {
        // Not in Tauri environment or command not available
      }
    }
    checkInitialDeepLink()

    return () => {
      unlisten.then(fn => fn())
    }
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsSubmitting(true)
    setError(null)

    try {
      const response = await ApiService.joinWaitlist(email, name || undefined)
      const data = response.data
      if (!data) {
        throw new Error('No data returned from registration')
      }

      if (data.tenantId) {
        localStorage.setItem('byaan_active_tenant', data.tenantId)
      }

      if (data.userId) {
        setLocalUser({ id: String(data.userId), email, fullName: data.userName ?? null })
      }

      await fetchTenants()
      await loadPreferencesFromBackend()

      if (posthog && data.userId) {
        posthog.identify(String(data.userId))
        posthog.people.set({ email, name: data.userName })
      }

      setAccessStatus({ hasAccess: true, onboarded: true, apiKey: data.apiKey || null })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to register')
    } finally {
      setIsSubmitting(false)
    }
  }

  if (isLoading) {
    return (
      <div className="waitlist-container">
        <div className="waitlist-card">
          <div className="waitlist-loading">
            <div className="spinner"></div>
            <p className="loading-text">Loading...</p>
          </div>
        </div>
      </div>
    )
  }

  if (!accessStatus) {
    return (
      <div className="waitlist-container">
        <div className="waitlist-card">
          <div className="waitlist-header">
            <h1 className="waitlist-title">Welcome to Byaan</h1>
            <p className="waitlist-subtitle">
              Your AI-powered data analytics companion
            </p>
          </div>

          <form onSubmit={handleSubmit} className="waitlist-form">
            <div className="form-group">
              <Label htmlFor="email">Email address</Label>
              <Input
                id="email"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                disabled={isSubmitting}
                className="waitlist-input"
              />
            </div>

            <div className="form-group">
              <Label htmlFor="name">Name (optional)</Label>
              <Input
                id="name"
                type="text"
                placeholder="Your name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={isSubmitting}
                className="waitlist-input"
              />
            </div>

            {error && <div className="error-message">{error}</div>}

            <Button
              type="submit"
              disabled={isSubmitting}
              className="waitlist-button"
            >
              {isSubmitting ? 'Setting up...' : 'Get Started'}
            </Button>
          </form>
        </div>
      </div>
    )
  }

  return <>{children}</>
}
