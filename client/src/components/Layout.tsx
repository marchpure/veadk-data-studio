import { useEffect, type ReactNode } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import CollapsibleSidebar from './CollapsibleSidebar'
import { ContextSidebar } from './context/ContextSidebar'
import { useStore } from '../stores/useStore'
import { useScopes } from '../hooks/useScopes'

interface LayoutProps {
  children: ReactNode
}

const isFullEditorRoute = (pathname: string): boolean => {
  const notebookMatch = pathname.match(/^\/notebook\/([^/]+)(\/preview)?$/)
  return notebookMatch !== null
}

export default function Layout({ children }: LayoutProps) {
  const location = useLocation()
  const navigate = useNavigate()
  const importShareId = useStore((s) => s.importShareId)
  const setImportShareId = useStore((s) => s.setImportShareId)
  const { canImportNotebook } = useScopes()

  // Navigate to home page when importShareId is set and we're not already there
  // This ensures the import modal can be displayed (it's only rendered on NotebooksPage)
  // Only do this if notebook import is enabled
  useEffect(() => {
    if (importShareId && location.pathname !== '/') {
      if (canImportNotebook) {
        navigate('/')
      } else {
        // Clear the import share ID if import is disabled
        setImportShareId(null)
      }
    }
  }, [importShareId, location.pathname, navigate, canImportNotebook, setImportShareId])

  const isPreviewPage = location.pathname.includes('/preview')
  const isFullPageRoute = isFullEditorRoute(location.pathname)

  return (
    <div className={`flex h-screen bg-[#1a1a1a] overflow-hidden ${isFullPageRoute ? 'relative' : ''}`}>
      <CollapsibleSidebar />

      <div className={`flex-1 min-h-0 ${isPreviewPage ? 'overflow-hidden' : 'overflow-y-auto custom-scrollbar'}`}>
        {children}
      </div>

      <ContextSidebar />
    </div>
  )
}
