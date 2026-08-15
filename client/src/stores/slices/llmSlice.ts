import type { StateCreator } from 'zustand'
import type { StoreState } from '../useStore'
import type { LLMConnection } from '../../services/api'
import { ApiService } from '../../services/api'

export interface LLMSlice {
  // State
  llmConnections: LLMConnection[]
  selectedLLMConnection: LLMConnection | null
  selectedModel: string | null
  availableModels: Record<string, string[]>
  supportedProviders: Record<string, any>
  isLoadingModels: boolean
  // Preferred model state
  preferredProvider: string | null
  preferredModel: string | null

  // Actions
  setLLMConnections: (connections: LLMConnection[]) => void
  setSelectedLLMConnection: (connection: LLMConnection | null) => void
  setSelectedModel: (model: string | null) => void
  addLLMConnection: (connection: LLMConnection) => void
  updateLLMConnection: (id: string, connection: Partial<LLMConnection>) => void
  deleteLLMConnection: (id: string) => void
  setAvailableModels: (models: Record<string, string[]>) => void
  setSupportedProviders: (providers: Record<string, any>) => void
  setIsLoadingModels: (loading: boolean) => void
  // Preferred model actions
  fetchPreferredModel: () => Promise<void>
  setPreferredModel: (provider: string, model: string) => Promise<void>
  clearPreferredModel: () => Promise<void>
}

export const createLLMSlice: StateCreator<
  StoreState,
  [],
  [],
  LLMSlice
> = (set) => ({
  // Initial state
  llmConnections: [],
  selectedLLMConnection: null,
  selectedModel: null,
  availableModels: {},
  supportedProviders: {},
  isLoadingModels: false,
  // Preferred model initial state
  preferredProvider: null,
  preferredModel: null,

  // Actions
  setLLMConnections: (connections) =>
    set(() => ({
      llmConnections: connections,
    })),

  setSelectedLLMConnection: (connection) =>
    set(() => ({
      selectedLLMConnection: connection,
    })),

  setSelectedModel: (model) =>
    set(() => ({
      selectedModel: model,
    })),

  addLLMConnection: (connection) =>
    set((state) => ({
      llmConnections: [...state.llmConnections, connection],
    })),

  updateLLMConnection: (id, connection) =>
    set((state) => ({
      llmConnections: state.llmConnections.map((conn) =>
        conn.id === id ? { ...conn, ...connection } : conn
      ),
      selectedLLMConnection:
        state.selectedLLMConnection?.id === id
          ? { ...state.selectedLLMConnection, ...connection }
          : state.selectedLLMConnection,
    })),

  deleteLLMConnection: (id) =>
    set((state) => ({
      llmConnections: state.llmConnections.filter((conn) => conn.id !== id),
      selectedLLMConnection:
        state.selectedLLMConnection?.id === id ? null : state.selectedLLMConnection,
    })),

  setAvailableModels: (models) =>
    set(() => ({
      availableModels: models,
    })),

  setSupportedProviders: (providers) =>
    set(() => ({
      supportedProviders: providers,
    })),

  setIsLoadingModels: (loading) =>
    set(() => ({
      isLoadingModels: loading,
    })),

  // Preferred model actions
  fetchPreferredModel: async () => {
    try {
      const { provider, model } = await ApiService.getPreferredModel()
      set(() => ({
        preferredProvider: provider,
        preferredModel: model,
      }))
    } catch (error) {
      console.error('Failed to fetch preferred model:', error)
    }
  },

  setPreferredModel: async (provider, model) => {
    try {
      await ApiService.setPreferredModel(provider, model)
      set(() => ({
        preferredProvider: provider,
        preferredModel: model,
      }))
    } catch (error) {
      console.error('Failed to set preferred model:', error)
      throw error
    }
  },

  clearPreferredModel: async () => {
    try {
      await ApiService.clearPreferredModel()
      set(() => ({
        preferredProvider: null,
        preferredModel: null,
      }))
    } catch (error) {
      console.error('Failed to clear preferred model:', error)
      throw error
    }
  },
})