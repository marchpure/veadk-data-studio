import { Link } from 'react-router-dom'
import { X } from 'lucide-react'

interface SetupPromptCardProps {
  icon: React.ReactNode
  title: string
  description: string
  actionLabel: string
  href?: string
  onClick?: () => void
  onDismiss?: () => void
}

export function SetupPromptCard({ icon, title, description, actionLabel, href, onClick, onDismiss }: SetupPromptCardProps) {
  return (
    <div className="flex items-center justify-between p-4 bg-amber-500/10 border border-amber-500/20 rounded-lg">
      <div className="flex items-center gap-3">
        <div className="text-amber-500">{icon}</div>
        <div>
          <h3 className="text-white font-medium text-sm">{title}</h3>
          <p className="text-gray-400 text-xs">{description}</p>
        </div>
      </div>
      <div className="flex items-center gap-2">
        {href ? (
          <Link to={href} className="text-sm text-amber-500 hover:text-amber-400 font-medium whitespace-nowrap">
            {actionLabel} →
          </Link>
        ) : onClick ? (
          <button onClick={onClick} className="text-sm text-amber-500 hover:text-amber-400 font-medium whitespace-nowrap">
            {actionLabel} →
          </button>
        ) : null}
        {onDismiss && (
          <button
            onClick={onDismiss}
            className="p-1 text-gray-500 hover:text-gray-300 transition-colors rounded"
            aria-label="Dismiss"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>
    </div>
  )
}
