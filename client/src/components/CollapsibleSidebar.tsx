import { useState, useEffect, useRef } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Database, SquarePen, PanelLeftClose, PanelLeft, Sparkles, Download, Home, Search, Boxes, LayoutDashboard, ClipboardCheck } from 'lucide-react'
import NotebookHistory from './NotebookHistory'
import CreateNotebook from './CreateNotebook'
import ImportNotebookModal from './ImportNotebookModal'
import { ProfileDropdown } from './ProfileDropdown'
import byaanLogo from '../assets/byaan-logo-orange.png'
import { useStore } from '../stores/useStore'
import { useScopes } from '../hooks/useScopes'
import { useCommandPalette } from '../contexts/CommandPaletteContext'
import { useAppConfig } from '../hooks/useAppConfig'

export default function CollapsibleSidebar() {
  const location = useLocation()
  const isMainPage = !location.pathname.includes('/notebook/')
  const openSidebar = useStore(state => state.openSidebar)
  const isSidebarOpen = useStore(state => state.isSidebarOpen)
  const { isViewer, canImportNotebook } = useScopes()
  const { openPalette } = useCommandPalette()
  const [importModalOpen, setImportModalOpen] = useState(false)
  const [isMobile, setIsMobile] = useState(() => window.matchMedia('(max-width: 767px)').matches)

  const { isSelfHosted } = useAppConfig()

  // Track if user has manually toggled sidebar (to respect their preference)
  const hasUserToggled = useRef(false)

  // Only manage expand/collapse state on main pages
  const [isExpanded, setIsExpanded] = useState(() => {
    if (window.matchMedia('(max-width: 767px)').matches) {
      return false
    }
    const stored = localStorage.getItem('sidebar-expanded')
    if (stored !== null) {
      hasUserToggled.current = true
      return stored === 'true'
    }
    return true // Default, will be overridden for viewers
  })

  // Collapse sidebar by default for viewers (only if user hasn't set a preference)
  useEffect(() => {
    if (isViewer && !hasUserToggled.current) {
      setIsExpanded(false)
    }
  }, [isViewer])

  useEffect(() => {
    const media = window.matchMedia('(max-width: 767px)')
    const handleViewportChange = (event: MediaQueryListEvent) => {
      setIsMobile(event.matches)
      if (event.matches) {
        setIsExpanded(false)
        return
      }
      const stored = localStorage.getItem('sidebar-expanded')
      setIsExpanded(stored === null ? !isViewer : stored === 'true')
    }
    media.addEventListener('change', handleViewportChange)
    return () => media.removeEventListener('change', handleViewportChange)
  }, [isViewer])

  useEffect(() => {
    if (isMobile) {
      setIsExpanded(false)
    }
  }, [isMobile, location.pathname])

  // Save to localStorage only when user manually toggles
  const handleSetExpanded = (value: boolean) => {
    hasUserToggled.current = true
    setIsExpanded(value)
    if (isMainPage && !isMobile) {
      localStorage.setItem('sidebar-expanded', String(value))
    }
  }

  const isActive = (path: string) => {
    if (path === '/') {
      return location.pathname === '/'
    }
    if (path === '/databases') {
      return location.pathname === '/databases' || location.pathname === '/sources'
    }
    if (path === '/data-models') {
      return location.pathname === '/data-models' || location.pathname.startsWith('/data-models/')
    }
    if (path === '/dashboard-assets') {
      return location.pathname === '/dashboard-assets' || location.pathname.startsWith('/dashboard-assets/')
    }
    if (path === '/evaluation') {
      return location.pathname === '/evaluation' || location.pathname.startsWith('/evaluation/')
    }
    if (path === '/llm-connections') {
      return location.pathname === '/llm-connections'
    }
    if (path === '/github') {
      return location.pathname === '/github'
    }
    return location.pathname === path
  }

  const handleToggleSidebar = () => {
    handleSetExpanded(!isExpanded)
  }

  // Only render sidebar on main pages (not on notebook pages)
  if (!isMainPage) {
    return null
  }

  return (
    <>
      {isMobile && isExpanded && (
        <button
          type="button"
          className="fixed inset-0 z-40 bg-black/60"
          aria-label="Close navigation"
          onClick={() => handleSetExpanded(false)}
        />
      )}
      <div
      className={`h-full shrink-0 bg-[#1a1a1a] border-r border-[#2a2a2a] flex flex-col overflow-hidden transition-all duration-300 ${
        isExpanded
          ? isMobile ? 'fixed inset-y-0 left-0 z-50 w-72 shadow-2xl' : 'w-72'
          : 'w-12 cursor-pointer hover:bg-[#222222]'
      }`}
      onClick={!isExpanded ? handleToggleSidebar : undefined}
      title={!isExpanded ? "Click to expand sidebar" : undefined}
    >
        <div className={`flex items-center justify-between bg-[#1a1a1a] h-[52px] transition-all duration-300 ${isExpanded ? 'px-4' : 'px-1'}`}>
        {isExpanded ? (
          <>
            <Link to="/" className="flex items-center gap-3 hover:opacity-80 transition-opacity">
              <img src={byaanLogo} alt="Byaan" className="h-7 w-7" />
              <h1 className="text-xl font-mono font-bold text-white">Byaan</h1>
            </Link>
            <button
              onClick={handleToggleSidebar}
              className="text-gray-300 hover:text-white transition-colors p-2 rounded-lg hover:bg-[#2a2a2a]"
              title="Close Sidebar"
            >
              <PanelLeftClose className="h-5 w-5" />
            </button>
          </>
        ) : (
          <div className="text-gray-300 hover:text-white p-2 rounded-lg hover:bg-[#2a2a2a] transition-colors">
            <PanelLeft className="h-5 w-5" />
          </div>
        )}
      </div>

      <nav className={`flex-1 overflow-hidden min-h-0 transition-all duration-300 ${isExpanded ? 'px-4 pt-2 pb-4' : 'px-2 py-4'}`}>
        <div className={`flex flex-col h-full min-h-0 ${isExpanded ? 'space-y-1' : 'space-y-1'}`}>
          {isViewer ? (
            <Link to="/" onClick={(e) => !isExpanded && e.stopPropagation()}>
              <div
                className={`flex items-center rounded-lg transition-all duration-300 cursor-pointer ${
                  isExpanded ? 'gap-3 px-3 py-1.5' : 'p-2 justify-center'
                } ${
                  isActive('/')
                    ? 'bg-brand-orange/10 text-brand-orange border-l-3 border-brand-orange'
                    : 'text-gray-300 hover:text-white hover:bg-[#2a2a2a]'
                }`}
                title={!isExpanded ? "Dashboards" : undefined}
              >
                <Home className="h-4 w-4 flex-shrink-0" />
                {isExpanded && <span className="text-sm whitespace-nowrap transition-opacity duration-300">Dashboards</span>}
              </div>
            </Link>
          ) : (
            <>
              <div onClick={(e) => !isExpanded && e.stopPropagation()}>
                <CreateNotebook
                  trigger={
                    <div
                      className={`flex items-center rounded-lg cursor-pointer group transition-all duration-300 ${
                        isExpanded
                          ? 'gap-3 px-3 py-1.5'
                          : 'p-2 justify-center'
                      }`}
                      title={!isExpanded ? "New Notebook" : undefined}
                    >
                      <SquarePen className="h-4 w-4 flex-shrink-0 text-white" />
                      {isExpanded && <span className="text-sm font-medium text-white whitespace-nowrap transition-opacity duration-300">New Notebook</span>}
                    </div>
                  }
                />
              </div>

              <button onClick={(e) => { if (!isExpanded) e.stopPropagation(); openPalette(); }}>
                <div
                  className={`flex items-center rounded-lg transition-all duration-300 cursor-pointer ${
                    isExpanded ? 'gap-3 px-3 py-1.5' : 'p-2 justify-center'
                  } text-[#c5c5c5] hover:text-white hover:bg-[#2a2a2a]`}
                  title={!isExpanded ? "Search (⌘K)" : undefined}
                >
                  <Search className="h-4 w-4 flex-shrink-0" />
                  {isExpanded && (
                    <>
                      <span className="text-sm whitespace-nowrap transition-opacity duration-300 flex-1 text-left">Search</span>
                      <kbd className="text-[10px] text-[#808080] bg-[#2a2a2a] px-1.5 py-0.5 rounded font-mono">⌘K</kbd>
                    </>
                  )}
                </div>
              </button>

              <Link to="/" onClick={(e) => !isExpanded && e.stopPropagation()}>
                <div
                  className={`flex items-center rounded-lg transition-all duration-300 cursor-pointer ${
                    isExpanded ? 'gap-3 px-3 py-1.5' : 'p-2 justify-center'
                  } ${
                    isActive('/')
                      ? 'bg-brand-orange/10 text-brand-orange border-l-3 border-brand-orange'
                      : 'text-gray-300 hover:text-white hover:bg-[#2a2a2a]'
                  }`}
                  title={!isExpanded ? "Home" : undefined}
                >
                  <Home className="h-4 w-4 flex-shrink-0" />
                  {isExpanded && <span className="text-sm whitespace-nowrap transition-opacity duration-300">Home</span>}
                </div>
              </Link>

              {!isSelfHosted && canImportNotebook && (
                <button onClick={(e) => { if (!isExpanded) e.stopPropagation(); setImportModalOpen(true); }}>
                  <div
                    className={`flex items-center rounded-lg transition-all duration-300 cursor-pointer ${
                      isExpanded ? 'gap-3 px-3 py-1.5' : 'p-2 justify-center'
                    } text-[#c5c5c5] hover:text-white hover:bg-[#2a2a2a]`}
                    title={!isExpanded ? "Import Notebook" : undefined}
                  >
                    <Download className="h-4 w-4 flex-shrink-0" />
                    {isExpanded && <span className="text-sm whitespace-nowrap transition-opacity duration-300">Import Notebook</span>}
                  </div>
                </button>
              )}

              <Link to="/sources" onClick={(e) => !isExpanded && e.stopPropagation()}>
                <div
                  className={`flex items-center rounded-lg transition-all duration-300 cursor-pointer ${
                    isExpanded ? 'gap-3 px-3 py-1.5' : 'p-2 justify-center'
                  } ${
                    isActive('/databases')
                      ? 'bg-brand-orange/10 text-brand-orange border-l-3 border-brand-orange'
                      : 'text-gray-300 hover:text-white hover:bg-[#2a2a2a]'
                  }`}
                  title={!isExpanded ? "Sources" : undefined}
                >
                  <Database className="h-4 w-4 flex-shrink-0" />
                  {isExpanded && <span className="text-sm whitespace-nowrap transition-opacity duration-300">Sources</span>}
                </div>
              </Link>

              <Link to="/data-models" onClick={(e) => !isExpanded && e.stopPropagation()}>
                <div
                  className={`flex items-center rounded-lg transition-all duration-300 cursor-pointer ${
                    isExpanded ? 'gap-3 px-3 py-1.5' : 'p-2 justify-center'
                  } ${
                    isActive('/data-models')
                      ? 'bg-brand-orange/10 text-brand-orange border-l-3 border-brand-orange'
                      : 'text-gray-300 hover:text-white hover:bg-[#2a2a2a]'
                  }`}
                  title={!isExpanded ? "Data Models" : undefined}
                >
                  <Boxes className="h-4 w-4 flex-shrink-0" />
                  {isExpanded && <span className="text-sm whitespace-nowrap transition-opacity duration-300">Data Models</span>}
                </div>
              </Link>

              <Link to="/dashboard-assets" onClick={(e) => !isExpanded && e.stopPropagation()}>
                <div
                  className={`flex items-center rounded-lg transition-all duration-300 cursor-pointer ${
                    isExpanded ? 'gap-3 px-3 py-1.5' : 'p-2 justify-center'
                  } ${
                    isActive('/dashboard-assets')
                      ? 'bg-brand-orange/10 text-brand-orange border-l-3 border-brand-orange'
                      : 'text-gray-300 hover:text-white hover:bg-[#2a2a2a]'
                  }`}
                  title={!isExpanded ? "Dashboards" : undefined}
                >
                  <LayoutDashboard className="h-4 w-4 flex-shrink-0" />
                  {isExpanded && <span className="text-sm whitespace-nowrap transition-opacity duration-300">Dashboards</span>}
                </div>
              </Link>

              <Link to="/evaluation" onClick={(e) => !isExpanded && e.stopPropagation()}>
                <div
                  className={`flex items-center rounded-lg transition-all duration-300 cursor-pointer ${
                    isExpanded ? 'gap-3 px-3 py-1.5' : 'p-2 justify-center'
                  } ${
                    isActive('/evaluation')
                      ? 'bg-brand-orange/10 text-brand-orange border-l-3 border-brand-orange'
                      : 'text-gray-300 hover:text-white hover:bg-[#2a2a2a]'
                  }`}
                  title={!isExpanded ? "Evaluation" : undefined}
                >
                  <ClipboardCheck className="h-4 w-4 flex-shrink-0" />
                  {isExpanded && <span className="text-sm whitespace-nowrap transition-opacity duration-300">Evaluation</span>}
                </div>
              </Link>

              <button onClick={(e) => { if (!isExpanded) e.stopPropagation(); openSidebar(); }}>
                <div
                  className={`flex items-center rounded-lg transition-all duration-300 cursor-pointer ${
                    isExpanded ? 'gap-3 px-3 py-1.5' : 'p-2 justify-center'
                  } ${
                    isSidebarOpen
                      ? 'bg-brand-orange/10 text-brand-orange border-l-3 border-brand-orange'
                      : 'text-gray-300 hover:text-white hover:bg-[#2a2a2a]'
                  }`}
                  title={!isExpanded ? "Context" : undefined}
                >
                  <Sparkles className="h-4 w-4 flex-shrink-0" />
                  {isExpanded && <span className="text-sm whitespace-nowrap transition-opacity duration-300">Context</span>}
                </div>
              </button>

              {isExpanded && (
                <div className="flex flex-col flex-1 min-h-0 pt-3 border-t border-[#2a2a2a] transition-all duration-300">
                  <div className="flex items-center gap-3 px-3 py-1 text-gray-400 mb-1">
                    <span className="text-xs font-medium transition-opacity duration-300">Recents</span>
                  </div>
                  <div className="flex-1 overflow-y-auto custom-scrollbar">
                    <NotebookHistory onNotebookClick={() => {}} />
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </nav>

      {/* User Profile Section */}
      <div
        className={`border-t border-[#2a2a2a] ${isExpanded ? 'p-3' : 'px-2 py-3'}`}
        onClick={(e) => e.stopPropagation()}
      >
        <ProfileDropdown
          isExpanded={isExpanded}
          onExpandSidebar={() => setIsExpanded(true)}
        />
      </div>

      {/* Import Notebook Modal */}
      {!isSelfHosted && canImportNotebook && (
        <ImportNotebookModal
          open={importModalOpen}
          onOpenChange={setImportModalOpen}
        />
      )}

      </div>
    </>
  )
}
