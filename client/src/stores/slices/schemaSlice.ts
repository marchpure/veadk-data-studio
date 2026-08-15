import type { StateCreator } from 'zustand'
import type { StoreState } from '../useStore'
import type { DatabaseSchemaResponse } from '../../services/api'
import { ApiService } from '../../services/api'

export interface SchemaSlice {
  // State
  currentNotebookId: string | null
  schema: DatabaseSchemaResponse | null
  isLoadingSchema: boolean
  schemaError: string | null
  
  // Actions
  setCurrentNotebook: (notebookId: string | null) => void
  loadSchema: (notebookId: string, datasourceType?: string) => Promise<void>
  forceLoadSchema: (notebookId: string, datasourceType?: string) => Promise<void>
  cacheSchema: (schema: DatabaseSchemaResponse) => void
  clearSchema: () => void
  setSchemaLoading: (loading: boolean) => void
  setSchemaError: (error: string | null) => void
}

export const createSchemaSlice: StateCreator<
  StoreState,
  [],
  [],
  SchemaSlice
> = (set, get) => ({
  // Initial state
  currentNotebookId: null,
  schema: null,
  isLoadingSchema: false,
  schemaError: null,
  
  // Actions
  setCurrentNotebook: (notebookId) =>
    set((state) => {
      // Clear schema if notebook changed
      if (state.currentNotebookId !== notebookId) {
        return {
          currentNotebookId: notebookId,
          schema: null,
          isLoadingSchema: false,
          schemaError: null,
        }
      }
      return { currentNotebookId: notebookId }
    }),

  loadSchema: async (notebookId: string, datasourceType?: string) => {
    const state = get()

    // Don't load if already loading or if we have schema for current notebook
    if (state.isLoadingSchema || (state.schema && state.currentNotebookId === notebookId)) {
      return
    }

    set({ isLoadingSchema: true, schemaError: null })

    try {
      const schemaData = await ApiService.getDatabaseSchema(notebookId, datasourceType)

      // Only cache if we're still on the same notebook
      const currentState = get()
      if (currentState.currentNotebookId === notebookId) {
        set({
          schema: schemaData,
          isLoadingSchema: false,
          schemaError: null,
        })
      }
    } catch (err: any) {
      // Only set error if we're still on the same notebook
      const currentState = get()
      if (currentState.currentNotebookId === notebookId) {
        let errorMessage = 'Failed to load database schema'
        
        // Extract error message from the response
        if (err?.message) {
          // Check if the error message contains our structured error response
          if (err.message.includes('"message":')) {
            try {
              // Try to parse the error detail from the message
              const match = err.message.match(/\{.*\}/s)
              if (match) {
                const errorDetail = JSON.parse(match[0])
                errorMessage = errorDetail.message || errorDetail.error || errorMessage
              }
            } catch {
              // If parsing fails, use the original message
              errorMessage = err.message
            }
          } else {
            errorMessage = err.message
          }
        }
        
        set({
          schema: null,
          isLoadingSchema: false,
          schemaError: errorMessage,
        })
      }
    }
  },

  forceLoadSchema: async (notebookId: string, datasourceType?: string) => {
    // Force reload schema regardless of current state
    set({ isLoadingSchema: true, schemaError: null })

    try {
      const schemaData = await ApiService.getDatabaseSchema(notebookId, datasourceType)

      // Only cache if we're still on the same notebook
      const currentState = get()
      if (currentState.currentNotebookId === notebookId) {
        set({
          schema: schemaData,
          isLoadingSchema: false,
          schemaError: null,
        })
      }
    } catch (err: any) {
      // Only set error if we're still on the same notebook
      const currentState = get()
      if (currentState.currentNotebookId === notebookId) {
        let errorMessage = 'Failed to load database schema'
        
        // Extract error message from the response
        if (err?.message) {
          // Check if the error message contains our structured error response
          if (err.message.includes('"message":')) {
            try {
              // Try to parse the error detail from the message
              const match = err.message.match(/\{.*\}/s)
              if (match) {
                const errorDetail = JSON.parse(match[0])
                errorMessage = errorDetail.message || errorDetail.error || errorMessage
              }
            } catch {
              // If parsing fails, use the original message
              errorMessage = err.message
            }
          } else {
            errorMessage = err.message
          }
        }
        
        set({
          schema: null,
          isLoadingSchema: false,
          schemaError: errorMessage,
        })
      }
    }
  },
    
  cacheSchema: (schema) =>
    set(() => ({
      schema,
      isLoadingSchema: false,
      schemaError: null,
    })),
    
  clearSchema: () =>
    set(() => ({
      schema: null,
      isLoadingSchema: false,
      schemaError: null,
    })),
    
  setSchemaLoading: (loading) =>
    set(() => ({
      isLoadingSchema: loading,
    })),
    
  setSchemaError: (error) =>
    set(() => ({
      schemaError: error,
      isLoadingSchema: false,
    })),
})