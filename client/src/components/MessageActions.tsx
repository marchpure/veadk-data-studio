import { Copy, ThumbsUp, ThumbsDown, Volume2, RotateCcw, Share } from "lucide-react"

export default function MessageActions() {
  return (
    <div className="flex items-center gap-2 mt-3 text-[#888888]">
      <button className="p-1 hover:bg-[#333333] rounded transition-colors">
        <Copy size={16} />
      </button>
      <button className="p-1 hover:bg-[#333333] rounded transition-colors">
        <ThumbsUp size={16} />
      </button>
      <button className="p-1 hover:bg-[#333333] rounded transition-colors">
        <ThumbsDown size={16} />
      </button>
      <button className="p-1 hover:bg-[#333333] rounded transition-colors">
        <Volume2 size={16} />
      </button>
      <button className="p-1 hover:bg-[#333333] rounded transition-colors">
        <RotateCcw size={16} />
      </button>
      <button className="p-1 hover:bg-[#333333] rounded transition-colors">
        <Share size={16} />
      </button>
    </div>
  )
}