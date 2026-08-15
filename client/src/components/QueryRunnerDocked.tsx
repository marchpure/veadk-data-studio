import React from 'react'
import { ArrowLeft, Database } from 'lucide-react'
import { NotebookQueryPanel } from './NotebookQueryPanel'

interface QueryRunnerDockedProps {
  notebookId?: string
  onBack?: () => void
  onDebugWithAssistant?: (query: string, error: string, errorDetail?: any) => void
  initialQuery?: string
  initialQueryVersion?: number
}

export default function QueryRunnerDocked({ notebookId, onBack, onDebugWithAssistant, initialQuery, initialQueryVersion }: QueryRunnerDockedProps) {
  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="bg-[#1a1a1a] px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {onBack && (
            <button
              onClick={onBack}
              className="px-2 py-1 text-xs bg-transparent hover:bg-[#2a2a2a] text-white border border-[#404040] rounded-md transition-colors flex items-center gap-1"
              title="Back to versions"
            >
              <ArrowLeft className="w-3 h-3" /> Versions
            </button>
          )}
          <div className="text-sm font-medium text-white flex items-center gap-2">
            <Database className="w-3.5 h-3.5" /> Query Runner
          </div>
        </div>
        <div />
      </div>

      {/* Body */}
      <div className="flex-1 min-h-0">
        <NotebookQueryPanel
          notebookId={notebookId}
          initialQuery={initialQuery}
          initialQueryVersion={initialQueryVersion}
          onDebugWithAssistant={onDebugWithAssistant}
        />
      </div>
    </div>
  )
}
