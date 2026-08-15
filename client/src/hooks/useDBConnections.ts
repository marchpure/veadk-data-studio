import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiService, type ConnectionListSimpleResponse, type ConnectionCreateRequest, type ConnectionRead, type FileType, type DatasetUploadResponse, type DatasourceListResponse, type SourceResource, type SourceResourceCreateRequest, type SourceResourceProcessing, type SourceResourceSyncResponse, type SourceSnapshotListResponse, type WebSourceResourceCreateRequest } from '../services/api'
import { showToast } from '../utils/toast'

// Query key factory
export const dbConnectionsKeys = {
  all: ['dbConnections'] as const,
  lists: () => [...dbConnectionsKeys.all, 'list'] as const,
  list: (filters: string) => [...dbConnectionsKeys.lists(), { filters }] as const,
  details: () => [...dbConnectionsKeys.all, 'detail'] as const,
  detail: (id: string) => [...dbConnectionsKeys.details(), id] as const,
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

export function useCreateSourceResource() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (payload: SourceResourceCreateRequest): Promise<SourceResource> => {
      return ApiService.createSourceResource(payload)
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['datasources'] })
      queryClient.invalidateQueries({ queryKey: ['source-resources'] })
      showToast.success(
        data.status === 'needs_confirmation'
          ? 'Source added. Authorization/configuration is required before sync.'
          : 'Source resource created successfully'
      )
    },
    onError: (error: Error) => {
      showToast.error(`Failed to create source resource: ${error.message}`)
    },
  })
}

export function useUploadPdfSourceResource() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ file, name }: { file: File; name?: string }): Promise<SourceResource> => {
      return ApiService.uploadPdfSourceResource(file, name)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['datasources'] })
      queryClient.invalidateQueries({ queryKey: ['source-resources'] })
      showToast.success('PDF source uploaded and indexed')
    },
    onError: (error: Error) => {
      queryClient.invalidateQueries({ queryKey: ['datasources'] })
      queryClient.invalidateQueries({ queryKey: ['source-resources'] })
      showToast.error(`Failed to upload PDF source: ${error.message}`)
    },
  })
}

export function useCreateWebSourceResource() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (payload: WebSourceResourceCreateRequest): Promise<SourceResource> => {
      return ApiService.createWebSourceResource(payload)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['datasources'] })
      queryClient.invalidateQueries({ queryKey: ['source-resources'] })
      showToast.success('Web source fetched and indexed')
    },
    onError: (error: Error) => {
      queryClient.invalidateQueries({ queryKey: ['datasources'] })
      queryClient.invalidateQueries({ queryKey: ['source-resources'] })
      showToast.error(`Failed to add web source: ${error.message}`)
    },
  })
}

export function useSyncSourceResource() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (resourceId: string): Promise<SourceResourceSyncResponse> => {
      return ApiService.syncSourceResource(resourceId)
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['datasources'] })
      queryClient.invalidateQueries({ queryKey: ['source-resources'] })
      queryClient.invalidateQueries({ queryKey: ['source-resource-processing', data.resource_id] })
      queryClient.invalidateQueries({ queryKey: ['source-resource-snapshots', data.resource_id] })
      if (data.status === 'failed') {
        showToast.error(`Source sync failed: ${data.message}`)
      } else if (data.status === 'needs_confirmation') {
        showToast.info(data.message)
      } else {
        showToast.success('Source resource synced')
      }
    },
    onError: (error: Error) => {
      showToast.error(`Failed to sync source resource: ${error.message}`)
    },
  })
}

export function useDeleteSourceResource() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (resourceId: string): Promise<void> => {
      return ApiService.deleteSourceResource(resourceId)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['datasources'] })
      queryClient.invalidateQueries({ queryKey: ['source-resources'] })
      showToast.success('Source resource deleted successfully')
    },
    onError: (error: Error) => {
      showToast.error(`Failed to delete source resource: ${error.message}`)
    },
  })
}

export function useSourceResourceProcessing(resourceId: string | null) {
  return useQuery({
    queryKey: ['source-resource-processing', resourceId],
    queryFn: async (): Promise<SourceResourceProcessing | null> => {
      if (!resourceId) return null
      return ApiService.getSourceResourceProcessing(resourceId)
    },
    enabled: !!resourceId,
    staleTime: 0,
  })
}

export function useSourceResourceSnapshots(resourceId: string | null) {
  return useQuery({
    queryKey: ['source-resource-snapshots', resourceId],
    queryFn: async (): Promise<SourceSnapshotListResponse | null> => {
      if (!resourceId) return null
      return ApiService.listSourceResourceSnapshots(resourceId)
    },
    enabled: !!resourceId,
    staleTime: 0,
  })
}
