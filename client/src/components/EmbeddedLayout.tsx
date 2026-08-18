import { NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { BarChart3, ClipboardCheck, Database, FolderOpen, Network } from 'lucide-react'
import DatabasesPage from '../pages/Databases'
import SourceDetailPage from '../pages/SourceDetailPage'
import DataModelsHomePage from '../features/data-modeling/pages/DataModelsHomePage'
import DataModelBuilderPage from '../features/data-modeling/pages/DataModelBuilderPage'
import DashboardWorkspacePage from '../features/dashboard/pages/DashboardWorkspacePage'
import EvaluationWorkspacePage from '../features/evaluation/pages/EvaluationWorkspacePage'
import FoldersPage from '../pages/FoldersPage'
import FolderDetailPage from '../pages/FolderDetailPage'
import { EMBEDDED_KNOWLEDGE_CENTER_BASE } from '../contexts/EmbeddedModeContext'
import type { ReactNode } from 'react'

const tabs = [
  { label: 'Sources', to: `${EMBEDDED_KNOWLEDGE_CENTER_BASE}/sources`, icon: Database },
  { label: 'Data Models', to: `${EMBEDDED_KNOWLEDGE_CENTER_BASE}/data-models`, icon: Network },
  { label: 'Dashboards', to: `${EMBEDDED_KNOWLEDGE_CENTER_BASE}/dashboard-assets`, icon: BarChart3 },
  { label: 'Evaluation', to: `${EMBEDDED_KNOWLEDGE_CENTER_BASE}/evaluation`, icon: ClipboardCheck },
  { label: 'Folders', to: `${EMBEDDED_KNOWLEDGE_CENTER_BASE}/folders`, icon: FolderOpen },
]

export default function EmbeddedLayout() {
  const location = useLocation()
  const activeTab =
    tabs.find((tab) => location.pathname === tab.to || location.pathname.startsWith(`${tab.to}/`)) ??
    tabs[1]

  return (
    <div className="flex h-screen min-w-0 flex-col overflow-hidden bg-[#1a1a1a] text-white" data-embedded-layout="knowledge-center">
      <header className="shrink-0 border-b border-[#30363a] bg-[#141719]">
        <div className="flex min-h-[52px] min-w-0 items-center gap-3 px-3 sm:px-4">
          <div className="hidden min-w-0 sm:block">
            <div className="truncate text-sm font-semibold text-[#f3f5f5]">Knowledge Center</div>
            <div className="truncate text-xs text-[#9aa4ac]">Byaan governed assets</div>
          </div>
          <nav className="min-w-0 flex-1 overflow-x-auto custom-scrollbar" aria-label="Knowledge Center sections">
            <div className="flex w-max min-w-full items-center gap-1 py-2">
              {tabs.map((tab) => {
                const Icon = tab.icon
                return (
                  <NavLink
                    key={tab.to}
                    to={tab.to}
                    className={({ isActive }) =>
                      `inline-flex h-9 shrink-0 items-center gap-2 rounded-md px-3 text-sm transition-colors ${
                        isActive || activeTab.to === tab.to
                          ? 'bg-brand-orange/15 text-brand-orange'
                          : 'text-[#c7cfd6] hover:bg-[#22272b] hover:text-white'
                      }`
                    }
                  >
                    <Icon className="h-4 w-4" />
                    <span>{tab.label}</span>
                  </NavLink>
                )
              })}
            </div>
          </nav>
        </div>
      </header>
      <main className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden custom-scrollbar">
        <Routes>
          <Route index element={<Navigate to="data-models" replace />} />
          <Route path="sources" element={<EmbeddedPage><DatabasesPage /></EmbeddedPage>} />
          <Route path="sources/:sourceId" element={<EmbeddedPage><SourceDetailPage /></EmbeddedPage>} />
          <Route path="data-models" element={<EmbeddedPage><DataModelsHomePage /></EmbeddedPage>} />
          <Route path="data-models/:modelId" element={<EmbeddedPage><DataModelBuilderPage /></EmbeddedPage>} />
          <Route path="dashboard-assets" element={<EmbeddedPage><DashboardWorkspacePage embedded /></EmbeddedPage>} />
          <Route path="dashboard-assets/:assetId" element={<EmbeddedPage><DashboardWorkspacePage embedded /></EmbeddedPage>} />
          <Route path="evaluation" element={<EmbeddedPage><EvaluationWorkspacePage /></EmbeddedPage>} />
          <Route path="evaluation/:suiteId" element={<EmbeddedPage><EvaluationWorkspacePage /></EmbeddedPage>} />
          <Route path="folders" element={<EmbeddedPage><FoldersPage /></EmbeddedPage>} />
          <Route path="folders/:id" element={<EmbeddedPage><FolderDetailPage /></EmbeddedPage>} />
          <Route path="*" element={<Navigate to="data-models" replace />} />
        </Routes>
      </main>
    </div>
  )
}

function EmbeddedPage({ children }: { children: ReactNode }) {
  return (
    <div className="min-w-0" data-embedded-page="knowledge-center">
      {children}
    </div>
  )
}
