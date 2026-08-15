import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { createPortal } from 'react-dom'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog'
import {
  Download,
  Loader2,
  Check,
  X,
  ChevronRight,
  ChevronLeft,
  ChevronDown,
  Database,
  AlertCircle,
  Hash,
  Lock,
  Eye,
  EyeOff,
  SkipForward,
  Play,
  Plus,
} from 'lucide-react'
import { ApiService, type ConnectionListItem, type ConnectionType, type Datasource } from '../services/api'
import { DatabaseConnectionDialog } from './DatabaseConnectionDialog'

type Step = 'shareId' | 'datasets' | 'importing' | 'complete'

interface NotebookSummary {
  title: string
  description: string | null
  datasets_count: number
  queries_count: number
  messages_count: number
  dashboards_count: number
}

interface ExportedDataset {
  original_name: string
  type: string
  queries: Array<{ id: string; name: string; query: string; output_schema: string | null }>
  files: string[] | null
}

interface DatasetMapping {
  dataset_index: number
  connection_id: string | null
  validated: boolean
  skipped: boolean
  error: string | null
}

interface ImportNotebookModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onImportSuccess?: (notebookId: string) => void
  initialShareId?: string
}

// Map export type to display name
const typeDisplayMap: Record<string, string> = {
  postgresql: 'PostgreSQL',
  mysql: 'MySQL',
  mongodb: 'MongoDB',
  sqlite: 'SQLite',
  mssql: 'SQL Server',
  csv_bundle: 'CSV Files',
  excel_bundle: 'Excel Files',
  file_bundle: 'File Upload',
}

// Map internal type to export type for matching
const internalToExportType: Record<string, string> = {
  pg: 'postgresql',
  mysql: 'mysql',
  mongo: 'mongodb',
  sqlite: 'sqlite',
  mssql: 'mssql',
}

// Map export type back to internal type for creating connections
const exportToInternalType: Record<string, ConnectionType> = {
  postgresql: 'pg',
  mysql: 'mysql',
  mongodb: 'mongo',
  sqlite: 'sqlite',
  mssql: 'mssql',
}

// File-based export types (not database connections)
const fileExportTypes = new Set(['csv_bundle', 'excel_bundle', 'file_bundle'])

// Base URL for notebook share links
const NOTEBOOK_SHARE_BASE_URL = 'https://www.byaan.ai/n'

// Create full URL from share ID
const getNotebookShareUrl = (shareId: string): string => `${NOTEBOOK_SHARE_BASE_URL}/${shareId}`

// Extract UUID from a share URL or return the input if it's already a UUID
// Supports formats:
// - https://www.byaan.ai/n/{uuid}
// - https://downloads.byaan.ai/n/{uuid}
// - byaan.ai/n/{uuid}
// - Just the UUID itself
const extractShareId = (input: string): string => {
  const trimmed = input.trim()

  // Check if it's a URL containing /n/{uuid}
  const urlPattern = /(?:https?:\/\/)?(?:www\.)?byaan\.ai\/n\/([a-f0-9-]+)/i
  const match = trimmed.match(urlPattern)
  if (match && match[1]) {
    return match[1]
  }

  // Otherwise return as-is (assume it's a UUID)
  return trimmed
}

// Check if an export type is file-based
const isFileBasedExportType = (exportType: string): boolean => {
  return fileExportTypes.has(exportType)
}

// Check if a datasource is compatible with an exported dataset type
const isDatasourceCompatible = (
  datasource: Datasource,
  exportedType: string
): boolean => {
  if (isFileBasedExportType(exportedType)) {
    // File-based export type should match a file-based datasource
    return datasource.source_type === 'dataset'
  } else {
    // Database export type should match a connection-based datasource with matching type
    if (datasource.source_type !== 'connection') return false
    // Check if the datasource's internal type matches the exported type
    const datasourceExportType = internalToExportType[datasource.type] || datasource.type
    return datasourceExportType === exportedType
  }
}

// Get default port for connection type
const getDefaultPort = (exportType: string | undefined): string => {
  if (!exportType) return '5432'
  const ports: Record<string, string> = {
    postgresql: '5432',
    mysql: '3306',
    mongodb: '27017',
    mssql: '1433',
    sqlite: '',
  }
  return ports[exportType] || '5432'
}

export default function ImportNotebookModal({
  open,
  onOpenChange,
  onImportSuccess,
  initialShareId,
}: ImportNotebookModalProps) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  // Step state
  const [step, setStep] = useState<Step>('shareId')

  // Share ID step state
  const [shareId, setShareId] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [isFetching, setIsFetching] = useState(false)
  const [fetchError, setFetchError] = useState<string | null>(null)

  // Notebook data state
  const [notebookExport, setNotebookExport] = useState<any>(null)
  const [summary, setSummary] = useState<NotebookSummary | null>(null)

  // Dataset mapping state
  const [currentDatasetIndex, setCurrentDatasetIndex] = useState(0)
  const [datasetMappings, setDatasetMappings] = useState<Map<number, DatasetMapping>>(new Map())
  const [connections, setConnections] = useState<ConnectionListItem[]>([])
  const [loadingConnections, setLoadingConnections] = useState(false)
  const [selectedConnectionId, setSelectedConnectionId] = useState<string | null>(null)
  const [testingQuery, setTestingQuery] = useState(false)
  const [testResult, setTestResult] = useState<{ success: boolean; error: string | null } | null>(null)

  // Import state
  const [_isImporting, setIsImporting] = useState(false)
  const [importError, setImportError] = useState<string | null>(null)
  const [importResult, setImportResult] = useState<{
    notebook_id: string
    imported: { datasets: number; queries: number; messages: number; dashboards: number }
    skipped_datasets: number
  } | null>(null)

  // Custom dropdown state
  const [isDropdownOpen, setIsDropdownOpen] = useState(false)
  const dropdownButtonRef = useRef<HTMLButtonElement>(null)
  const [dropdownPosition, setDropdownPosition] = useState({ top: 0, left: 0, width: 0 })

  // Connection creation state (inline form for database types)
  const [showConnectionForm, setShowConnectionForm] = useState(false)
  const [isCreatingConnection, setIsCreatingConnection] = useState(false)
  const [connectionFormError, setConnectionFormError] = useState<string | null>(null)
  const [connectionConfig, setConnectionConfig] = useState({
    name: '',
    host: 'localhost',
    port: '5432',
    database: '',
    user: '',
    password: '',
    connectionString: '',
  })

  // DatabaseConnectionDialog state (for file-based datasets)
  const [showConnectionDialog, setShowConnectionDialog] = useState(false)
  const [connectionDialogMode, setConnectionDialogMode] = useState<'create' | 'select'>('create')
  const [isCreatingDatasource, setIsCreatingDatasource] = useState(false)
  const [datasources, setDatasources] = useState<Datasource[]>([])
  const [loadingDatasources, setLoadingDatasources] = useState(false)

  // Reset state when modal opens/closes
  useEffect(() => {
    if (!open) {
      // Reset everything when modal closes
      setTimeout(() => {
  setStep('shareId')
  setShareId('')
  setPassword('')
  setShowPassword(false)
  setIsFetching(false)
  setFetchError(null)
  setNotebookExport(null)
  setSummary(null)
  setCurrentDatasetIndex(0)
  setDatasetMappings(new Map())
  setSelectedConnectionId(null)
  setTestResult(null)
  setIsImporting(false)
  setImportError(null)
  setImportResult(null)
  // Reset connection creation state
  setShowConnectionForm(false)
  setIsCreatingConnection(false)
  setConnectionFormError(null)
  setConnectionConfig({
    name: '',
    host: 'localhost',
    port: '5432',
    database: '',
    user: '',
    password: '',
    connectionString: '',
  })
  // Reset dialog state
  setShowConnectionDialog(false)
  setConnectionDialogMode('create')
  setIsCreatingDatasource(false)
      }, 200)
    }
  }, [open])

  // Handle initialShareId from deep link - auto-fill and fetch
  useEffect(() => {
    if (open && initialShareId && step === 'shareId' && !shareId && !isFetching) {
      // Extract UUID from URL if needed (in case a full URL is passed)
      const actualShareId = extractShareId(initialShareId)
      // Display the full URL in the input field for consistency
      setShareId(getNotebookShareUrl(actualShareId))
      // Auto-fetch after a small delay to let the state settle
      const timer = setTimeout(async () => {
  setIsFetching(true)
  setFetchError(null)
  try {
    const response = await ApiService.fetchSharedNotebook(actualShareId, undefined)
    if (response.success && response.data) {
      setNotebookExport(response.data.notebook_export)
      setSummary(response.data.summary)
      const datasets = response.data.notebook_export.datasets || []
      const initialMappings = new Map<number, DatasetMapping>()
      datasets.forEach((_: ExportedDataset, index: number) => {
        initialMappings.set(index, {
          dataset_index: index,
          connection_id: null,
          validated: false,
          skipped: false,
          error: null,
        })
      })
      setDatasetMappings(initialMappings)
      if (datasets.length > 0) {
        setStep('datasets')
      }
    }
  } catch (err: any) {
    const errorMessage = err.message || 'Failed to fetch notebook'
    if (errorMessage.includes('401') || errorMessage.toLowerCase().includes('password')) {
      setFetchError('This notebook is password protected. Please enter the password.')
    } else {
      setFetchError(errorMessage)
    }
  } finally {
    setIsFetching(false)
  }
      }, 100)
      return () => clearTimeout(timer)
    }
  }, [open, initialShareId, step, shareId, isFetching])

  // Load connections and datasources when entering datasets step
  useEffect(() => {
    if (step === 'datasets') {
      if (connections.length === 0) {
  loadConnections()
      }
      if (datasources.length === 0) {
  loadDatasources()
      }
    }
  }, [step])

  // Reset state and auto-select name-matched datasource when dataset changes
  useEffect(() => {
    if (step === 'datasets' && notebookExport?.datasets) {
      setTestResult(null)
      setConnectionFormError(null)
      setIsDropdownOpen(false)
      // Reset form when switching datasets
      setConnectionConfig({
  name: '',
  host: 'localhost',
  port: getDefaultPort(notebookExport?.datasets?.[currentDatasetIndex]?.type),
  database: '',
  user: '',
  password: '',
  connectionString: '',
      })
    }
  }, [currentDatasetIndex, step])

  // Update dropdown position when opened and on scroll/resize
  useEffect(() => {
    const updatePosition = () => {
      if (isDropdownOpen && dropdownButtonRef.current) {
        const rect = dropdownButtonRef.current.getBoundingClientRect()
        setDropdownPosition({
          top: rect.bottom,
          left: rect.left,
          width: rect.width,
        })
      }
    }

    if (isDropdownOpen) {
      updatePosition()
      // Update position on scroll or resize
      window.addEventListener('scroll', updatePosition, true)
      window.addEventListener('resize', updatePosition)
      return () => {
        window.removeEventListener('scroll', updatePosition, true)
        window.removeEventListener('resize', updatePosition)
      }
    }
  }, [isDropdownOpen])

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as HTMLElement
      // Check if click is outside both the button and the dropdown menu
      if (
  isDropdownOpen &&
  dropdownButtonRef.current &&
  !dropdownButtonRef.current.contains(target) &&
  !target.closest('[data-dropdown-menu]')
      ) {
  setIsDropdownOpen(false)
      }
    }

    if (isDropdownOpen) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [isDropdownOpen])

  // Auto-select datasource when name match is found (with type compatibility check)
  useEffect(() => {
    if (step === 'datasets' && datasources.length > 0 && notebookExport?.datasets?.[currentDatasetIndex]) {
      const dataset = notebookExport.datasets[currentDatasetIndex] as ExportedDataset
      // Find by EXACT name match (case-sensitive) AND type compatibility
      const matchedDatasource = datasources.find(
  (ds) => ds.name === dataset.original_name && isDatasourceCompatible(ds, dataset.type)
      )
      if (matchedDatasource) {
  setSelectedConnectionId(matchedDatasource.id)
  setShowConnectionForm(false)
      } else {
  setSelectedConnectionId(null)
      }
    }
  }, [step, currentDatasetIndex, datasources, notebookExport])

  // Auto-show connection form when no compatible name match AND no compatible datasources exist
  useEffect(() => {
    if (step === 'datasets' && !loadingDatasources && notebookExport?.datasets?.[currentDatasetIndex]) {
      const dataset = notebookExport.datasets[currentDatasetIndex] as ExportedDataset
      // Check for name match WITH type compatibility
      const hasCompatibleMatch = datasources.some(
  (ds) => ds.name === dataset.original_name && isDatasourceCompatible(ds, dataset.type)
      )
      // Check if there are any compatible datasources (even without name match)
      const hasCompatibleDatasources = datasources.some(
  (ds) => isDatasourceCompatible(ds, dataset.type)
      )
      if (!hasCompatibleMatch && !hasCompatibleDatasources) {
  // No compatible datasources at all - show connection form for database types
  const internalType = exportToInternalType[dataset.type]
  if (internalType) {
    setShowConnectionForm(true)
  } else {
    setShowConnectionForm(false)
  }
      } else {
  // Has compatible datasources - don't show form, let user pick from dropdown
  setShowConnectionForm(false)
      }
    }
  }, [step, currentDatasetIndex, datasources, loadingDatasources, notebookExport])

  const loadConnections = async () => {
    setLoadingConnections(true)
    try {
      const response = await ApiService.listAllConnections()
      setConnections(response.items || [])
    } catch (err) {
      console.error('Error loading connections:', err)
    } finally {
      setLoadingConnections(false)
    }
  }

  const handleFetchNotebook = async () => {
    if (!shareId.trim()) return

    setIsFetching(true)
    setFetchError(null)

    // Extract UUID from URL if a full link was pasted
    const actualShareId = extractShareId(shareId)

    try {
      const response = await ApiService.fetchSharedNotebook(actualShareId, password || undefined)

      if (response.success && response.data) {
  setNotebookExport(response.data.notebook_export)
  setSummary(response.data.summary)

  // Initialize mappings for all datasets
  const datasets = response.data.notebook_export.datasets || []
  const initialMappings = new Map<number, DatasetMapping>()
  datasets.forEach((_: ExportedDataset, index: number) => {
    initialMappings.set(index, {
      dataset_index: index,
      connection_id: null,
      validated: false,
      skipped: false,
      error: null,
    })
  })
  setDatasetMappings(initialMappings)

  // Move to datasets step if there are datasets, otherwise import directly
  if (datasets.length > 0) {
    setStep('datasets')
  } else {
    // No datasets, just import the notebook
    handleImport()
  }
      }
    } catch (err: any) {
      const errorMessage = err.message || 'Failed to fetch notebook'
      setFetchError(errorMessage)
    } finally {
      setIsFetching(false)
    }
  }

  const handleTestQuery = async () => {
    if (!selectedConnectionId) return

    const currentDataset = notebookExport?.datasets?.[currentDatasetIndex] as ExportedDataset | undefined
    if (!currentDataset || !currentDataset.queries.length) return

    setTestingQuery(true)
    setTestResult(null)

    try {
      // Use the first query as the test query
      const testQuery = currentDataset.queries[0].query

      // Find the selected datasource to determine its type
      const selectedDatasource = datasources.find((ds) => ds.id === selectedConnectionId)

      // Determine the correct API call based on datasource type
      let apiParams: { connectionId?: string; datasetId?: string }
      if (selectedDatasource?.source_type === 'dataset') {
  // File-based dataset - pass dataset_id
  apiParams = { datasetId: selectedConnectionId }
      } else if (selectedDatasource?.source_type === 'connection' && selectedDatasource.connection_id) {
  // Connection-based datasource - pass the underlying connection_id
  apiParams = { connectionId: selectedDatasource.connection_id }
      } else {
  // Fallback: assume it's a connection ID (for backwards compatibility)
  apiParams = { connectionId: selectedConnectionId }
      }

      const response = await ApiService.testImportQuery(apiParams, testQuery)

      if (response.success && response.data) {
  setTestResult({
    success: response.data.success,
    error: response.data.error,
  })

  // Update mapping if test was successful
  if (response.data.success) {
    const newMappings = new Map(datasetMappings)
    newMappings.set(currentDatasetIndex, {
      dataset_index: currentDatasetIndex,
      connection_id: selectedConnectionId,
      validated: true,
      skipped: false,
      error: null,
    })
    setDatasetMappings(newMappings)
  }
      }
    } catch (err: any) {
      setTestResult({
  success: false,
  error: err.message || 'Failed to test query',
      })
    } finally {
      setTestingQuery(false)
    }
  }

  const handleSkipDataset = () => {
    const newMappings = new Map(datasetMappings)
    newMappings.set(currentDatasetIndex, {
      dataset_index: currentDatasetIndex,
      connection_id: null,
      validated: false,
      skipped: true,
      error: null,
    })
    setDatasetMappings(newMappings)

    // Move to next dataset or import step
    if (currentDatasetIndex < (notebookExport?.datasets?.length || 0) - 1) {
      setCurrentDatasetIndex(currentDatasetIndex + 1)
      setSelectedConnectionId(null)
      setTestResult(null)
    }
  }

  // Create a new connection for the current dataset type
  const handleCreateConnection = async () => {
    const dataset = notebookExport?.datasets?.[currentDatasetIndex] as ExportedDataset | undefined
    if (!dataset) return

    const internalType = exportToInternalType[dataset.type]
    if (!internalType) {
      setConnectionFormError('Cannot create connection for this dataset type')
      return
    }

    // Validate form
    if (!connectionConfig.name.trim()) {
      setConnectionFormError('Connection name is required')
      return
    }

    if (internalType === 'mongo') {
      if (!connectionConfig.connectionString.trim()) {
  setConnectionFormError('Connection string is required')
  return
      }
    } else if (internalType === 'sqlite') {
      if (!connectionConfig.database.trim()) {
  setConnectionFormError('Database path is required')
  return
      }
    } else {
      // pg, mysql, mssql
      if (!connectionConfig.host.trim() || !connectionConfig.port.trim() ||
    !connectionConfig.database.trim() || !connectionConfig.user.trim() ||
    !connectionConfig.password.trim()) {
  setConnectionFormError('All fields are required')
  return
      }
    }

    setIsCreatingConnection(true)
    setConnectionFormError(null)

    try {
      // Build connection object based on type
      let connectionObj: Record<string, unknown>
      if (internalType === 'mongo') {
  connectionObj = { connection_string: connectionConfig.connectionString }
      } else if (internalType === 'sqlite') {
  connectionObj = { database: connectionConfig.database }
      } else {
  connectionObj = {
    host: connectionConfig.host,
    port: parseInt(connectionConfig.port),
    database: connectionConfig.database,
    user: connectionConfig.user,
    password: connectionConfig.password,
  }
      }

      const newConnection = await ApiService.createConnection({
  type: internalType,
  name: connectionConfig.name,
  connection_obj: connectionObj,
      })

      // Reload connections and auto-select the new one
      await loadConnections()
      setSelectedConnectionId(newConnection.id)
      setShowConnectionForm(false)
      // Reset form for next time
      setConnectionConfig({
  name: '',
  host: 'localhost',
  port: getDefaultPort(dataset.type),
  database: '',
  user: '',
  password: '',
  connectionString: '',
      })
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to create connection'
      setConnectionFormError(errorMessage)
    } finally {
      setIsCreatingConnection(false)
    }
  }

  // Load datasources for the connection dialog
  const loadDatasources = async () => {
    setLoadingDatasources(true)
    try {
      const response = await ApiService.listAllDatasources()
      if (response.items) {
  setDatasources(response.items)
      }
    } catch (err) {
      console.error('Error loading datasources:', err)
    } finally {
      setLoadingDatasources(false)
    }
  }

  // Handle creating a datasource via DatabaseConnectionDialog (for file-based datasets)
  const handleCreateDatasource = async (data: {
    type: ConnectionType | 'upload' | 'url'
    name: string
    connectionObj?: Record<string, unknown>
    files?: File[]
    aliases?: Record<string, string>
    fileType?: 'csv' | 'excel' | 'parquet' | 'json'
    urls?: string[]
  }) => {
    setIsCreatingDatasource(true)
    try {
      let newDatasourceId: string | null = null

      if (data.type === 'upload' && data.files && data.fileType) {
  // File upload
  const response = await ApiService.uploadMultipleFiles(
    data.files,
    data.name,
    data.fileType,
    undefined,
    data.aliases
  )
  if (response.dataset_id) {
    newDatasourceId = response.dataset_id
  }
      } else if (data.type === 'url' && data.urls) {
  // URL import
  const response = await ApiService.uploadFromURL(data.urls, data.name, data.fileType)
  if (response.dataset_id) {
    newDatasourceId = response.dataset_id
  }
      } else if (data.connectionObj) {
  // Database connection
  const newConnection = await ApiService.createConnection({
    type: data.type as ConnectionType,
    name: data.name,
    connection_obj: data.connectionObj,
  })
  newDatasourceId = newConnection.id
      }

      if (newDatasourceId) {
  // Reload connections and datasources
  await loadConnections()
  await loadDatasources()
  setSelectedConnectionId(newDatasourceId)
  setShowConnectionDialog(false)
      }
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to create datasource'
      console.error('Error creating datasource:', errorMessage)
      throw err // Re-throw so the dialog can show the error
    } finally {
      setIsCreatingDatasource(false)
    }
  }

  // Open the connection dialog for file-based datasets
  const handleOpenConnectionDialog = () => {
    loadDatasources()
    setConnectionDialogMode('create')
    setShowConnectionDialog(true)
  }

  const handleNextDataset = () => {
    if (currentDatasetIndex < (notebookExport?.datasets?.length || 0) - 1) {
      setCurrentDatasetIndex(currentDatasetIndex + 1)
      setSelectedConnectionId(null)
      setTestResult(null)
    }
  }

  const handlePrevDataset = () => {
    if (currentDatasetIndex > 0) {
      setCurrentDatasetIndex(currentDatasetIndex - 1)
      setSelectedConnectionId(null)
      setTestResult(null)
    }
  }

  const handleImport = async () => {
    setStep('importing')
    setIsImporting(true)
    setImportError(null)

    try {
      // Build dataset mappings array with correct ID based on datasource type
      const mappingsArray = Array.from(datasetMappings.values()).map((m) => {
  // Find the datasource that was selected for this mapping
  const selectedDatasource = datasources.find((ds) => ds.id === m.connection_id)

  if (selectedDatasource?.source_type === 'dataset') {
    // File-based dataset - pass dataset_id (attach existing)
    return {
      dataset_index: m.dataset_index,
      dataset_id: m.connection_id, // This is actually a dataset ID
      connection_id: null,
      skipped: m.skipped,
    }
  } else if (selectedDatasource?.source_type === 'connection' && selectedDatasource.connection_id) {
    // Connection-based datasource - pass the underlying connection_id
    return {
      dataset_index: m.dataset_index,
      connection_id: selectedDatasource.connection_id,
      dataset_id: null,
      skipped: m.skipped,
    }
  } else {
    // Fallback - assume it's a connection ID (for backwards compatibility)
    return {
      dataset_index: m.dataset_index,
      connection_id: m.connection_id,
      dataset_id: null,
      skipped: m.skipped,
    }
  }
      })

      const response = await ApiService.importNotebook(notebookExport, mappingsArray)

      if (response.success && response.data) {
  setImportResult(response.data)
  setStep('complete')

  // Invalidate caches so notebook and datasets appear immediately
  await queryClient.invalidateQueries({ queryKey: ['notebooks'] })
  await queryClient.invalidateQueries({ queryKey: ['datasources'] })
      }
    } catch (err: any) {
      setImportError(err.message || 'Failed to import notebook')
      setStep('datasets') // Go back to datasets step on error
    } finally {
      setIsImporting(false)
    }
  }

  const handleGoToNotebook = async () => {
    if (importResult?.notebook_id) {
      // Invalidate notebooks cache to ensure the newly imported notebook is fetched
      // This ensures the ChatPreview page has the correct model selection
      await queryClient.invalidateQueries({ queryKey: ['notebooks'] })
      onOpenChange(false)
      onImportSuccess?.(importResult.notebook_id)
      navigate(`/notebook/${importResult.notebook_id}`)
    }
  }

  // Get current dataset
  const currentDataset = notebookExport?.datasets?.[currentDatasetIndex] as ExportedDataset | undefined
  const currentMapping = datasetMappings.get(currentDatasetIndex)

  // Find datasource by EXACT name match (case-sensitive) AND type compatibility
  const nameMatchedDatasource = currentDataset
    ? datasources.find(
  (ds) =>
    ds.name === currentDataset.original_name &&
    isDatasourceCompatible(ds, currentDataset.type)
      )
    : undefined

  // Get compatible connections for current dataset type (fallback if no name match)
  const compatibleConnections = connections.filter((conn) => {
    if (!currentDataset) return false
    const exportType = currentDataset.type
    const connExportType = internalToExportType[conn.type] || conn.type
    return connExportType === exportType
  })

  // Get ALL compatible datasources for current dataset type (both connections and file datasets)
  const compatibleDatasources = datasources.filter((ds) => {
    if (!currentDataset) return false
    return isDatasourceCompatible(ds, currentDataset.type)
  })

  // Check if at least one dataset is connected
  const hasConnectedDataset = Array.from(datasetMappings.values()).some(
    (m) => m.validated && !m.skipped
  )

  const canImport = hasConnectedDataset || (notebookExport?.datasets?.length === 0)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg bg-[#1a1a1a] border-[#404040] max-h-[85vh] flex flex-col">
  <DialogHeader>
    <DialogTitle className="text-white flex items-center gap-2">
      <Download className="w-4 h-4" />
      Import Notebook
    </DialogTitle>
  </DialogHeader>

  <div className="space-y-4 flex-1 overflow-hidden flex flex-col">
    {/* Step 1: Share ID Input */}
    {step === 'shareId' && (
      <div className="space-y-4">
        <p className="text-sm text-gray-400">
          Paste the share link to import a notebook into your workspace.
        </p>

        {/* Share Link Input */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            <Hash className="w-4 h-4 inline-block mr-1.5" />
            Share Link
          </label>
          <input
            type="text"
            value={shareId}
            onChange={(e) => setShareId(e.target.value)}
            placeholder="https://www.byaan.ai/n/..."
            className="w-full px-3 py-2 text-sm bg-[#252525] border border-[#404040] rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-brand-orange transition-colors"
            disabled={isFetching}
          />
        </div>

        {/* Password Input (optional) */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            <Lock className="w-4 h-4 inline-block mr-1.5" />
            Password
            <span className="text-gray-500 font-normal ml-1.5">(optional)</span>
          </label>
          <div className="relative">
            <input
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter if notebook is protected"
              className="w-full px-3 py-2 pr-10 text-sm bg-[#252525] border border-[#404040] rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-brand-orange transition-colors"
              disabled={isFetching}
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

        {/* Error message */}
        {fetchError && (
          <div className="flex items-center gap-2 text-red-400 text-sm bg-red-400/10 py-2 px-3 rounded-lg">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            {fetchError}
          </div>
        )}

        {/* Fetch button */}
        <button
          onClick={handleFetchNotebook}
          disabled={isFetching || !shareId.trim()}
          className="w-full px-4 py-2.5 text-sm font-medium bg-brand-orange hover:bg-brand-orange-hover text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
        >
          {isFetching ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Fetching...
            </>
          ) : (
            <>
              <Download className="w-4 h-4" />
              Fetch Notebook
            </>
          )}
        </button>
      </div>
    )}

    {/* Step 2: Dataset Connection */}
    {step === 'datasets' && summary && currentDataset && (
      <div className="space-y-4 flex-1 overflow-hidden flex flex-col">
        {/* Notebook Summary */}
        <div className="p-3 bg-[#252525] rounded-lg border border-[#333]">
          <h3 className="text-white font-medium mb-1">{summary.title}</h3>
          <p className="text-xs text-gray-400">
            {summary.datasets_count} dataset{summary.datasets_count !== 1 ? 's' : ''} | {summary.queries_count} queries | {summary.messages_count} messages
          </p>
        </div>

        {/* Dataset Progress */}
        <div className="flex items-center justify-between text-sm">
          <span className="text-gray-400">
            Dataset {currentDatasetIndex + 1} of {notebookExport?.datasets?.length}
          </span>
          <div className="flex items-center gap-1">
            {Array.from({ length: notebookExport?.datasets?.length || 0 }).map((_, i) => {
              const mapping = datasetMappings.get(i)
              return (
                <div
                  key={i}
                  className={`w-2 h-2 rounded-full ${
                    mapping?.validated
                      ? 'bg-green-500'
                      : mapping?.skipped
                      ? 'bg-gray-500'
                      : i === currentDatasetIndex
                      ? 'bg-brand-orange'
                      : 'bg-[#404040]'
                  }`}
                />
              )
            })}
          </div>
        </div>

        {/* Current Dataset Info */}
        <div className="p-4 bg-[#252525] rounded-lg border border-[#333] flex-1 overflow-hidden flex flex-col">
          <div className="flex items-center gap-2 mb-3">
            <Database className="w-4 h-4 text-brand-orange" />
            <span className="text-white font-medium">{currentDataset.original_name}</span>
            <span className="text-xs text-gray-500 bg-[#333] px-2 py-0.5 rounded">
              {typeDisplayMap[currentDataset.type] || currentDataset.type}
            </span>
          </div>

          <p className="text-xs text-gray-400 mb-3">
            {currentDataset.queries.length} saved quer{currentDataset.queries.length !== 1 ? 'ies' : 'y'}
          </p>

          {/* Connection Selection or Creation Form */}
          <div className="mb-3 flex-1">
            {loadingConnections || loadingDatasources ? (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="w-5 h-5 text-gray-400 animate-spin" />
              </div>
            ) : !showConnectionForm && compatibleDatasources.length > 0 ? (
              // Show custom dropdown with optional recommendation banner
              <div className="space-y-3">
                {/* Show recommendation banner if name match exists */}
                {nameMatchedDatasource && (
                  <div className="flex items-center gap-2 text-green-400 text-sm bg-green-400/10 py-2 px-3 rounded-lg">
                    <Check className="w-4 h-4" />
                    Recommended: "{nameMatchedDatasource.name}" matched by name
                  </div>
                )}
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm text-gray-400">Select datasource:</label>
                  <button
                    onClick={() => {
                      if (isFileBasedExportType(currentDataset.type)) {
                        handleOpenConnectionDialog()
                      } else {
                        setShowConnectionForm(true)
                      }
                    }}
                    className="text-xs text-brand-orange hover:text-brand-orange-hover flex items-center gap-1"
                  >
                    <Plus className="w-3 h-3" />
                    Create new
                  </button>
                </div>

                {/* Custom Dropdown Button */}
                <button
                  ref={dropdownButtonRef}
                  onClick={() => setIsDropdownOpen(!isDropdownOpen)}
                  className="w-full p-3 rounded-lg border-2 border-[#404040] bg-[#252525] hover:border-[#555555] transition-all text-left"
                >
                  {selectedConnectionId ? (
                    <div className="flex items-center justify-between">
                      <span className="text-white text-sm font-medium truncate">
                        {datasources.find(ds => ds.id === selectedConnectionId)?.name || 'Select a datasource...'}
                      </span>
                      <div className="flex items-center gap-2">
                        {(() => {
                          const selected = datasources.find(ds => ds.id === selectedConnectionId)
                          return selected ? (
                            <>
                              {selected.source_type === 'dataset' && selected.files_count && (
                                <span className="text-[#aaaaaa] text-xs bg-[#333333] px-2 py-0.5 rounded">
                                  {selected.files_count} file{selected.files_count > 1 ? 's' : ''}
                                </span>
                              )}
                              <span className="text-[#aaaaaa] text-xs">
                                {selected.source_type === 'dataset' ? 'File' : selected.type}
                              </span>
                            </>
                          ) : null
                        })()}
                        <ChevronDown className={`w-4 h-4 text-gray-400 transition-transform ${isDropdownOpen ? 'rotate-180' : ''}`} />
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-center justify-between">
                      <span className="text-gray-500 text-sm">Select a datasource...</span>
                      <ChevronDown className={`w-4 h-4 text-gray-400 transition-transform ${isDropdownOpen ? 'rotate-180' : ''}`} />
                    </div>
                  )}
                </button>

                {/* Dropdown Menu Portal */}
                {isDropdownOpen && createPortal(
                  <div
                    data-dropdown-menu
                    style={{
                      position: 'fixed',
                      top: `${dropdownPosition.top}px`,
                      left: `${dropdownPosition.left}px`,
                      width: `${dropdownPosition.width}px`,
                      zIndex: 99999,
                      pointerEvents: 'auto',
                    }}
                    className="mt-1 bg-[#1a1a1a] border-2 border-[#404040] rounded-lg shadow-xl"
                    onWheel={(e) => {
                      // Allow wheel events to propagate to the scrollable child
                      e.stopPropagation()
                    }}
                  >
                    <div
                      className="space-y-2 p-2 max-h-[220px] overflow-y-auto custom-scrollbar"
                      style={{
                        overscrollBehavior: 'contain',
                        touchAction: 'pan-y',
                      }}
                      onWheel={(e) => {
                        // Prevent the event from bubbling up to parent containers
                        e.stopPropagation()
                      }}
                    >
                      {compatibleDatasources
                        .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
                        .map((datasource) => {
                          const isSelected = selectedConnectionId === datasource.id
                          return (
                            <div
                              key={datasource.id}
                              onClick={(e) => {
                                e.preventDefault()
                                e.stopPropagation()
                                setSelectedConnectionId(datasource.id)
                                setTestResult(null)
                                setIsDropdownOpen(false)
                                // Reset validated state when connection changes
                                const newMappings = new Map(datasetMappings)
                                const currentMapping = newMappings.get(currentDatasetIndex)
                                if (currentMapping) {
                                  newMappings.set(currentDatasetIndex, {
                                    ...currentMapping,
                                    connection_id: datasource.id,
                                    validated: false,
                                  })
                                  setDatasetMappings(newMappings)
                                }
                              }}
                              className={`p-3 rounded-lg border-2 cursor-pointer transition-all ${
                                isSelected
                                  ? 'bg-brand-orange/10 border-brand-orange'
                                  : 'bg-[#252525] border-[#404040] hover:border-[#555555]'
                              }`}
                              style={{ pointerEvents: 'auto' }}
                            >
                              <div className="flex items-center justify-between">
                                <span className="text-white text-sm font-medium truncate">
                                  {datasource.name || 'Unknown Datasource'}
                                </span>
                                <div className="flex items-center gap-2">
                                  {datasource.source_type === 'dataset' && datasource.files_count && (
                                    <span className="text-[#aaaaaa] text-xs bg-[#333333] px-2 py-0.5 rounded">
                                      {datasource.files_count} file{datasource.files_count > 1 ? 's' : ''}
                                    </span>
                                  )}
                                  <span className="text-[#aaaaaa] text-xs">
                                    {datasource.source_type === 'dataset' ? 'File' : datasource.type}
                                  </span>
                                </div>
                              </div>
                            </div>
                          )
                        })}
                    </div>
                  </div>,
                  document.body
                )}
              </div>
            ) : showConnectionForm && exportToInternalType[currentDataset.type] ? (
              // Inline connection creation form
              <div className="space-y-3 p-3 bg-[#1a1a1a] rounded-lg border border-[#404040]">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm text-white font-medium flex items-center gap-2">
                    <Plus className="w-4 h-4 text-brand-orange" />
                    Create {typeDisplayMap[currentDataset.type]} Connection
                  </span>
                  {compatibleDatasources.length > 0 && (
                    <button
                      onClick={() => setShowConnectionForm(false)}
                      className="text-xs text-gray-400 hover:text-white"
                    >
                      Use existing
                    </button>
                  )}
                </div>

                {/* Connection Name */}
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Connection Name *</label>
                  <input
                    type="text"
                    value={connectionConfig.name}
                    onChange={(e) => setConnectionConfig(prev => ({ ...prev, name: e.target.value }))}
                    placeholder={`My ${typeDisplayMap[currentDataset.type]} Connection`}
                    className="w-full px-2 py-1.5 text-sm bg-[#252525] border border-[#404040] rounded text-white placeholder-gray-500 focus:outline-none focus:border-brand-orange"
                    disabled={isCreatingConnection}
                  />
                </div>

                {/* MongoDB: Connection String */}
                {exportToInternalType[currentDataset.type] === 'mongo' && (
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">Connection String *</label>
                    <input
                      type="text"
                      value={connectionConfig.connectionString}
                      onChange={(e) => setConnectionConfig(prev => ({ ...prev, connectionString: e.target.value }))}
                      placeholder="mongodb://username:password@host:port/database"
                      className="w-full px-2 py-1.5 text-sm bg-[#252525] border border-[#404040] rounded text-white placeholder-gray-500 focus:outline-none focus:border-brand-orange font-mono"
                      disabled={isCreatingConnection}
                    />
                  </div>
                )}

                {/* SQLite: Database Path */}
                {exportToInternalType[currentDataset.type] === 'sqlite' && (
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">Database File Path *</label>
                    <input
                      type="text"
                      value={connectionConfig.database}
                      onChange={(e) => setConnectionConfig(prev => ({ ...prev, database: e.target.value }))}
                      placeholder="/path/to/database.db"
                      className="w-full px-2 py-1.5 text-sm bg-[#252525] border border-[#404040] rounded text-white placeholder-gray-500 focus:outline-none focus:border-brand-orange font-mono"
                      disabled={isCreatingConnection}
                    />
                  </div>
                )}

                {/* PostgreSQL, MySQL, MSSQL: Host/Port/Database/User/Password */}
                {['pg', 'mysql', 'mssql'].includes(exportToInternalType[currentDataset.type] || '') && (
                  <>
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="block text-xs text-gray-400 mb-1">Host *</label>
                        <input
                          type="text"
                          value={connectionConfig.host}
                          onChange={(e) => setConnectionConfig(prev => ({ ...prev, host: e.target.value }))}
                          placeholder="localhost"
                          className="w-full px-2 py-1.5 text-sm bg-[#252525] border border-[#404040] rounded text-white placeholder-gray-500 focus:outline-none focus:border-brand-orange"
                          disabled={isCreatingConnection}
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-gray-400 mb-1">Port *</label>
                        <input
                          type="text"
                          value={connectionConfig.port}
                          onChange={(e) => setConnectionConfig(prev => ({ ...prev, port: e.target.value }))}
                          placeholder={getDefaultPort(currentDataset.type)}
                          className="w-full px-2 py-1.5 text-sm bg-[#252525] border border-[#404040] rounded text-white placeholder-gray-500 focus:outline-none focus:border-brand-orange"
                          disabled={isCreatingConnection}
                        />
                      </div>
                    </div>
                    <div>
                      <label className="block text-xs text-gray-400 mb-1">Database *</label>
                      <input
                        type="text"
                        value={connectionConfig.database}
                        onChange={(e) => setConnectionConfig(prev => ({ ...prev, database: e.target.value }))}
                        placeholder="database_name"
                        className="w-full px-2 py-1.5 text-sm bg-[#252525] border border-[#404040] rounded text-white placeholder-gray-500 focus:outline-none focus:border-brand-orange"
                        disabled={isCreatingConnection}
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="block text-xs text-gray-400 mb-1">User *</label>
                        <input
                          type="text"
                          value={connectionConfig.user}
                          onChange={(e) => setConnectionConfig(prev => ({ ...prev, user: e.target.value }))}
                          placeholder="username"
                          className="w-full px-2 py-1.5 text-sm bg-[#252525] border border-[#404040] rounded text-white placeholder-gray-500 focus:outline-none focus:border-brand-orange"
                          disabled={isCreatingConnection}
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-gray-400 mb-1">Password *</label>
                        <input
                          type="password"
                          value={connectionConfig.password}
                          onChange={(e) => setConnectionConfig(prev => ({ ...prev, password: e.target.value }))}
                          placeholder="password"
                          className="w-full px-2 py-1.5 text-sm bg-[#252525] border border-[#404040] rounded text-white placeholder-gray-500 focus:outline-none focus:border-brand-orange"
                          disabled={isCreatingConnection}
                        />
                      </div>
                    </div>
                  </>
                )}

                {/* Error message */}
                {connectionFormError && (
                  <div className="flex items-center gap-2 text-red-400 text-xs bg-red-400/10 py-1.5 px-2 rounded">
                    <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
                    {connectionFormError}
                  </div>
                )}

                {/* Create button */}
                <button
                  onClick={handleCreateConnection}
                  disabled={isCreatingConnection}
                  className="w-full px-3 py-2 text-sm font-medium bg-brand-orange hover:bg-brand-orange-hover text-white rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  {isCreatingConnection ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Creating...
                    </>
                  ) : (
                    <>
                      <Plus className="w-4 h-4" />
                      Create Connection
                    </>
                  )}
                </button>
              </div>
            ) : (
              // No compatible datasources - show button to add
              <div className="space-y-3 p-3 bg-[#1a1a1a] rounded-lg border border-[#404040]">
                <div className="text-sm text-gray-400">
                  No compatible {typeDisplayMap[currentDataset.type] || currentDataset.type} datasource found.
                </div>
                <p className="text-xs text-gray-500">
                  {isFileBasedExportType(currentDataset.type)
                    ? `This dataset requires uploading ${typeDisplayMap[currentDataset.type] || currentDataset.type} files to match the original data structure.`
                    : `Create a new ${typeDisplayMap[currentDataset.type] || currentDataset.type} connection to import this dataset.`}
                </p>
                <button
                  onClick={() => {
                    if (isFileBasedExportType(currentDataset.type)) {
                      handleOpenConnectionDialog()
                    } else {
                      setShowConnectionForm(true)
                    }
                  }}
                  className="w-full px-3 py-2 text-sm font-medium bg-brand-orange hover:bg-brand-orange-hover text-white rounded transition-colors flex items-center justify-center gap-2"
                >
                  <Plus className="w-4 h-4" />
                  Add {typeDisplayMap[currentDataset.type] || currentDataset.type} Datasource
                </button>
              </div>
            )}
          </div>

          {/* Test Query Section */}
          {selectedConnectionId && currentDataset.queries.length > 0 && (
            <div className="mb-3">
              <label className="block text-xs text-gray-500 mb-1">Test query:</label>
              <code className="block text-xs text-gray-400 bg-[#1a1a1a] p-2 rounded overflow-x-auto overflow-y-auto custom-scrollbar whitespace-pre-wrap max-h-20">
                {currentDataset.queries[0].query.substring(0, 200)}
                {currentDataset.queries[0].query.length > 200 ? '...' : ''}
              </code>

              <div className="flex items-center gap-2 mt-2">
                <button
                  onClick={handleTestQuery}
                  disabled={testingQuery || currentMapping?.validated}
                  className="px-3 py-1.5 text-sm bg-[#333] hover:bg-[#404040] text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
                >
                  {testingQuery ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      Testing...
                    </>
                  ) : (
                    <>
                      <Play className="w-3.5 h-3.5" />
                      Run Test
                    </>
                  )}
                </button>

                {testResult && (
                  <span
                    className={`text-sm flex items-center gap-1 ${
                      testResult.success ? 'text-green-400' : 'text-red-400'
                    }`}
                  >
                    {testResult.success ? (
                      <>
                        <Check className="w-4 h-4" />
                        Connected
                      </>
                    ) : (
                      <>
                        <X className="w-4 h-4" />
                        {testResult.error || 'Failed'}
                      </>
                    )}
                  </span>
                )}
              </div>
            </div>
          )}

          {/* Status Badges */}
          {currentMapping?.validated && (
            <div className="flex items-center gap-2 text-green-400 text-sm bg-green-400/10 py-2 px-3 rounded-lg">
              <Check className="w-4 h-4" />
              Connection validated
            </div>
          )}
          {currentMapping?.skipped && (
            <div className="flex items-center gap-2 text-gray-400 text-sm bg-gray-400/10 py-2 px-3 rounded-lg">
              <SkipForward className="w-4 h-4" />
              Dataset skipped
            </div>
          )}
        </div>

        {/* Navigation Buttons */}
        <div className="flex items-center justify-between pt-2 border-t border-[#333]">
          <button
            onClick={handlePrevDataset}
            disabled={currentDatasetIndex === 0}
            className="px-3 py-2 text-sm text-gray-400 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1"
          >
            <ChevronLeft className="w-4 h-4" />
            Previous
          </button>

          <div className="flex items-center gap-2">
            <button
              onClick={handleSkipDataset}
              disabled={currentMapping?.validated}
              className="px-3 py-2 text-sm text-gray-400 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1"
            >
              <SkipForward className="w-4 h-4" />
              Skip
            </button>

            {currentDatasetIndex < (notebookExport?.datasets?.length || 0) - 1 ? (
              <button
                onClick={handleNextDataset}
                disabled={!currentMapping?.validated && !currentMapping?.skipped}
                className="px-4 py-2 text-sm font-medium bg-brand-orange hover:bg-brand-orange-hover text-white rounded-lg disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1"
              >
                Next
                <ChevronRight className="w-4 h-4" />
              </button>
            ) : (
              <button
                onClick={handleImport}
                disabled={!canImport}
                className="px-4 py-2 text-sm font-medium bg-brand-orange hover:bg-brand-orange-hover text-white rounded-lg disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1"
              >
                <Download className="w-4 h-4" />
                Import
              </button>
            )}
          </div>
        </div>

        {/* Import Error */}
        {importError && (
          <div className="flex items-center gap-2 text-red-400 text-sm bg-red-400/10 py-2 px-3 rounded-lg">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            {importError}
          </div>
        )}
      </div>
    )}

    {/* Step 3: Importing */}
    {step === 'importing' && (
      <div className="flex flex-col items-center justify-center py-12">
        <Loader2 className="w-12 h-12 text-brand-orange animate-spin mb-4" />
        <p className="text-white font-medium">Importing notebook...</p>
        <p className="text-sm text-gray-400 mt-1">This may take a moment</p>
      </div>
    )}

    {/* Step 4: Complete */}
    {step === 'complete' && importResult && (
      <div className="space-y-4">
        <div className="flex flex-col items-center justify-center py-8">
          <div className="w-12 h-12 rounded-full bg-green-500/20 flex items-center justify-center mb-4">
            <Check className="w-6 h-6 text-green-400" />
          </div>
          <h3 className="text-white font-medium text-lg mb-1">Import Successful!</h3>
          <p className="text-sm text-gray-400 text-center">
            Your notebook has been imported successfully.
          </p>
        </div>

        {/* Import Summary */}
        <div className="p-4 bg-[#252525] rounded-lg border border-[#333]">
          <h4 className="text-sm font-medium text-white mb-3">Import Summary</h4>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-400">Datasets:</span>
              <span className="text-white">{importResult.imported.datasets}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Queries:</span>
              <span className="text-white">{importResult.imported.queries}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Messages:</span>
              <span className="text-white">{importResult.imported.messages}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Dashboards:</span>
              <span className="text-white">{importResult.imported.dashboards}</span>
            </div>
            {importResult.skipped_datasets > 0 && (
              <div className="flex justify-between col-span-2">
                <span className="text-gray-400">Skipped Datasets:</span>
                <span className="text-yellow-400">{importResult.skipped_datasets}</span>
              </div>
            )}
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex gap-3">
          <button
            onClick={() => onOpenChange(false)}
            className="flex-1 px-4 py-2.5 text-sm font-medium bg-[#333] hover:bg-[#404040] text-white rounded-lg transition-colors"
          >
            Close
          </button>
          <button
            onClick={handleGoToNotebook}
            className="flex-1 px-4 py-2.5 text-sm font-medium bg-brand-orange hover:bg-brand-orange-hover text-white rounded-lg transition-colors flex items-center justify-center gap-2"
          >
            Open Notebook
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    )}
  </div>
      </DialogContent>

      {/* DatabaseConnectionDialog for file-based datasets */}
      <DatabaseConnectionDialog
  open={showConnectionDialog}
  onOpenChange={setShowConnectionDialog}
  mode={connectionDialogMode}
  datasources={datasources}
  selectedConnectionId={selectedConnectionId || undefined}
  onConnectionSelect={(id) => setSelectedConnectionId(id)}
  onConfirmConnection={() => {
    setShowConnectionDialog(false)
  }}
  onCreateConnection={handleCreateDatasource}
  title="Add Datasource"
  submitButtonText="Create Datasource"
  showPreviousConnectionsOption={false}
  isLoading={isCreatingDatasource}
      />
    </Dialog>
  )
}
