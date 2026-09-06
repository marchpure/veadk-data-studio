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

function ProviderDetailSurface() {
  const { id = '' } = useParams()
  return <OpenConnectorSurface surface="providers" resourcePath={`/${encodeURIComponent(id)}`} title="提供商" />
}

export function DataWorkshopApp() {
  return <WorkshopShell><Routes>
    <Route path="/" element={<Navigate to="/home" replace />} />
    <Route path="/home" element={<WorkshopHome />} />
    <Route path="/connections/overview" element={<OpenConnectorSurface surface="overview" title="总览" />} />
    <Route path="/connections/providers" element={<OpenConnectorSurface surface="providers" title="提供商" />} />
    <Route path="/connections/marketplace" element={<OpenConnectorSurface surface="marketplace" title="市场" />} />
    <Route path="/connections/actions" element={<OpenConnectorSurface surface="actions" title="操作" />} />
    <Route path="/connections/runs" element={<OpenConnectorSurface surface="runs" title="运行记录" />} />
    <Route path="/connections/access" element={<OpenConnectorSurface surface="access" title="访问权限" />} />
    <Route path="/connections/trace" element={<Navigate to="/connections/runs" replace />} />
    <Route path="/connections/providers/market" element={<Navigate to="/connections/providers" replace />} />
    <Route path="/connections/providers/new/:providerId" element={<Navigate to="/connections/providers" replace />} />
    <Route path="/connections/providers/:id/access" element={<Navigate to="/connections/access" replace />} />
    <Route path="/connections/providers/:id" element={<ProviderDetailSurface />} />
    <Route path="/connections/access/identity" element={<Navigate to="/connections/access" replace />} />
    <Route path="/connections/docs" element={<ConnectionDocs />} />
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
