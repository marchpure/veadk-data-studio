import type { StateCreator } from 'zustand'
import type { StoreState } from '../useStore'
import { ApiService } from '../../services/api'
import type { Folder, FolderMember, FolderNotebook, FolderDashboard, CloneNotebookResponse } from '../../types/folder'

export interface FolderSlice {
  folders: Folder[]
  activeFolderId: string | null
  folderMembers: FolderMember[]
  folderNotebooks: FolderNotebook[]
  folderDashboards: FolderDashboard[]
  isLoadingFolders: boolean
  folderError: string | null

  fetchFolders: () => Promise<void>
  setActiveFolder: (folderId: string | null) => void
  fetchFolderMembers: (folderId: string) => Promise<void>
  fetchFolderNotebooks: (folderId: string) => Promise<void>
  fetchFolderDashboards: (folderId: string) => Promise<void>
  createFolder: (name: string, description?: string, is_public?: boolean) => Promise<Folder>
  updateFolder: (folderId: string, name?: string, description?: string, is_public?: boolean) => Promise<Folder>
  deleteFolder: (folderId: string) => Promise<void>
  addFolderMember: (folderId: string, userId: string) => Promise<void>
  removeFolderMember: (folderId: string, memberId: string) => Promise<void>
  shareNotebookToFolder: (folderId: string, notebookId: string, isSnapshot?: boolean) => Promise<void>
  unshareNotebookFromFolder: (folderId: string, notebookId: string) => Promise<void>
  unshareDashboardFromFolder: (folderId: string, dashboardId: string) => Promise<void>
  cloneNotebook: (folderId: string, notebookId: string, newName?: string) => Promise<CloneNotebookResponse>
  updateSnapshot: (folderId: string, notebookId: string) => Promise<void>
  clearFolders: () => void
}

const initialState = {
  folders: [] as Folder[],
  activeFolderId: null as string | null,
  folderMembers: [] as FolderMember[],
  folderNotebooks: [] as FolderNotebook[],
  folderDashboards: [] as FolderDashboard[],
  isLoadingFolders: false,
  folderError: null as string | null,
}

export const createFolderSlice: StateCreator<StoreState, [], [], FolderSlice> = (set, get) => ({
  ...initialState,

  fetchFolders: async () => {
    const { isAuthenticated } = get()
    if (!isAuthenticated) {
      return
    }

    set({ isLoadingFolders: true, folderError: null })
    try {
      const response = await ApiService.getFolders()
      set({ folders: response.items, isLoadingFolders: false })
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to fetch folders'
      set({ folderError: message, isLoadingFolders: false })
      console.error('Error fetching folders:', error)
    }
  },

  setActiveFolder: (folderId) => {
    set({ activeFolderId: folderId })
  },

  fetchFolderMembers: async (folderId) => {
    try {
      const response = await ApiService.getFolderMembers(folderId)
      set({ folderMembers: response.items })
    } catch (error) {
      console.error('Failed to fetch folder members:', error)
    }
  },

  fetchFolderNotebooks: async (folderId) => {
    try {
      const response = await ApiService.getFolderNotebooks(folderId)
      set({ folderNotebooks: response.items })
    } catch (error) {
      console.error('Failed to fetch folder notebooks:', error)
    }
  },

  fetchFolderDashboards: async (folderId) => {
    try {
      const response = await ApiService.getFolderDashboards(folderId)
      set({ folderDashboards: response.items })
    } catch (error) {
      console.error('Failed to fetch folder dashboards:', error)
    }
  },

  createFolder: async (name, description, is_public) => {
    const folder = await ApiService.createFolder({ name, description, is_public })
    set((state) => ({ folders: [folder, ...state.folders] }))
    return folder
  },

  updateFolder: async (folderId, name, description, is_public) => {
    const folder = await ApiService.updateFolder(folderId, { name, description, is_public })
    set((state) => ({
      folders: state.folders.map((f) => (f.id === folderId ? folder : f)),
    }))
    return folder
  },

  deleteFolder: async (folderId) => {
    await ApiService.deleteFolder(folderId)
    set((state) => ({
      folders: state.folders.filter((f) => f.id !== folderId),
      activeFolderId: state.activeFolderId === folderId ? null : state.activeFolderId,
    }))
  },

  addFolderMember: async (folderId, userId) => {
    await ApiService.addFolderMember(folderId, userId)
    await get().fetchFolderMembers(folderId)
  },

  removeFolderMember: async (folderId, memberId) => {
    await ApiService.removeFolderMember(folderId, memberId)
    set((state) => ({
      folderMembers: state.folderMembers.filter((m) => m.id !== memberId),
    }))
  },

  shareNotebookToFolder: async (folderId, notebookId, isSnapshot = false) => {
    await ApiService.shareNotebookToFolder(folderId, notebookId, isSnapshot)
    await get().fetchFolderNotebooks(folderId)
  },

  unshareNotebookFromFolder: async (folderId, notebookId) => {
    await ApiService.unshareNotebookFromFolder(folderId, notebookId)
    set((state) => ({
      folderNotebooks: state.folderNotebooks.filter((n) => n.notebook_id !== notebookId),
    }))
  },

  unshareDashboardFromFolder: async (folderId, dashboardId) => {
    await ApiService.unshareDashboardFromFolder(folderId, dashboardId)
    set((state) => ({
      folderDashboards: state.folderDashboards.filter((d) => d.dashboard_id !== dashboardId),
    }))
  },

  cloneNotebook: async (folderId, notebookId, newName) => {
    const result = await ApiService.cloneNotebookFromFolder(folderId, notebookId, newName)
    // Invalidate notebooks cache so the list updates when user navigates back
    const { queryClient } = await import('@/lib/queryClient')
    queryClient.invalidateQueries({ queryKey: ['notebooks'] })
    return result
  },

  updateSnapshot: async (folderId, notebookId) => {
    await ApiService.updateSnapshot(folderId, notebookId)
    await get().fetchFolderNotebooks(folderId)
  },

  clearFolders: () => {
    set({
      folders: [],
      activeFolderId: null,
      folderMembers: [],
      folderNotebooks: [],
      folderDashboards: [],
      folderError: null,
    })
  },
})
