import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ApiService } from '../services/api'
import type { ConnectionCreateRequest, DatasetConnectRequest, DatasetAssociateRequest } from '../services/api'

import { useStore } from '../stores/useStore'
import { showToast } from '../utils/toast'

export const useNotebookConnections = (notebookId: string | null) => {
  const setConnections = useStore(state => state.setConnections)

  return useQuery({
    queryKey: ['notebook-connections', notebookId],
    queryFn: async () => {
      if (!notebookId) return []
      const connections = await ApiService.getNotebookConnectionsWithDetails(notebookId)
      setConnections(connections)
      return connections
    },
    enabled: !!notebookId,
  })
}

export const useConnectNotebook = () => {
  const queryClient = useQueryClient()
  const updateConnection = useStore(state => state.updateConnection)
  const forceLoadSchema = useStore(state => state.forceLoadSchema)

  return useMutation({
    mutationFn: ({ notebookId, data }: { notebookId: string; data: DatasetConnectRequest }) =>
      ApiService.connectNotebook(notebookId, data),
    onSuccess: async (response, variables) => {
      // Fetch fresh connection details to get updated schema
      try {
        // Invalidate all relevant queries first
        queryClient.invalidateQueries({ queryKey: ['notebook-connections', variables.notebookId] })
        queryClient.invalidateQueries({ queryKey: ['all-connections'] })

        const connectionId = response.connection?.id
        if (connectionId) {
          const freshConnectionDetails = await ApiService.getConnectionDetails(connectionId)

          // Update the store with fresh data including schema
          updateConnection(freshConnectionDetails.id, freshConnectionDetails)

          // Force refresh notebook schema to update @ mentions and schema viewer
          await forceLoadSchema(variables.notebookId, freshConnectionDetails.type)
        }

        // Toast handling moved to component level for better control
      } catch (error) {
        console.error('Error fetching connection details:', error)
        // Still invalidate queries even if fetching details fails
        queryClient.invalidateQueries({ queryKey: ['notebook-connections', variables.notebookId] })
        queryClient.invalidateQueries({ queryKey: ['all-connections'] })
      }
    },
    onError: (error) => {
      console.error('Error connecting database:', error)
      // Toast handling moved to component level for better control
    },
  })
}

export const useAssociateNotebookConnection = () => {
  const queryClient = useQueryClient()
  const updateConnection = useStore(state => state.updateConnection)
  const forceLoadSchema = useStore(state => state.forceLoadSchema)

  return useMutation({
    mutationFn: ({ notebookId, data }: { notebookId: string; data: DatasetAssociateRequest }) => {
      return ApiService.associateNotebookConnection(notebookId, data)
    },
    onSuccess: async (response, variables) => {

      // Check if multiple connections were associated
      const isMultiple = variables.data.connection_ids && variables.data.connection_ids.length > 0

      try {
        // Invalidate all relevant queries first
        queryClient.invalidateQueries({ queryKey: ['notebook-connections', variables.notebookId] })
        queryClient.invalidateQueries({ queryKey: ['all-connections'] })

        if (isMultiple) {
          // For multiple connections, force refresh the entire notebook schema
          // This updates @ mentions, schema viewer, and all schema consumers
          const connections = response.connections || []
          if (connections.length > 0) {
            const dbType = connections[0].type
            await forceLoadSchema(variables.notebookId, dbType)
          }

          // Update store for each connection
          for (const conn of connections) {
            const freshConnectionDetails = await ApiService.getConnectionDetails(conn.id)
            updateConnection(freshConnectionDetails.id, freshConnectionDetails)
          }
        } else {
          // Single connection - fetch details and update store
          const connectionId = response.connection?.id
          if (connectionId) {
            const freshConnectionDetails = await ApiService.getConnectionDetails(connectionId)
            updateConnection(freshConnectionDetails.id, freshConnectionDetails)

            // Also refresh notebook schema for consistency
            await forceLoadSchema(variables.notebookId, freshConnectionDetails.type)
          }
        }

        // Toast handling moved to component level for better control
      } catch (error) {
        console.error('Error fetching connection details or refreshing schema:', error)
        // Still invalidate queries even if fetching details fails
        queryClient.invalidateQueries({ queryKey: ['notebook-connections', variables.notebookId] })
        queryClient.invalidateQueries({ queryKey: ['all-connections'] })
      }
    },
    onError: (error) => {
      console.error('Error associating connection:', error)
      // Toast handling moved to component level for better control
    },
  })
}

export const useUpdateConnection = () => {
  const queryClient = useQueryClient()
  const updateConnection = useStore(state => state.updateConnection)
  const forceLoadSchema = useStore(state => state.forceLoadSchema)
  const currentNotebookId = useStore(state => state.currentNotebookId)

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: ConnectionCreateRequest }) =>
      ApiService.updateConnection(id, data),
    onSuccess: async (connection, variables) => {
      // Fetch fresh connection details to get updated schema
      try {
        const freshConnectionDetails = await ApiService.getConnectionDetails(variables.id)

        // Invalidate all relevant queries
        queryClient.invalidateQueries({ queryKey: ['notebook-connections'] })
        queryClient.invalidateQueries({ queryKey: ['all-connections'] })

        // Update the store with fresh data including schema
        updateConnection(freshConnectionDetails.id, freshConnectionDetails)

        // Force refresh notebook schema if we're currently viewing a notebook
        // This ensures schema updates appear immediately in @ mentions and schema viewer
        if (currentNotebookId) {
          await forceLoadSchema(currentNotebookId, freshConnectionDetails.type)
        }

        showToast.success('Connection updated successfully')
      } catch (error) {
        console.error('Error fetching updated connection details:', error)
        // Still update with what we have from the update response
        updateConnection(connection.id, connection)
        showToast.success('Connection updated successfully')
      }
    },
    onError: (error) => {
      console.error('Error updating connection:', error)
      showToast.error('Failed to update connection')
    },
  })
}

export const useAllConnections = () => {
  return useQuery({
    queryKey: ['all-connections'],
    queryFn: async () => {
      const response = await ApiService.listAllConnections()
      return response.items
    },
  })
}