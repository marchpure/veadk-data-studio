import type { StateCreator } from 'zustand'
import type { StoreState } from '../useStore'

export interface Download {
  id: string
  fileName: string
  fileType: 'pdf' | 'html' | 'csv'
  filePath?: string // Full path for Tauri, undefined for web
  status: 'success' | 'error'
  timestamp: number
}

export interface DownloadSlice {
  // State
  downloads: Download[]

  // Actions
  addDownload: (download: Omit<Download, 'id' | 'timestamp'>) => void
  removeDownload: (id: string) => void
  clearDownloads: () => void
}

export const createDownloadSlice: StateCreator<
  StoreState,
  [],
  [],
  DownloadSlice
> = (set) => ({
  // Initial state
  downloads: [],

  // Actions
  addDownload: (download) =>
    set((state) => ({
      downloads: [
        ...state.downloads,
        {
          ...download,
          id: crypto.randomUUID(),
          timestamp: Date.now(),
        },
      ],
    })),

  removeDownload: (id) =>
    set((state) => ({
      downloads: state.downloads.filter((d) => d.id !== id),
    })),

  clearDownloads: () =>
    set(() => ({
      downloads: [],
    })),
})
