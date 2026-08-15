import type { StateCreator } from 'zustand'
import type { StoreState } from '../useStore'
import type { Notebook } from '../../services/api'

export interface NotebookSlice {
  // State
  notebooks: Notebook[]
  currentNotebook: Notebook | null
  isLoadingNotebooks: boolean
  notebookDatasourcesChangedTrigger: number
  threads: unknown[]

  // Actions
  setNotebooks: (notebooks: Notebook[]) => void
  setCurrentNotebook: (notebook: Notebook | null) => void
  addNotebook: (notebook: Notebook) => void
  updateNotebook: (id: string, notebook: Partial<Notebook>) => void
  deleteNotebook: (id: string) => void
  setIsLoadingNotebooks: (loading: boolean) => void
  triggerNotebookDatasourcesChanged: () => void
  setThreads: (threads: unknown[]) => void
}

export const createNotebookSlice: StateCreator<
  StoreState,
  [],
  [],
  NotebookSlice
> = (set) => ({
  // Initial state
  notebooks: [],
  currentNotebook: null,
  isLoadingNotebooks: false,
  notebookDatasourcesChangedTrigger: 0,
  threads: [],

  // Actions
  setNotebooks: (notebooks) =>
    set(() => ({
      notebooks,
    })),

  setCurrentNotebook: (notebook) =>
    set(() => ({
      currentNotebook: notebook,
    })),

  addNotebook: (notebook) =>
    set((state) => ({
      notebooks: [...state.notebooks, notebook],
    })),

  updateNotebook: (id, notebook) =>
    set((state) => ({
      notebooks: state.notebooks.map((nb) =>
        nb.id === id ? { ...nb, ...notebook } : nb
      ),
      currentNotebook:
        state.currentNotebook?.id === id
          ? { ...state.currentNotebook, ...notebook }
          : state.currentNotebook,
    })),

  deleteNotebook: (id) =>
    set((state) => ({
      notebooks: state.notebooks.filter((nb) => nb.id !== id),
      currentNotebook: state.currentNotebook?.id === id ? null : state.currentNotebook,
    })),

  setIsLoadingNotebooks: (loading) =>
    set(() => ({
      isLoadingNotebooks: loading,
    })),

  setThreads: (threads) =>
    set(() => ({
      threads,
    })),

  triggerNotebookDatasourcesChanged: () =>
    set((state) => ({
      notebookDatasourcesChangedTrigger: state.notebookDatasourcesChangedTrigger + 1,
    })),
})
