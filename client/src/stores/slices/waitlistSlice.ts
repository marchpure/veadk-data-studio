/**
 * Waitlist Slice - Zustand state management for waitlist
 */

import type { StateCreator } from 'zustand'
import type { StoreState } from '../useStore'

export interface AccessStatus {
  hasAccess: boolean
  onboarded: boolean
  apiKey: string | null
  position?: number
  message?: string
}

export interface WaitlistSlice {
  // State
  accessStatus: AccessStatus | null
  isLoading: boolean
  error: string | null

  // Actions
  setAccessStatus: (status: AccessStatus | null) => void
  setIsLoading: (isLoading: boolean) => void
  setError: (error: string | null) => void
  clearError: () => void
  reset: () => void
}

const initialState = {
  accessStatus: null,
  isLoading: true,
  error: null,
}

export const createWaitlistSlice: StateCreator<
  StoreState,
  [],
  [],
  WaitlistSlice
> = (set) => ({
  ...initialState,

  setAccessStatus: (status) => set({ accessStatus: status }),

  setIsLoading: (isLoading) => set({ isLoading }),

  setError: (error) => set({ error }),

  clearError: () => set({ error: null }),

  reset: () => set(initialState),
})
