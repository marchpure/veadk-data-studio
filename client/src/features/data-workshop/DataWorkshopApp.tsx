import { Navigate, Route, Routes, useLocation, useParams } from 'react-router-dom'
import { WorkshopShell } from './components/WorkshopShell'
import { ConnectionAccess } from './pages/Access'
import { ConnectionDetail, ConnectionOverview, ProviderMarket } from './pages/Connections'
import { ConsoleEmbed, NewConnectionEmbed } from './pages/ConsoleEmbed'
import { ConnectionDocs } from './pages/Docs'
import { WorkshopHome } from './pages/Home'
import { SkillMount } from './pages/SkillMount'
import OpenVikingPage from '../../pages/OpenVikingPage'
import './data-workshop.css'

function OwnedElsewhere({ title, owner }: { title: string; owner: string }) {
  return <div className="dw-page"><div className="dw-page-heading"><span className="dw-eyebrow">Data Workshop</span><h1>{title}</h1><p>此工作区由 {owner} 模块提供，保留在统一 Shell 中。</p></div></div>
}

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

export function DataWorkshopApp() {
  return <WorkshopShell><Routes>
    <Route path="/" element={<Navigate to="/home" replace />} />
    <Route path="/home" element={<WorkshopHome />} />
    <Route path="/connections/overview" element={<ConnectionOverview />} />
    <Route path="/connections/providers" element={<Navigate to="/connections/providers/market" replace />} />
    <Route path="/connections/providers/market" element={<ProviderMarket />} />
    <Route path="/connections/providers/new/:providerId" element={<NewConnectionEmbed />} />
    <Route path="/connections/providers/:id" element={<ConnectionDetail />} />
    <Route path="/connections/providers/:id/access" element={<ConnectionAccess />} />
    <Route path="/connections/actions" element={<ConsoleEmbed title="Actions" consolePath="actions" />} />
    <Route path="/connections/trace" element={<ConsoleEmbed title="Trace" consolePath="traces" />} />
    <Route path="/connections/access/identity" element={<ConsoleEmbed title="Identity 配置" consolePath="access" />} />
    <Route path="/connections/access" element={<ConnectionAccess />} />
    <Route path="/connections/docs" element={<ConnectionDocs />} />
    <Route path="/kb/connect" element={<OpenVikingPage connectOnly />} />
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
