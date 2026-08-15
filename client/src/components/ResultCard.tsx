import React, { useMemo, useState } from 'react'
import { Eye, Code, RefreshCw, Download, Maximize2, Check, Copy, Terminal, ArrowLeft } from 'lucide-react'

type TabKey = 'preview' | 'code' | 'query'

interface DashboardVersion {
  version_num: number
  created_at: string
}

interface ResultCardProps {
  // Layout variant: default card or docked (fills panel)
  variant?: 'card' | 'docked'
  activeTab: TabKey
  onTabChange: (tab: TabKey) => void

  // Preview
  processedHtmlContent: string

  // Code
  generatedCode: string

  // Actions
  isRefreshing?: boolean
  onRefresh?: () => void

  availableVersions?: DashboardVersion[]
  selectedVersion?: number | null
  latestVersionNum?: number
  onVersionChange?: (version: number | null) => void

  isExportingPdf?: boolean
  onExportPdf?: () => void
  isExportingHtml?: boolean
  onExportHtml?: () => void

  onOpenFullscreen?: () => void

  isTauri?: boolean
  onToggleDevTools?: () => void

  // Query
  onOpenQueryPanel?: () => void

  // Navigation back to version chooser
  onBackToVersions?: () => void

  // Code editing/loading state
  isCodeLoading?: boolean
  codeLoadingMessage?: string
}

export default function ResultCard({
  variant = 'card',
  activeTab,
  onTabChange,
  processedHtmlContent,
  generatedCode,
  isRefreshing,
  onRefresh,
  availableVersions = [],
  selectedVersion = null,
  latestVersionNum = 1,
  onVersionChange,
  isExportingPdf,
  onExportPdf,
  isExportingHtml,
  onExportHtml,
  onOpenFullscreen,
  isTauri,
  onToggleDevTools,
  onOpenQueryPanel,
  onBackToVersions,
  isCodeLoading = false,
  codeLoadingMessage,
}: ResultCardProps) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(generatedCode || '')
      setCopied(true)
      setTimeout(() => setCopied(false), 1200)
    } catch {
      // ignore copy errors
    }
  }

  const hasPreview = useMemo(() => !!processedHtmlContent, [processedHtmlContent])
  const hasCode = useMemo(() => !!generatedCode, [generatedCode])

  const docked = variant === 'docked'

  return (
    <div className="mt-3 h-full flex flex-col">
      <div className="bg-[#2a2a2a] border border-[#404040] rounded-lg overflow-hidden">
        {/* Header */}
        <div className="bg-[#1a1a1a] px-4 py-3 border-b border-[#404040] flex items-center justify-between">
          <div className="flex items-center gap-2">
            {onBackToVersions && (
              <button
                onClick={onBackToVersions}
                className="px-2 py-1 text-xs bg-transparent hover:bg-[#2a2a2a] text-white border border-[#404040] rounded-md transition-colors flex items-center gap-1"
                title="Back to versions"
              >
                <ArrowLeft className="w-3 h-3" /> Versions
              </button>
            )}
            <div className="text-sm font-medium text-white">Dashboard</div>
          </div>
          <div className="flex items-center gap-2">
            {availableVersions.length > 0 && onVersionChange && (
              <select
                value={selectedVersion ?? 'latest'}
                onChange={(e) => {
                  const val = e.target.value
                  onVersionChange(val === 'latest' ? null : parseInt(val))
                }}
                className="px-3 py-1.5 text-xs bg-transparent text-white rounded-lg border border-[#404040] hover:bg-[#2a2a2a] focus:outline-none focus:border-[#555555] transition-colors cursor-pointer w-auto"
                title="Select dashboard version"
              >
                <option value="latest" className="bg-[#2a2a2a]">Latest (v{latestVersionNum})</option>
                {availableVersions.map(v => (
                  <option key={v.version_num} value={v.version_num} className="bg-[#2a2a2a]">
                    v{v.version_num} - {new Date(v.created_at).toLocaleString()}
                  </option>
                ))}
              </select>
            )}
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
                <Download className="inline-block w-3 h-3 mr-1" />
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

        {/* Tabs */}
        <div className="px-3 pt-3 flex gap-2">
          <button
            onClick={() => onTabChange('preview')}
            className={`px-4 py-2 text-xs font-medium rounded-md transition-colors ${
              activeTab === 'preview' ? 'text-white bg-[#2a2a2a] border border-[#404040]' : 'text-gray-400 hover:text-white hover:bg-[#2a2a2a] border border-transparent'
            }`}
          >
            <Eye className="inline-block w-3.5 h-3.5 mr-1" />
            Preview
          </button>
          <button
            onClick={() => onTabChange('code')}
            className={`px-4 py-2 text-xs font-medium rounded-md transition-colors ${
              activeTab === 'code' ? 'text-white bg-[#2a2a2a] border border-[#404040]' : 'text-gray-400 hover:text-white hover:bg-[#2a2a2a] border border-transparent'
            }`}
          >
            <Code className="inline-block w-3.5 h-3.5 mr-1" />
            Code
          </button>
          {/* Query tab removed */}
        </div>

        {/* Body */}
        <div className="p-3" style={docked ? { height: 'calc(100vh - 220px)' } : undefined}>
          {activeTab === 'preview' && (
            <div className={`rounded-lg border border-[#404040] bg-[#1a1a1a] overflow-hidden ${docked ? 'h-full flex flex-col' : ''}`}>
              {hasPreview ? (
                <iframe
                  srcDoc={processedHtmlContent}
                  className={`w-full ${docked ? 'flex-1' : 'h-[480px]'} border-0`}
                  style={docked ? { minHeight: 0 } : undefined}
                  title="HTML Preview Inline"
                  sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals"
                />
              ) : (
                <div className="flex items-center justify-center h-[200px] text-gray-500">
                  <div className="text-center">
                    <Eye className="w-8 h-8 mx-auto mb-2 opacity-60" />
                    <p className="text-sm">No HTML to preview yet</p>
                  </div>
                </div>
              )}
            </div>
          )}

          {activeTab === 'code' && (
            <div className={`relative rounded-lg border border-[#404040] bg-[#1a1a1a] ${docked ? 'h-full flex flex-col' : ''}`}>
              <button
                onClick={handleCopy}
                className="absolute top-3 right-3 z-10 p-2 bg-[#333333] hover:bg-[#404040] text-white rounded-lg transition-colors"
                title="Copy code"
              >
                {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
              </button>
              <pre className={`p-4 ${docked ? 'flex-1 min-h-0 overflow-y-auto' : 'max-h-[520px] overflow-y-auto'} custom-scrollbar text-sm text-gray-200 whitespace-pre-wrap`}>
                {hasCode ? generatedCode : 'No HTML code available'}
              </pre>
              {isCodeLoading && (
                <div className="absolute inset-0 bg-black/40 flex items-center justify-center">
                  <div className="flex items-center gap-3 px-4 py-2 rounded-lg bg-[#2a2a2a] border border-[#404040]">
                    <div className="w-4 h-4 border-2 border-gray-600 border-t-white rounded-full animate-spin" />
                    <span className="text-xs text-[#e5e5e5]">{codeLoadingMessage || 'Applying changes to HTML...'}</span>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Query tab content removed */}
        </div>

        {/* Footer */}
        <div className="px-3 pb-3">
          <div className="flex items-center justify-center">
            <button
              onClick={onOpenFullscreen}
              className="px-3 py-1.5 text-xs bg-transparent hover:bg-[#2a2a2a] text-white border border-[#404040] rounded-lg transition-colors flex items-center gap-2"
              title="Open fullscreen"
            >
              <Maximize2 className="w-3.5 h-3.5" />
              Fullscreen
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
