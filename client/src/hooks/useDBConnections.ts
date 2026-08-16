import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ApiService,
  type ConnectionListSimpleResponse,
  type ConnectionCreateRequest,
  type ConnectionRead,
  type FileType,
  type DatasetUploadResponse,
  type DatasourceListResponse,
  type SourceOverviewResponse,
  type SourceResource,
  type SourceResourceCreateRequest,
  type SourceResourceSyncRequest,
  type SourceResourceSnapshotsResponse,
  type ConnectorDefinition,
  type FeishuOAuthStartResponse,
  type FeishuOAuthResult,
  type FeishuStatus,
  type KnowledgeSearchResponse,
  type SourceConnection,
  type SourceConnectionCreateRequest,
  type SourceResourceImportRequest,
  type SourceResourceImportResponse,
  type SourceConsumersResponse,
  type SourceLineageResponse,
  type SourceParsedAssetsResponse,
  type SourceProjectionReview,
  type SourceProjectionReviewRequest,
  type SourceResourcePickerResponse,
  type SourceResourceProcessing,
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
  processing: (resourceId?: string) => [...sourceConnectorKeys.all, 'processing', resourceId || 'none'] as const,
  sourceResource: (resourceId?: string) => [...sourceConnectorKeys.all, 'source-resource', resourceId || 'none'] as const,
  snapshots: (resourceId?: string) => [...sourceConnectorKeys.all, 'snapshots', resourceId || 'none'] as const,
  parsedAssets: (resourceId?: string) => [...sourceConnectorKeys.all, 'parsed-assets', resourceId || 'none'] as const,
  lineage: (resourceId?: string) => [...sourceConnectorKeys.all, 'lineage', resourceId || 'none'] as const,
  consumers: (resourceId?: string) => [...sourceConnectorKeys.all, 'consumers', resourceId || 'none'] as const,
  knowledgeSearches: (resourceId?: string) => [...sourceConnectorKeys.all, 'knowledge-search', resourceId || 'none'] as const,
  knowledgeSearch: (resourceId?: string, query?: string) => [...sourceConnectorKeys.all, 'knowledge-search', resourceId || 'none', query || ''] as const,
}

export const sourceOverviewKeys = {
  all: ['source-overview'] as const,
  overview: () => [...sourceOverviewKeys.all, 'overview'] as const,
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
      queryClient.invalidateQueries({ queryKey: sourceOverviewKeys.all })
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
      queryClient.invalidateQueries({ queryKey: sourceOverviewKeys.all })
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
      queryClient.invalidateQueries({ queryKey: sourceOverviewKeys.all })
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
      queryClient.invalidateQueries({ queryKey: sourceOverviewKeys.all })
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
      queryClient.invalidateQueries({ queryKey: sourceOverviewKeys.all })
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
      queryClient.invalidateQueries({ queryKey: sourceOverviewKeys.all })
      queryClient.invalidateQueries({ queryKey: ['source-resources'] })
      showToast.success(data.status === 'ready' ? 'Source resource indexed' : 'Source resource created; connector content required')
    },
    onError: (error: Error) => {
      showToast.error(`Failed to create source resource: ${error.message}`)
    },
  })
}

export function useCreateFileSourceResource() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ file, name }: { file: File; name: string }): Promise<SourceResource> => {
      return ApiService.createFileSourceResource(file, name)
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['datasources'] })
      queryClient.invalidateQueries({ queryKey: sourceOverviewKeys.all })
      queryClient.invalidateQueries({ queryKey: ['source-resources'] })
      showToast.success(data.status === 'ready' ? 'File source indexed' : 'File source captured; parsing needs attention')
    },
    onError: (error: Error) => {
      showToast.error(`Failed to create file source: ${error.message}`)
    },
  })
}

export const useCreatePdfSourceResource = useCreateFileSourceResource

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
      queryClient.invalidateQueries({ queryKey: sourceOverviewKeys.all })
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
      queryClient.invalidateQueries({ queryKey: sourceOverviewKeys.all })
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
      queryClient.invalidateQueries({ queryKey: sourceOverviewKeys.all })
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
      error.code !== 'needs_authorization' && error.code !== 'reauthorization_required' && failureCount < 2,
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
      queryClient.invalidateQueries({ queryKey: sourceOverviewKeys.all })
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

export function useSourceResourceProcessing(resourceId?: string, enabled = true) {
  return useQuery({
    queryKey: sourceConnectorKeys.processing(resourceId),
    queryFn: async (): Promise<SourceResourceProcessing> => {
      if (!resourceId) throw new Error('Missing source resource id')
      return ApiService.getSourceResourceProcessing(resourceId)
    },
    enabled: enabled && !!resourceId,
    staleTime: 5 * 1000,
    gcTime: 2 * 60 * 1000,
    refetchInterval: query => {
      const stage = query.state.data?.stage
      return stage && !['indexed', 'failed'].includes(stage) ? 3000 : false
    },
  })
}

export function useSourceResource(resourceId?: string) {
  return useQuery({
    queryKey: sourceConnectorKeys.sourceResource(resourceId),
    queryFn: async (): Promise<SourceResource> => {
      if (!resourceId) throw new Error('Missing source resource id')
      return ApiService.getSourceResource(resourceId)
    },
    enabled: !!resourceId,
    staleTime: 15 * 1000,
    gcTime: 2 * 60 * 1000,
  })
}

export function useSyncSourceResource() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ resourceId, payload = {} }: { resourceId: string; payload?: SourceResourceSyncRequest }): Promise<SourceResource> => {
      return ApiService.syncSourceResource(resourceId, payload)
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: sourceConnectorKeys.sourceResource(data.id) })
      queryClient.invalidateQueries({ queryKey: sourceConnectorKeys.processing(data.id) })
      queryClient.invalidateQueries({ queryKey: sourceConnectorKeys.snapshots(data.id) })
      queryClient.invalidateQueries({ queryKey: sourceConnectorKeys.parsedAssets(data.id) })
      queryClient.invalidateQueries({ queryKey: sourceConnectorKeys.lineage(data.id) })
      queryClient.invalidateQueries({ queryKey: sourceConnectorKeys.consumers(data.id) })
      queryClient.invalidateQueries({ queryKey: sourceConnectorKeys.knowledgeSearches(data.id) })
      queryClient.invalidateQueries({ queryKey: ['source-resources'] })
      queryClient.invalidateQueries({ queryKey: ['datasources'] })
      queryClient.invalidateQueries({ queryKey: sourceOverviewKeys.all })
      showToast.success('Source sync started')
    },
    onError: (error: Error) => {
      showToast.error(`Failed to sync source: ${error.message}`)
    },
  })
}

export function useReviewSourceResourceProjection() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ resourceId, payload = { status: 'verified' } }: { resourceId: string; payload?: SourceProjectionReviewRequest }): Promise<SourceProjectionReview> => {
      return ApiService.reviewSourceResourceProjection(resourceId, payload)
    },
    onSuccess: (_data, variables) => {
      const resourceId = variables.resourceId
      queryClient.invalidateQueries({ queryKey: sourceConnectorKeys.sourceResource(resourceId) })
      queryClient.invalidateQueries({ queryKey: sourceConnectorKeys.processing(resourceId) })
      queryClient.invalidateQueries({ queryKey: sourceConnectorKeys.parsedAssets(resourceId) })
      queryClient.invalidateQueries({ queryKey: sourceConnectorKeys.lineage(resourceId) })
      queryClient.invalidateQueries({ queryKey: ['datasources'] })
      queryClient.invalidateQueries({ queryKey: sourceOverviewKeys.all })
      showToast.success('Projection review saved')
    },
    onError: (error: Error) => {
      showToast.error(`Failed to review projection: ${error.message}`)
    },
  })
}

export function useDeleteSourceResource() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (resourceId: string): Promise<void> => {
      return ApiService.deleteSourceResource(resourceId)
    },
    onSuccess: (_data, resourceId) => {
      queryClient.invalidateQueries({ queryKey: sourceConnectorKeys.sourceResource(resourceId) })
      queryClient.invalidateQueries({ queryKey: sourceConnectorKeys.processing(resourceId) })
      queryClient.invalidateQueries({ queryKey: sourceConnectorKeys.snapshots(resourceId) })
      queryClient.invalidateQueries({ queryKey: sourceConnectorKeys.parsedAssets(resourceId) })
      queryClient.invalidateQueries({ queryKey: sourceConnectorKeys.lineage(resourceId) })
      queryClient.invalidateQueries({ queryKey: sourceConnectorKeys.consumers(resourceId) })
      queryClient.invalidateQueries({ queryKey: sourceConnectorKeys.knowledgeSearches(resourceId) })
      queryClient.invalidateQueries({ queryKey: ['source-resources'] })
      queryClient.invalidateQueries({ queryKey: ['datasources'] })
      queryClient.invalidateQueries({ queryKey: sourceOverviewKeys.all })
      showToast.success('Source removed from active inventory')
    },
    onError: (error: Error) => {
      showToast.error(`Failed to remove source: ${error.message}`)
    },
  })
}

export function useRefreshSourceOverviewConnectionSchema() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ connectionId }: { connectionId: string }) => {
      return ApiService.refreshConnectionSchema(connectionId)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['datasources'] })
      queryClient.invalidateQueries({ queryKey: ['source-detail-schema'] })
      queryClient.invalidateQueries({ queryKey: sourceOverviewKeys.all })
      showToast.success('Schema/profile refreshed')
    },
    onError: (error: Error) => {
      showToast.error(`Failed to refresh schema/profile: ${error.message}`)
    },
  })
}

export function useSourceResourceSnapshots(resourceId?: string) {
  return useQuery({
    queryKey: sourceConnectorKeys.snapshots(resourceId),
    queryFn: async (): Promise<SourceResourceSnapshotsResponse> => {
      if (!resourceId) throw new Error('Missing source resource id')
      return ApiService.listSourceResourceSnapshots(resourceId)
    },
    enabled: !!resourceId,
    staleTime: 30 * 1000,
    gcTime: 2 * 60 * 1000,
  })
}

export function useSourceResourceParsedAssets(resourceId?: string) {
  return useQuery({
    queryKey: sourceConnectorKeys.parsedAssets(resourceId),
    queryFn: async (): Promise<SourceParsedAssetsResponse> => {
      if (!resourceId) throw new Error('Missing source resource id')
      return ApiService.getSourceResourceParsedAssets(resourceId)
    },
    enabled: !!resourceId,
    staleTime: 30 * 1000,
    gcTime: 2 * 60 * 1000,
  })
}

export function useSourceResourceLineage(resourceId?: string) {
  return useQuery({
    queryKey: sourceConnectorKeys.lineage(resourceId),
    queryFn: async (): Promise<SourceLineageResponse> => {
      if (!resourceId) throw new Error('Missing source resource id')
      return ApiService.getSourceResourceLineage(resourceId)
    },
    enabled: !!resourceId,
    staleTime: 30 * 1000,
    gcTime: 2 * 60 * 1000,
  })
}

export function useSourceResourceConsumers(resourceId?: string) {
  return useQuery({
    queryKey: sourceConnectorKeys.consumers(resourceId),
    queryFn: async (): Promise<SourceConsumersResponse> => {
      if (!resourceId) throw new Error('Missing source resource id')
      return ApiService.getSourceResourceConsumers(resourceId)
    },
    enabled: !!resourceId,
    staleTime: 30 * 1000,
    gcTime: 2 * 60 * 1000,
  })
}

export function useKnowledgeSearch(resourceId?: string, query = '', enabled = true) {
  return useQuery({
    queryKey: sourceConnectorKeys.knowledgeSearch(resourceId, query),
    queryFn: async (): Promise<KnowledgeSearchResponse> => {
      if (!resourceId) throw new Error('Missing source resource id')
      return ApiService.searchKnowledge({ query: query.trim(), resource_ids: [resourceId], limit: 8 })
    },
    enabled: enabled && !!resourceId,
    staleTime: 15 * 1000,
    gcTime: 2 * 60 * 1000,
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

export function useSourceOverview() {
  return useQuery({
    queryKey: sourceOverviewKeys.overview(),
    queryFn: async (): Promise<SourceOverviewResponse> => {
      return ApiService.listSourcesOverview()
    },
    staleTime: 60 * 1000,
    gcTime: 5 * 60 * 1000,
    retry: (failureCount, error) => {
      const message = error instanceof Error ? error.message.toLowerCase() : ''
      if (message.includes('no tenant specified') || message.includes('workspace')) {
        return false
      }
      return failureCount < 3
    },
  })
}

export function useSourceOverviewItem(sourceId?: string) {
  return useQuery({
    queryKey: [...sourceOverviewKeys.overview(), sourceId],
    queryFn: async () => {
      if (!sourceId) throw new Error('Missing source id')
      const response = await ApiService.listSourcesOverview()
      const item = response.items.find(source => source.id === sourceId)
      if (!item) throw new Error('Source not found')
      return item
    },
    enabled: !!sourceId,
    staleTime: 60 * 1000,
    gcTime: 5 * 60 * 1000,
    retry: (failureCount, error) => {
      const message = error instanceof Error ? error.message.toLowerCase() : ''
      if (message.includes('not found') || message.includes('no tenant specified') || message.includes('workspace')) {
        return false
      }
      return failureCount < 3
    },
  })
}
