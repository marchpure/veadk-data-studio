import React, { useState, useMemo } from 'react'
import { Eye, Code, RefreshCw, Download, Maximize2, Check, Copy, ChevronDown, Database } from 'lucide-react'
import { showToast } from '../utils/toast'

type TabKey = 'preview' | 'code'

interface DashboardVersion {
  version_num: number
  created_at: string
}

interface InlineDashboardCardProps {
  // Preview
  processedHtmlContent: string
  iframeKey?: number

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
  onOpenQueryPanel?: () => void

  isTauri?: boolean
  onToggleDevTools?: () => void

  // Code editing/loading state
  isCodeLoading?: boolean
  codeLoadingMessage?: string

  // Errors
  iframeErrors?: any[]
}

export function InlineDashboardCard({
  processedHtmlContent,
  iframeKey = 0,
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
  onOpenQueryPanel,
  isTauri,
  onToggleDevTools,
  isCodeLoading = false,
  codeLoadingMessage,
  iframeErrors = []
}: InlineDashboardCardProps) {
  const [activeTab, setActiveTab] = useState<TabKey>('preview')
  const [copied, setCopied] = useState(false)
  const [showVersionDropdown, setShowVersionDropdown] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(generatedCode || '')
      setCopied(true)
      showToast.success('Code copied to clipboard')
      setTimeout(() => setCopied(false), 2000)
    } catch {
      showToast.error('Failed to copy code')
    }
  }

  const hasPreview = useMemo(() => !!processedHtmlContent, [processedHtmlContent])
  const hasCode = useMemo(() => !!generatedCode, [generatedCode])
  
  // Format version info
  const versionInfo = selectedVersion 
    ? `v${selectedVersion}` 
    : `v${latestVersionNum} (Latest)`

  const selectedVersionData = availableVersions.find(v => v.version_num === (selectedVersion || latestVersionNum))
  const versionTime = selectedVersionData ? new Date(selectedVersionData.created_at).toLocaleString() : ''

  return (
    <div className="mt-4 mb-4 mx-auto max-w-[50.4rem]">
      <div className="bg-[#2a2a2a] border border-[#404040] rounded-xl overflow-hidden shadow-lg dashboard-card-shadow">
        {/* Header */}
        <div className="bg-gradient-to-r from-[#232323] to-[#2a2a2a] px-4 py-3 border-b border-[#404040]">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></div>
                Dashboard
              </h3>
              
              {/* Version Info */}
              {availableVersions.length > 0 && (
                <div className="relative">
                  <button
                    onClick={() => setShowVersionDropdown(!showVersionDropdown)}
                    className="flex items-center gap-1.5 px-2.5 py-1 text-xs bg-[#1a1a1a] hover:bg-[#2a2a2a] text-gray-300 border border-[#404040] rounded-md transition-colors"
                  >
                    <span>{versionInfo}</span>
                    <ChevronDown className="w-3 h-3" />
                  </button>
                  
                  {showVersionDropdown && (
                    <div className="absolute top-full mt-1 left-0 w-48 bg-[#1a1a1a] border border-[#404040] rounded-lg shadow-xl z-10 version-dropdown">
                      <button
                        onClick={() => {
                          onVersionChange?.(null)
                          setShowVersionDropdown(false)
                        }}
                        className={`w-full text-left px-3 py-2 text-xs hover:bg-[#2a2a2a] transition-colors ${selectedVersion === null ? 'bg-[#2a2a2a] text-white' : 'text-gray-300'}`}
                      >
                        Latest (v{latestVersionNum})
                      </button>
                      {availableVersions.map(v => (
                        <button
                          key={v.version_num}
                          onClick={() => {
                            onVersionChange?.(v.version_num)
                            setShowVersionDropdown(false)
                          }}
                          className={`w-full text-left px-3 py-2 text-xs hover:bg-[#2a2a2a] transition-colors ${selectedVersion === v.version_num ? 'bg-[#2a2a2a] text-white' : 'text-gray-300'}`}
                        >
                          v{v.version_num} - {new Date(v.created_at).toLocaleString()}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
              
              {versionTime && (
                <span className="text-[11px] text-gray-500">
                  {versionTime}
                </span>
              )}
            </div>
            
            {/* Action Buttons */}
            <div className="flex items-center gap-1">
              <button
                onClick={onRefresh}
                disabled={isRefreshing}
                className="p-1.5 hover:bg-[#333333] rounded-md transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed text-gray-400 hover:text-white dashboard-button"
                title="Refresh dashboard"
              >
                <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
              </button>
              
              <button
                onClick={onOpenQueryPanel}
                className="p-1.5 hover:bg-[#333333] rounded-md transition-all duration-200 text-gray-400 hover:text-white dashboard-button"
                title="View queries"
              >
                <Database className="w-4 h-4" />
              </button>
              
              <div className="w-px h-4 bg-[#404040] mx-1" />
              
              <button
                onClick={onExportPdf}
                disabled={isExportingPdf}
                className="p-1.5 hover:bg-[#333333] rounded-md transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed text-gray-400 hover:text-white dashboard-button"
                title="Export as PDF"
              >
                <Download className="w-4 h-4" />
              </button>
              
              <button
                onClick={onExportHtml}
                disabled={isExportingHtml}
                className="p-1.5 hover:bg-[#333333] rounded-md transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed text-gray-400 hover:text-white dashboard-button"
                title="Export as HTML"
              >
                <Code className="w-4 h-4" />
              </button>
              
              <button
                onClick={onOpenFullscreen}
                className="p-1.5 hover:bg-[#333333] rounded-md transition-all duration-200 text-gray-400 hover:text-white dashboard-button"
                title="Open fullscreen"
              >
                <Maximize2 className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 px-3 pt-3">
          <button
            onClick={() => setActiveTab('preview')}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
              activeTab === 'preview'
                ? 'text-white bg-[#333333]'
                : 'text-gray-400 hover:text-white hover:bg-[#2a2a2a]'
            }`}
          >
            <Eye className="inline-block w-3.5 h-3.5 mr-1" />
            Preview
          </button>
          <button
            onClick={() => setActiveTab('code')}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
              activeTab === 'code'
                ? 'text-white bg-[#333333]'
                : 'text-gray-400 hover:text-white hover:bg-[#2a2a2a]'
            }`}
          >
            <Code className="inline-block w-3.5 h-3.5 mr-1" />
            HTML Code
          </button>
        </div>

        {/* Content */}
        <div className="p-3">
          {activeTab === 'preview' && (
            <div className="rounded-lg border border-[#404040] bg-[#1a1a1a] overflow-hidden">
              {hasPreview ? (
                <div className="relative">
                  <iframe
                    key={iframeKey}
                    srcDoc={processedHtmlContent}
                    className="w-full h-[500px] border-0"
                    title="Dashboard Preview"
                    sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals"
                  />
                  {iframeErrors.length > 0 && (
                    <div className="absolute top-3 right-3 px-2 py-1 bg-red-500/90 text-white text-xs rounded-md">
                      {iframeErrors.length} error{iframeErrors.length > 1 ? 's' : ''}
                    </div>
                  )}
                </div>
              ) : (
                <div className="flex items-center justify-center h-[300px] text-gray-500">
                  <div className="text-center">
                    <Eye className="w-8 h-8 mx-auto mb-2 opacity-60" />
                    <p className="text-sm">No dashboard to preview yet</p>
                    <p className="text-xs text-gray-600 mt-1">Start chatting to generate a dashboard</p>
                  </div>
                </div>
              )}
            </div>
          )}

          {activeTab === 'code' && (
            <div className="relative rounded-lg border border-[#404040] bg-[#1a1a1a]">
              <button
                onClick={handleCopy}
                className="absolute top-3 right-3 z-10 p-2 bg-[#333333] hover:bg-[#404040] text-white rounded-lg transition-colors"
                title="Copy code"
              >
                {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
              </button>
              <pre className="p-4 max-h-[500px] overflow-y-auto custom-scrollbar text-sm text-gray-200 whitespace-pre-wrap font-mono">
                {hasCode ? generatedCode : 'No HTML code available'}
              </pre>
              {isCodeLoading && (
                <div className="absolute inset-0 bg-black/40 flex items-center justify-center rounded-lg">
                  <div className="flex items-center gap-3 px-4 py-2 rounded-lg bg-[#2a2a2a] border border-[#404040]">
                    <div className="w-4 h-4 border-2 border-gray-600 border-t-white rounded-full animate-spin" />
                    <span className="text-xs text-[#e5e5e5]">{codeLoadingMessage || 'Updating HTML...'}</span>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}