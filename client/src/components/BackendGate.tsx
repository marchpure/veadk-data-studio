import { type PropsWithChildren, useEffect, useState } from 'react'
import BackendLoadingScreen from './BackendLoadingScreen'
import { getBackendUrl, isTauriApp } from '../lib/tauri-api'

const CHECK_INTERVAL_MS = 500

interface GateState {
  ready: boolean
  statusMessage: string
  errorMessage?: string
  canRetry?: boolean
}

export default function BackendGate({ children }: PropsWithChildren) {
  const [state, setState] = useState<GateState>(() => ({
    ready: !isTauriApp(),
    statusMessage: 'Waiting for backend to become reachable…'
  }))

  useEffect(() => {
    // For non-Tauri (web dev mode), backend is already ready via proxy
    if (!isTauriApp()) {
      setState({ ready: true, statusMessage: 'Backend ready' })
      return
    }

    let cancelled = false
    let activeController: AbortController | null = null

    const checkLoop = async () => {
      while (!cancelled) {

        try {
          const backendUrl = await getBackendUrl()
          activeController = new AbortController()
          const response = await fetch(`${backendUrl}/health?ts=${Date.now()}`, {
            cache: 'no-store',
            signal: activeController.signal
          })
          activeController = null

          if (!response.ok) {
            throw new Error(`Health check returned ${response.status}`)
          }

          const payload = await response.json().catch(() => ({ status: 'unknown' }))

          // Backend reported an error
          if (payload?.status === 'error') {
            if (!cancelled) {
              setState({
                ready: false,
                statusMessage: 'Backend initialization failed',
                errorMessage: payload.message || payload.error || 'Backend failed to initialize. Please check logs for details.',
                canRetry: true
              })
            }
            // Wait before retrying in case user wants to retry
            await new Promise(resolve => setTimeout(resolve, CHECK_INTERVAL_MS))
            continue
          }

          // If backend is still starting (running migrations), show appropriate message
          if (payload?.status === 'starting') {
            if (!cancelled) {
              setState({
                ready: false,
                statusMessage: payload.message || 'Preparing database…'
              })
            }
            await new Promise(resolve => setTimeout(resolve, CHECK_INTERVAL_MS))
            continue
          }

          if (payload?.status !== 'healthy') {
            throw new Error('Backend reported unhealthy state')
          }

          // Backend is healthy!
          if (!cancelled) {
            setState({ ready: true, statusMessage: 'Backend ready' })
          }
          return
        } catch (error) {
          if (cancelled) {
            return
          }

          if (error instanceof DOMException && error.name === 'AbortError') {
            continue
          }

          // Keep trying silently - backend is still starting
          if (!cancelled) {
            setState({
              ready: false,
              statusMessage: `Preparing your workspace…`
            })
          }

          await new Promise(resolve => setTimeout(resolve, CHECK_INTERVAL_MS))
        }
      }
    }

    setState({ ready: false, statusMessage: 'Starting backend…' })
    checkLoop()

    return () => {
      cancelled = true
      if (activeController) {
        activeController.abort()
      }
    }
  }, [])

  if (state.ready) {
    return <>{children}</>
  }

  const handleRetry = () => {
    window.location.reload()
  }

  return (
    <BackendLoadingScreen
      statusMessage={state.statusMessage}
      errorMessage={state.errorMessage}
      onRetry={state.canRetry ? handleRetry : undefined}
    />
  )
}
