import { useEffect, useState } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog'
import {
  Share2,
  Copy,
  Trash2,
  ExternalLink,
  Loader2,
  Check,
  Lock,
  Unlock,
  Eye,
  EyeOff,
  Layout,
  FileJson,
  Pencil,
  FolderOpen,
  CheckCircle,
} from 'lucide-react'
import { ApiService } from '../services/api'
import { openExternalUrl, copyToClipboard, isTauriApp } from '../lib/tauri-api'
import type { DashboardFolder, NotebookFolder } from '../types/folder'
import { showToast } from '../utils/toast'

// Base URL for notebook share links (same domain as dashboard shares)
const NOTEBOOK_SHARE_BASE_URL = 'https://www.byaan.ai/n'

// Helper to construct full notebook share URL
const getNotebookShareUrl = (shareId: string) => `${NOTEBOOK_SHARE_BASE_URL}/${shareId}`

interface Share {
  id: string
  share_url?: string
  created_at: string
  updated_at?: string
  has_password?: boolean
  password?: string | null
}

type TabType = 'dashboard' | 'notebook'

interface ShareModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  notebookId: string
  dashboardId?: string
  version: number
  onShareDashboardToFolder?: () => void
  onShareNotebookToFolder?: () => void
  canShareExternally?: boolean
}

export default function ShareModal({ open, onOpenChange, notebookId, dashboardId, version, onShareDashboardToFolder, onShareNotebookToFolder, canShareExternally = true }: ShareModalProps) {
  const isDesktop = isTauriApp()
  const [activeTab, setActiveTab] = useState<TabType>('dashboard')

  // Dashboard (single share) state
  const [dashboardShare, setDashboardShare] = useState<Share | null>(null)
  const [isLoadingDashboard, setIsLoadingDashboard] = useState(false)
  const [isCreatingDashboard, setIsCreatingDashboard] = useState(false)
  const [isDeletingDashboard, setIsDeletingDashboard] = useState(false)
  const [isDashboardCopied, setIsDashboardCopied] = useState(false)
  const [isDashboardPasswordCopied, setIsDashboardPasswordCopied] = useState(false)
  const [showDashboardSharePassword, setShowDashboardSharePassword] = useState(false)
  const [editingDashboardPassword, setEditingDashboardPassword] = useState(false)
  const [dashboardEditPassword, setDashboardEditPassword] = useState('')
  const [isUpdatingDashboardPassword, setIsUpdatingDashboardPassword] = useState(false)

  // Notebook (multiple shares) state
  const [notebookShares, setNotebookShares] = useState<Share[]>([])
  const [isLoadingNotebook, setIsLoadingNotebook] = useState(false)
  const [isCreatingNotebook, setIsCreatingNotebook] = useState(false)
  const [deletingNotebookId, setDeletingNotebookId] = useState<string | null>(null)
  const [copiedNotebookId, setCopiedNotebookId] = useState<string | null>(null)
  const [copiedNotebookPasswordId, setCopiedNotebookPasswordId] = useState<string | null>(null)
  const [visiblePasswordIds, setVisiblePasswordIds] = useState<Set<string>>(new Set())
  const [editingPasswordShareId, setEditingPasswordShareId] = useState<string | null>(null)
  const [editPassword, setEditPassword] = useState('')
  const [isUpdatingPassword, setIsUpdatingPassword] = useState(false)

  // Shared state
  const [error, setError] = useState<string | null>(null)
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [enablePassword, setEnablePassword] = useState(false)

  // Folder share state
  const [dashboardFolderShares, setDashboardFolderShares] = useState<DashboardFolder[]>([])
  const [notebookFolderShares, setNotebookFolderShares] = useState<NotebookFolder[]>([])
  const [updatingFolderId, setUpdatingFolderId] = useState<string | null>(null)

  // Load data when modal opens
  useEffect(() => {
    if (open && notebookId) {
      loadDashboardShare()
      if (!isDesktop) loadNotebookShares()
      if (!isDesktop && onShareNotebookToFolder) loadNotebookFolderShares()
      if (onShareDashboardToFolder) loadDashboardFolderShares()
    }
  }, [open, notebookId])

  // Reset state when switching tabs
  useEffect(() => {
    setPassword('')
    setEnablePassword(false)
    setShowPassword(false)
    setError(null)
  }, [activeTab])

  // =====================
  // Dashboard Tab Functions
  // =====================

  const loadDashboardShare = async () => {
    setIsLoadingDashboard(true)
    setError(null)
    try {
      const response = await ApiService.getNotebookShare(notebookId)
      if (response.success && response.data) {
        setDashboardShare(response.data.share)
      }
    } catch (err) {
      console.error('Error loading dashboard share:', err)
    } finally {
      setIsLoadingDashboard(false)
    }
  }

  const handleCreateOrUpdateDashboardShare = async () => {
    setIsCreatingDashboard(true)
    setError(null)
    try {
      const passwordToUse = enablePassword && password.trim() ? password.trim() : undefined
      const updatePassword = enablePassword && !password.trim() ? true : undefined

      const response = await ApiService.shareNotebook(notebookId, version, passwordToUse, updatePassword)
      if (response.success && response.data) {
        try {
          await copyToClipboard(response.data.share_url)
          setIsDashboardCopied(true)
          setTimeout(() => setIsDashboardCopied(false), 2000)
        } catch (clipboardErr) {
          console.error('Failed to copy to clipboard:', clipboardErr)
        }

        setPassword('')
        setEnablePassword(false)
        await loadDashboardShare()
      }
    } catch (err) {
      setError('Failed to share')
      console.error('Error sharing:', err)
    } finally {
      setIsCreatingDashboard(false)
    }
  }

  const handleCopyDashboardUrl = async () => {
    if (!dashboardShare?.share_url) return
    try {
      await copyToClipboard(dashboardShare.share_url)
      setIsDashboardCopied(true)
      setTimeout(() => setIsDashboardCopied(false), 2000)
    } catch (err) {
      console.error('Failed to copy:', err)
    }
  }

  const handleCopyDashboardPassword = async () => {
    if (!dashboardShare?.password) return
    try {
      await copyToClipboard(dashboardShare.password)
      setIsDashboardPasswordCopied(true)
      setTimeout(() => setIsDashboardPasswordCopied(false), 2000)
    } catch (err) {
      console.error('Failed to copy password:', err)
    }
  }

  const handleDeleteDashboardShare = async () => {
    setIsDeletingDashboard(true)
    setError(null)
    try {
      await ApiService.deleteShare(notebookId)
      setDashboardShare(null)
      setShowDashboardSharePassword(false)
    } catch (err) {
      setError('Failed to delete share')
      console.error('Error deleting share:', err)
    } finally {
      setIsDeletingDashboard(false)
    }
  }

  const handleOpenDashboardPasswordEdit = () => {
    setEditingDashboardPassword(true)
    setDashboardEditPassword('')
  }

  const handleCancelDashboardPasswordEdit = () => {
    setEditingDashboardPassword(false)
    setDashboardEditPassword('')
  }

  const handleSaveDashboardPassword = async () => {
    setIsUpdatingDashboardPassword(true)
    setError(null)
    try {
      const passwordToUse = dashboardEditPassword.trim() || undefined
      const updatePassword = !passwordToUse ? true : undefined

      await ApiService.shareNotebook(notebookId, version, passwordToUse, updatePassword)
      setEditingDashboardPassword(false)
      setDashboardEditPassword('')
      await loadDashboardShare()
    } catch (err) {
      setError('Failed to update password')
      console.error('Error updating dashboard password:', err)
    } finally {
      setIsUpdatingDashboardPassword(false)
    }
  }

  const handleRemoveDashboardPassword = async () => {
    setIsUpdatingDashboardPassword(true)
    setError(null)
    try {
      await ApiService.shareNotebook(notebookId, version, undefined, true)
      await loadDashboardShare()
    } catch (err) {
      setError('Failed to remove password')
      console.error('Error removing dashboard password:', err)
    } finally {
      setIsUpdatingDashboardPassword(false)
    }
  }

  // =====================
  // Notebook Tab Functions
  // =====================

  const loadNotebookShares = async () => {
    setIsLoadingNotebook(true)
    try {
      const response = await ApiService.listNotebookJsonShares(notebookId)
      if (response.success && response.data) {
        setNotebookShares(response.data.shares || [])
      }
    } catch (err) {
      console.error('Error loading notebook shares:', err)
    } finally {
      setIsLoadingNotebook(false)
    }
  }

  const loadDashboardFolderShares = async () => {
    if (!notebookId) return
    try {
      const response = await ApiService.getNotebookDashboardFolders(notebookId)
      setDashboardFolderShares(response.items || [])
    } catch (err) {
      console.error('Error loading dashboard folder shares:', err)
    }
  }

  const loadNotebookFolderShares = async () => {
    try {
      const response = await ApiService.getNotebookFolders(notebookId)
      setNotebookFolderShares(response.items || [])
    } catch (err) {
      console.error('Error loading notebook folder shares:', err)
    }
  }

  const handleCreateNotebookShare = async () => {
    setIsCreatingNotebook(true)
    setError(null)
    try {
      const passwordToUse = enablePassword && password.trim() ? password.trim() : undefined
      const response = await ApiService.shareNotebookJson(notebookId, passwordToUse)
      if (response.success && response.data) {
        setPassword('')
        setEnablePassword(false)

        try {
          const shareUrl = getNotebookShareUrl(response.data.share_id)
          await copyToClipboard(shareUrl)
          setCopiedNotebookId(response.data.share_id)
          setTimeout(() => setCopiedNotebookId(null), 2000)
        } catch (clipboardErr) {
          console.error('Failed to copy to clipboard:', clipboardErr)
        }

        await loadNotebookShares()
      }
    } catch (err) {
      setError('Failed to create share')
      console.error('Error creating notebook share:', err)
    } finally {
      setIsCreatingNotebook(false)
    }
  }

  const handleDeleteNotebookShare = async (shareId: string) => {
    setDeletingNotebookId(shareId)
    setError(null)
    try {
      await ApiService.deleteNotebookJsonShare(notebookId, shareId)
      setNotebookShares((prev) => prev.filter((s) => s.id !== shareId))
    } catch (err) {
      setError('Failed to delete share')
      console.error('Error deleting notebook share:', err)
    } finally {
      setDeletingNotebookId(null)
    }
  }

  const handleCopyNotebookShareId = async (share: Share) => {
    try {
      const shareUrl = getNotebookShareUrl(share.id)
      await copyToClipboard(shareUrl)
      setCopiedNotebookId(share.id)
      setTimeout(() => setCopiedNotebookId(null), 2000)
    } catch (err) {
      console.error('Failed to copy:', err)
    }
  }

  const handleCopyNotebookPassword = async (share: Share) => {
    if (!share.password) return
    try {
      await copyToClipboard(share.password)
      setCopiedNotebookPasswordId(share.id)
      setTimeout(() => setCopiedNotebookPasswordId(null), 2000)
    } catch (err) {
      console.error('Failed to copy password:', err)
    }
  }

  const toggleNotebookPasswordVisibility = (shareId: string) => {
    setVisiblePasswordIds((prev) => {
      const newSet = new Set(prev)
      if (newSet.has(shareId)) {
        newSet.delete(shareId)
      } else {
        newSet.add(shareId)
      }
      return newSet
    })
  }

  const handleOpenPasswordEdit = (shareId: string) => {
    setEditingPasswordShareId(shareId)
    setEditPassword('')
  }

  const handleCancelPasswordEdit = () => {
    setEditingPasswordShareId(null)
    setEditPassword('')
  }

  const handleSaveNotebookPassword = async (shareId: string) => {
    setIsUpdatingPassword(true)
    setError(null)
    try {
      await ApiService.updateNotebookJsonSharePassword(notebookId, shareId, editPassword.trim() || null)
      setEditingPasswordShareId(null)
      setEditPassword('')
      await loadNotebookShares()
    } catch (err) {
      setError('Failed to update password')
      console.error('Error updating notebook share password:', err)
    } finally {
      setIsUpdatingPassword(false)
    }
  }

  const handleRemoveNotebookPassword = async (shareId: string) => {
    setIsUpdatingPassword(true)
    setError(null)
    try {
      await ApiService.updateNotebookJsonSharePassword(notebookId, shareId, null)
      await loadNotebookShares()
    } catch (err) {
      setError('Failed to remove password')
      console.error('Error removing notebook share password:', err)
    } finally {
      setIsUpdatingPassword(false)
    }
  }

  // =====================
  // Shared Functions
  // =====================

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr)
    return date.toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  const isLoading = activeTab === 'dashboard' ? isLoadingDashboard : isLoadingNotebook
  const isCreating = activeTab === 'dashboard' ? isCreatingDashboard : isCreatingNotebook

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md bg-[#1a1a1a] border-[#404040] max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="text-white flex items-center gap-2">
            <Share2 className="w-4 h-4" />
            Share
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 flex-1 overflow-hidden flex flex-col">
          {/* Tab Switcher — hidden in desktop (Tauri) since notebook share is web-only */}
          {!isDesktop && (
            <div className="flex gap-2">
              <button
                onClick={() => setActiveTab('dashboard')}
                className={`flex-1 px-3 py-2 text-sm font-medium rounded-lg transition-colors flex items-center justify-center gap-2 ${
                  activeTab === 'dashboard'
                    ? 'bg-brand-orange text-white'
                    : 'bg-[#252525] text-gray-400 hover:text-white hover:bg-[#333]'
                }`}
              >
                <Layout className="w-4 h-4" />
                Dashboard
              </button>
              <button
                onClick={() => setActiveTab('notebook')}
                className={`flex-1 px-3 py-2 text-sm font-medium rounded-lg transition-colors flex items-center justify-center gap-2 ${
                  activeTab === 'notebook'
                    ? 'bg-brand-orange text-white'
                    : 'bg-[#252525] text-gray-400 hover:text-white hover:bg-[#333]'
                }`}
              >
                <FileJson className="w-4 h-4" />
                Notebook
              </button>
            </div>
          )}

          {/* Tab Description */}
          {!isDesktop && (
            <p className="text-xs text-gray-500">
              {activeTab === 'dashboard'
                ? 'Share the current dashboard view as a standalone HTML page.'
                : 'Share the complete notebook including chat history, datasets, and all versions.'}
            </p>
          )}

          {/* Loading state */}
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-6 h-6 text-gray-400 animate-spin" />
            </div>
          ) : activeTab === 'dashboard' ? (
            // =====================
            // DASHBOARD TAB CONTENT
            // =====================
            <>
              {/* Current share display (if exists) - only for external sharing */}
              {canShareExternally && dashboardShare && (
                <div className="p-4 bg-[#252525] rounded-lg border border-[#333]">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-medium text-white">Current Share</h3>
                    {dashboardShare.has_password && (
                      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-xs bg-brand-orange/20 text-brand-orange rounded">
                        <Lock className="w-3 h-3" />
                        Protected
                      </span>
                    )}
                  </div>

                  {/* Share URL */}
                  <div className="flex items-center gap-2 mb-3">
                    <input
                      readOnly
                      value={dashboardShare.share_url || ''}
                      className="flex-1 px-3 py-2 text-sm bg-[#1a1a1a] border border-[#404040] rounded-lg text-gray-300 truncate"
                    />
                    <button
                      onClick={() => dashboardShare.share_url && openExternalUrl(dashboardShare.share_url)}
                      className="p-2 text-gray-400 hover:text-white hover:bg-[#333] rounded-lg transition-colors"
                      title="Open in browser"
                    >
                      <ExternalLink className="w-4 h-4" />
                    </button>
                    <button
                      onClick={handleCopyDashboardUrl}
                      className="p-2 text-gray-400 hover:text-white hover:bg-[#333] rounded-lg transition-colors"
                      title="Copy link"
                    >
                      {isDashboardCopied ? (
                        <Check className="w-4 h-4 text-green-400" />
                      ) : (
                        <Copy className="w-4 h-4" />
                      )}
                    </button>
                  </div>

                  {/* Password management section */}
                  <div className="mb-3 pt-3 border-t border-[#333]">
                    {editingDashboardPassword ? (
                      // Password edit form
                      <div className="space-y-2">
                        <div className="relative">
                          <input
                            type="text"
                            value={dashboardEditPassword}
                            onChange={(e) => setDashboardEditPassword(e.target.value)}
                            placeholder={dashboardShare.has_password ? 'New password (empty to remove)' : 'Enter password'}
                            className="w-full px-3 py-1.5 text-xs bg-[#1a1a1a] border border-[#404040] rounded text-white placeholder-gray-500 focus:outline-none focus:border-brand-orange"
                            autoFocus
                            disabled={isUpdatingDashboardPassword}
                          />
                        </div>
                        <div className="flex gap-2">
                          <button
                            onClick={handleSaveDashboardPassword}
                            disabled={isUpdatingDashboardPassword}
                            className="flex-1 px-2 py-1 text-xs font-medium bg-brand-orange hover:bg-brand-orange-hover text-white rounded transition-colors disabled:opacity-50 flex items-center justify-center gap-1"
                          >
                            {isUpdatingDashboardPassword ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Save'}
                          </button>
                          <button
                            onClick={handleCancelDashboardPasswordEdit}
                            disabled={isUpdatingDashboardPassword}
                            className="px-2 py-1 text-xs text-gray-400 hover:text-white hover:bg-[#333] rounded transition-colors disabled:opacity-50"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : dashboardShare.has_password && dashboardShare.password ? (
                      // Password display with edit/remove buttons
                      <div className="space-y-2">
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-gray-500">Password:</span>
                          <code className="flex-1 text-xs text-gray-300 bg-[#1a1a1a] px-2 py-1 rounded font-mono">
                            {showDashboardSharePassword ? dashboardShare.password : '••••••••'}
                          </code>
                          <button
                            onClick={() => setShowDashboardSharePassword(!showDashboardSharePassword)}
                            className="p-1 text-gray-400 hover:text-white hover:bg-[#333] rounded transition-colors"
                            title={showDashboardSharePassword ? 'Hide password' : 'Show password'}
                          >
                            {showDashboardSharePassword ? (
                              <EyeOff className="w-3.5 h-3.5" />
                            ) : (
                              <Eye className="w-3.5 h-3.5" />
                            )}
                          </button>
                          <button
                            onClick={handleCopyDashboardPassword}
                            className="p-1 text-gray-400 hover:text-white hover:bg-[#333] rounded transition-colors"
                            title="Copy password"
                          >
                            {isDashboardPasswordCopied ? (
                              <Check className="w-3.5 h-3.5 text-green-400" />
                            ) : (
                              <Copy className="w-3.5 h-3.5" />
                            )}
                          </button>
                        </div>
                        <div className="flex gap-2">
                          <button
                            onClick={handleOpenDashboardPasswordEdit}
                            disabled={isUpdatingDashboardPassword}
                            className="text-xs text-gray-400 hover:text-white flex items-center gap-1 transition-colors"
                          >
                            <Pencil className="w-3 h-3" />
                            Change
                          </button>
                          <button
                            onClick={handleRemoveDashboardPassword}
                            disabled={isUpdatingDashboardPassword}
                            className="text-xs text-gray-400 hover:text-red-400 flex items-center gap-1 transition-colors"
                          >
                            {isUpdatingDashboardPassword ? <Loader2 className="w-3 h-3 animate-spin" /> : <Unlock className="w-3 h-3" />}
                            Remove
                          </button>
                        </div>
                      </div>
                    ) : (
                      // No password - show add button
                      <button
                        onClick={handleOpenDashboardPasswordEdit}
                        disabled={isUpdatingDashboardPassword}
                        className="text-xs text-gray-400 hover:text-brand-orange flex items-center gap-1 transition-colors"
                      >
                        <Lock className="w-3 h-3" />
                        Add password
                      </button>
                    )}
                  </div>

                  {/* Last updated timestamp */}
                  <p className="text-xs text-gray-500">
                    {dashboardShare.updated_at
                      ? `Last updated: ${formatDate(dashboardShare.updated_at)}`
                      : `Created: ${formatDate(dashboardShare.created_at)}`}
                  </p>
                </div>
              )}

              {/* Create/Update share section - only for external sharing */}
              {canShareExternally && (
                <div className="p-4 bg-[#252525] rounded-lg border border-[#333]">
                  <h3 className="text-sm font-medium text-white mb-3">
                    {dashboardShare ? 'Update Share' : 'Create Share'}
                  </h3>

                  {/* Version indicator */}
                  <p className="text-xs text-gray-400 mb-3">
                    Sharing version {version} of this dashboard.
                    {dashboardShare && dashboardShare.has_password && !enablePassword && ' Current password will be kept.'}
                  </p>

                  {/* Password protection toggle */}
                  <label className="flex items-center gap-3 cursor-pointer mb-3">
                    <input
                      type="checkbox"
                      checked={enablePassword}
                      onChange={(e) => {
                        setEnablePassword(e.target.checked)
                        if (!e.target.checked) setPassword('')
                      }}
                      className="w-4 h-4 rounded border-[#505050] bg-[#1a1a1a] text-brand-orange focus:ring-brand-orange focus:ring-offset-0 accent-brand-orange cursor-pointer"
                      disabled={isCreating}
                    />
                    <span className="text-sm text-gray-400 flex items-center gap-1.5">
                      <Lock className="w-3.5 h-3.5" />
                      {dashboardShare?.has_password ? 'Change password' : 'Password protect'}
                    </span>
                  </label>

                  {/* Password input */}
                  {enablePassword && (
                    <div className="mb-3">
                      <div className="relative">
                        <input
                          type={showPassword ? 'text' : 'password'}
                          value={password}
                          onChange={(e) => setPassword(e.target.value)}
                          placeholder={
                            dashboardShare?.has_password
                              ? 'Enter new password (leave empty to remove)'
                              : 'Enter password'
                          }
                          className="w-full px-3 py-2 pr-10 text-sm bg-[#1a1a1a] border border-[#404040] rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-brand-orange transition-colors"
                          disabled={isCreating}
                          autoFocus
                        />
                        <button
                          type="button"
                          onClick={() => setShowPassword(!showPassword)}
                          className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-500 hover:text-gray-300 transition-colors"
                        >
                          {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                        </button>
                      </div>
                      {dashboardShare?.has_password && (
                        <p className="text-xs text-gray-500 mt-1">Leave empty to remove password protection</p>
                      )}
                    </div>
                  )}

                  {/* Share/Update button */}
                  <button
                    onClick={handleCreateOrUpdateDashboardShare}
                    disabled={isCreating}
                    className="w-full px-4 py-2.5 text-sm font-medium bg-brand-orange hover:bg-brand-orange-hover text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                  >
                    {isCreating ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        {dashboardShare ? 'Updating...' : 'Creating...'}
                      </>
                    ) : (
                      <>
                        <Share2 className="w-4 h-4" />
                        {dashboardShare ? 'Update Share' : 'Share Dashboard'}
                      </>
                    )}
                  </button>
                </div>
              )}

              {/* Delete share button (only if share exists) - only for external sharing */}
              {canShareExternally && dashboardShare && (
                <button
                  onClick={handleDeleteDashboardShare}
                  disabled={isDeletingDashboard}
                  className="w-full px-4 py-2 text-sm text-red-400 hover:text-red-300 hover:bg-red-400/10 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  {isDeletingDashboard ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Removing...
                    </>
                  ) : (
                    <>
                      <Trash2 className="w-4 h-4" />
                      Remove Share Link
                    </>
                  )}
                </button>
              )}

              {/* Share dashboard to folder button */}
              {onShareDashboardToFolder && (
                <div className="pt-3 border-t border-[#333]">
                  <button
                    onClick={() => {
                      onOpenChange(false)
                      onShareDashboardToFolder()
                    }}
                    className={`w-full px-4 py-2.5 text-sm font-medium rounded-lg transition-colors flex items-center justify-center gap-2 ${
                      dashboardFolderShares.length > 0
                        ? 'bg-green-900/20 hover:bg-green-900/30 text-green-400 border border-green-900/30'
                        : 'bg-[#252525] hover:bg-[#333] text-white border border-[#404040]'
                    }`}
                  >
                    {dashboardFolderShares.length > 0 ? (
                      <CheckCircle className="w-4 h-4" />
                    ) : (
                      <FolderOpen className="w-4 h-4" />
                    )}
                    Share Dashboard to Folder
                    {dashboardFolderShares.length > 0 && (
                      <span className="text-xs bg-green-900/30 px-1.5 py-0.5 rounded">
                        {dashboardFolderShares.length}
                      </span>
                    )}
                  </button>
                  {dashboardFolderShares.length > 0 ? (
                    <div className="mt-3 space-y-2">
                      <p className="text-xs text-gray-400 text-center">Shared to:</p>
                      {dashboardFolderShares.map((share) => {
                        const isOutdated = share.shared_version !== null && share.shared_version !== undefined && share.shared_version < version
                        const isUpdating = updatingFolderId === share.folder_id
                        return (
                          <div key={share.folder_id} className="flex items-center justify-between px-3 py-2 bg-[#1a1a1a] rounded-lg">
                            <div className="flex items-center gap-2">
                              <span className="text-sm text-green-400">{share.folder_name}</span>
                              <span className="text-xs text-gray-500">(v{share.shared_version ?? '?'})</span>
                            </div>
                            {isOutdated && dashboardId && (
                              <button
                                onClick={async () => {
                                  try {
                                    setUpdatingFolderId(share.folder_id)
                                    await ApiService.shareDashboardToFolder(share.folder_id, dashboardId)
                                    showToast.success(`Updated to v${version}`)
                                    loadDashboardFolderShares()
                                  } catch {
                                    showToast.error('Failed to update')
                                  } finally {
                                    setUpdatingFolderId(null)
                                  }
                                }}
                                disabled={isUpdating}
                                className="text-xs text-brand-orange hover:text-brand-orange/80 transition-colors disabled:opacity-50 flex items-center gap-1"
                              >
                                {isUpdating ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
                                Update to v{version}
                              </button>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  ) : (
                    <p className="text-xs text-gray-500 mt-2 text-center">
                      Share this dashboard with folder members for collaboration.
                    </p>
                  )}
                </div>
              )}
            </>
          ) : (
            // =====================
            // NOTEBOOK TAB CONTENT
            // =====================
            <>
              {/* Create new share section - only for external sharing */}
              {canShareExternally && (
                <div className="p-4 bg-[#252525] rounded-lg border border-[#333]">
                  <h3 className="text-sm font-medium text-white mb-3">Create New Share</h3>

                  {/* Password protection toggle */}
                  <label className="flex items-center gap-3 cursor-pointer mb-3">
                    <input
                      type="checkbox"
                      checked={enablePassword}
                      onChange={(e) => {
                        setEnablePassword(e.target.checked)
                        if (!e.target.checked) setPassword('')
                      }}
                      className="w-4 h-4 rounded border-[#505050] bg-[#1a1a1a] text-brand-orange focus:ring-brand-orange focus:ring-offset-0 accent-brand-orange cursor-pointer"
                      disabled={isCreating}
                    />
                    <span className="text-sm text-gray-400 flex items-center gap-1.5">
                      <Lock className="w-3.5 h-3.5" />
                      Password protect
                    </span>
                  </label>

                  {/* Password input */}
                  {enablePassword && (
                    <div className="mb-3">
                      <div className="relative">
                        <input
                          type={showPassword ? 'text' : 'password'}
                          value={password}
                          onChange={(e) => setPassword(e.target.value)}
                          placeholder="Enter password"
                          className="w-full px-3 py-2 pr-10 text-sm bg-[#1a1a1a] border border-[#404040] rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-brand-orange transition-colors"
                          disabled={isCreating}
                          autoFocus
                        />
                        <button
                          type="button"
                          onClick={() => setShowPassword(!showPassword)}
                          className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-500 hover:text-gray-300 transition-colors"
                        >
                          {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Share button */}
                  <button
                    onClick={handleCreateNotebookShare}
                    disabled={isCreating || (enablePassword && !password.trim())}
                    className="w-full px-4 py-2.5 text-sm font-medium bg-brand-orange hover:bg-brand-orange-hover text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                  >
                    {isCreating ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        Creating...
                      </>
                    ) : (
                      <>
                        <Share2 className="w-4 h-4" />
                        Share Notebook
                      </>
                    )}
                  </button>
                </div>
              )}

              {/* Shared Links section - only for external sharing */}
              {canShareExternally && (
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-medium text-white">Shared Links</h3>
                  <span className="text-xs text-gray-500">
                    {notebookShares.length} {notebookShares.length === 1 ? 'link' : 'links'}
                  </span>
                </div>
              )}

              {canShareExternally && notebookShares.length === 0 ? (
                <div className="text-center py-6 text-gray-500 text-sm">No shares yet. Create one above.</div>
              ) : canShareExternally && (
                <div className="space-y-2 overflow-y-auto flex-1 pr-1 scrollbar-thin scrollbar-thumb-[#404040] scrollbar-track-transparent">
                  {notebookShares.map((share) => (
                    <div key={share.id} className="p-3 bg-[#252525] rounded-lg border border-[#404040]">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          {share.has_password ? (
                            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-xs bg-brand-orange/20 text-brand-orange rounded">
                              <Lock className="w-3 h-3" />
                              Protected
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-xs bg-gray-600/20 text-gray-400 rounded">
                              <Unlock className="w-3 h-3" />
                              Public
                            </span>
                          )}
                        </div>
                        <button
                          onClick={() => handleDeleteNotebookShare(share.id)}
                          disabled={deletingNotebookId === share.id}
                          className="p-1.5 text-gray-400 hover:text-red-400 hover:bg-[#333] rounded transition-colors disabled:opacity-50"
                          title="Delete"
                        >
                          {deletingNotebookId === share.id ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                          ) : (
                            <Trash2 className="w-4 h-4" />
                          )}
                        </button>
                      </div>
                      {/* Share URL */}
                      <div className="flex items-center gap-2">
                        <input
                          readOnly
                          value={getNotebookShareUrl(share.id)}
                          className="flex-1 px-2 py-1.5 text-xs bg-[#1a1a1a] border border-[#404040] rounded text-gray-300 truncate font-mono"
                        />
                        <button
                          onClick={() => openExternalUrl(getNotebookShareUrl(share.id))}
                          className="p-1.5 text-gray-400 hover:text-white hover:bg-[#333] rounded transition-colors"
                          title="Open in browser"
                        >
                          <ExternalLink className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleCopyNotebookShareId(share)}
                          className="p-1.5 text-gray-400 hover:text-white hover:bg-[#333] rounded transition-colors"
                          title="Copy link"
                        >
                          {copiedNotebookId === share.id ? (
                            <Check className="w-4 h-4 text-green-400" />
                          ) : (
                            <Copy className="w-4 h-4" />
                          )}
                        </button>
                      </div>
                      <p className="text-xs text-gray-500 mt-1">{formatDate(share.created_at)}</p>

                      {/* Password management section */}
                      <div className="mt-2 pt-2 border-t border-[#333]">
                        {editingPasswordShareId === share.id ? (
                          // Password edit form
                          <div className="space-y-2">
                            <div className="relative">
                              <input
                                type="text"
                                value={editPassword}
                                onChange={(e) => setEditPassword(e.target.value)}
                                placeholder={share.has_password ? 'New password (empty to remove)' : 'Enter password'}
                                className="w-full px-3 py-1.5 text-xs bg-[#1a1a1a] border border-[#404040] rounded text-white placeholder-gray-500 focus:outline-none focus:border-brand-orange"
                                autoFocus
                                disabled={isUpdatingPassword}
                              />
                            </div>
                            <div className="flex gap-2">
                              <button
                                onClick={() => handleSaveNotebookPassword(share.id)}
                                disabled={isUpdatingPassword}
                                className="flex-1 px-2 py-1 text-xs font-medium bg-brand-orange hover:bg-brand-orange-hover text-white rounded transition-colors disabled:opacity-50 flex items-center justify-center gap-1"
                              >
                                {isUpdatingPassword ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Save'}
                              </button>
                              <button
                                onClick={handleCancelPasswordEdit}
                                disabled={isUpdatingPassword}
                                className="px-2 py-1 text-xs text-gray-400 hover:text-white hover:bg-[#333] rounded transition-colors disabled:opacity-50"
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        ) : share.has_password && share.password ? (
                          // Password display with edit/remove buttons
                          <div className="space-y-2">
                            <div className="flex items-center gap-2">
                              <span className="text-xs text-gray-500">Password:</span>
                              <code className="flex-1 text-xs text-gray-300 bg-[#1a1a1a] px-2 py-1 rounded font-mono">
                                {visiblePasswordIds.has(share.id) ? share.password : '••••••••'}
                              </code>
                              <button
                                onClick={() => toggleNotebookPasswordVisibility(share.id)}
                                className="p-1 text-gray-400 hover:text-white hover:bg-[#333] rounded transition-colors"
                                title={visiblePasswordIds.has(share.id) ? 'Hide password' : 'Show password'}
                              >
                                {visiblePasswordIds.has(share.id) ? (
                                  <EyeOff className="w-3.5 h-3.5" />
                                ) : (
                                  <Eye className="w-3.5 h-3.5" />
                                )}
                              </button>
                              <button
                                onClick={() => handleCopyNotebookPassword(share)}
                                className="p-1 text-gray-400 hover:text-white hover:bg-[#333] rounded transition-colors"
                                title="Copy password"
                              >
                                {copiedNotebookPasswordId === share.id ? (
                                  <Check className="w-3.5 h-3.5 text-green-400" />
                                ) : (
                                  <Copy className="w-3.5 h-3.5" />
                                )}
                              </button>
                            </div>
                            <div className="flex gap-2">
                              <button
                                onClick={() => handleOpenPasswordEdit(share.id)}
                                disabled={isUpdatingPassword}
                                className="text-xs text-gray-400 hover:text-white flex items-center gap-1 transition-colors"
                              >
                                <Pencil className="w-3 h-3" />
                                Change
                              </button>
                              <button
                                onClick={() => handleRemoveNotebookPassword(share.id)}
                                disabled={isUpdatingPassword}
                                className="text-xs text-gray-400 hover:text-red-400 flex items-center gap-1 transition-colors"
                              >
                                {isUpdatingPassword ? <Loader2 className="w-3 h-3 animate-spin" /> : <Unlock className="w-3 h-3" />}
                                Remove
                              </button>
                            </div>
                          </div>
                        ) : (
                          // No password - show add button
                          <button
                            onClick={() => handleOpenPasswordEdit(share.id)}
                            disabled={isUpdatingPassword}
                            className="text-xs text-gray-400 hover:text-brand-orange flex items-center gap-1 transition-colors"
                          >
                            <Lock className="w-3 h-3" />
                            Add password
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Share notebook to folder button */}
              {onShareNotebookToFolder && (
                <div className="pt-3 border-t border-[#333]">
                  <button
                    onClick={() => {
                      onOpenChange(false)
                      onShareNotebookToFolder()
                    }}
                    className={`w-full px-4 py-2.5 text-sm font-medium rounded-lg transition-colors flex items-center justify-center gap-2 ${
                      notebookFolderShares.length > 0
                        ? 'bg-green-900/20 hover:bg-green-900/30 text-green-400 border border-green-900/30'
                        : 'bg-[#252525] hover:bg-[#333] text-white border border-[#404040]'
                    }`}
                  >
                    {notebookFolderShares.length > 0 ? (
                      <CheckCircle className="w-4 h-4" />
                    ) : (
                      <FolderOpen className="w-4 h-4" />
                    )}
                    Share Notebook to Folder
                    {notebookFolderShares.length > 0 && (
                      <span className="text-xs bg-green-900/30 px-1.5 py-0.5 rounded">
                        {notebookFolderShares.length}
                      </span>
                    )}
                  </button>
                  {notebookFolderShares.length > 0 ? (
                    <p className="text-xs text-green-400/70 mt-2 text-center">
                      Shared to: {notebookFolderShares.map(f => f.folder_name).join(', ')}
                    </p>
                  ) : (
                    <p className="text-xs text-gray-500 mt-2 text-center">
                      Share this notebook with folder members for collaboration.
                    </p>
                  )}
                </div>
              )}
            </>
          )}

          {/* Error message */}
          {error && (
            <div className="text-red-400 text-sm text-center bg-red-400/10 py-2 px-3 rounded-lg">{error}</div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
