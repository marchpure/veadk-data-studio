import type { StateCreator } from 'zustand'

export interface TableMention {
  name: string
  position: number
}

export interface TableMentionsSlice {
  // State
  inputValue: string
  showDropdown: boolean
  selectedIndex: number
  cursorPosition: number
  mentionStart: number
  searchQuery: string
  
  // Actions
  setInputValue: (value: string) => void
  setShowDropdown: (show: boolean) => void
  setSelectedIndex: (index: number | ((prev: number) => number)) => void
  setCursorPosition: (position: number) => void
  setMentionStart: (start: number) => void
  setSearchQuery: (query: string) => void
  resetTableMentions: () => void
}

const initialState = {
  inputValue: '',
  showDropdown: false,
  selectedIndex: 0,
  cursorPosition: 0,
  mentionStart: -1,
  searchQuery: '',
}

export const createTableMentionsSlice: StateCreator<
  TableMentionsSlice,
  [],
  [],
  TableMentionsSlice
> = (set, get) => ({
  ...initialState,

  setInputValue: (value: string) => {
    set({ inputValue: value })
  },

  setShowDropdown: (show: boolean) => {
    set({ showDropdown: show })
  },

  setSelectedIndex: (index: number | ((prev: number) => number)) => {
    set((state) => ({ 
      selectedIndex: typeof index === 'function' ? index(state.selectedIndex) : index 
    }))
  },

  setCursorPosition: (position: number) => {
    set({ cursorPosition: position })
  },

  setMentionStart: (start: number) => {
    set({ mentionStart: start })
  },

  setSearchQuery: (query: string) => {
    set({ searchQuery: query })
  },

  resetTableMentions: () => {
    set(initialState)
  },
})