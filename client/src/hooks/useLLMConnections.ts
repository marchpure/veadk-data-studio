import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
// import { ApiService, LLMConnection, LLMConnectionCreateRequest } from '../services/api'
import { ApiService } from '../services/api'
import type { LLMConnectionCreateRequest } from '../services/api'

import { useStore } from '../stores/useStore'
import { showToast } from '../utils/toast'

export const useLLMConnections = () => {
  const setLLMConnections = useStore(state => state.setLLMConnections)
  
  return useQuery({
    queryKey: ['llm-connections'],
    queryFn: async () => {
      const response = await ApiService.listLLMConnections()
      setLLMConnections(response.items)
      return response.items
    },
  })
}

export const useCreateLLMConnection = () => {
  const queryClient = useQueryClient()
  const addLLMConnection = useStore(state => state.addLLMConnection)
  
  return useMutation({
    mutationFn: (data: LLMConnectionCreateRequest) => ApiService.createLLMConnection(data),
    onSuccess: (connection) => {
      queryClient.invalidateQueries({ queryKey: ['llm-connections'] })
      addLLMConnection(connection)
      showToast.success('LLM connection created successfully')
    },
    onError: (error) => {
      console.error('Error creating LLM connection:', error)
      showToast.error('Failed to create LLM connection')
    },
  })
}

export const useUpdateLLMConnection = () => {
  const queryClient = useQueryClient()
  const updateLLMConnection = useStore(state => state.updateLLMConnection)
  
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: LLMConnectionCreateRequest }) =>
      ApiService.updateLLMConnection(id, data),
    onSuccess: (connection) => {
      queryClient.invalidateQueries({ queryKey: ['llm-connections'] })
      updateLLMConnection(connection.id, connection)
      showToast.success('LLM connection updated successfully')
    },
    onError: (error) => {
      console.error('Error updating LLM connection:', error)
      showToast.error('Failed to update LLM connection')
    },
  })
}

export const useDeleteLLMConnection = () => {
  const queryClient = useQueryClient()
  const deleteLLMConnection = useStore(state => state.deleteLLMConnection)
  
  return useMutation({
    mutationFn: (connectionId: string) => ApiService.deleteLLMConnection(connectionId),
    onSuccess: (_, connectionId) => {
      queryClient.invalidateQueries({ queryKey: ['llm-connections'] })
      deleteLLMConnection(connectionId)
      showToast.success('LLM connection deleted successfully')
    },
    onError: (error) => {
      console.error('Error deleting LLM connection:', error)
      showToast.error('Failed to delete LLM connection')
    },
  })
}

export const useAvailableModels = (provider?: string) => {
  const setAvailableModels = useStore(state => state.setAvailableModels)
  
  return useQuery({
    queryKey: ['available-models', provider],
    queryFn: async () => {
      const response = await ApiService.getAvailableModels(provider)
      if ('models_by_provider' in response) {
        setAvailableModels(response.models_by_provider)
        return response.models_by_provider
      }
      return response
    },
  })
}

export const useSupportedProviders = () => {
  const setSupportedProviders = useStore(state => state.setSupportedProviders)
  
  return useQuery({
    queryKey: ['supported-providers'],
    queryFn: async () => {
      const providers = await ApiService.getSupportedProviders()
      setSupportedProviders(providers)
      return providers
    },
  })
}