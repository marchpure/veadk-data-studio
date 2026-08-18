import { createContext, useCallback, useContext, type ReactNode } from 'react'

export const EMBEDDED_KNOWLEDGE_CENTER_BASE = '/embedded/knowledge-center'

const EmbeddedModeContext = createContext(false)

export function EmbeddedModeProvider({ enabled, children }: { enabled: boolean; children: ReactNode }) {
  return (
    <EmbeddedModeContext.Provider value={enabled}>
      {children}
    </EmbeddedModeContext.Provider>
  )
}

export function useEmbeddedMode() {
  return useContext(EmbeddedModeContext)
}

export function isEmbeddedKnowledgeCenterPath(pathname: string) {
  return pathname === EMBEDDED_KNOWLEDGE_CENTER_BASE || pathname.startsWith(`${EMBEDDED_KNOWLEDGE_CENTER_BASE}/`)
}

type LocationLike = {
  pathname: string
  search?: string
  state?: unknown
}

function getStateFromPathname(state: unknown) {
  if (!state || typeof state !== 'object') return null
  const from = (state as { from?: unknown }).from
  if (!from || typeof from !== 'object') return null
  const pathname = (from as { pathname?: unknown }).pathname
  return typeof pathname === 'string' ? pathname : null
}

export function hasEmbeddedKnowledgeCenterQuery(search?: string) {
  return new URLSearchParams(search ?? '').get('embedded') === 'veadk-studio'
}

export function isEmbeddedKnowledgeCenterLocation(location: LocationLike) {
  return isEmbeddedKnowledgeCenterPath(location.pathname)
    || isEmbeddedKnowledgeCenterPath(getStateFromPathname(location.state) ?? '')
    || hasEmbeddedKnowledgeCenterQuery(location.search)
}

export function isKnowledgeCenterChildPath(pathname: string) {
  return [
    '/sources',
    '/databases',
    '/data-models',
    '/dashboard-assets',
    '/evaluation',
    '/folders',
  ].some((path) => pathname === path || pathname.startsWith(`${path}/`))
}

export function knowledgeCenterPath(path: string) {
  const normalized = path.startsWith('/') ? path : `/${path}`
  if (normalized === '/databases' || normalized.startsWith('/databases/')) {
    return `${EMBEDDED_KNOWLEDGE_CENTER_BASE}${normalized.replace('/databases', '/sources')}`
  }
  return `${EMBEDDED_KNOWLEDGE_CENTER_BASE}${normalized}`
}

export function isRunningInEmbeddedFrame() {
  try {
    return window.self !== window.top
  } catch {
    return true
  }
}

export function useKnowledgeCenterPath() {
  const embedded = useEmbeddedMode()
  return useCallback(
    (path: string) => (embedded ? knowledgeCenterPath(path) : path),
    [embedded],
  )
}
