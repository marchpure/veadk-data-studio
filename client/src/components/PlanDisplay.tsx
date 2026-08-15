import { useState, useEffect } from 'react'
import { Check, Circle, Loader2, AlertCircle, ChevronRight, ChevronDown, X } from 'lucide-react'
import type { Plan, PlanStep } from '../stores/slices/planSlice'

interface PlanDisplayProps {
  plan: Plan
  onDismiss?: () => void
}

function StatusIcon({ status, size = 'sm' }: { status: PlanStep['status']; size?: 'sm' | 'xs' }) {
  const sizeClass = size === 'sm' ? 'w-4 h-4' : 'w-3 h-3'
  switch (status) {
    case 'pending':
      return <Circle className={`${sizeClass} text-gray-400`} />
    case 'running':
      return <Loader2 className={`${sizeClass} text-blue-500 animate-spin`} />
    case 'completed':
      return <Check className={`${sizeClass} text-green-500`} />
    case 'failed':
      return <AlertCircle className={`${sizeClass} text-red-500`} />
  }
}

export default function PlanDisplay({ plan, onDismiss }: PlanDisplayProps) {
  const [isExpanded, setIsExpanded] = useState(false)

  const isExecuting = plan.steps.some((s) => s.status === 'running')
  const isComplete = (plan.steps.length > 0 && plan.steps.every((s) => s.status === 'completed')) || plan.isComplete
  const hasFailed = plan.steps.some((s) => s.status === 'failed')
  const currentStepIndex = plan.steps.findIndex((s) => s.status === 'running')
  const currentStep = currentStepIndex >= 0 ? plan.steps[currentStepIndex] : null
  const completedCount = plan.steps.filter((s) => s.status === 'completed').length

  useEffect(() => {
    if (plan.isAwaitingApproval) {
      setIsExpanded(true)
    }
  }, [plan.isAwaitingApproval])

  const getSummaryText = () => {
    if (isComplete) {
      return `Plan complete (${plan.steps.length} steps)`
    }
    if (hasFailed) {
      return `Step failed`
    }
    if (isExecuting && currentStep) {
      return `Step ${currentStepIndex + 1} of ${plan.steps.length}: ${currentStep.name}`
    }
    if (plan.isAwaitingApproval) {
      return `Plan ready — ${plan.steps.length} steps awaiting your approval`
    }
    if (completedCount > 0) {
      return `${completedCount} of ${plan.steps.length} steps completed`
    }
    return `${plan.steps.length} steps planned`
  }

  const getSummaryStatus = (): PlanStep['status'] => {
    if (isComplete) return 'completed'
    if (hasFailed) return 'failed'
    if (isExecuting) return 'running'
    return 'pending'
  }

  return (
    <div className="bg-[#1a1a1a] rounded-lg border border-[#333] max-w-full overflow-hidden">
      {/* Collapsed/Header view - always visible */}
      <div className="w-full flex items-center hover:bg-[#222] transition-colors">
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex-1 flex items-center gap-2 p-3 text-left min-w-0"
        >
          <div className="flex-shrink-0 text-gray-400">
            {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
          </div>
          <StatusIcon status={getSummaryStatus()} size="sm" />
          <span className={`text-sm flex-1 truncate ${isComplete ? 'text-green-400' : hasFailed ? 'text-red-400' : 'text-white'}`}>
            {getSummaryText()}
          </span>
        </button>
        {onDismiss && (
          <button
            onClick={onDismiss}
            className="flex-shrink-0 p-2 mr-1 rounded text-gray-400 hover:text-white hover:bg-[#333] transition-colors"
            aria-label="Dismiss plan"
            title="Dismiss"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Expanded view */}
      {isExpanded && (
        <div className="border-t border-[#333] px-3 pb-3">
          <div className="space-y-1 pt-2">
            {plan.steps.map((step, idx) => (
              <div
                key={step.id}
                className={`flex items-center gap-2 py-1 px-2 rounded ${step.status === 'running' ? 'bg-blue-500/10' : ''}`}
              >
                <StatusIcon status={step.status} size="xs" />
                <span className={`text-xs flex-1 truncate ${step.status === 'completed' ? 'text-gray-500' : step.status === 'running' ? 'text-white' : 'text-gray-400'}`}>
                  {idx + 1}. {step.name}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
