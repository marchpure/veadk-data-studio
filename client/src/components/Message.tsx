import { memo, useState } from "react"
import { X } from "lucide-react"
import type { Message as MessageType } from "../types/chat"
import MarkdownRenderer from "./MarkdownRenderer"

interface MessageProps {
  message: MessageType
  onCodeInject?: (data: { query: string; connectionId?: string }) => void
}

const Message = memo(function Message({ message, onCodeInject }: MessageProps) {
  const [fullscreenImage, setFullscreenImage] = useState<{mime_type: string, file_data: string, file_name: string} | null>(null)

  if (message.role === "user") {
    return (
      <>
        <div className="flex justify-end">
          <div className="bg-[#2a2a2a] text-white rounded-xl px-3 py-1.5 max-w-[70%] break-words border border-[#3a3a3a]">
            {message.attachments && message.attachments.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-2">
                {message.attachments.map((attachment, index) => (
                  <img
                    key={index}
                    src={`data:${attachment.mime_type};base64,${attachment.file_data}`}
                    alt={attachment.file_name}
                    className="max-w-[200px] max-h-[200px] object-contain rounded-lg cursor-pointer hover:opacity-80 transition-opacity"
                    onClick={() => setFullscreenImage(attachment)}
                  />
                ))}
              </div>
            )}
            <div className="text-sm leading-snug [&_p]:mb-1 [&_ul]:my-1 [&_ol]:my-1 [&_pre]:my-2">
              <MarkdownRenderer content={message.content} onCodeInject={onCodeInject} />
            </div>
          </div>
        </div>
        {fullscreenImage && (
          <div
            className="fixed inset-0 z-[9999] bg-black/90 flex items-center justify-center p-4"
            onClick={() => setFullscreenImage(null)}
          >
            <button
              className="absolute top-4 right-4 w-10 h-10 bg-white/10 hover:bg-white/20 rounded-full flex items-center justify-center transition-colors"
              onClick={() => setFullscreenImage(null)}
            >
              <X className="w-6 h-6 text-white" />
            </button>
            <img
              src={`data:${fullscreenImage.mime_type};base64,${fullscreenImage.file_data}`}
              alt={fullscreenImage.file_name}
              className="max-w-full max-h-full object-contain"
              onClick={(e) => e.stopPropagation()}
            />
          </div>
        )}
      </>
    )
  }

  // Assistant message: plain, full-width content (no bubble background)
  return (
    <div className="flex">
      <div className="w-full text-white">
        <MarkdownRenderer content={message.content} onCodeInject={onCodeInject} />
      </div>
    </div>
  )
})

export default Message
