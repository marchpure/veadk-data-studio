import { Navigate, Route, Routes } from 'react-router-dom'
import { WorkshopShell } from './components/WorkshopShell'
import { ConnectionAccess } from './pages/Access'
import { ConnectionDetail, ConnectionOverview, ProviderMarket } from './pages/Connections'
import { ConsoleEmbed, NewConnectionEmbed } from './pages/ConsoleEmbed'
import { ConnectionDocs } from './pages/Docs'
import { WorkshopHome } from './pages/Home'
import './data-workshop.css'

function OwnedElsewhere({ title, owner }: { title: string; owner: string }) {
  return <div className="dw-page"><div className="dw-page-heading"><span className="dw-eyebrow">Data Workshop</span><h1>{title}</h1><p>此工作区由 {owner} 模块提供，保留在统一 Shell 中。</p></div></div>
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
    <Route path="/kb/*" element={<OwnedElsewhere title="知识库" owner="OpenViking" />} />
    <Route path="/skill/*" element={<OwnedElsewhere title="Skill" owner="Skill Creator" />} />
    <Route path="/sessions/*" element={<OwnedElsewhere title="最近会话" owner="Skill Creator" />} />
    <Route path="/mcp/*" element={<Navigate to="/connections/docs" replace />} />
    <Route path="/mcp" element={<Navigate to="/connections/docs" replace />} />
    <Route path="*" element={<Navigate to="/home" replace />} />
  </Routes></WorkshopShell>
}
