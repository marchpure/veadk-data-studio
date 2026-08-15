import { useEffect, useState } from 'react'
import { useStore } from '../stores/useStore'
import { CheckCircle2, FileText, FileCode2, Table, X, FolderOpen } from 'lucide-react'
import { isTauriApp, openFileInFinder } from '../lib/tauri-api'

const FILE_TYPE_CONFIG = {
  pdf: {
    icon: FileText,
    label: 'PDF',
    color: 'text-red-400',
  },
  html: {
    icon: FileCode2,
    label: 'HTML',
    color: 'text-blue-400',
  },
  csv: {
    icon: Table,
    label: 'CSV',
    color: 'text-green-400',
  },
}

const AUTO_DISMISS_DELAY = 8000 // 8 seconds

function DownloadItem({ download }: { download: { id: string; fileName: string; fileType: 'pdf' | 'html' | 'csv'; filePath?: string; status: 'success' | 'error'; timestamp: number } }) {
  const [isVisible, setIsVisible] = useState(false)
  const [isPaused, setIsPaused] = useState(false)
  const removeDownload = useStore((state) => state.removeDownload)
  const config = FILE_TYPE_CONFIG[download.fileType]
  const Icon = config.icon
  const isInTauri = isTauriApp()

  useEffect(() => {
    // Trigger slide-in animation
    setIsVisible(true)

    // Auto-dismiss timer
    const timer = setTimeout(() => {
      if (!isPaused) {
        handleDismiss()
      }
    }, AUTO_DISMISS_DELAY)

    return () => clearTimeout(timer)
  }, [isPaused])

  const handleDismiss = () => {
    setIsVisible(false)
    // Wait for animation to complete before removing from store
    setTimeout(() => {
      removeDownload(download.id)
    }, 300)
  }

  const handleOpenInFinder = async () => {
    if (download.filePath) {
      try {
        await openFileInFinder(download.filePath)
      } catch (error) {
        console.error('Failed to open file in finder:', error)
      }
    }
  }

  return (
    <div
      className={`
        transform transition-all duration-300 ease-out
        ${isVisible ? 'translate-x-0 opacity-100' : 'translate-x-full opacity-0'}
      `}
      onMouseEnter={() => setIsPaused(true)}
      onMouseLeave={() => setIsPaused(false)}
    >
      <div className="bg-[#1a1a1a] border border-gray-800 rounded-lg shadow-lg backdrop-blur-md p-4 min-w-[320px] max-w-[400px]">
        <div className="flex items-start gap-3">
          {/* Success Icon */}
          <div className="flex-shrink-0 mt-0.5">
            <CheckCircle2 className="w-5 h-5 text-green-500" />
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <Icon className={`w-4 h-4 ${config.color}`} />
              <span className="text-xs text-gray-400 font-medium">{config.label} document</span>
            </div>
            <p className="text-sm text-white truncate" title={download.fileName}>
              {download.fileName}
            </p>

            {/* Actions */}
            {isInTauri && download.filePath && (
              <button
                onClick={handleOpenInFinder}
                className="mt-2 flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300 transition-colors"
              >
                <FolderOpen className="w-3.5 h-3.5" />
                <span>Open in Finder</span>
              </button>
            )}
          </div>

          {/* Close Button */}
          <button
            onClick={handleDismiss}
            className="flex-shrink-0 text-gray-400 hover:text-white transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  )
}

export function DownloadNotification() {
  const downloads = useStore((state) => state.downloads)

  if (downloads.length === 0) {
    return null
  }

  return (
    <div className="fixed bottom-4 right-4 z-[10000] flex flex-col gap-3 pointer-events-none">
      <div className="pointer-events-auto flex flex-col gap-3 max-h-[calc(100vh-2rem)] overflow-y-auto">
        {downloads.map((download) => (
          <DownloadItem key={download.id} download={download} />
        ))}
      </div>
    </div>
  )
}
