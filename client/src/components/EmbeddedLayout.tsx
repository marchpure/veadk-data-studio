import { NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { BarChart3, ClipboardCheck, Database, FolderOpen, MessageSquareText, Network } from 'lucide-react'
import ChatPreview from '../pages/ChatPreview'
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
  { label: 'Ask Data', to: `${EMBEDDED_KNOWLEDGE_CENTER_BASE}/ask`, icon: MessageSquareText },
  { label: 'Dashboards', to: `${EMBEDDED_KNOWLEDGE_CENTER_BASE}/dashboard-assets`, icon: BarChart3 },
  { label: 'Evaluation', to: `${EMBEDDED_KNOWLEDGE_CENTER_BASE}/evaluation`, icon: ClipboardCheck },
  { label: 'Folders', to: `${EMBEDDED_KNOWLEDGE_CENTER_BASE}/folders`, icon: FolderOpen },
]

export default function EmbeddedLayout() {
  const location = useLocation()
  const activeTab =
    tabs.find((tab) => location.pathname === tab.to || location.pathname.startsWith(`${tab.to}/`)) ??
    tabs[0]

  return (
    <div className="flex h-screen min-w-0 flex-col overflow-hidden bg-[#f7f7f8] text-[#18181b]" data-embedded-layout="knowledge-center">
      <header className="shrink-0 border-b border-[#e4e4e7] bg-[#f7f7f8]">
        <div className="flex min-h-[46px] min-w-0 items-center gap-3 px-3 sm:px-4">
          <div className="hidden min-w-0 sm:block">
            <div className="truncate text-[13px] font-medium text-[#18181b]">Data Studio</div>
            <div className="truncate text-[11px] text-[#71717a]">Knowledge Center</div>
          </div>
          <nav className="min-w-0 flex-1 overflow-x-auto custom-scrollbar" aria-label="Knowledge Center sections">
            <div className="flex w-max min-w-full items-center gap-0.5 py-1.5">
              {tabs.map((tab) => {
                const Icon = tab.icon
                return (
                  <NavLink
                    key={tab.to}
                    to={tab.to}
                    className={({ isActive }) =>
                      `inline-flex h-8 shrink-0 items-center gap-2 rounded-md px-2.5 text-[13px] transition-colors ${
                        isActive || activeTab.to === tab.to
                          ? 'bg-white text-[#18181b] shadow-[0_1px_2px_rgba(24,24,27,0.06),inset_0_0_0_1px_rgba(24,24,27,0.06)]'
                          : 'text-[#71717a] hover:bg-[#ededee] hover:text-[#18181b]'
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
          <Route index element={<Navigate to={tabs[0].to} replace />} />
          <Route path="sources" element={<EmbeddedPage><DatabasesPage /></EmbeddedPage>} />
          <Route path="sources/:sourceId" element={<EmbeddedPage><SourceDetailPage /></EmbeddedPage>} />
          <Route path="data-models" element={<EmbeddedPage><DataModelsHomePage /></EmbeddedPage>} />
          <Route path="data-models/:modelId" element={<EmbeddedPage><DataModelBuilderPage /></EmbeddedPage>} />
          <Route path="ask" element={<EmbeddedPage page="ask-data"><ChatPreview embedded /></EmbeddedPage>} />
          <Route path="ask/:id" element={<EmbeddedPage page="ask-data"><ChatPreview embedded /></EmbeddedPage>} />
          <Route path="ask/:id/preview" element={<EmbeddedPage page="ask-data"><ChatPreview embedded /></EmbeddedPage>} />
          <Route path="dashboard-assets" element={<EmbeddedPage><DashboardWorkspacePage embedded /></EmbeddedPage>} />
          <Route path="dashboard-assets/:assetId" element={<EmbeddedPage><DashboardWorkspacePage embedded /></EmbeddedPage>} />
          <Route path="evaluation" element={<EmbeddedPage><EvaluationWorkspacePage /></EmbeddedPage>} />
          <Route path="evaluation/:suiteId" element={<EmbeddedPage><EvaluationWorkspacePage /></EmbeddedPage>} />
          <Route path="folders" element={<EmbeddedPage><FoldersPage /></EmbeddedPage>} />
          <Route path="folders/:id" element={<EmbeddedPage><FolderDetailPage /></EmbeddedPage>} />
          <Route path="*" element={<Navigate to={tabs[0].to} replace />} />
        </Routes>
      </main>
    </div>
  )
}

function EmbeddedPage({ children, page = 'knowledge-center' }: { children: ReactNode; page?: 'knowledge-center' | 'ask-data' }) {
  return (
    <div className="min-w-0" data-embedded-page={page}>
      {children}
    </div>
  )
}
