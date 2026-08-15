import React, { useEffect, useRef } from 'react'
import { X, Database } from 'lucide-react'
import { NotebookQueryPanel } from './NotebookQueryPanel'

interface QueryPanelOverlayProps {
  isOpen: boolean
  onClose: () => void
  notebookId?: string
  onDebugWithAssistant?: (query: string, error: string, errorDetail?: any) => void
  injectedQuery?: string
  injectedQueryVersion?: number
  injectedConnectionId?: string
}

export function QueryPanelOverlay({ isOpen, onClose, notebookId, onDebugWithAssistant, injectedQuery, injectedQueryVersion, injectedConnectionId }: QueryPanelOverlayProps) {
  const panelRef = useRef<HTMLDivElement>(null)

  // Handle ESC key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose()
      }
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [isOpen, onClose])

  // Handle click outside - only close on backdrop clicks, not panel clicks
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      // Only close if clicking directly on the backdrop
      if (isOpen && e.target && (e.target as HTMLElement).classList.contains('query-panel-backdrop')) {
        onClose()
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [isOpen, onClose])

  return (
    <div className={`fixed inset-0 z-50 flex justify-end ${isOpen ? '' : 'pointer-events-none invisible'}`}>
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50 query-panel-backdrop" />
      
      {/* Panel */}
      <div 
        ref={panelRef}
        className="relative w-full max-w-[75vw] bg-[#1a1a1a] border-l border-[#404040] shadow-2xl animate-slide-in-right"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[#404040]">
          <h2 className="text-lg font-medium text-white flex items-center gap-2">
            <Database className="w-5 h-5" />
            Dashboard Queries
          </h2>
          <button
            onClick={onClose}
            className="p-1.5 hover:bg-[#2a2a2a] rounded-lg transition-colors text-gray-400 hover:text-white"
            title="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="h-[calc(100vh-73px)] overflow-hidden">
          <NotebookQueryPanel
            notebookId={notebookId}
            onDebugWithAssistant={onDebugWithAssistant}
            injectedQuery={injectedQuery}
            injectedQueryVersion={injectedQueryVersion}
            injectedConnectionId={injectedConnectionId}
          />
        </div>
      </div>
    </div>
  )
}

// Add animation to tailwind config or use inline styles
const style = document.createElement('style')
style.textContent = `
  @keyframes slide-in-right {
    from {
      transform: translateX(100%);
    }
    to {
      transform: translateX(0);
    }
  }
  .animate-slide-in-right {
    animation: slide-in-right 0.3s ease-out;
  }
`
document.head.appendChild(style)