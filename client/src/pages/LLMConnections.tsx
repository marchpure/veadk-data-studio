import { useState, useEffect, useMemo } from 'react'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'
import { Card } from '../components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select'
import { Trash2, Loader2, Eye, EyeOff, Search, Pencil, LogIn, Check, Zap, Lock, Copy, Info } from 'lucide-react'
import { type LLMConnection, type LLMConnectionCreateRequest } from '../services/api'
import { PROVIDER_CONFIGS, type LLMProvider } from '../types/llm'
import { useStore } from '../stores/useStore'
import { useLLMConnections, useCreateLLMConnection, useUpdateLLMConnection, useDeleteLLMConnection } from '../hooks/useLLMConnections'
import { ModelInputList } from '../components/ModelInputList'
import { ClaudeOAuthDialog } from '../components/ClaudeOAuthDialog'
import { CodexOAuthDialog } from '../components/CodexOAuthDialog'
import { useClaudeOAuthStatus } from '../hooks/useClaudeOAuthStatus'
import { useCodexOAuthStatus } from '../hooks/useCodexOAuthStatus'
import { useScopes } from '../hooks/useScopes'

type CodexTokensLike =
  | { access_token?: unknown; refresh_token?: unknown; expires_at?: unknown }
  | null
  | undefined

const buildCleanedConfig = (
  provider: LLMProvider,
  cfg: Record<string, unknown>,
  codexTokens: CodexTokensLike
): Record<string, unknown> => {
  const out: Record<string, unknown> = { ...cfg }
  if ((provider === 'azure' || provider === 'bedrock') && Array.isArray(out.models)) {
    out.models = (out.models as unknown[]).filter(
      (m): m is string => typeof m === 'string' && m.trim().length > 0
    )
  }
  if (provider === 'claude_code') {
    out.use_claude_code_auth = true
  }
  if (provider === 'codex' && codexTokens) {
    out.access_token = codexTokens.access_token
    out.refresh_token = codexTokens.refresh_token
    out.expires_at = codexTokens.expires_at
  }
  return out
}

const stableStringify = (v: unknown): string =>
  JSON.stringify(v, (_, val) =>
    val && typeof val === 'object' && !Array.isArray(val)
      ? Object.fromEntries(
          Object.keys(val as Record<string, unknown>)
            .sort()
            .map(k => [k, (val as Record<string, unknown>)[k]])
        )
      : val
  )

export default function LLMConnectionsPage() {
  const { canCreateLLMConnection, canEditLLMConnection, canDeleteLLMConnection } = useScopes()
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [showEditDialog, setShowEditDialog] = useState(false)
  const [editingConnection, setEditingConnection] = useState<LLMConnection | null>(null)

  // Delete confirmation state
  const [deleteDialogOpen, setDeleteDialogOpen] = useState<boolean>(false)
  const [connectionToDelete, setConnectionToDelete] = useState<LLMConnection | null>(null)
  const [searchQuery, setSearchQuery] = useState('')

  // Form state for create and edit dialogs
  const [selectedProvider, setSelectedProvider] = useState<LLMProvider>('openai')
  const [connectionName, setConnectionName] = useState<string>('')
  const [config, setConfig] = useState<Record<string, any>>({})

  const [originalSnapshot, setOriginalSnapshot] = useState<{
    name: string
    type: LLMProvider
    config: Record<string, unknown>
  } | null>(null)

  // Password visibility state
  const [showPasswords, setShowPasswords] = useState<Record<string, boolean>>({})

  // Claude OAuth state
  const [showClaudeOAuthDialog, setShowClaudeOAuthDialog] = useState(false)
  const claudeOAuth = useClaudeOAuthStatus()
  const { checkStatus: checkClaudeOAuthStatus } = claudeOAuth

  // Codex OAuth state
  const [showCodexOAuthDialog, setShowCodexOAuthDialog] = useState(false)
  const codexOAuth = useCodexOAuthStatus()

  // Claude auth method toggle (oauth vs token)
  const [selectedAuthMethod, setSelectedAuthMethod] = useState<'oauth' | 'token'>('oauth')
  const [tokenInput, setTokenInput] = useState('')
  const [tokenError, setTokenError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [showTokenInput, setShowTokenInput] = useState(false)

  // Check Claude OAuth status on mount and when dialog closes
  useEffect(() => {
    checkClaudeOAuthStatus()
  }, [showClaudeOAuthDialog, checkClaudeOAuthStatus])

  // Sync selectedAuthMethod with actual auth status
  useEffect(() => {
    if (claudeOAuth.authMethod) {
      setSelectedAuthMethod(claudeOAuth.authMethod as 'oauth' | 'token')
    }
  }, [claudeOAuth.authMethod])

  const handleSaveToken = async () => {
    if (!tokenInput.trim()) {
      setTokenError('Please enter a token')
      return
    }
    setTokenError(null)
    const result = await claudeOAuth.saveToken(tokenInput.trim())
    if (result.success) {
      setTokenInput('')
      setShowTokenInput(false)
    } else {
      setTokenError(result.error || 'Failed to save token')
    }
  }

  const copyCommand = async () => {
    try {
      await navigator.clipboard.writeText('claude setup-token')
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Ignore copy errors
    }
  }
  
  // Use React Query hooks
  const { data: connections = [], isLoading: loading, error } = useLLMConnections()
  const createMutation = useCreateLLMConnection()
  const updateMutation = useUpdateLLMConnection()
  const deleteMutation = useDeleteLLMConnection()
  
  // Use Zustand store
  const { llmConnections } = useStore()

  // Get existing provider types to prevent duplicates
  const existingProviderTypes = new Set(
    (connections.length > 0 ? connections : llmConnections).map(c => c.type)
  )

  const getBadgeVariant = (type: string): "openai" | "azure" | "groq" | "openrouter" | "claude_code" | "default" => {
    switch (type) {
      case 'openai':
      case 'codex':
        return 'openai'
      case 'azure':
        return 'azure'
      case 'groq':
        return 'groq'
      case 'openrouter':
        return 'openrouter'
      case 'claude_code':
        return 'claude_code'
      case 'xai':
        return 'default'
      default:
        return 'default'
    }
  }

  const formatProviderName = (type: string) => {
    const providerConfig = PROVIDER_CONFIGS[type as LLMProvider]
    return providerConfig?.displayName || type
  }

  const formatTimeAgo = (dateString: string): string => {
    const date = new Date(dateString)
    const now = new Date()
    const diffInMs = now.getTime() - date.getTime()
    const diffInMinutes = Math.floor(diffInMs / (1000 * 60))
    const diffInHours = Math.floor(diffInMs / (1000 * 60 * 60))
    const diffInDays = Math.floor(diffInMs / (1000 * 60 * 60 * 24))
    const diffInMonths = Math.floor(diffInDays / 30)
    const diffInYears = Math.floor(diffInDays / 365)

    if (diffInMinutes < 1) return 'just now'
    if (diffInMinutes < 60) return `${diffInMinutes} minute${diffInMinutes > 1 ? 's' : ''} ago`
    if (diffInHours < 24) return `${diffInHours} hour${diffInHours > 1 ? 's' : ''} ago`
    if (diffInDays < 30) return `${diffInDays} day${diffInDays > 1 ? 's' : ''} ago`
    if (diffInMonths < 12) return `${diffInMonths} month${diffInMonths > 1 ? 's' : ''} ago`
    return `${diffInYears} year${diffInYears > 1 ? 's' : ''} ago`
  }

  // Use either React Query data or store data with search filtering
  const displayConnections = (connections.length > 0 ? connections : llmConnections)
    .filter(conn => {
      if (!searchQuery) return true
      const query = searchQuery.toLowerCase()
      return (
        (conn.name || '').toLowerCase().includes(query) ||
        formatProviderName(conn.type).toLowerCase().includes(query)
      )
    })
    .sort((a, b) =>
      new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    )

  const handleCreateConnection = async () => {
    const cleanedConfig = buildCleanedConfig(selectedProvider, config, codexOAuth.tokens)

    const connectionData: LLMConnectionCreateRequest = {
      type: selectedProvider,
      name: connectionName || undefined,
      config: cleanedConfig
    }

    createMutation.mutate(connectionData, {
      onSuccess: () => {
        setShowCreateDialog(false)
        resetForm()
        codexOAuth.reset()
      }
    })
  }

  const resetForm = () => {
    // Select first available (non-connected) provider
    const availableProvider = Object.values(PROVIDER_CONFIGS).find(
      p => !existingProviderTypes.has(p.name)
    )
    setSelectedProvider((availableProvider?.name || 'openai') as LLMProvider)
    setConnectionName('')
    setConfig({})
    setShowPasswords({})
    setShowTokenInput(false)
    setTokenInput('')
    setTokenError(null)
  }

  const togglePasswordVisibility = (fieldName: string) => {
    setShowPasswords(prev => ({
      ...prev,
      [fieldName]: !prev[fieldName]
    }))
  }

  const handleUpdateConnection = async () => {
    if (!editingConnection) return

    const cleanedConfig = buildCleanedConfig(selectedProvider, config, codexOAuth.tokens)

    const connectionData: LLMConnectionCreateRequest = {
      type: selectedProvider,
      name: connectionName || undefined,
      config: cleanedConfig
    }

    updateMutation.mutate(
      { id: editingConnection.id, data: connectionData },
      {
        onSuccess: () => {
          setShowEditDialog(false)
          setEditingConnection(null)
          setOriginalSnapshot(null)
          resetForm()
        }
      }
    )
  }

  const hasChanges = useMemo(() => {
    if (!editingConnection || !originalSnapshot) return false
    const current = {
      name: connectionName || '',
      type: selectedProvider,
      config: buildCleanedConfig(selectedProvider, config, codexOAuth.tokens),
    }
    const original = {
      name: originalSnapshot.name,
      type: originalSnapshot.type,
      config: buildCleanedConfig(originalSnapshot.type, originalSnapshot.config, codexOAuth.tokens),
    }
    return stableStringify(current) !== stableStringify(original)
  }, [editingConnection, originalSnapshot, connectionName, selectedProvider, config, codexOAuth.tokens])

  const handleEditClick = (connection: LLMConnection) => {
    setEditingConnection(connection)
    setSelectedProvider(connection.type as LLMProvider)
    setConnectionName(connection.name || '')
    const initialConfig =
      typeof structuredClone === 'function'
        ? structuredClone(connection.config)
        : JSON.parse(JSON.stringify(connection.config))
    setConfig(initialConfig)
    setOriginalSnapshot({
      name: connection.name || '',
      type: connection.type as LLMProvider,
      config: typeof structuredClone === 'function'
        ? structuredClone(connection.config)
        : JSON.parse(JSON.stringify(connection.config)),
    })
    setShowEditDialog(true)
  }

  const handleDeleteClick = (connection: LLMConnection, event: React.MouseEvent) => {
    event.stopPropagation() // Prevent any parent click handlers
    setConnectionToDelete(connection)
    setDeleteDialogOpen(true)
  }

  const confirmDelete = () => {
    if (!connectionToDelete) return
    
    deleteMutation.mutate(connectionToDelete.id, {
      onSuccess: () => {
        setDeleteDialogOpen(false)
        setConnectionToDelete(null)
      },
    })
  }

  const cancelDelete = () => {
    setDeleteDialogOpen(false)
    setConnectionToDelete(null)
  }

  return (
    <div className="bg-[#0d0d0d] w-full h-full flex flex-col">
      {/* Header Section */}
      <div className="w-full px-8 pt-[50px] pb-8">
        <div className="max-w-[850px] mx-auto">
          {/* Title and Button */}
          <div className="flex items-center justify-between mb-8">
            <h1 className="text-2xl font-bold text-white tracking-tight">AI Models</h1>
            {canCreateLLMConnection && (
              <Button
                onClick={() => {
                  // Select first available provider when opening dialog
                  const availableProvider = Object.values(PROVIDER_CONFIGS).find(
                    p => !existingProviderTypes.has(p.name)
                  )
                  if (availableProvider) {
                    setSelectedProvider(availableProvider.name as LLMProvider)
                  }
                  setShowCreateDialog(true)
                }}
                variant="brand-primary"
                disabled={createMutation.isPending || updateMutation.isPending || deleteMutation.isPending}
                className="font-medium px-5 py-2.5 rounded-md text-sm"
              >
                + New connection
              </Button>
            )}
          </div>

          {/* Search Bar */}
          <div className="relative">
            <Search className="absolute left-4 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-500" />
            <Input
              type="text"
              placeholder="Search AI models..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-12 pr-4 py-6 bg-transparent border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-gray-600 focus:ring-0"
            />
          </div>
        </div>
      </div>

      {/* Scrollable Content Section */}
      <div className="flex-1 overflow-y-auto custom-scrollbar min-h-0">
        <div className="w-full px-8 pb-6">
          {/* Error Message */}
          {error && (
            <div className="bg-red-900/20 border border-red-500 text-red-400 px-4 py-3 rounded-md mb-6">
              {error.message || 'An error occurred'}
            </div>
          )}

          {/* Loading State */}
          {loading ? (
            <div className="text-center py-12">
              <div className="animate-spin w-8 h-8 border-2 border-brand-orange border-t-transparent rounded-full mx-auto mb-4"></div>
              <p className="text-gray-400">Loading LLM connections...</p>
            </div>
          ) : (
            <>
              {/* Empty State */}
              {displayConnections.length === 0 ? (
                <div className="max-w-[850px] mx-auto">
                  <Card className="p-12 text-center bg-[#1a1a1a] border-gray-800">
                    <div className="max-w-md mx-auto">
                      <div className="w-16 h-16 bg-brand-orange/10 rounded-full flex items-center justify-center mx-auto mb-4">
                        <svg className="w-8 h-8 text-brand-orange" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                        </svg>
                      </div>
                      <h3 className="text-xl font-semibold text-white mb-2">No LLM Connections</h3>
                      <p className="text-gray-400 mb-6">
                        Get started by adding your first AI model connection. You can connect to OpenAI, Anthropic, OpenRouter, Azure, or AWS Bedrock.
                      </p>
                    </div>
                  </Card>
                </div>
              ) : (
                <>
                  {/* Connection Cards */}
                  <div className="max-w-[850px] mx-auto grid grid-cols-1 md:grid-cols-2 gap-6">
                    {displayConnections.map(connection => {
                      const timeAgo = formatTimeAgo(connection.created_at)
                      return (
                        <Card key={connection.id} className="p-6 bg-[#1a1a1a] border-gray-800 hover:border-gray-700 transition-colors">
                          <div className="flex items-start justify-between mb-3">
                            <div className="flex-1">
                              {/* Connection Name and Provider Badge */}
                              <div className="flex items-center gap-3 mb-2">
                                <h3 className="text-lg font-normal text-white">
                                  {connection.name || `${formatProviderName(connection.type)} Connection`}
                                </h3>
                                <Badge variant={getBadgeVariant(connection.type)}>
                                  {formatProviderName(connection.type)}
                                </Badge>
                              </div>

                              {/* Description */}
                              <p className="text-sm text-gray-400 mb-3">
                                AI model connection for {formatProviderName(connection.type)}
                              </p>

                              {/* Timestamp */}
                              <p className="text-xs text-gray-500">
                                Updated {timeAgo}
                              </p>
                            </div>

                            {/* Action Buttons */}
                            <div className="flex gap-2 ml-4">
                              {canEditLLMConnection(connection.created_by) && (
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  onClick={() => handleEditClick(connection)}
                                  disabled={updateMutation.isPending || deleteMutation.isPending}
                                  className="text-gray-400 hover:text-white hover:bg-gray-800"
                                >
                                  <Pencil className="w-4 h-4" />
                                </Button>
                              )}
                              {canDeleteLLMConnection(connection.created_by) && (
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  onClick={(e) => handleDeleteClick(connection, e)}
                                  disabled={updateMutation.isPending || deleteMutation.isPending}
                                  className="text-gray-400 hover:text-red-400 hover:bg-gray-800"
                                >
                                  <Trash2 className="w-4 h-4" />
                                </Button>
                              )}
                            </div>
                          </div>
                        </Card>
                      )
                    })}
                  </div>
                </>
              )}
            </>
          )}
        </div>
      </div>

        {/* Create Dialog */}
        <Dialog open={showCreateDialog} onOpenChange={(open) => {
          if (!open && createMutation.isPending) return
          if (!open) resetForm()
          setShowCreateDialog(open)
        }}>
          <DialogContent className="max-w-lg bg-[#2a2a2a] border-[#444444]">
            <DialogHeader>
              <DialogTitle className="text-white">Add LLM Connection</DialogTitle>
            </DialogHeader>

            <div className="space-y-3">
              <div>
                <Label className="text-white">Select LLM Provider</Label>
                <div className="mt-2 grid grid-cols-3 gap-3">
                  {Object.values(PROVIDER_CONFIGS).map(provider => {
                    const isAlreadyConnected = existingProviderTypes.has(provider.name)
                    return (
                      <div
                        key={provider.name}
                        onClick={() => !isAlreadyConnected && setSelectedProvider(provider.name as LLMProvider)}
                        className={`flex flex-col items-center justify-center p-2 rounded-md border transition-all ${
                          isAlreadyConnected
                            ? 'border-[#333333] bg-[#1a1a1a] cursor-not-allowed opacity-50'
                            : selectedProvider === provider.name
                              ? 'border-brand-orange bg-brand-orange/10 cursor-pointer'
                              : 'border-[#555555] hover:border-[#777777] hover:bg-[#333333] cursor-pointer'
                        }`}
                      >
                        <span className={`text-sm font-medium ${isAlreadyConnected ? 'text-gray-500' : 'text-white'}`}>
                          {provider.displayName}
                        </span>
                        {isAlreadyConnected && (
                          <span className="text-xs text-gray-500 mt-1">Connected</span>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>

              <div>
                <Label htmlFor="connection-name" className="text-white">
                  Connection Name
                </Label>
                <Input
                  id="connection-name"
                  type="text"
                  placeholder="e.g., My OpenAI Connection"
                  value={connectionName}
                  onChange={(e) => setConnectionName(e.target.value)}
                  className="mt-1 bg-[#1a1a1a] border-[#555555] text-white"
                />
                <p className="text-xs text-gray-400 mt-1">Optional: Give this connection a custom name</p>
              </div>

              {/* Special handling for Claude Code - show auth method toggle */}
              {selectedProvider === 'claude_code' && (
                <div className="space-y-4">
                  {/* Auth Method Toggle */}
                  <div>
                    <Label className="text-white mb-2 block">Authentication Method</Label>
                    <div className="grid grid-cols-2 gap-2">
                      <button
                        type="button"
                        onClick={() => setSelectedAuthMethod('oauth')}
                        className={`flex items-center gap-2 p-3 rounded-md border transition-all ${
                          selectedAuthMethod === 'oauth'
                            ? 'border-brand-orange bg-brand-orange/10'
                            : 'border-[#555555] hover:border-[#777777] hover:bg-[#333333]'
                        }`}
                      >
                        <Zap className="w-4 h-4 text-yellow-400" />
                        <div className="text-left">
                          <span className="text-sm font-medium text-white block">Quick OAuth</span>
                          <span className="text-xs text-gray-400">(Expires daily)</span>
                        </div>
                      </button>
                      <button
                        type="button"
                        onClick={() => setSelectedAuthMethod('token')}
                        className={`flex items-center gap-2 p-3 rounded-md border transition-all ${
                          selectedAuthMethod === 'token'
                            ? 'border-brand-orange bg-brand-orange/10'
                            : 'border-[#555555] hover:border-[#777777] hover:bg-[#333333]'
                        }`}
                      >
                        <Lock className="w-4 h-4 text-blue-400" />
                        <div className="text-left">
                          <span className="text-sm font-medium text-white block">Long-term Token</span>
                          <span className="text-xs text-gray-400">(Lasts 1 year)</span>
                        </div>
                      </button>
                    </div>
                  </div>

                  {/* OAuth Section */}
                  {selectedAuthMethod === 'oauth' && (
                    <div className="p-4 bg-[#1a1a1a] rounded-md border border-[#555555]">
                      <div className="flex items-center justify-between mb-3">
                        <div>
                          <Label className="text-white">Authentication Status</Label>
                          <p className="text-xs text-gray-400 mt-1">
                            Quick & easy setup. Token expires daily.
                          </p>
                        </div>
                        {claudeOAuth.authenticated ? (
                          <div className="flex items-center gap-1.5 px-2.5 py-1 bg-green-500/10 border border-green-500/30 rounded-md">
                            <Check className="w-3.5 h-3.5 text-green-400" />
                            <span className="text-xs font-medium text-green-400">Authorized</span>
                          </div>
                        ) : (
                          <div className="flex items-center gap-1.5 px-2.5 py-1 bg-gray-500/10 border border-gray-500/30 rounded-md">
                            <span className="text-xs font-medium text-gray-400">Not Authorized</span>
                          </div>
                        )}
                      </div>

                      <Button
                        type="button"
                        onClick={() => setShowClaudeOAuthDialog(true)}
                        variant={claudeOAuth.authenticated ? "outline" : "default"}
                        className={claudeOAuth.authenticated
                          ? "w-full border-[#555555] text-white hover:bg-[#3a3a3a]"
                          : "w-full bg-brand-orange hover:bg-brand-orange/90"
                        }
                      >
                        <LogIn className="w-4 h-4 mr-2" />
                        {claudeOAuth.authenticated ? 'Re-authorize Claude' : 'Authenticate with Claude'}
                      </Button>

                      <div className="flex items-start gap-2 mt-3 p-2 bg-[#2a2a2a] rounded">
                        <Info className="w-4 h-4 text-gray-500 mt-0.5 flex-shrink-0" />
                        <p className="text-xs text-gray-500">
                          For longer sessions without daily re-authentication, use Long-term Token method.
                        </p>
                      </div>
                    </div>
                  )}

                  {/* Long-term Token Section */}
                  {selectedAuthMethod === 'token' && (
                    <div className="p-4 bg-[#1a1a1a] rounded-md border border-[#555555]">
                      <div className="flex items-center justify-between mb-3">
                        <div>
                          <Label className="text-white">Long-term Token Setup</Label>
                          <p className="text-xs text-gray-400 mt-1">
                            One-time setup. Token lasts ~1 year.
                          </p>
                        </div>
                        {claudeOAuth.authenticated && claudeOAuth.authMethod === 'token' ? (
                          <div className="flex items-center gap-1.5 px-2.5 py-1 bg-green-500/10 border border-green-500/30 rounded-md">
                            <Check className="w-3.5 h-3.5 text-green-400" />
                            <span className="text-xs font-medium text-green-400">Configured</span>
                          </div>
                        ) : (
                          <div className="flex items-center gap-1.5 px-2.5 py-1 bg-gray-500/10 border border-gray-500/30 rounded-md">
                            <span className="text-xs font-medium text-gray-400">Not Configured</span>
                          </div>
                        )}
                      </div>

                      {claudeOAuth.authenticated && claudeOAuth.authMethod === 'token' && !showTokenInput ? (
                        <div className="space-y-3">
                          <p className="text-sm text-gray-400">
                            Your long-term token is configured and active.
                          </p>
                          <Button
                            type="button"
                            onClick={() => {
                              setTokenInput('')
                              setTokenError(null)
                              setShowTokenInput(true)
                            }}
                            variant="outline"
                            className="w-full border-[#555555] text-white hover:bg-[#3a3a3a]"
                          >
                            Update Token
                          </Button>
                        </div>
                      ) : (
                        <div className="space-y-3">
                          <div>
                            <p className="text-xs text-gray-400 mb-2">Step 1: Run this command in terminal:</p>
                            <div className="flex items-center gap-2">
                              <code className="flex-1 p-2 bg-[#2a2a2a] rounded text-sm text-gray-300 font-mono">
                                claude setup-token
                              </code>
                              <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                onClick={copyCommand}
                                className="border-[#555555] text-white hover:bg-[#3a3a3a] px-2"
                              >
                                {copied ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
                              </Button>
                            </div>
                          </div>

                          <div>
                            <p className="text-xs text-gray-400 mb-2">Step 2: Paste the token here:</p>
                            <Input
                              type="password"
                              placeholder="Paste your token here..."
                              value={tokenInput}
                              onChange={(e) => {
                                setTokenInput(e.target.value)
                                setTokenError(null)
                              }}
                              className="bg-[#2a2a2a] border-[#555555] text-white"
                            />
                          </div>

                          {tokenError && (
                            <div className="p-2 bg-red-900/20 border border-red-500/30 rounded">
                              <p className="text-xs text-red-400">{tokenError}</p>
                            </div>
                          )}

                          <Button
                            type="button"
                            onClick={handleSaveToken}
                            disabled={!tokenInput.trim() || claudeOAuth.savingToken}
                            className="w-full bg-brand-orange hover:bg-brand-orange/90 disabled:bg-gray-600"
                          >
                            {claudeOAuth.savingToken && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                            Save Token
                          </Button>

                          <p className="text-xs text-gray-500 text-center">
                            Requires Claude Pro or Max subscription
                          </p>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* Special handling for Codex - show OAuth */}
              {selectedProvider === 'codex' && (
                <div className="p-4 bg-[#1a1a1a] rounded-md border border-[#555555]">
                  <div className="flex items-center justify-between mb-3">
                    <div>
                      <Label className="text-white">Authentication Status</Label>
                      <p className="text-xs text-gray-400 mt-1">
                        Authenticate with your ChatGPT Plus/Pro subscription.
                      </p>
                    </div>
                    {codexOAuth.authenticated ? (
                      <div className="flex items-center gap-1.5 px-2.5 py-1 bg-green-500/10 border border-green-500/30 rounded-md">
                        <Check className="w-3.5 h-3.5 text-green-400" />
                        <span className="text-xs font-medium text-green-400">Authorized</span>
                      </div>
                    ) : (
                      <div className="flex items-center gap-1.5 px-2.5 py-1 bg-gray-500/10 border border-gray-500/30 rounded-md">
                        <span className="text-xs font-medium text-gray-400">Not Authorized</span>
                      </div>
                    )}
                  </div>

                  <Button
                    type="button"
                    onClick={() => setShowCodexOAuthDialog(true)}
                    variant={codexOAuth.authenticated ? "outline" : "default"}
                    className={codexOAuth.authenticated
                      ? "w-full border-[#555555] text-white hover:bg-[#3a3a3a]"
                      : "w-full bg-brand-orange hover:bg-brand-orange/90"
                    }
                  >
                    <LogIn className="w-4 h-4 mr-2" />
                    {codexOAuth.authenticated ? 'Re-authorize OpenAI' : 'Authenticate with OpenAI'}
                  </Button>
                </div>
              )}

              {PROVIDER_CONFIGS[selectedProvider].fields.map(field => {
                // Skip checkbox fields for claude_code - OAuth handled separately
                if (selectedProvider === 'claude_code' && field.type === 'checkbox') {
                  return null
                }

                return (
                <div key={field.name}>
                  {/* Special handling for checkbox fields */}
                  {field.type === 'checkbox' ? (
                    <div className="flex items-start space-x-3 p-3 bg-[#1a1a1a] rounded-md border border-[#555555]">
                      <input
                        type="checkbox"
                        id={field.name}
                        checked={config[field.name] || false}
                        onChange={(e) => setConfig({...config, [field.name]: e.target.checked})}
                        className="mt-1 h-4 w-4 rounded border-gray-600 text-brand-orange focus:ring-brand-orange focus:ring-offset-0 bg-[#2a2a2a]"
                      />
                      <div className="flex-1">
                        <Label htmlFor={field.name} className="text-white cursor-pointer">
                          {field.label}
                        </Label>
                        {field.description && (
                          <p className="text-xs text-gray-400 mt-1">{field.description}</p>
                        )}
                      </div>
                    </div>
                  ) :
                  /* Special handling for models field in Azure/Bedrock */
                  field.name === 'models' && (selectedProvider === 'azure' || selectedProvider === 'bedrock') ? (
                    <ModelInputList
                      models={Array.isArray(config[field.name]) ? config[field.name] : (config[field.name] ? [config[field.name]] : [''])}
                      onChange={(models) => {
                        // Don't filter here - allow empty strings so user can add fields
                        setConfig({...config, [field.name]: models})
                      }}
                      label={field.label}
                      placeholder={field.placeholder}
                      description={field.description}
                    />
                  ) : (
                    <>
                      <Label htmlFor={field.name} className="text-white">
                        {field.label} {field.required && <span className="text-red-400">*</span>}
                      </Label>
                      {field.type === 'password' ? (
                        <div className="relative">
                          <Input
                            id={field.name}
                            type={showPasswords[field.name] ? "text" : "password"}
                            placeholder={field.placeholder}
                            value={config[field.name] || ''}
                            onChange={(e) => setConfig({...config, [field.name]: e.target.value})}
                            className="mt-1 bg-[#1a1a1a] border-[#555555] text-white pr-10"
                          />
                          {config[field.name] && (
                            <button
                              type="button"
                              onClick={() => togglePasswordVisibility(field.name)}
                              className="absolute right-3 top-1/2 transform -translate-y-1/2 text-[#aaaaaa] hover:text-white transition-colors"
                            >
                              {showPasswords[field.name] ? (
                                <EyeOff className="h-4 w-4" />
                              ) : (
                                <Eye className="h-4 w-4" />
                              )}
                            </button>
                          )}
                        </div>
                      ) : field.type === 'select' ? (
                        <Select
                          value={config[field.name] || ''}
                          onValueChange={(value) => setConfig({...config, [field.name]: value})}
                        >
                          <SelectTrigger className="mt-1 bg-[#1a1a1a] border-[#555555] text-white">
                            <SelectValue placeholder={`Select ${field.label.toLowerCase()}`} />
                          </SelectTrigger>
                          <SelectContent className="bg-[#2a2a2a] border-[#555555]">
                            {field.options?.map(option => (
                              <SelectItem key={option.value} value={option.value}>
                                {option.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      ) : (
                        <Input
                          id={field.name}
                          type={field.type}
                          placeholder={field.placeholder}
                          value={config[field.name] || ''}
                          onChange={(e) => setConfig({...config, [field.name]: e.target.value})}
                          className="mt-1 bg-[#1a1a1a] border-[#555555] text-white"
                        />
                      )}
                    </>
                  )}
                </div>
              );
              })}

              <div className="flex justify-end gap-2 pt-4">
                <Button
                  variant="outline"
                  onClick={() => {
                    setShowCreateDialog(false)
                    resetForm()
                  }}
                  disabled={createMutation.isPending}
                  className="border-[#555555] text-white hover:bg-[#3a3a3a]"
                >
                  Cancel
                </Button>
                <Button
                  onClick={handleCreateConnection}
                  disabled={
                    createMutation.isPending ||
                    (selectedProvider === 'claude_code' && !claudeOAuth.authenticated) ||
                    (selectedProvider === 'codex' && !codexOAuth.authenticated)
                  }
                  className={`${
                    createMutation.isPending ||
                    (selectedProvider === 'claude_code' && !claudeOAuth.authenticated) ||
                    (selectedProvider === 'codex' && !codexOAuth.authenticated)
                      ? 'bg-gray-500 cursor-not-allowed'
                      : 'bg-brand-orange hover:bg-brand-orange/90'
                  } flex items-center gap-2`}
                >
                  {createMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
                  Create Connection
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>

        {/* Edit Dialog */}
        <Dialog open={showEditDialog} onOpenChange={(open) => {
          if (!open && updateMutation.isPending) return
          if (!open) {
            resetForm()
            setEditingConnection(null)
            setOriginalSnapshot(null)
          }
          setShowEditDialog(open)
        }}>
          <DialogContent className="max-w-lg bg-[#2a2a2a] border-[#444444]">
            <DialogHeader>
              <DialogTitle className="text-white">Edit LLM Connection</DialogTitle>
            </DialogHeader>

              {/* Informational box */}
              <div className="p-3 bg-[#1a1a1a] rounded-md border border-[#555555]">
                <p className="text-sm text-[#aaaaaa]">
                  Update your AI model connection. Provide the required (*) fields to modify your LLM.
                </p>
              </div>

            <div className="space-y-3">
              <div>
                <Label className="text-white">Select LLM Provider <span className="text-red-400">*</span></Label>
                <div className="mt-2 grid grid-cols-3 gap-3">
                  {Object.values(PROVIDER_CONFIGS).map(provider => (
                    <div
                      key={provider.name}
                      onClick={() => setSelectedProvider(provider.name as LLMProvider)}
                      className={`flex items-center justify-center p-2 cursor-pointer rounded-md border transition-all ${
                        selectedProvider === provider.name
                          ? 'border-brand-orange bg-brand-orange/10'
                          : 'border-[#555555] hover:border-[#777777] hover:bg-[#333333]'
                      }`}
                    >
                      <span className="text-sm font-medium text-white">{provider.displayName}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <Label htmlFor="connection-name-edit" className="text-white">
                  Connection Name
                </Label>
                <Input
                  id="connection-name-edit"
                  type="text"
                  placeholder="e.g., My OpenAI Connection"
                  value={connectionName}
                  onChange={(e) => setConnectionName(e.target.value)}
                  className="mt-1 bg-[#1a1a1a] border-[#555555] text-white"
                />
                <p className="text-xs text-gray-400 mt-1">Optional: Give this connection a custom name</p>
              </div>

              {/* Special handling for Claude Code - show auth method toggle */}
              {selectedProvider === 'claude_code' && (
                <div className="space-y-4">
                  {/* Auth Method Toggle */}
                  <div>
                    <Label className="text-white mb-2 block">Authentication Method</Label>
                    <div className="grid grid-cols-2 gap-2">
                      <button
                        type="button"
                        onClick={() => setSelectedAuthMethod('oauth')}
                        className={`flex items-center gap-2 p-3 rounded-md border transition-all ${
                          selectedAuthMethod === 'oauth'
                            ? 'border-brand-orange bg-brand-orange/10'
                            : 'border-[#555555] hover:border-[#777777] hover:bg-[#333333]'
                        }`}
                      >
                        <Zap className="w-4 h-4 text-yellow-400" />
                        <div className="text-left">
                          <span className="text-sm font-medium text-white block">Quick OAuth</span>
                          <span className="text-xs text-gray-400">(Expires daily)</span>
                        </div>
                      </button>
                      <button
                        type="button"
                        onClick={() => setSelectedAuthMethod('token')}
                        className={`flex items-center gap-2 p-3 rounded-md border transition-all ${
                          selectedAuthMethod === 'token'
                            ? 'border-brand-orange bg-brand-orange/10'
                            : 'border-[#555555] hover:border-[#777777] hover:bg-[#333333]'
                        }`}
                      >
                        <Lock className="w-4 h-4 text-blue-400" />
                        <div className="text-left">
                          <span className="text-sm font-medium text-white block">Long-term Token</span>
                          <span className="text-xs text-gray-400">(Lasts 1 year)</span>
                        </div>
                      </button>
                    </div>
                  </div>

                  {/* OAuth Section */}
                  {selectedAuthMethod === 'oauth' && (
                    <div className="p-4 bg-[#1a1a1a] rounded-md border border-[#555555]">
                      <div className="flex items-center justify-between mb-3">
                        <div>
                          <Label className="text-white">Authentication Status</Label>
                          <p className="text-xs text-gray-400 mt-1">
                            Quick & easy setup. Token expires daily.
                          </p>
                        </div>
                        {claudeOAuth.authenticated ? (
                          <div className="flex items-center gap-1.5 px-2.5 py-1 bg-green-500/10 border border-green-500/30 rounded-md">
                            <Check className="w-3.5 h-3.5 text-green-400" />
                            <span className="text-xs font-medium text-green-400">Authorized</span>
                          </div>
                        ) : (
                          <div className="flex items-center gap-1.5 px-2.5 py-1 bg-gray-500/10 border border-gray-500/30 rounded-md">
                            <span className="text-xs font-medium text-gray-400">Not Authorized</span>
                          </div>
                        )}
                      </div>

                      <Button
                        type="button"
                        onClick={() => setShowClaudeOAuthDialog(true)}
                        className="w-full bg-[#2a2a2a] hover:bg-[#333333] border border-[#555555] text-white flex items-center justify-center gap-2"
                      >
                        <LogIn className="w-4 h-4" />
                        {claudeOAuth.authenticated ? 'Re-authorize Claude' : 'Authorize Claude'}
                      </Button>

                      <div className="flex items-start gap-2 mt-3 p-2 bg-[#2a2a2a] rounded">
                        <Info className="w-4 h-4 text-gray-500 mt-0.5 flex-shrink-0" />
                        <p className="text-xs text-gray-500">
                          For longer sessions without daily re-authentication, use Long-term Token method.
                        </p>
                      </div>
                    </div>
                  )}

                  {/* Long-term Token Section */}
                  {selectedAuthMethod === 'token' && (
                    <div className="p-4 bg-[#1a1a1a] rounded-md border border-[#555555]">
                      <div className="flex items-center justify-between mb-3">
                        <div>
                          <Label className="text-white">Long-term Token Setup</Label>
                          <p className="text-xs text-gray-400 mt-1">
                            One-time setup. Token lasts ~1 year.
                          </p>
                        </div>
                        {claudeOAuth.authenticated && claudeOAuth.authMethod === 'token' ? (
                          <div className="flex items-center gap-1.5 px-2.5 py-1 bg-green-500/10 border border-green-500/30 rounded-md">
                            <Check className="w-3.5 h-3.5 text-green-400" />
                            <span className="text-xs font-medium text-green-400">Configured</span>
                          </div>
                        ) : (
                          <div className="flex items-center gap-1.5 px-2.5 py-1 bg-gray-500/10 border border-gray-500/30 rounded-md">
                            <span className="text-xs font-medium text-gray-400">Not Configured</span>
                          </div>
                        )}
                      </div>

                      {claudeOAuth.authenticated && claudeOAuth.authMethod === 'token' && !showTokenInput ? (
                        <div className="space-y-3">
                          <p className="text-sm text-gray-400">
                            Your long-term token is configured and active.
                          </p>
                          <Button
                            type="button"
                            onClick={() => {
                              setTokenInput('')
                              setTokenError(null)
                              setShowTokenInput(true)
                            }}
                            variant="outline"
                            className="w-full border-[#555555] text-white hover:bg-[#3a3a3a]"
                          >
                            Update Token
                          </Button>
                        </div>
                      ) : (
                        <div className="space-y-3">
                          <div>
                            <p className="text-xs text-gray-400 mb-2">Step 1: Run this command in terminal:</p>
                            <div className="flex items-center gap-2">
                              <code className="flex-1 p-2 bg-[#2a2a2a] rounded text-sm text-gray-300 font-mono">
                                claude setup-token
                              </code>
                              <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                onClick={copyCommand}
                                className="border-[#555555] text-white hover:bg-[#3a3a3a] px-2"
                              >
                                {copied ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
                              </Button>
                            </div>
                          </div>

                          <div>
                            <p className="text-xs text-gray-400 mb-2">Step 2: Paste the token here:</p>
                            <Input
                              type="password"
                              placeholder="Paste your token here..."
                              value={tokenInput}
                              onChange={(e) => {
                                setTokenInput(e.target.value)
                                setTokenError(null)
                              }}
                              className="bg-[#2a2a2a] border-[#555555] text-white"
                            />
                          </div>

                          {tokenError && (
                            <div className="p-2 bg-red-900/20 border border-red-500/30 rounded">
                              <p className="text-xs text-red-400">{tokenError}</p>
                            </div>
                          )}

                          <Button
                            type="button"
                            onClick={handleSaveToken}
                            disabled={!tokenInput.trim() || claudeOAuth.savingToken}
                            className="w-full bg-brand-orange hover:bg-brand-orange/90 disabled:bg-gray-600"
                          >
                            {claudeOAuth.savingToken && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                            Save Token
                          </Button>

                          <p className="text-xs text-gray-500 text-center">
                            Requires Claude Pro or Max subscription
                          </p>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* Special handling for Codex in edit dialog */}
              {selectedProvider === 'codex' && (
                <div className="p-4 bg-[#1a1a1a] rounded-md border border-[#555555]">
                  <div className="flex items-center justify-between mb-3">
                    <div>
                      <Label className="text-white">Authentication Status</Label>
                      <p className="text-xs text-gray-400 mt-1">
                        Authenticate with your ChatGPT Plus/Pro subscription.
                      </p>
                    </div>
                    {codexOAuth.authenticated ? (
                      <div className="flex items-center gap-1.5 px-2.5 py-1 bg-green-500/10 border border-green-500/30 rounded-md">
                        <Check className="w-3.5 h-3.5 text-green-400" />
                        <span className="text-xs font-medium text-green-400">Authorized</span>
                      </div>
                    ) : (
                      <div className="flex items-center gap-1.5 px-2.5 py-1 bg-gray-500/10 border border-gray-500/30 rounded-md">
                        <span className="text-xs font-medium text-gray-400">Not Authorized</span>
                      </div>
                    )}
                  </div>

                  <Button
                    type="button"
                    onClick={() => setShowCodexOAuthDialog(true)}
                    className="w-full bg-[#2a2a2a] hover:bg-[#333333] border border-[#555555] text-white flex items-center justify-center gap-2"
                  >
                    <LogIn className="w-4 h-4" />
                    {codexOAuth.authenticated ? 'Re-authorize OpenAI' : 'Authorize OpenAI'}
                  </Button>
                </div>
              )}

              {PROVIDER_CONFIGS[selectedProvider].fields.map(field => {
                if (selectedProvider === 'claude_code' && field.type === 'checkbox') {
                  return null
                }

                return (
                <div key={field.name}>
                  {/* Special handling for checkbox fields */}
                  {field.type === 'checkbox' ? (
                    <div className="flex items-start space-x-3 p-3 bg-[#1a1a1a] rounded-md border border-[#555555]">
                      <input
                        type="checkbox"
                        id={`${field.name}-edit`}
                        checked={config[field.name] || false}
                        onChange={(e) => setConfig({...config, [field.name]: e.target.checked})}
                        className="mt-1 h-4 w-4 rounded border-gray-600 text-brand-orange focus:ring-brand-orange focus:ring-offset-0 bg-[#2a2a2a]"
                      />
                      <div className="flex-1">
                        <Label htmlFor={`${field.name}-edit`} className="text-white cursor-pointer">
                          {field.label}
                        </Label>
                        {field.description && (
                          <p className="text-xs text-gray-400 mt-1">{field.description}</p>
                        )}
                      </div>
                    </div>
                  ) :
                  /* Special handling for models field in Azure/Bedrock */
                  field.name === 'models' && (selectedProvider === 'azure' || selectedProvider === 'bedrock') ? (
                    <ModelInputList
                      models={Array.isArray(config[field.name]) ? config[field.name] : (config[field.name] ? [config[field.name]] : [''])}
                      onChange={(models) => {
                        // Don't filter here - allow empty strings so user can add fields
                        setConfig({...config, [field.name]: models})
                      }}
                      label={field.label}
                      placeholder={field.placeholder}
                      description={field.description}
                    />
                  ) : (
                    <>
                      <Label htmlFor={`${field.name}-edit`} className="text-white">
                        {field.label} {field.required && <span className="text-red-400">*</span>}
                      </Label>
                      {field.type === 'password' ? (
                        <div className="relative">
                          <Input
                            id={`${field.name}-edit`}
                            type={showPasswords[field.name] ? "text" : "password"}
                            placeholder={field.placeholder}
                            value={config[field.name] || ''}
                            onChange={(e) => setConfig({...config, [field.name]: e.target.value})}
                            className="mt-1 bg-[#1a1a1a] border-[#555555] text-white pr-10"
                          />
                          {config[field.name] && (
                            <button
                              type="button"
                              onClick={() => togglePasswordVisibility(field.name)}
                              className="absolute right-3 top-1/2 transform -translate-y-1/2 text-[#aaaaaa] hover:text-white transition-colors"
                            >
                              {showPasswords[field.name] ? (
                                <EyeOff className="h-4 w-4" />
                              ) : (
                                <Eye className="h-4 w-4" />
                              )}
                            </button>
                          )}
                        </div>
                      ) : field.type === 'select' ? (
                        <Select
                          value={config[field.name] || ''}
                          onValueChange={(value) => setConfig({...config, [field.name]: value})}
                        >
                          <SelectTrigger className="mt-1 bg-[#1a1a1a] border-[#555555] text-white">
                            <SelectValue placeholder={`Select ${field.label.toLowerCase()}`} />
                          </SelectTrigger>
                          <SelectContent className="bg-[#2a2a2a] border-[#555555]">
                            {field.options?.map(option => (
                              <SelectItem key={option.value} value={option.value}>
                                {option.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      ) : (
                        <Input
                          id={`${field.name}-edit`}
                          type={field.type}
                          placeholder={field.placeholder}
                          value={config[field.name] || ''}
                          onChange={(e) => setConfig({...config, [field.name]: e.target.value})}
                          className="mt-1 bg-[#1a1a1a] border-[#555555] text-white"
                        />
                      )}
                    </>
                  )}
                </div>
              )})}

              <div className="flex justify-end gap-2 pt-4">
                <Button
                  variant="outline"
                  onClick={() => {
                    setShowEditDialog(false)
                    setEditingConnection(null)
                    setOriginalSnapshot(null)
                    resetForm()
                  }}
                  disabled={updateMutation.isPending}
                  className="border-[#555555] text-white hover:bg-[#3a3a3a]"
                >
                  Cancel
                </Button>
                {(() => {
                  const updateDisabled =
                    updateMutation.isPending ||
                    !hasChanges ||
                    (selectedProvider === 'claude_code' && !claudeOAuth.authenticated) ||
                    (selectedProvider === 'codex' && !codexOAuth.authenticated)
                  return (
                    <Button
                      onClick={handleUpdateConnection}
                      disabled={updateDisabled}
                      className={`${
                        updateDisabled
                          ? 'bg-gray-500 cursor-not-allowed'
                          : 'bg-brand-orange hover:bg-brand-orange/90'
                      } flex items-center gap-2`}
                    >
                      {updateMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
                      {updateMutation.isPending ? 'Updating...' : 'Update Connection'}
                    </Button>
                  )
                })()}
              </div>
            </div>
          </DialogContent>
        </Dialog>

        {/* Delete Confirmation Dialog */}
        <Dialog open={deleteDialogOpen} onOpenChange={(open) => {
          if (!open && deleteMutation.isPending) return
          setDeleteDialogOpen(open)
        }}>
          <DialogContent className="max-w-md bg-[#2a2a2a] border-[#444444]">
            <DialogHeader>
              <DialogTitle className="text-white">Delete LLM Connection?</DialogTitle>
            </DialogHeader>
            
            <div className="space-y-4">
              <p className="text-sm text-[#aaaaaa]">
                This action will permanently delete <span className="font-semibold text-white">"{connectionToDelete?.name || `${connectionToDelete?.type} Connection`}"</span> model.
              </p>

              <div className="flex justify-end gap-2 mt-6">
                <Button
                  variant="outline"
                  onClick={cancelDelete}
                  disabled={deleteMutation.isPending}
                  className="border-[#555555] text-white hover:bg-[#3a3a3a]"
                >
                  Cancel
                </Button>
                <Button
                  onClick={confirmDelete}
                  disabled={deleteMutation.isPending}
                  className={`${
                    deleteMutation.isPending
                      ? 'bg-gray-500 cursor-not-allowed'
                      : 'bg-red-800 hover:bg-red-900'
                  } text-white flex items-center gap-2`}
                >
                  {deleteMutation.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Trash2 className="mr-2 h-4 w-4" />
                  )}
                  {deleteMutation.isPending ? 'Deleting...' : 'Delete'}
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>

        {/* Claude OAuth Dialog */}
        <ClaudeOAuthDialog
          open={showClaudeOAuthDialog}
          onOpenChange={setShowClaudeOAuthDialog}
          onSuccess={checkClaudeOAuthStatus}
        />

        {/* Codex OAuth Dialog */}
        <CodexOAuthDialog
          open={showCodexOAuthDialog}
          onOpenChange={setShowCodexOAuthDialog}
          onTokensReceived={(tokens) => codexOAuth.setTokens(tokens)}
        />
      </div>
  )
}