import React from 'react'
import { Clock, Eye, Database } from 'lucide-react'

interface DashboardVersion {
  version_num: number
  created_at: string
}

interface VersionSidebarProps {
  availableVersions: DashboardVersion[]
  latestVersionNum: number
  selectedVersion: number | null
  onSelect: (version: number | null) => void
  onOpenQueryRunner?: () => void
  className?: string
}

export default function VersionSidebar({
  availableVersions,
  latestVersionNum,
  selectedVersion,
  onSelect,
  onOpenQueryRunner,
  className = ''
}: VersionSidebarProps) {
  // Deduplicate versions by version_num and hide duplicate of "Latest"
  const uniqueVersions = Array.from(new Map(availableVersions.map(v => [v.version_num, v])).values())
  const nonLatestVersions = uniqueVersions.filter(v => v.version_num !== latestVersionNum)
  const hasMultipleVersions = uniqueVersions.length > 1

  return (
    <div className={`h-full flex flex-col bg-[#1a1a1a] ${className}`}>
        {/* Query Runner entry */}
        <button
            onClick={onOpenQueryRunner}
            className={`w-full text-left px-4 py-3 border-b border-[#2a2a2a] hover:bg-[#232323] transition-colors cursor-pointer`}
            title="Open Query Runner"
        >
            <div className="flex items-center justify-between">
                <div className="text-xs text-white font-medium flex items-center gap-2">
                    <Database className="w-3.5 h-3.5" /> Query Runner
                </div>
            </div>
        </button>
      <div className="border-b border-[#404040]">
        <div className="px-4 py-3 text-sm font-medium text-white">Dashboards</div>
          <div className="flex-1 overflow-y-auto custom-scrollbar">

              {/* When multiple versions exist, show a "Latest" row and the rest excluding latest */}
              {hasMultipleVersions ? (
                  <>
                      <button
                          onClick={() => onSelect(null)}
                          className={`w-full text-left px-4 py-3 border-b border-[#2a2a2a] hover:bg-[#232323] transition-colors cursor-pointer ${
                              selectedVersion === null ? 'bg-[#232323]' : ''
                          }`}
                          title={`Open Latest (v${latestVersionNum})`}
                      >
                          <div className="flex items-center justify-between">
                              <div>
                                  <div className="text-xs text-white font-medium">Latest</div>
                                  <div className="text-[11px] text-[#aaaaaa]">v{latestVersionNum}</div>
                              </div>
                              <Eye className="w-4 h-4 text-white/80" />
                          </div>
                      </button>

                      {nonLatestVersions.map((v) => (
                          <button
                              key={v.version_num}
                              onClick={() => onSelect(v.version_num)}
                              className={`w-full text-left px-4 py-3 border-b border-[#2a2a2a] hover:bg-[#232323] transition-colors cursor-pointer ${
                                  selectedVersion === v.version_num ? 'bg-[#232323]' : ''
                              }`}
                              title={`Open v${v.version_num}`}
                          >
                              <div className="flex items-center justify-between">
                                  <div>
                                      <div className="text-xs text-white font-medium">v{v.version_num}</div>
                                      <div className="flex items-center gap-1 text-[11px] text-[#aaaaaa]">
                                          <Clock className="w-3 h-3" />
                                          <span>{new Date(v.created_at).toLocaleString()}</span>
                                      </div>
                                  </div>
                                  <Eye className="w-4 h-4 text-white/80" />
                              </div>
                          </button>
                      ))}
                  </>
              ) : (
                  // Single version: show only the version row (no separate Latest row)
                  uniqueVersions.map((v) => (
                      <button
                          key={v.version_num}
                          onClick={() => onSelect(v.version_num)}
                          className={`w-full text-left px-4 py-3 border-b border-[#2a2a2a] hover:bg-[#232323] transition-colors cursor-pointer ${
                              selectedVersion === v.version_num ? 'bg-[#232323]' : ''
                          }`}
                          title={`Open v${v.version_num}`}
                      >
                          <div className="flex items-center justify-between">
                              <div>
                                  <div className="text-xs text-white font-medium">v{v.version_num}</div>
                                  <div className="flex items-center gap-1 text-[11px] text-[#aaaaaa]">
                                      <Clock className="w-3 h-3" />
                                      <span>{new Date(v.created_at).toLocaleString()}</span>
                                  </div>
                              </div>
                              <Eye className="w-4 h-4 text-white/80" />
                          </div>
                      </button>
                  ))
              )}
          </div>
      </div>
    </div>
  )
}
