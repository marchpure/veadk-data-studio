import { Navigate } from 'react-router-dom'
import { useScopes } from '../hooks/useScopes'

interface ViewerRedirectProps {
  children: React.ReactNode
}

export function ViewerRedirect({ children }: ViewerRedirectProps) {
  const { isViewer } = useScopes()

  if (isViewer) {
    return <Navigate to="/" replace />
  }

  return <>{children}</>
}
