import { useState, useEffect } from 'react'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select'
import { Button } from './ui/button'
import { Badge } from './ui/badge'
import { ApiService, type LLMConnection } from '../services/api'
import { PROVIDER_CONFIGS } from '../types/llm'
import { showToast } from '../utils/toast'

// Removed unused interfaces - ProviderModels and ModelSelectionSelectorProps
// These were likely from an earlier iteration of the component

interface LLMConnectionSelectorProps {
  value?: string
  onValueChange: (connectionId: string | undefined) => void
  placeholder?: string
  allowNone?: boolean
  className?: string
}

export function LLMConnectionSelector({ 
  value, 
  onValueChange, 
  placeholder = "Select AI model...",
  allowNone = true,
  className = ""
}: LLMConnectionSelectorProps) {
  const [connections, setConnections] = useState<LLMConnection[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadConnections()
  }, [])

  const loadConnections = async () => {
    try {
      setLoading(true)
      const response = await ApiService.listLLMConnections()
      setConnections(response.items)
      setError(null)
      
      // Auto-select the first connection if none is selected and we have connections
      if (!value && response.items.length > 0 && !allowNone) {
        onValueChange(response.items[0].id)
      }
    } catch (err) {
      console.error('Error loading LLM connections:', err)
      const errorMessage = 'Failed to load LLM connections'
      setError(errorMessage)
      showToast.error(errorMessage)
    } finally {
      setLoading(false)
    }
  }

  const getDisplayName = (connection: LLMConnection) => {
    const providerConfig = PROVIDER_CONFIGS[connection.type as keyof typeof PROVIDER_CONFIGS]
    const providerName = providerConfig?.displayName || connection.type
    return `${providerName} Connection`
  }

  const getProviderBadge = (type: string) => {
    const providerConfig = PROVIDER_CONFIGS[type as keyof typeof PROVIDER_CONFIGS]
    return providerConfig?.displayName || type
  }

  if (loading) {
    return (
      <div className={`flex items-center justify-center h-10 px-3 py-2 border border-[#404040] rounded-md bg-[#333333] ${className}`}>
        <span className="text-gray-400 text-sm">Loading models...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className={`flex items-center justify-between h-10 px-3 py-2 border border-red-500 rounded-md bg-red-900/20 ${className}`}>
        <span className="text-red-400 text-sm">Failed to load models</span>
        <Button size="sm" variant="ghost" onClick={loadConnections}>
          Retry
        </Button>
      </div>
    )
  }

  if (connections.length === 0) {
    return (
      <div className={`flex items-center justify-between h-10 px-3 py-2 border border-[#404040] rounded-md bg-[#333333] ${className}`}>
        <span className="text-gray-400 text-sm">No AI models configured</span>
        <Button 
          size="sm" 
          variant="ghost"
          onClick={() => window.location.href = '/llm-connections'}
        >
          Add Model
        </Button>
      </div>
    )
  }

  const selectedConnection = connections.find(c => c.id === value)

  return (
    <Select value={value || ''} onValueChange={(newValue) => onValueChange(newValue || undefined)}>
      <SelectTrigger className={className}>
        <SelectValue placeholder={placeholder}>
          {selectedConnection ? (
            <div className="flex items-center gap-2">
              <Badge variant="secondary" className="text-xs">
                {getProviderBadge(selectedConnection.type)}
              </Badge>
              <span className="truncate">{getDisplayName(selectedConnection)}</span>
            </div>
          ) : (
            placeholder
          )}
        </SelectValue>
      </SelectTrigger>
      <SelectContent>

        {connections
          .filter(connection => connection.id && connection.id.trim() !== '')
          .map(connection => (
          <SelectItem key={connection.id} value={connection.id}>
            <div className="flex items-center gap-2 min-w-0">
              <Badge variant="secondary" className="text-xs shrink-0">
                {getProviderBadge(connection.type)}
              </Badge>
              <div className="min-w-0 flex-1">
                <div className="font-medium truncate">{getDisplayName(connection)}</div>
                <div className="text-xs text-gray-400 truncate">
                  Created {new Date(connection.created_at).toLocaleDateString()}
                </div>
              </div>
            </div>
          </SelectItem>
        ))}
        
        <div className="border-t border-gray-600 mt-2 pt-2">
          <button
            onClick={() => window.location.href = '/llm-connections'}
            className="w-full px-3 py-2 text-left text-sm text-blue-400 hover:bg-[#404040] rounded-sm"
          >
            + Manage AI Models
          </button>
        </div>
      </SelectContent>
    </Select>
  )
}