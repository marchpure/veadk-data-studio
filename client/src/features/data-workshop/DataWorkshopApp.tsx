import { Navigate, Route, Routes, useLocation, useParams } from 'react-router-dom'
import { WorkshopShell } from './components/WorkshopShell'
import { ConnectionDocs } from './pages/Docs'
import { WorkshopHome } from './pages/Home'
import { OpenConnectorSurface } from './pages/OpenConnectorSurface'
import { SkillMount } from './pages/SkillMount'
import OpenVikingPage from '../../pages/OpenVikingPage'
import './data-workshop.css'

function SkillRedirect({ source }: { source: 'new' | 'skill' | 'session' }) {
  const location = useLocation()
  const { skillId, sessionId, '*': sessionPath } = useParams()
  const search = new URLSearchParams(location.search)

  if (source === 'new') search.set('mode', 'new')
  if (source === 'skill' && skillId) search.set('skillId', skillId)
  if (source === 'session') {
    const legacySessionId = sessionId || sessionPath?.split('/').filter(Boolean)[0]
    if (legacySessionId) search.set('sessionId', legacySessionId)
  }

  return <Navigate to={{ pathname: '/skill', search: search.toString() }} replace />
}

function ConnectionSurfaceRoute() {
  const location = useLocation()
  const path = location.pathname
  if (path === '/connections/trace') return <Navigate to="/connections/runs" replace />
  if (path === '/connections/providers/market' || path.startsWith('/connections/providers/new/')) {
    return <Navigate to="/connections/providers" replace />
  }
  if (path === '/connections/access/identity' || /^\/connections\/providers\/[^/]+\/access$/.test(path)) {
    return <Navigate to="/connections/access" replace />
  }
  if (path === '/connections/overview') return <OpenConnectorSurface surface="overview" title="总览" />
  if (path === '/connections/providers') return <OpenConnectorSurface surface="providers" title="提供商" />
  if (path === '/connections/marketplace') return <OpenConnectorSurface surface="marketplace" title="市场" />
  if (path === '/connections/actions') return <OpenConnectorSurface surface="actions" title="操作" />
  if (path === '/connections/runs') return <OpenConnectorSurface surface="runs" title="运行记录" />
  if (path === '/connections/access') return <OpenConnectorSurface surface="access" title="访问权限" />
  const provider = path.match(/^\/connections\/providers\/([^/]+)$/)?.[1]
  if (provider) {
    return <OpenConnectorSurface
      surface="providers"
      resourcePath={`/${encodeURIComponent(decodeURIComponent(provider))}`}
      title="提供商"
    />
  }
  return <Navigate to="/connections/overview" replace />
}

export function DataWorkshopApp() {
  return <WorkshopShell><Routes>
    <Route path="/" element={<Navigate to="/home" replace />} />
    <Route path="/home" element={<WorkshopHome />} />
    <Route path="/connections/docs" element={<ConnectionDocs />} />
    <Route path="/connections/*" element={<ConnectionSurfaceRoute />} />
    <Route path="/kb/connect" element={<Navigate to="/kb/new" replace />} />
    <Route path="/kb/*" element={<OpenVikingPage />} />
    <Route path="/skill" element={<SkillMount />} />
    <Route path="/skill/new" element={<SkillRedirect source="new" />} />
    <Route path="/skill/:skillId" element={<SkillRedirect source="skill" />} />
    <Route path="/skill/*" element={<Navigate to="/skill" replace />} />
    <Route path="/sessions" element={<SkillRedirect source="session" />} />
    <Route path="/sessions/:sessionId" element={<SkillRedirect source="session" />} />
    <Route path="/sessions/*" element={<SkillRedirect source="session" />} />
    <Route path="/mcp/*" element={<Navigate to="/connections/docs" replace />} />
    <Route path="/mcp" element={<Navigate to="/connections/docs" replace />} />
    <Route path="*" element={<Navigate to="/home" replace />} />
  </Routes></WorkshopShell>
}
