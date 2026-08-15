import { useState, useEffect } from 'react'
import { Button } from './ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from './ui/dialog'
import { Input } from './ui/input'
import { Label } from './ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select'
import { Loader2, Eye, EyeOff, LogIn, Check } from 'lucide-react'
import { type LLMConnectionCreateRequest } from '../services/api'
import { PROVIDER_CONFIGS, type LLMProvider } from '../types/llm'
import { useCreateLLMConnection } from '../hooks/useLLMConnections'
import { ModelInputList } from './ModelInputList'
import { ClaudeOAuthDialog } from './ClaudeOAuthDialog'
import { useClaudeOAuthStatus } from '../hooks/useClaudeOAuthStatus'

interface LLMConfigProps {
  trigger: React.ReactNode
  onSuccess?: () => void
  className?: string
  existingProviderTypes?: Set<string>
}

export function LLMConfig({ trigger, onSuccess, className = "", existingProviderTypes = new Set() }: LLMConfigProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [selectedProvider, setSelectedProvider] = useState<LLMProvider>('openai')
  const [connectionName, setConnectionName] = useState<string>('')
  const [config, setConfig] = useState<Record<string, any>>({})
  const [showPasswords, setShowPasswords] = useState<Record<string, boolean>>({})

  // Claude OAuth state
  const [showClaudeOAuthDialog, setShowClaudeOAuthDialog] = useState(false)
  const claudeOAuth = useClaudeOAuthStatus()

  const createMutation = useCreateLLMConnection()

  // Check Claude OAuth status on mount and when dialog closes
  useEffect(() => {
    if (isOpen) {
      claudeOAuth.checkStatus()
    }
  }, [isOpen, showClaudeOAuthDialog])

  const resetForm = () => {
    setSelectedProvider('openai')
    setConnectionName('')
    setConfig({})
    setShowPasswords({})
  }

  const togglePasswordVisibility = (fieldName: string) => {
    setShowPasswords(prev => ({
      ...prev,
      [fieldName]: !prev[fieldName]
    }))
  }

  const handleCreateConnection = async () => {
    const connectionData: LLMConnectionCreateRequest = {
      type: selectedProvider,
      name: connectionName || undefined,
      config: config
    }

    createMutation.mutate(connectionData, {
      onSuccess: () => {
        setIsOpen(false)
        resetForm()
        if (onSuccess) {
          onSuccess()
        }
      }
    })
  }

  return (
    <>
      <Dialog open={isOpen} onOpenChange={(open) => {
        if (!open && createMutation.isPending) return
        if (!open) resetForm()
        setIsOpen(open)
      }}>
        <DialogTrigger asChild className={className}>
          {trigger}
        </DialogTrigger>
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

          {/* Special handling for Claude Code - show OAuth button */}
          {selectedProvider === 'claude_code' && (
            <div className="p-4 bg-[#1a1a1a] rounded-md border border-[#555555]">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <Label className="text-white">Authentication Status</Label>
                  <p className="text-xs text-gray-400 mt-1">
                    Connect your Claude Pro or Max subscription
                  </p>
                </div>
                {claudeOAuth.authenticated ? (
                  <div className="flex items-center gap-2 text-green-400">
                    <Check className="w-4 h-4" />
                    <span className="text-sm">Authenticated</span>
                  </div>
                ) : (
                  <div className="text-yellow-400 text-sm">Not authenticated</div>
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
                {claudeOAuth.authenticated ? 'Re-authenticate' : 'Authenticate with Claude'}
              </Button>

              {!claudeOAuth.authenticated && (
                <p className="text-xs text-gray-500 mt-2 text-center">
                  You'll be redirected to claude.ai to authorize access
                </p>
              )}
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
                setIsOpen(false)
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
                (selectedProvider === 'claude_code' && !claudeOAuth.authenticated)
              }
              className={`${
                createMutation.isPending ||
                (selectedProvider === 'claude_code' && !claudeOAuth.authenticated)
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

    {/* Claude OAuth Dialog */}
    <ClaudeOAuthDialog
      open={showClaudeOAuthDialog}
      onOpenChange={setShowClaudeOAuthDialog}
      onSuccess={() => {
        claudeOAuth.checkStatus()
        setShowClaudeOAuthDialog(false)
      }}
    />
    </>
  )
}
