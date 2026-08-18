import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { useLocation } from 'react-router-dom'

import { isEmbeddedKnowledgeCenterPath } from '../contexts/EmbeddedModeContext'

export default function QueryDevtoolsGate() {
  const location = useLocation()

  // The floating launcher obscures the Ask Data composer in embedded mode.
  if (isEmbeddedKnowledgeCenterPath(location.pathname)) return null
  return <ReactQueryDevtools initialIsOpen={false} />
}
