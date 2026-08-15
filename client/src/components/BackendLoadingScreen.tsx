import { useMemo } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'

interface BackendLoadingScreenProps {
  statusMessage: string
  errorMessage?: string | null
  onRetry?: () => void
}

const statusMessages = [
  'Starting backend services…',
  'Preparing database…',
  'Warming up AI models…',
  'Almost ready…'
]

export default function BackendLoadingScreen({ statusMessage, errorMessage, onRetry }: BackendLoadingScreenProps) {
  const helperMessage = useMemo(() => {
    if (errorMessage) {
      return null // We'll show the error message directly
    }
    return statusMessages[Math.floor(Math.random() * statusMessages.length)]
  }, [errorMessage])

  // Show error state
  if (errorMessage) {
    return (
      <div className="flex h-screen w-full flex-col items-center justify-center bg-[#0f172a] text-white px-8">
        <div className="max-w-md space-y-6 text-center">
          <div className="flex justify-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-red-500/20">
              <AlertTriangle className="h-8 w-8 text-red-400" />
            </div>
          </div>

          <div className="space-y-2">
            <h1 className="text-2xl font-semibold text-white">{statusMessage}</h1>
            <p className="text-sm text-gray-300 leading-relaxed">{errorMessage}</p>
          </div>

          {onRetry && (
            <button
              onClick={onRetry}
              className="inline-flex items-center gap-2 px-6 py-3 bg-brand-orange hover:bg-brand-orange-hover text-white font-medium rounded-lg transition-all shadow-lg hover:shadow-xl hover:glow-orange-sm"
            >
              <RefreshCw className="h-4 w-4" />
              Try Again
            </button>
          )}

          <div className="pt-4 border-t border-gray-700">
            <p className="text-xs text-gray-400">
              If the problem persists, please check the backend logs for more details.
            </p>
          </div>
        </div>
      </div>
    )
  }

  // Show loading state
  return (
    <div className="flex h-screen w-full flex-col items-center justify-center bg-[#0f172a] text-white">
      <div className="mb-8 flex h-14 w-14 items-center justify-center rounded-full border-4 border-brand-orange border-t-transparent animate-spin" />
      <div className="space-y-3 text-center px-8">
        <h1 className="text-xl font-semibold">Booting Byaan</h1>
        <p className="text-sm text-gray-300">{statusMessage}</p>
        {helperMessage && <p className="text-sm text-gray-400">{helperMessage}</p>}
        <p className="text-xs text-gray-400 pt-4">This may take a minute on first launch…</p>
      </div>
    </div>
  )
}
