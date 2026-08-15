interface LoadingIndicatorProps {
  text?: string
}

export default function LoadingIndicator({ text }: LoadingIndicatorProps) {
  return (
    <div className="mb-8">
      <div className="flex items-center gap-2 text-[#888888]">
          {text && <span className="text-xs">{text}</span>}
        <div className="flex space-x-1">
          <div className="w-2 h-2 bg-[#666666] rounded-full animate-bounce"></div>
          <div
            className="w-2 h-2 bg-[#666666] rounded-full animate-bounce"
            style={{ animationDelay: "0.1s" }}
          ></div>
          <div
            className="w-2 h-2 bg-[#666666] rounded-full animate-bounce"
            style={{ animationDelay: "0.2s" }}
          ></div>
        </div>
      </div>
    </div>
  )
}
