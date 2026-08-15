import { SquarePen } from 'lucide-react'
import CreateNotebook from '../CreateNotebook'
import { useStore } from '../../stores/useStore'
import { useScopes } from '../../hooks/useScopes'

export default function WelcomeSection() {
  const user = useStore((state) => state.user)
  const { isViewer } = useScopes()

  // Get first name or fallback to "there"
  const firstName = user?.full_name?.split(' ')[0] || 'there'

  return (
    <div className="flex items-center justify-between">
      <h1 className="text-2xl font-bold text-white">
        Welcome back, {firstName}
      </h1>
      {!isViewer && (
        <CreateNotebook
          trigger={
            <button className="flex items-center gap-2 bg-brand-orange hover:bg-brand-orange/90 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors">
              <SquarePen className="w-4 h-4" />
              New Notebook
            </button>
          }
        />
      )}
    </div>
  )
}
