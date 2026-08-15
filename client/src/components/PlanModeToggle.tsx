import { ListChecks } from 'lucide-react'
import { useStore } from '../stores/useStore'

interface PlanModeToggleProps {
  notebookId: string
}

export default function PlanModeToggle({ notebookId }: PlanModeToggleProps) {
  const planMode = useStore((state) => state.notebookPlanMode[notebookId] || false)
  const setPlanMode = useStore((state) => state.setPlanMode)

  return (
    <button
      onClick={() => setPlanMode(notebookId, !planMode)}
      className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs transition-all ${
        planMode
          ? 'bg-blue-500/10 border border-blue-500 text-blue-400'
          : 'bg-[#262626] border border-[#3a3a3a] text-gray-300 hover:border-blue-500/50 hover:text-white'
      }`}
      title={planMode ? 'Plan Mode: ON' : 'Plan Mode: OFF'}
    >
      <ListChecks className="w-3.5 h-3.5" />
      <span>Plan</span>
    </button>
  )
}
