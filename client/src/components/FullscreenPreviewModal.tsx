import React from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog'
import { RefreshCw, Download, Terminal, Loader2, Share2 } from 'lucide-react'
interface FullscreenPreviewModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title?: string
  processedHtmlContent: string
  iframeKey?: number
  isRefreshing?: boolean
  onRefresh?: () => void
  isExportingPdf?: boolean
  onExportPdf?: () => void
  isExportingHtml?: boolean
  onExportHtml?: () => void
  onShare?: () => void
  isTauri?: boolean
  onToggleDevTools?: () => void
}

export default function FullscreenPreviewModal({
  open,
  onOpenChange,
  title = 'Dashboard Preview',
  processedHtmlContent,
  iframeKey = 0,
  isRefreshing,
  onRefresh,
  isExportingPdf,
  onExportPdf,
  isExportingHtml,
  onExportHtml,
  onShare,
  isTauri,
  onToggleDevTools,
}: FullscreenPreviewModalProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-none w-[95vw] h-[90vh] p-0 bg-[#1a1a1a] border-[#404040] overflow-hidden">
        <div className="flex flex-col h-full">
          <div className="flex items-center justify-between px-4 h-12 border-b border-[#404040] bg-[#1a1a1a]">
            <DialogHeader>
              <DialogTitle className="text-white text-sm">{title}</DialogTitle>
            </DialogHeader>
            <div className="flex items-center gap-2 pr-8">
              {onRefresh && (
                <button
                  onClick={onRefresh}
                  disabled={isRefreshing}
                  className="px-3 py-1.5 text-xs bg-transparent hover:bg-[#2a2a2a] text-white border border-[#404040] rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  title="Refresh"
                >
                  <RefreshCw className={`inline-block w-3 h-3 mr-1 ${isRefreshing ? 'animate-spin' : ''}`} />
                  {isRefreshing ? 'Refreshing...' : 'Refresh'}
                </button>
              )}
              {onExportPdf && (
                <button
                  onClick={onExportPdf}
                  disabled={isExportingPdf}
                  className="px-3 py-1.5 text-xs bg-transparent hover:bg-[#2a2a2a] text-white border border-[#404040] rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  title="Export PDF"
                >
                  {isExportingPdf ? (
                    <Loader2 className="inline-block w-3 h-3 mr-1 animate-spin" />
                  ) : (
                    <Download className="inline-block w-3 h-3 mr-1" />
                  )}
                  {isExportingPdf ? 'Exporting...' : 'PDF'}
                </button>
              )}
              {onExportHtml && (
                <button
                  onClick={onExportHtml}
                  disabled={isExportingHtml}
                  className="px-3 py-1.5 text-xs bg-transparent hover:bg-[#2a2a2a] text-white border border-[#404040] rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  title="Export HTML"
                >
                  <Download className="inline-block w-3 h-3 mr-1" />
                  {isExportingHtml ? 'Exporting...' : 'HTML'}
                </button>
              )}
              {onShare && (
                <button
                  onClick={onShare}
                  className="px-3 py-1.5 text-xs bg-transparent hover:bg-[#2a2a2a] text-white border border-[#404040] rounded-lg transition-colors"
                  title="Share"
                >
                  <Share2 className="inline-block w-3 h-3 mr-1" />
                  Share
                </button>
              )}
              {isTauri && onToggleDevTools && (
                <button
                  onClick={onToggleDevTools}
                  className="px-3 py-1.5 text-xs bg-transparent hover:bg-[#2a2a2a] text-white border border-[#404040] rounded-lg transition-colors"
                  title="Toggle DevTools"
                >
                  <Terminal className="inline-block w-3 h-3 mr-1" />
                  DevTools
                </button>
              )}
            </div>
          </div>

          <div className="flex-1 bg-[#1a1a1a] overflow-hidden">
            {processedHtmlContent ? (
              <iframe
                key={iframeKey}
                srcDoc={processedHtmlContent}
                className="w-full h-full border-0"
                title="HTML Preview Fullscreen"
                sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals"
              />
            ) : (
              <div className="flex items-center justify-center h-full text-gray-500">
                <div className="text-center">
                  <p className="text-lg font-medium mb-2 text-[#e5e5e5]">No HTML to preview</p>
                  <p className="text-sm">Load an HTML file to see the preview</p>
                </div>
              </div>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

