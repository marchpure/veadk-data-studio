import React, { useState, useRef, useEffect, memo } from 'react'
import { ArrowUp, Shuffle } from 'lucide-react'
import { TableMentionInput } from "./TableMentionInput"
import { useStore } from "../stores/useStore"
import type { ColumnInfo } from "../hooks/useTableMentions"

interface EmptyStateInputProps {
  notebookId: string | undefined
  datasources: Array<{ id: string; name: string; tables: Record<string, any> }>
  tableNames: string[]
  getTableColumns: (tableName: string, datasourceName?: string) => ColumnInfo[]
  onSubmit: (messageContent: string) => Promise<void>
  selectedProvider: any
  selectedModel: any
  handleCancelGeneration: () => void
}

export const EmptyStateInput = memo(function EmptyStateInput({
  notebookId,
  datasources,
  tableNames,
  getTableColumns,
  onSubmit,
  selectedProvider,
  selectedModel,
  handleCancelGeneration
}: EmptyStateInputProps) {
  const [input, setInput] = useState("")
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // Subscribe to per-notebook streaming state
  const notebookStreamingState = useStore(state => state.notebookStreamingState)
  const isLoading = notebookId ? notebookStreamingState[notebookId] || false : false
  const prevIsLoadingRef = useRef(isLoading)

  // Auto-focus input when agent completes response
  useEffect(() => {
    if (prevIsLoadingRef.current && !isLoading) {
      // Agent just finished responding
      inputRef.current?.focus()
    }
    prevIsLoadingRef.current = isLoading
  }, [isLoading])

  // Auto-focus on mount
  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    // Prevent submission if loading
    if (isLoading) return

    const messageContent = input.trim()
    if (!messageContent) return

    setInput("")  // Clear input immediately
    await onSubmit(messageContent)  // Call parent's submit handler
  }

  const hasInput = input.trim().length > 0

  return (
    <div className="flex flex-col items-center justify-center h-full bg-[#1a1a1a] px-8">

      {/* Subtitle */}
      <h1 className="text-2xl font-bold text-[#888888] mb-8 text-center">
        Let's Byaan the data!
      </h1>

      {/* Input Area */}
      <div className="w-full max-w-[50.4rem]">
        <div className="relative bg-[#262626] border border-[#333333] rounded-xl p-3 transition-all focus-within:border-[#404040]">
          <TableMentionInput
            ref={inputRef}
            value={input}
            datasources={datasources}
            tableNames={tableNames}
            getTableColumns={getTableColumns}
            onValueChange={setInput}
            onSubmit={() => {
              // Only submit if not loading
              if (!isLoading) {
                const event = new Event('submit') as any
                handleSubmit(event)
              }
            }}
            placeholder={!selectedProvider || !selectedModel ? "Configure your LLM connection first!" : isLoading ? "Stop generation to send message..." : "Type your message..."}
            disabled={!selectedProvider || !selectedModel}
            className="w-full text-[#e5e5e5] text-base pr-12 min-h-[40px]"
          />
          {isLoading ? (
            <button
              onClick={handleCancelGeneration}
              className="absolute right-2 top-1/2 transform -translate-y-1/2 w-8 h-8 bg-white hover:bg-gray-100 rounded-full transition-colors flex items-center justify-center"
              title="Stop generation"
            >
              <div className="w-3.5 h-3.5 bg-black rounded-sm"></div>
            </button>
          ) : (
            <button
              onClick={(e) => {
                // Prevent submission if loading
                if (!isLoading) {
                  const event = new Event('submit') as any
                  handleSubmit(event)
                }
              }}
              disabled={!hasInput || !selectedProvider || !selectedModel || isLoading}
              className={`absolute right-2 top-1/2 transform -translate-y-1/2 w-8 h-8 rounded-full transition-colors flex items-center justify-center ${
                hasInput && selectedProvider && selectedModel && !isLoading
                  ? 'bg-white hover:bg-gray-100 text-black cursor-pointer'
                  : 'bg-[#404040] text-gray-600 cursor-not-allowed'
              }`}
              title={isLoading ? "Stop generation to send message" : hasInput ? "Send message" : "Type a message to send"}
            >
              <ArrowUp className="w-4 h-4" />
            </button>
          )}
        </div>

      </div>
    </div>
  )
})
