import { ExternalLink, RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { workshopApi } from '../api'
import { AsyncState } from '../components/AsyncState'
import type { LoadState } from '../types'
import './openconnector-surface.css'

const openConnectorSurfaces = [
  'overview',
  'providers',
  'marketplace',
  'actions',
  'runs',
  'access',
] as const

export type OpenConnectorSurfaceKey = (typeof openConnectorSurfaces)[number]

interface OpenConnectorRouteChangedMessage {
  type: 'openconnector.route.changed'
  version: 1
  surface: OpenConnectorSurfaceKey
  resourcePath: string
  search: string
}

const parentRouteBySurface: Record<OpenConnectorSurfaceKey, string> = {
  overview: '/connections/overview',
  providers: '/connections/providers',
  marketplace: '/connections/marketplace',
  actions: '/connections/actions',
  runs: '/connections/runs',
  access: '/connections/access',
}

const sensitiveQueryKeys = new Set([
  'access_token',
  'admin_token',
  'api_key',
  'authorization',
  'client_secret',
  'password',
  'refresh_token',
  'secret',
  'token',
])
const embedOnlyQueryKeys = new Set(['embed'])

export function OpenConnectorSurface({
  surface,
  title = surface,
  resourcePath = '',
}: {
  surface: OpenConnectorSurfaceKey
  title?: string
  resourcePath?: string
}) {
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const navigate = useNavigate()
  const location = useLocation()
  const [state, setState] = useState<LoadState>('loading')
  const [launchUrl, setLaunchUrl] = useState('')
  const [frameReady, setFrameReady] = useState(false)
  const safeSearch = sanitizeSearch(location.search)
  const desiredRoute = useRef({ surface, resourcePath, search: safeSearch })
  desiredRoute.current = { surface, resourcePath, search: safeSearch }

  const load = useCallback(async () => {
    setState('loading')
    setFrameReady(false)
    try {
      const requested = desiredRoute.current
      const session = await createSurfaceLaunchSession(
        requested.surface,
        requested.search,
        requested.resourcePath,
      )
      setLaunchUrl(validateSurfaceLaunchUrl(
        session.launch_url,
        requested.surface,
        requested.search,
        requested.resourcePath,
      ))
      setState('ready')
    } catch {
      setState('error')
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load, resourcePath, surface])

  useEffect(() => {
    const onMessage = (event: MessageEvent<unknown>) => {
      if (
        event.origin !== window.location.origin
        || event.source !== iframeRef.current?.contentWindow
        || !isRouteChangedMessage(event.data)
      ) {
        return
      }
      const nextLocation = `${parentRouteBySurface[event.data.surface]}${event.data.resourcePath}${event.data.search}`
      if (`${location.pathname}${location.search}` !== nextLocation) {
        void navigate(nextLocation)
      }
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [location.pathname, location.search, navigate])

  useEffect(() => {
    const frameWindow = iframeRef.current?.contentWindow
    if (!frameWindow || state !== 'ready' || !frameReady) return
    frameWindow.postMessage({
      type: 'openconnector.route.navigate',
      version: 1,
      surface,
      resourcePath,
      search: safeSearch,
    }, window.location.origin)
  }, [frameReady, resourcePath, safeSearch, state, surface])

  if (state !== 'ready') {
    return (
      <div className="dw-page dw-openconnector-surface">
        <AsyncState
          state={state === 'empty' ? 'error' : state}
          message="无法建立 OpenConnector Console 会话，请检查服务配置。"
          onRetry={load}
        />
      </div>
    )
  }

  return (
    <section className="dw-openconnector-surface" aria-label={`OpenConnector ${title}`}>
      <div className="dw-openconnector-toolbar">
        <span>通过短期安全会话加载 OpenConnector</span>
        <div>
          <a className="dw-icon-text" href={standaloneUrl(launchUrl)} target="_blank" rel="noreferrer">
            <ExternalLink size={15} />
            新窗口打开
          </a>
          <button className="dw-icon-text" onClick={() => void load()}>
            <RefreshCw size={15} />
            刷新会话
          </button>
        </div>
      </div>
      <div className="dw-openconnector-frame">
        <iframe
          ref={iframeRef}
          title={`OpenConnector ${title}`}
          src={launchUrl}
          onLoad={() => setFrameReady(true)}
          onError={() => setState('error')}
        />
      </div>
    </section>
  )
}

async function createSurfaceLaunchSession(
  surface: OpenConnectorSurfaceKey,
  search: string,
  resourcePath: string,
): Promise<{ launch_url: string; expires_at: number }> {
  return workshopApi.createLaunchSession(surface, search, resourcePath)
}

function validateSurfaceLaunchUrl(
  launchUrl: string,
  surface: OpenConnectorSurfaceKey,
  search: string,
  resourcePath: string,
): string {
  const url = new URL(launchUrl, window.location.origin)
  const routeSearch = new URLSearchParams(url.search)
  routeSearch.delete('embed')
  const routeSearchValue = routeSearch.toString()
  if (
    url.origin !== window.location.origin
    || url.pathname !== `/oc/${surface}${resourcePath}`
    || url.searchParams.get('embed') !== 'studio'
    || sanitizeSearch(routeSearchValue) !== search
    || (routeSearchValue ? `?${routeSearchValue}` : '') !== search
  ) {
    throw new Error('OpenConnector launch URL did not match the requested same-origin surface')
  }
  return `${url.pathname}${url.search}`
}

function standaloneUrl(launchUrl: string): string {
  const url = new URL(launchUrl, window.location.origin)
  url.searchParams.delete('embed')
  return `${url.pathname}${url.search}`
}

function isRouteChangedMessage(value: unknown): value is OpenConnectorRouteChangedMessage {
  if (!value || typeof value !== 'object') return false
  const message = value as Partial<OpenConnectorRouteChangedMessage>
  return message.type === 'openconnector.route.changed'
    && message.version === 1
    && isSurface(message.surface)
    && typeof message.resourcePath === 'string'
    && isSafeResourcePath(message.surface, message.resourcePath)
    && typeof message.search === 'string'
    && sanitizeSearch(message.search) === message.search
}

function isSurface(value: unknown): value is OpenConnectorSurfaceKey {
  return typeof value === 'string'
    && openConnectorSurfaces.some(surface => surface === value)
}

function isSafeResourcePath(surface: OpenConnectorSurfaceKey, resourcePath: string): boolean {
  if (!resourcePath) return true
  return (surface === 'providers' || surface === 'actions')
    && /^\/[A-Za-z0-9][A-Za-z0-9_.~-]{0,255}$/.test(resourcePath)
}

function sanitizeSearch(search: string): string {
  const sanitized = new URLSearchParams(search)
  for (const key of [...sanitized.keys()]) {
    const normalizedKey = key.toLowerCase().replaceAll('-', '_')
    if (sensitiveQueryKeys.has(normalizedKey) || embedOnlyQueryKeys.has(normalizedKey)) {
      sanitized.delete(key)
    }
  }
  const value = sanitized.toString()
  return value ? `?${value}` : ''
}
