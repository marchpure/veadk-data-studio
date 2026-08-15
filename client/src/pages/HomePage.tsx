import { useState, useEffect, useRef, useCallback, useLayoutEffect } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { AlertTriangle, Database, FolderPlus, Folder, Github, Plug } from 'lucide-react'
import WelcomeSection from '../components/home/WelcomeSection'
import SharedDashboardsSection from '../components/home/SharedDashboardsSection'
import SharedNotebooksSection from '../components/home/SharedNotebooksSection'
import MyNotebooksSection from '../components/home/MyNotebooksSection'
import { SetupPromptCard } from '../components/home/SetupPromptCard'
import { CreateFolderModal } from '../components/folders/CreateFolderModal'
import { MCPKeysModal } from '../components/MCPKeysModal'
import { cn } from '../lib/utils'
import { useLLMConnections } from '../hooks/useLLMConnections'
import { useDatasources } from '../hooks/useDBConnections'
import { useGitHubStatus } from '../hooks/useGitHubStatus'
import { useMCPKeys } from '../hooks/useMCPKeys'
import { useScopes } from '../hooks/useScopes'
import { useAppConfig } from '../hooks/useAppConfig'

type TabType = 'dashboards' | 'notebooks' | 'my-notebooks'

const VALID_TABS: TabType[] = ['dashboards', 'notebooks', 'my-notebooks']

function getInitialTab(isViewer: boolean, isSelfHosted: boolean): TabType {
  if (!isSelfHosted) return 'my-notebooks'
  if (isViewer) return 'dashboards'
  const saved = localStorage.getItem('home_active_tab')
  if (saved && VALID_TABS.includes(saved as TabType)) {
    return saved as TabType
  }
  return 'dashboards'
}

export default function HomePage() {
  const navigate = useNavigate()
  const { dashboardId } = useParams<{ dashboardId?: string }>()
  const { canCreateFolder, canCreateLLMConnection, canCreateDatasource, isViewer } = useScopes()
  const { isSelfHosted } = useAppConfig()

  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<TabType>(() => getInitialTab(isViewer, isSelfHosted))
  const [showCreateFolderModal, setShowCreateFolderModal] = useState(false)
  const [mcpModalOpen, setMcpModalOpen] = useState(false)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const scrollSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const handleScroll = useCallback(() => {
    if (scrollSaveTimerRef.current) clearTimeout(scrollSaveTimerRef.current)
    scrollSaveTimerRef.current = setTimeout(() => {
      if (scrollContainerRef.current) {
        sessionStorage.setItem(`home_scroll_${activeTab}`, String(scrollContainerRef.current.scrollTop))
      }
    }, 100)
  }, [activeTab])

  useLayoutEffect(() => {
    const saved = sessionStorage.getItem(`home_scroll_${activeTab}`)
    if (saved && scrollContainerRef.current) {
      scrollContainerRef.current.scrollTop = Number(saved)
    }
  }, [activeTab])
  const [mcpDismissed, setMcpDismissed] = useState(() => localStorage.getItem('byaan_mcp_setup_dismissed') === 'true')

  useEffect(() => {
    if (dashboardId && isSelfHosted) {
      setActiveTab('dashboards')
    }
  }, [dashboardId, isSelfHosted])

  useEffect(() => {
    if (!isViewer) {
      localStorage.setItem('home_active_tab', activeTab)
    }
  }, [activeTab, isViewer])

  const { data: llmConnections, isLoading: isLoadingLLM } = useLLMConnections()
  const { data: datasources, isLoading: isLoadingDatasources } = useDatasources()
  const { data: githubStatus, isLoading: isLoadingGitHub } = useGitHubStatus()
  const { data: mcpKeys, isLoading: isLoadingMCP } = useMCPKeys()

  const hasNoLLMConnections = !isLoadingLLM && (!llmConnections || llmConnections.length === 0)
  const hasNoDatasources = !isLoadingDatasources && (!datasources || datasources.total === 0)
  const hasNoGitHub = !isLoadingGitHub && (!githubStatus || !githubStatus.connected)
  const showMCPBanner = isSelfHosted
    ? !isLoadingMCP && (!mcpKeys || mcpKeys.filter(k => k.is_active).length === 0)
    : !mcpDismissed

  return (
    <div className="bg-[#0d0d0d] w-full h-full flex flex-col">
      {/* Header Section */}
      <div className="w-full px-8 pt-[50px] pb-8">
        <div className="max-w-[850px] mx-auto">
          <WelcomeSection />

          {/* Setup Prompt Cards - Hidden for viewers */}
          {!isViewer && ((hasNoLLMConnections && canCreateLLMConnection) || (hasNoDatasources && canCreateDatasource) || hasNoGitHub || showMCPBanner) ? (
            <div className="mt-6 space-y-3">
              {hasNoLLMConnections && canCreateLLMConnection && (
                <SetupPromptCard
                  icon={<AlertTriangle className="w-5 h-5" />}
                  title="No AI model connected"
                  description="Connect an AI model to start analyzing your data"
                  actionLabel="Connect AI Model"
                  href="/llm-connections"
                />
              )}
              {hasNoDatasources && canCreateDatasource && (
                <SetupPromptCard
                  icon={<Database className="w-5 h-5" />}
                  title="No datasources configured"
                  description="Add a database or upload files to get started"
                  actionLabel="Add Datasource"
                  href="/databases"
                />
              )}
              {hasNoGitHub && (
                <SetupPromptCard
                  icon={<Github className="w-5 h-5" />}
                  title="GitHub not connected"
                  description="Connect GitHub to analyze and chat with your repositories"
                  actionLabel="Connect GitHub"
                  href="/github"
                />
              )}
              {showMCPBanner && (
                <SetupPromptCard
                  icon={<Plug className="w-5 h-5" />}
                  title="MCP not configured"
                  description="Connect Claude Code, Cursor, or other AI tools to query your data"
                  actionLabel="Setup MCP"
                  onClick={() => setMcpModalOpen(true)}
                  onDismiss={!isSelfHosted ? () => {
                    localStorage.setItem('byaan_mcp_setup_dismissed', 'true')
                    setMcpDismissed(true)
                  } : undefined}
                />
              )}
            </div>
          ) : null}

          {/* Error Message */}
          {error && (
            <div className="bg-red-900/20 border border-red-500 text-red-400 px-4 py-3 rounded-md mt-6">
              {error}
              <button
                onClick={() => setError(null)}
                className="ml-4 text-red-300 hover:text-red-100"
              >
                Dismiss
              </button>
            </div>
          )}

          {/* Tab Toggle with Folder Management Icons */}
          <div className="flex items-center justify-between mt-6">
            <div className="flex gap-2">
              {isSelfHosted && (
                <button
                  onClick={() => setActiveTab('dashboards')}
                  className={cn(
                    "px-4 py-2 rounded-lg text-sm font-medium transition-colors",
                    activeTab === 'dashboards'
                      ? "bg-brand-orange text-white"
                      : "text-gray-400 hover:text-white hover:bg-gray-800"
                  )}
                >
                  Dashboards
                </button>
              )}
              {isSelfHosted && !isViewer && (
                <button
                  onClick={() => setActiveTab('notebooks')}
                  className={cn(
                    "px-4 py-2 rounded-lg text-sm font-medium transition-colors",
                    activeTab === 'notebooks'
                      ? "bg-brand-orange text-white"
                      : "text-gray-400 hover:text-white hover:bg-gray-800"
                  )}
                >
                  Notebooks
                </button>
              )}
              {!isViewer && (
                <button
                  onClick={() => setActiveTab('my-notebooks')}
                  className={cn(
                    "px-4 py-2 rounded-lg text-sm font-medium transition-colors",
                    activeTab === 'my-notebooks'
                      ? "bg-brand-orange text-white"
                      : "text-gray-400 hover:text-white hover:bg-gray-800"
                  )}
                >
                  My Notebooks
                </button>
              )}
            </div>

            {isSelfHosted && canCreateFolder && (
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setShowCreateFolderModal(true)}
                  className="p-1.5 text-gray-500 hover:text-white transition-colors rounded"
                  title="Create folder"
                >
                  <FolderPlus className="w-4 h-4" />
                </button>
                <Link
                  to="/folders"
                  className="flex items-center gap-1.5 px-2.5 py-1.5 text-gray-400 hover:text-white transition-colors rounded text-sm"
                  title="Manage folders"
                >
                  <Folder className="w-4 h-4" />
                  <span>Folders</span>
                </Link>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Scrollable Content Section */}
      <div ref={scrollContainerRef} onScroll={handleScroll} className="flex-1 overflow-y-auto custom-scrollbar min-h-0">
        <div className="w-full px-8 pb-6">
          <div className="max-w-[850px] mx-auto">
            {activeTab === 'dashboards' ? (
              <SharedDashboardsSection onError={setError} deepLinkDashboardId={dashboardId} />
            ) : activeTab === 'notebooks' ? (
              <SharedNotebooksSection onError={setError} />
            ) : (
              <MyNotebooksSection onError={setError} />
            )}
          </div>
        </div>
      </div>

      {/* Create Folder Modal */}
      <CreateFolderModal
        open={showCreateFolderModal}
        onOpenChange={setShowCreateFolderModal}
        onSuccess={() => navigate('/folders')}
      />

      {/* MCP Setup Modal */}
      <MCPKeysModal
        open={mcpModalOpen}
        onClose={() => {
          setMcpModalOpen(false)
          setMcpDismissed(localStorage.getItem('byaan_mcp_setup_dismissed') === 'true')
        }}
      />
    </div>
  )
}
