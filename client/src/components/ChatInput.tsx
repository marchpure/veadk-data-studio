import type React from "react"
import { useRef, useEffect } from "react"
import { Send } from "lucide-react"

interface ChatInputProps {
  input: string
  setInput: (value: string) => void
  onSubmit: (e: React.FormEvent) => void
  isLoading: boolean
}

export default function ChatInput({ input, setInput, onSubmit, isLoading }: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const adjustTextareaHeight = () => {
    const textarea = textareaRef.current
    if (textarea) {
      textarea.style.height = 'auto'
      textarea.style.height = `${Math.min(textarea.scrollHeight, 128)}px`
    }
  }

  useEffect(() => {
    adjustTextareaHeight()
  }, [input])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSubmit(e as unknown as React.FormEvent)
    }
  }

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value)
    adjustTextareaHeight()
  }

  return (
    <div className="flex-shrink-0 p-4">
      <div className="max-w-3xl mx-auto">
        <form onSubmit={onSubmit} className="relative">
          <div className="flex items-end bg-[#333333] rounded-3xl px-4 py-3">

            <textarea
              ref={textareaRef}
              value={input}
              onChange={handleChange}
              onKeyDown={handleKeyDown}
              placeholder="What's on your mind?"
              className="flex-1 bg-transparent text-white placeholder-[#888888] focus:outline-none resize-none overflow-y-auto custom-scrollbar"
              disabled={isLoading}
              rows={1}
              style={{ minHeight: '24px', maxHeight: '128px', lineHeight: '1.5' }}
            />

            <div className="flex items-center gap-2 ml-3 mb-0.5">
            <button
                  type="submit"
                  disabled={isLoading || !input.trim()}
                  className="p-2 text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors hover:bg-[#444444] rounded-full"
                >
                  <Send size={16} />
                </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  )
}