import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ApiService,
  type ConnectionListSimpleResponse,
  type ConnectionCreateRequest,
  type ConnectionRead,
  type FileType,
  type DatasetUploadResponse,
  type DatasourceListResponse,
  type SourceResource,
  type SourceResourceCreateRequest,
  type ConnectorDefinition,
  type FeishuOAuthStartResponse,
  type FeishuOAuthResult,
  type FeishuStatus,
  type SourceConnection,
  type SourceConnectionCreateRequest,
  type SourceResourceImportRequest,
  type SourceResourceImportResponse,
  type SourceResourcePickerResponse,
  type SourceResourceQuickLocateResponse,
} from '../services/api'
import { showToast } from '../utils/toast'

// Query key factory
export const dbConnectionsKeys = {
  all: ['dbConnections'] as const,
  lists: () => [...dbConnectionsKeys.all, 'list'] as const,
  list: (filters: string) => [...dbConnectionsKeys.lists(), { filters }] as const,
  details: () => [...dbConnectionsKeys.all, 'detail'] as const,
  detail: (id: string) => [...dbConnectionsKeys.details(), id] as const,
}

export const sourceConnectorKeys = {
  all: ['source-connectors'] as const,
  definitions: () => [...sourceConnectorKeys.all, 'definitions'] as const,
  connections: (provider?: string) => [...sourceConnectorKeys.all, 'connections', provider || 'all'] as const,
  feishuStatus: () => [...sourceConnectorKeys.all, 'feishu-status'] as const,
  resources: (
    connectionId?: string,
    scope?: string,
    parentToken?: string,
    resourceType?: string,
    query?: string,
    pageToken?: string,
  ) => [
    ...sourceConnectorKeys.all,
    'resources',
    connectionId || 'none',
    scope || 'default',
    parentToken || 'root',
    resourceType || 'all',
    query || '',
    pageToken || '',
  ] as const,
}

// Hook to get all database connections
export function useDBConnections() {
  return useQuery({
    queryKey: dbConnectionsKeys.lists(),
    queryFn: async (): Promise<ConnectionListSimpleResponse> => {
      return ApiService.listAllConnections()
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 10 * 60 * 1000,  // 10 minutes
  })
}

// Hook to create a database connection
export function useCreateDBConnection() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (connectionData: ConnectionCreateRequest): Promise<ConnectionRead> => {
      return ApiService.createConnection(connectionData)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: dbConnectionsKeys.lists() })
      queryClient.invalidateQueries({ queryKey: ['all-connections'] }) // Sync with notebook creation
      queryClient.invalidateQueries({ queryKey: ['datasources'] }) // Sync unified datasources
      showToast.success('Database connection created successfully')
    },
    onError: (error: Error) => {
      showToast.error(`Failed to create connection: ${error.message}`)
    },
  })
}

// Hook to delete a database connection
export function useDeleteDBConnection() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (connectionId: string): Promise<void> => {
      return ApiService.deleteConnection(connectionId)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: dbConnectionsKeys.lists() })
      queryClient.invalidateQueries({ queryKey: ['all-connections'] }) // Sync with notebook creation
      queryClient.invalidateQueries({ queryKey: ['datasources'] }) // Sync unified datasources
      showToast.success('Database connection deleted successfully')
    },
    onError: (error: Error) => {
      showToast.error(`Failed to delete connection: ${error.message}`)
    },
  })
}

// Hook to update a database connection
export function useUpdateDBConnection() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ id, data }: { id: string; data: ConnectionCreateRequest }) => {
      return ApiService.updateConnection(id, data)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: dbConnectionsKeys.lists() })
      queryClient.invalidateQueries({ queryKey: ['all-connections'] }) // Sync with notebook creation
      queryClient.invalidateQueries({ queryKey: ['datasources'] }) // Sync unified datasources
      showToast.success('Database connection updated successfully')
    },
    onError: (error: Error) => {
      showToast.error(`Failed to update connection: ${error.message}`)
    },
  })
}

// Hook to get connection details
export function useGetConnectionDetails(connectionId: string | null) {
  return useQuery({
    queryKey: dbConnectionsKeys.detail(connectionId || ''),
    queryFn: async () => {
      if (!connectionId) return null
      return ApiService.getConnectionDetails(connectionId)
    },
    enabled: !!connectionId,
    staleTime: 0, // Always fetch fresh data when editing
  })
}

// Hook to upload multiple files (CSV/Excel/Parquet/JSON - handles both single and multiple)
// Now uploads to datasets instead of connections
export function useUploadMultipleFiles() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      files,
      name,
      fileType,
      notebookId,
      aliases
    }: {
      files: File[]
      name: string
      fileType: FileType
      notebookId?: string
      aliases?: Record<string, string>
    }): Promise<DatasetUploadResponse> => {
      return ApiService.uploadMultipleFiles(files, name, fileType, notebookId, aliases)
    },
    onSuccess: (data, variables) => {
      // Invalidate datasets for the notebook if provided
      if (variables.notebookId) {
        queryClient.invalidateQueries({ queryKey: ['datasets', variables.notebookId] })
      }
      // Invalidate unified datasources list
      queryClient.invalidateQueries({ queryKey: ['datasources'] })
      // Still invalidate connections for backward compatibility
      queryClient.invalidateQueries({ queryKey: dbConnectionsKeys.lists() })
      queryClient.invalidateQueries({ queryKey: ['all-connections'] })

      const fileTypeLabel = data.file_type?.toUpperCase() || 'file'
      const fileWord = data.files_count === 1 ? 'file' : 'files'
      showToast.success(`Successfully uploaded ${data.files_count} ${fileTypeLabel} ${fileWord}`)
    },
    onError: (error: Error) => {
      showToast.error(`Failed to upload files: ${error.message}`)
    },
  })
}

// Hook to upload files from URLs
export function useUploadFromURL() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      urls,
      name,
      fileType,
      notebookId,
      signal,
    }: {
      urls: string[]
      name: string
      fileType?: FileType
      notebookId?: string
      signal?: AbortSignal
    }): Promise<DatasetUploadResponse> => {
      return ApiService.uploadFromURL(urls, name, fileType, notebookId, signal)
    },
    onSuccess: (data, variables) => {
      // Invalidate datasets for the notebook if provided
      if (variables.notebookId) {
        queryClient.invalidateQueries({ queryKey: ['datasets', variables.notebookId] })
      }
      // Invalidate unified datasources list
      queryClient.invalidateQueries({ queryKey: ['datasources'] })
      // Still invalidate connections for backward compatibility
      queryClient.invalidateQueries({ queryKey: dbConnectionsKeys.lists() })
      queryClient.invalidateQueries({ queryKey: ['all-connections'] })

      const fileTypeLabel = data.file_type?.toUpperCase() || 'file'
      const fileWord = data.files_count === 1 ? 'file' : 'files'
      showToast.success(`Successfully downloaded ${data.files_count} ${fileTypeLabel} ${fileWord} from URL`)
    },
    onError: (error: Error) => {
      showToast.error(`Failed to upload from URL: ${error.message}`)
    },
  })
}

// Hook to create knowledge-oriented source resources (PDF/Web/Feishu Doc/Sheet)
export function useCreateSourceResource() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (payload: SourceResourceCreateRequest): Promise<SourceResource> => {
      return ApiService.createSourceResource(payload)
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['datasources'] })
      queryClient.invalidateQueries({ queryKey: ['source-resources'] })
      showToast.success(data.status === 'ready' ? 'Source resource indexed' : 'Source resource created; connector content required')
    },
    onError: (error: Error) => {
      showToast.error(`Failed to create source resource: ${error.message}`)
    },
  })
}

export function useCreatePdfSourceResource() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ file, name }: { file: File; name: string }): Promise<SourceResource> => {
      return ApiService.createPdfSourceResource(file, name)
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['datasources'] })
      queryClient.invalidateQueries({ queryKey: ['source-resources'] })
      showToast.success(data.status === 'ready' ? 'PDF source resource indexed' : 'PDF source resource captured; parsing needs attention')
    },
    onError: (error: Error) => {
      showToast.error(`Failed to create PDF source resource: ${error.message}`)
    },
  })
}

export function useConnectorDefinitions() {
  return useQuery({
    queryKey: sourceConnectorKeys.definitions(),
    queryFn: async (): Promise<{ items: ConnectorDefinition[]; total: number }> => {
      return ApiService.listConnectorDefinitions()
    },
    staleTime: 5 * 60 * 1000,
    gcTime: 10 * 60 * 1000,
  })
}

export function useSourceConnections(provider?: string) {
  return useQuery({
    queryKey: sourceConnectorKeys.connections(provider),
    queryFn: async (): Promise<{ items: SourceConnection[]; total: number }> => {
      return ApiService.listSourceConnections(provider)
    },
    staleTime: 30 * 1000,
    gcTime: 5 * 60 * 1000,
  })
}

export function useFeishuStatus() {
  return useQuery({
    queryKey: sourceConnectorKeys.feishuStatus(),
    queryFn: async (): Promise<FeishuStatus> => {
      return ApiService.getFeishuStatus()
    },
    staleTime: 15 * 1000,
    gcTime: 5 * 60 * 1000,
  })
}

export function useStartFeishuOAuth() {
  return useMutation({
    mutationFn: async (): Promise<FeishuOAuthStartResponse> => {
      return ApiService.startFeishuOAuth()
    },
    onError: (error: Error) => {
      showToast.error(`Failed to start Feishu authorization: ${error.message}`)
    },
  })
}

export function useFeishuOAuthResult() {
  return useMutation({
    mutationFn: async (state: string): Promise<FeishuOAuthResult> => {
      return ApiService.getFeishuOAuthResult(state)
    },
  })
}

export function useCreateSourceConnection() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (payload: SourceConnectionCreateRequest): Promise<SourceConnection> => {
      return ApiService.createSourceConnection(payload)
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: sourceConnectorKeys.connections() })
      queryClient.invalidateQueries({ queryKey: sourceConnectorKeys.connections(data.provider) })
      showToast.success(`${data.display_name} connected`)
    },
    onError: (error: Error) => {
      showToast.error(`Failed to connect source: ${error.message}`)
    },
  })
}

export function useRefreshSourceConnection() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (connectionId: string): Promise<SourceConnection> => {
      return ApiService.refreshSourceConnection(connectionId)
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: sourceConnectorKeys.connections() })
      queryClient.invalidateQueries({ queryKey: sourceConnectorKeys.connections(data.provider) })
      if (data.provider === 'feishu') {
        queryClient.invalidateQueries({ queryKey: sourceConnectorKeys.feishuStatus() })
      }
      showToast.success('Source connection refreshed')
    },
    onError: (error: Error) => {
      showToast.error(`Failed to refresh source connection: ${error.message}`)
    },
  })
}

export function useDeleteSourceConnection() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (connectionId: string): Promise<{ deleted: boolean; affected_resource_count: number }> => {
      return ApiService.deleteSourceConnection(connectionId)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: sourceConnectorKeys.all })
      queryClient.invalidateQueries({ queryKey: ['datasources'] })
      showToast.success('Source connection disconnected')
    },
    onError: (error: Error) => {
      showToast.error(`Failed to disconnect source connection: ${error.message}`)
    },
  })
}

export function useListSourceConnectionResources(params: {
  connectionId?: string
  provider?: string
  scope?: string
  parent_token?: string
  resource_type?: string
  query?: string
  page_token?: string
  page_size?: number
}) {
  return useQuery({
    queryKey: sourceConnectorKeys.resources(
      params.connectionId,
      params.scope,
      params.parent_token,
      params.resource_type,
      params.query,
      params.page_token,
    ),
    queryFn: async (): Promise<SourceResourcePickerResponse> => {
      if (!params.connectionId) {
        return { items: [], next_page_token: null, scope: params.scope || 'recent', connection_status: 'missing_connection' }
      }
      return ApiService.listSourceConnectionResources(params.connectionId, {
        provider: params.provider,
        scope: params.scope,
        parent_token: params.parent_token,
        resource_type: params.resource_type,
        query: params.query,
        page_token: params.page_token,
        page_size: params.page_size,
      })
    },
    enabled: !!params.connectionId,
    staleTime: 10 * 1000,
    gcTime: 2 * 60 * 1000,
    retry: (failureCount, error: Error & { code?: string }) =>
      error.code !== 'reauthorization_required' && failureCount < 2,
  })
}

export function useImportSourceResources() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (payload: SourceResourceImportRequest): Promise<SourceResourceImportResponse> => {
      return ApiService.importSourceResources(payload)
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['datasources'] })
      queryClient.invalidateQueries({ queryKey: ['source-resources'] })
      queryClient.invalidateQueries({ queryKey: sourceConnectorKeys.all })
      if (data.failed > 0) {
        const failedSummary = data.results
          .filter(item => item.status !== 'ready')
          .slice(0, 2)
          .map(item => {
            const name = item.selection.name || item.selection.external_id
            const message = item.error?.message || item.status
            return `${name}: ${message}`
          })
          .join('; ')
        showToast.error(`Imported ${data.succeeded}; ${data.failed} failed${failedSummary ? ` - ${failedSummary}` : ''}`)
      } else {
        showToast.success(`Imported ${data.succeeded} source resource${data.succeeded !== 1 ? 's' : ''}`)
      }
    },
    onError: (error: Error) => {
      showToast.error(`Failed to import source resources: ${error.message}`)
    },
  })
}

export function useLocateSourceConnectionResource() {
  return useMutation({
    mutationFn: async ({ connectionId, url }: { connectionId: string; url: string }): Promise<SourceResourceQuickLocateResponse> => {
      return ApiService.locateSourceConnectionResource(connectionId, url)
    },
    onError: (error: Error) => {
      showToast.error(`Failed to locate source resource: ${error.message}`)
    },
  })
}

// Hook to get all datasources (connections + datasets)
export function useDatasources() {
  return useQuery({
    queryKey: ['datasources'],
    queryFn: async (): Promise<DatasourceListResponse> => {
      return ApiService.listAllDatasources()
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 10 * 60 * 1000,  // 10 minutes
    retry: (failureCount, error) => {
      const message = error instanceof Error ? error.message.toLowerCase() : ''
      if (message.includes('no tenant specified') || message.includes('workspace')) {
        return false
      }
      return failureCount < 3
    },
  })
}
