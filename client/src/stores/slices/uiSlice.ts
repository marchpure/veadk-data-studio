import type { StateCreator } from 'zustand'
import type { StoreState } from '../useStore'

export interface UISlice {
  // State
  isSidebarOpen: boolean
  isModalOpen: boolean
  modalType: 'connection' | 'llm' | 'notebook' | null
  activeTab: string
  theme: 'light' | 'dark' | 'system'
  querySavedTrigger: number
  importShareId: string | null

  // Actions
  toggleSidebar: () => void
  setSidebarOpen: (open: boolean) => void
  openModal: (type: 'connection' | 'llm' | 'notebook') => void
  closeModal: () => void
  setActiveTab: (tab: string) => void
  setTheme: (theme: 'light' | 'dark' | 'system') => void
  triggerQuerySaved: () => void
  setImportShareId: (id: string | null) => void
}

export const createUISlice: StateCreator<
  StoreState,
  [],
  [],
  UISlice
> = (set) => ({
  // Initial state
  isSidebarOpen: true,
  isModalOpen: false,
  modalType: null,
  activeTab: 'chat',
  theme: 'system',
  querySavedTrigger: 0,
  importShareId: null,

  // Actions
  toggleSidebar: () =>
    set((state) => ({
      isSidebarOpen: !state.isSidebarOpen,
    })),

  setSidebarOpen: (open) =>
    set(() => ({
      isSidebarOpen: open,
    })),

  openModal: (type) =>
    set(() => ({
      isModalOpen: true,
      modalType: type,
    })),

  closeModal: () =>
    set(() => ({
      isModalOpen: false,
      modalType: null,
    })),

  setActiveTab: (tab) =>
    set(() => ({
      activeTab: tab,
    })),

  setTheme: (theme) =>
    set(() => ({
      theme,
    })),

  triggerQuerySaved: () =>
    set((state) => ({
      querySavedTrigger: state.querySavedTrigger + 1,
    })),

  setImportShareId: (id) =>
    set(() => ({
      importShareId: id,
    })),
})