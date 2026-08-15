import React from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog'
import { NotebookQueryPanel } from './NotebookQueryPanel'
import { type ErrorDetail } from '../services/api'

interface QueryPanelModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  notebookId?: string
  onDebugWithAssistant?: (query: string, error: string, errorDetail?: ErrorDetail) => void
}

export default function QueryPanelModal({ open, onOpenChange, notebookId, onDebugWithAssistant }: QueryPanelModalProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-none w-[95vw] h-[90vh] p-0 bg-[#1a1a1a] border-[#404040]">
        <div className="flex flex-col h-full">
          <div className="flex items-center justify-between px-4 h-12 border-b border-[#404040] bg-[#1a1a1a]">
            <DialogHeader>
              <DialogTitle className="text-white text-sm">Query Panel</DialogTitle>
            </DialogHeader>
          </div>
          <div className="flex-1 overflow-hidden">
            <NotebookQueryPanel
              notebookId={notebookId}
              onDebugWithAssistant={onDebugWithAssistant}
            />
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

