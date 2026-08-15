import React from 'react'
import { Eye, Clock } from 'lucide-react'

interface DashboardVersion {
  version_num: number
  created_at: string
}

interface VersionChooserProps {
  availableVersions: DashboardVersion[]
  latestVersionNum: number
  selectedVersion: number | null
  onSelect: (version: number | null) => void
}

export default function VersionChooser({ availableVersions, latestVersionNum, selectedVersion, onSelect }: VersionChooserProps) {
  return (
    <div className="mt-3">
      <div className="bg-[#2a2a2a] border border-[#404040] rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b border-[#404040] bg-[#1a1a1a]">
          <div className="text-sm font-medium text-white">Dashboard Versions</div>
        </div>

        <div className="p-3 space-y-2">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <button
              onClick={() => onSelect(null)}
              className={`text-left px-3 py-3 rounded-md border ${selectedVersion === null ? 'border-white/40' : 'border-[#404040] hover:border-[#555555]'} bg-[#1a1a1a] transition-colors`}
              title={`Open Latest (v${latestVersionNum})`}
            >
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-xs text-white font-medium">Latest</div>
                  <div className="text-[11px] text-[#aaaaaa]">v{latestVersionNum}</div>
                </div>
                <div className="text-white/80">
                  <Eye className="w-4 h-4" />
                </div>
              </div>
            </button>

            {availableVersions.map(v => (
              <button
                key={v.version_num}
                onClick={() => onSelect(v.version_num)}
                className={`text-left px-3 py-3 rounded-md border ${selectedVersion === v.version_num ? 'border-white/40' : 'border-[#404040] hover:border-[#555555]'} bg-[#1a1a1a] transition-colors`}
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
                  <div className="text-white/80">
                    <Eye className="w-4 h-4" />
                  </div>
                </div>
              </button>
            ))}
          </div>

          <div className="pt-2 text-[11px] text-[#888888]">
            Select a version to open it in the result card below.
          </div>
        </div>
      </div>
    </div>
  )
}

