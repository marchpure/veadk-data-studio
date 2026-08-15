import type { StateCreator } from 'zustand'
import type { StoreState } from '../useStore'

export type PlanStepStatus = 'pending' | 'running' | 'completed' | 'failed'
export type PlanStatusAction = 'start_plan' | 'start_step' | 'complete_step' | 'fail_step' | 'complete_plan'

export interface PlanStep {
  id: string
  name: string
  description: string
  status: PlanStepStatus
}

export interface Plan {
  plan_id: string
  notebook_id: string
  steps: PlanStep[]
  created_at?: string
  totalSteps?: number
  isComplete?: boolean
  isAwaitingApproval?: boolean
}

export interface PlanStatusEvent {
  action: PlanStatusAction
  notebook_id?: string
  steps?: Array<{ name: string; description?: string }>
  step_number?: number
  total_steps?: number
}

export interface PlanSlice {
  notebookPlanMode: Record<string, boolean>
  activePlans: Record<string, Plan | null>

  setPlanMode: (notebookId: string, enabled: boolean) => void
  getPlanMode: (notebookId: string) => boolean
  setActivePlan: (notebookId: string, plan: Plan | null) => void
  updatePlanStep: (notebookId: string, stepId: string, status: PlanStepStatus) => void
  handlePlanStatus: (notebookId: string, event: PlanStatusEvent) => void
  clearPlan: (notebookId: string) => void
}

export const createPlanSlice: StateCreator<StoreState, [], [], PlanSlice> = (set, get) => ({
  notebookPlanMode: {},
  activePlans: {},

  setPlanMode: (notebookId, enabled) =>
    set((state) => ({
      notebookPlanMode: {
        ...state.notebookPlanMode,
        [notebookId]: enabled,
      },
    })),

  getPlanMode: (notebookId) => {
    const state = get()
    return state.notebookPlanMode[notebookId] || false
  },

  setActivePlan: (notebookId, plan) =>
    set((state) => ({
      activePlans: {
        ...state.activePlans,
        [notebookId]: plan,
      },
    })),

  updatePlanStep: (notebookId, stepId, status) =>
    set((state) => {
      const plan = state.activePlans[notebookId]
      if (!plan) return state

      const updatedSteps = plan.steps.map((step) => (step.id === stepId ? { ...step, status } : step))

      return {
        activePlans: {
          ...state.activePlans,
          [notebookId]: { ...plan, steps: updatedSteps },
        },
      }
    }),

  handlePlanStatus: (notebookId, event) =>
    set((state) => {
      const { action, steps: eventSteps, step_number, total_steps } = event
      let plan = state.activePlans[notebookId]

      switch (action) {
        case 'start_plan': {
          const steps: PlanStep[] = eventSteps
            ? eventSteps.map((s, idx) => ({
                id: `step_${idx + 1}`,
                name: s.name,
                description: s.description || '',
                status: 'pending' as PlanStepStatus,
              }))
            : Array.from({ length: total_steps || 0 }, (_, i) => ({
                id: `step_${i + 1}`,
                name: `Step ${i + 1}`,
                description: '',
                status: 'pending' as PlanStepStatus,
              }))

          plan = {
            plan_id: `plan_${Date.now()}`,
            notebook_id: notebookId,
            steps,
            totalSteps: steps.length,
            isComplete: false,
            isAwaitingApproval: true,
          }
          break
        }
        case 'start_step': {
          if (plan) {
            const stepIndex = (step_number || 1) - 1
            const updatedSteps = [...plan.steps]
            if (stepIndex < updatedSteps.length) {
              updatedSteps[stepIndex] = {
                ...updatedSteps[stepIndex],
                status: 'running',
              }
            }
            plan = { ...plan, steps: updatedSteps, isAwaitingApproval: false }
          }
          // If no plan exists, ignore - start_plan should be called first
          break
        }
        case 'complete_step': {
          if (plan && step_number) {
            const stepIndex = step_number - 1
            const updatedSteps = [...plan.steps]
            if (stepIndex < updatedSteps.length) {
              updatedSteps[stepIndex] = { ...updatedSteps[stepIndex], status: 'completed' }
            }
            plan = { ...plan, steps: updatedSteps }
          }
          break
        }
        case 'fail_step': {
          if (plan && step_number) {
            const stepIndex = step_number - 1
            const updatedSteps = [...plan.steps]
            if (stepIndex < updatedSteps.length) {
              updatedSteps[stepIndex] = { ...updatedSteps[stepIndex], status: 'failed' }
            }
            plan = { ...plan, steps: updatedSteps }
          }
          break
        }
        case 'complete_plan': {
          if (plan) {
            plan = { ...plan, isComplete: true }
          }
          break
        }
      }

      return {
        activePlans: {
          ...state.activePlans,
          [notebookId]: plan,
        },
      }
    }),

  clearPlan: (notebookId) =>
    set((state) => ({
      activePlans: {
        ...state.activePlans,
        [notebookId]: null,
      },
    })),
})
