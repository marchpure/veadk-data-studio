import { useState, useRef, useMemo, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { Button } from '../components/ui/button'
import { Card } from '../components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Trash2, Loader2, Database, Pencil, Upload, FileText, X, Search, Link as LinkIcon, Leaf, Cylinder, Server, HardDrive, Users, Lock, Cloud, ChevronDown, ChevronRight, CheckCircle2, AlertCircle, Network, ShieldAlert } from 'lucide-react'
import { useDatasources, useCreateDBConnection, useDeleteDBConnection, useUploadMultipleFiles, useUploadFromURL, useConnectorDefinitions, useCreateSourceResource, useCreatePdfSourceResource, useSourceOverview, useSourceResourceProcessing, sourceOverviewKeys } from '../hooks/useDBConnections'
import { ApiService, type ConnectionCreateRequest, type ConnectionType, type Datasource, type DatabricksCatalog, type DatabricksOAuthTokens, type DatabricksWarehouse, type FileType, type ConnectorDefinition, type SourceOverviewItem, type SourceResource, type SourceResourceProcessing } from '../services/api'
import { SourceConnectorImportPanel } from '../components/SourceConnectorImportPanel'
import { showToast } from '../utils/toast'
import { useStore } from '../stores/useStore'
import { useScopes } from '../hooks/useScopes'
import { useAppConfig } from '../hooks/useAppConfig'
import { DatabricksOAuthSettings } from '../components/databricks/DatabricksOAuthSettings'
import { isTauriApp, openExternalUrl } from '../lib/tauri-api'

type DatabricksPair = { catalog: string; schema: string | null }
const pairKey = (p: DatabricksPair) => `${p.catalog}::${p.schema ?? '*'}`
type SourceConnectorCreateType = `connector:${string}`
type DatasourceCreateType = ConnectionType | 'upload' | 'url' | 'pdf' | 'web' | SourceConnectorCreateType
type SourceInventoryTab = 'all' | 'needs_attention'
type AddSourceFamilyId = 'files' | 'business_docs' | 'databases' | 'warehouses' | 'object_storage' | 'web' | 'api'

type AddSourceOption = {
  id: DatasourceCreateType | `planned:${string}`
  label: string
  family: AddSourceFamilyId
  icon: typeof Upload
  availability: 'available' | 'beta' | 'planned'
  outputs: Array<'Context' | 'Dataset' | 'Semantic-ready' | 'Dashboard-ready'>
  description: string
  limitations?: string[]
  modelingModes?: string[]
  connector?: ConnectorDefinition
}

const isSourceConnectorType = (value: string): value is SourceConnectorCreateType => value.startsWith('connector:')
const isPlannedSourceOption = (value: string): value is `planned:${string}` => value.startsWith('planned:')
const sourceConnectorId = (value: DatasourceCreateType): string | null =>
  isSourceConnectorType(value) ? value.slice('connector:'.length) : null
const isDirectSourceResourceType = (value: DatasourceCreateType) => value === 'pdf' || value === 'web'
const needsAttentionStates = new Set(['auth', 'permission', 'parse', 'index', 'stale', 'policy'])

const directSourceProcessingSteps = [
  { id: 'capture', label: 'Capture' },
  { id: 'parse', label: 'Parse' },
  { id: 'detect', label: 'Detect tables' },
  { id: 'normalize', label: 'Normalize dataset' },
  { id: 'index', label: 'Index context' },
  { id: 'suggest', label: 'Generate semantic suggestions' },
  { id: 'ready', label: 'Ready' },
] as const

const directSourceProgressIndex = (
  resource: SourceResource,
  processing?: SourceResourceProcessing,
) => {
  if (resource.status !== 'ready' || processing?.stage === 'failed') return -1
  if (processing?.stage === 'waiting_for_connector') return 0
  if (processing?.stage === 'captured') return 1
  if (processing?.stage === 'indexed') return directSourceProcessingSteps.length - 1
  if (resource.projected_dataset_id) return 5
  if (resource.latest_snapshot_id) return 4
  return 1
}

const directSourceProcessingTone = (
  resource: SourceResource,
  processing?: SourceResourceProcessing,
) => {
  if (resource.status !== 'ready' || processing?.stage === 'failed') return 'failed'
  if (processing?.stage === 'indexed') return 'ready'
  return 'processing'
}

const directSourceResourceLabel = (type?: string | null) => {
  switch (type) {
    case 'pdf':
      return 'PDF'
    case 'file':
      return 'File'
    case 'web':
      return 'Web'
    default:
      return type?.replace(/_/g, ' ') || 'Source'
  }
}

const addSourceFamilies: Array<{
  id: AddSourceFamilyId
  label: string
  description: string
  icon: typeof Upload
}> = [
  { id: 'files', label: 'Files', description: 'PDF, CSV, Excel and local file imports', icon: Upload },
  { id: 'business_docs', label: 'Business docs', description: 'Feishu/Lark documents, sheets and bases', icon: FileText },
  { id: 'databases', label: 'Databases', description: 'Operational SQL and local databases', icon: Database },
  { id: 'warehouses', label: 'Warehouses', description: 'Databricks and lakehouse sources', icon: Server },
  { id: 'object_storage', label: 'Object storage', description: 'Buckets, prefixes and objects', icon: HardDrive },
  { id: 'web', label: 'Web', description: 'URLs and governed web capture', icon: LinkIcon },
  { id: 'api', label: 'API / More', description: 'Planned SaaS and SDK connectors', icon: Cloud },
]

const connectorCategoryFamily = (category: string): AddSourceFamilyId => {
  if (category === 'documents') return 'business_docs'
  if (category === 'object_storage') return 'object_storage'
  if (category === 'data_lake') return 'warehouses'
  if (category === 'databases') return 'databases'
  return 'api'
}

const connectorModeLabel = (mode: string): string => {
  switch (mode) {
    case 'context_assisted':
      return 'Context-assisted'
    case 'projection':
      return 'Projection'
    case 'relational':
      return 'Relational'
    case 'warehouse':
      return 'Warehouse'
    case 'business_object':
      return 'Business object'
    case 'event':
      return 'Event'
    default:
      return mode.replace(/_/g, ' ')
  }
}

const readinessGateSummary = (connector?: ConnectorDefinition): string | null => {
  if (!connector?.readiness_gates?.length) return null
  const passed = connector.readiness_gates.filter(gate => gate.status === 'passed').length
  return `${passed}/${connector.readiness_gates.length} gates`
}

const missingReadinessGates = (connector?: ConnectorDefinition) =>
  connector?.readiness_gates?.filter(gate => gate.status !== 'passed') || []

export default function DatabasesPage() {
  const queryClient = useQueryClient()
  const openSidebar = useStore(state => state.openSidebar)
  const setActiveSection = useStore(state => state.setActiveSection)
  const setSelectedDatasource = useStore(state => state.setSelectedDatasource)
  const { canCreateDatasource, canEditDatasource, canDeleteDatasource } = useScopes()
  const { isSelfHosted } = useAppConfig()

  const showSharingFeatures = !isTauriApp() && isSelfHosted

  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [showUploadDialog, setShowUploadDialog] = useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [connectionToDelete, setConnectionToDelete] = useState<Datasource | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [inventoryTab, setInventoryTab] = useState<SourceInventoryTab>('all')
  const [csvFile, setCsvFile] = useState<File | null>(null)
  const [csvFiles, setCsvFiles] = useState<File[]>([])
  const [fileAliases, setFileAliases] = useState<Record<string, string>>({})
  const [fileType, setFileType] = useState<'csv' | 'excel' | 'parquet' | 'json'>('csv')
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Upload dialog states
  const [uploadFiles, setUploadFiles] = useState<File[]>([])
  const [uploadFileAliases, setUploadFileAliases] = useState<Record<string, string>>({})
  const [uploadFileType, setUploadFileType] = useState<'csv' | 'excel' | 'parquet' | 'json' | ''>('')
  const [uploadConnectionName, setUploadConnectionName] = useState('')
  const [isDragging, setIsDragging] = useState(false)
  const uploadFileInputRef = useRef<HTMLInputElement>(null)

  // URL upload states
  const [uploadMode, setUploadMode] = useState<'file' | 'url'>('file')
  const [uploadURLs, setUploadURLs] = useState<string[]>([''])
  const [urlAbortController, setUrlAbortController] = useState<AbortController | null>(null)
  const [pdfSourceFile, setPdfSourceFile] = useState<File | null>(null)
  const [webSourceUrl, setWebSourceUrl] = useState('')
  const [directSourceResult, setDirectSourceResult] = useState<SourceResource | null>(null)
  const sourceResourceFileInputRef = useRef<HTMLInputElement>(null)

  // Form state for create dialog
  const [selectedFamily, setSelectedFamily] = useState<AddSourceFamilyId>('files')
  const [selectedPlannedOption, setSelectedPlannedOption] = useState<AddSourceOption | null>(null)
  const [selectedType, setSelectedType] = useState<DatasourceCreateType>('upload')
  const [connectionConfig, setConnectionConfig] = useState({
    name: '',
    host: 'localhost',
    port: '5432',
    database: '',
    user: '',
    password: '',
    oracleServiceName: '',
    oracleSid: '',
    oracleSchema: '',
    connectionString: '',
    region: '',
    accessKeyId: '',
    secretAccessKey: '',
    endpointUrl: '',
    queryMode: 'partiql' as 'partiql' | 'native',
    serverHostname: '',
    httpPath: '',
    accessToken: '',
    catalog: '',
    databricksSchema: '',
  })

  const [togglingVisibility, setTogglingVisibility] = useState<string | null>(null)

  // Databricks 2-step wizard state
  const [databricksStep, setDatabricksStep] = useState<1 | 2>(1)
  const [discoveredCatalogs, setDiscoveredCatalogs] = useState<DatabricksCatalog[] | null>(null)
  const [discovering, setDiscovering] = useState(false)
  const [discoverError, setDiscoverError] = useState<string | null>(null)
  const [selectedPairs, setSelectedPairs] = useState<DatabricksPair[]>([])
  const [expandedCatalogs, setExpandedCatalogs] = useState<Set<string>>(new Set())
  const [databricksNamePrefix, setDatabricksNamePrefix] = useState('')
  const [batchProgress, setBatchProgress] = useState<{
    done: number
    total: number
    failures: Array<{ pair: DatabricksPair; error: string }>
  } | null>(null)
  const [databricksCatalogFilter, setDatabricksCatalogFilter] = useState('')

  const [databricksOAuthConfigured, setDatabricksOAuthConfigured] = useState<boolean>(!isSelfHosted)
  const [databricksOAuthCanConfigure, setDatabricksOAuthCanConfigure] = useState<boolean>(false)
  const [showManageDatabricksOAuth, setShowManageDatabricksOAuth] = useState<boolean>(false)
  const [oauthTokens, setOauthTokens] = useState<DatabricksOAuthTokens | null>(null)
  const oauthStateRef = useRef<string | null>(null)
  const oauthAbortRef = useRef<AbortController | null>(null)
  const [oauthSigningIn, setOauthSigningIn] = useState(false)
  const [oauthError, setOauthError] = useState<string | null>(null)
  const [warehouses, setWarehouses] = useState<DatabricksWarehouse[] | null>(null)
  const [selectedWarehouseId, setSelectedWarehouseId] = useState<string | null>(null)
  const [loadingWarehouses, setLoadingWarehouses] = useState(false)

  const refreshDatabricksAuthStatus = () => {
    ApiService.getDatabricksAuthStatus()
      .then(s => {
        setDatabricksOAuthConfigured(!!s.configured)
        setDatabricksOAuthCanConfigure(!!s.can_configure)
      })
      .catch(() => {
        setDatabricksOAuthConfigured(!isSelfHosted)
        setDatabricksOAuthCanConfigure(false)
      })
  }

  useEffect(() => {
    refreshDatabricksAuthStatus()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    setDirectSourceResult(null)
  }, [selectedType])

  const databricksTileVisible = !isSelfHosted || databricksOAuthConfigured || databricksOAuthCanConfigure

  // Use React Query hooks
  const { data: datasourcesResponse } = useDatasources()
  const { data: sourceOverviewResponse, isLoading: loading, error } = useSourceOverview()
  const createMutation = useCreateDBConnection()
  const deleteMutation = useDeleteDBConnection()
  const uploadMultipleFilesMutation = useUploadMultipleFiles()
  const uploadFromURLMutation = useUploadFromURL()
  const createSourceResourceMutation = useCreateSourceResource()
  const createPdfSourceResourceMutation = useCreatePdfSourceResource()
  const connectorDefinitionsQuery = useConnectorDefinitions()
  const connectorDefinitions = useMemo(() => connectorDefinitionsQuery.data?.items || [], [connectorDefinitionsQuery.data?.items])
  const datasourceById = useMemo(() => new Map((datasourcesResponse?.items || []).map(item => [item.id, item])), [datasourcesResponse?.items])
  const isCreatingAnyDatasource = createMutation.isPending || uploadMultipleFilesMutation.isPending || uploadFromURLMutation.isPending || createSourceResourceMutation.isPending || createPdfSourceResourceMutation.isPending
  const selectedConnectorDefinition = useMemo<ConnectorDefinition | undefined>(() => {
    const id = sourceConnectorId(selectedType)
    if (!id) return undefined
    return connectorDefinitions.find(item => item.id === id)
  }, [connectorDefinitions, selectedType])
  const addSourceOptions = useMemo<AddSourceOption[]>(() => {
    const baseOptions: AddSourceOption[] = [
      {
        id: 'upload',
        label: 'Upload files',
        family: 'files',
        icon: Upload,
        availability: 'available',
        outputs: ['Dataset', 'Semantic-ready'],
        description: 'CSV, Excel, Parquet and JSON files become normalized datasets.',
        modelingModes: ['Projection'],
      },
      {
        id: 'pdf',
        label: 'Files as Source',
        family: 'files',
        icon: FileText,
        availability: 'available',
        outputs: ['Context', 'Dataset'],
        description: 'Capture PDF, CSV, Excel, Docx and PPTX snapshots with evidence and optional dataset projection.',
        limitations: ['CSV and .xlsx/.xlsm Excel files can be projected into datasets; PDF, Docx and PPTX remain context-assisted unless tables are reviewed.'],
        modelingModes: ['Context-assisted', 'Projection'],
      },
      {
        id: 'url',
        label: 'Import file URL',
        family: 'files',
        icon: LinkIcon,
        availability: 'available',
        outputs: ['Dataset'],
        description: 'Download supported data files from public URLs.',
        modelingModes: ['Projection'],
      },
      {
        id: 'web',
        label: 'Web page',
        family: 'web',
        icon: LinkIcon,
        availability: 'available',
        outputs: ['Context'],
        description: 'Capture a public web page with SSRF and redirect protections.',
        limitations: ['Context-assisted only; cannot become a production metric fact source by itself.'],
        modelingModes: ['Context-assisted'],
      },
      { id: 'pg', label: 'PostgreSQL', family: 'databases', icon: Cylinder, availability: 'available', outputs: ['Dataset', 'Semantic-ready', 'Dashboard-ready'], description: 'Connect a PostgreSQL database for schema, sample and profile.', modelingModes: ['Relational'] },
      { id: 'mysql', label: 'MySQL', family: 'databases', icon: Database, availability: 'available', outputs: ['Dataset', 'Semantic-ready', 'Dashboard-ready'], description: 'Connect MySQL-compatible operational data.', modelingModes: ['Relational'] },
      { id: 'mssql', label: 'SQL Server', family: 'databases', icon: Server, availability: 'available', outputs: ['Dataset', 'Semantic-ready', 'Dashboard-ready'], description: 'Connect SQL Server data for semantic modeling.', modelingModes: ['Relational'] },
      { id: 'oracle', label: 'Oracle', family: 'databases', icon: Database, availability: 'available', outputs: ['Dataset', 'Semantic-ready', 'Dashboard-ready'], description: 'Connect Oracle schemas with service name or SID.', modelingModes: ['Relational'] },
      { id: 'sqlite', label: 'SQLite', family: 'databases', icon: HardDrive, availability: 'available', outputs: ['Dataset', 'Semantic-ready', 'Dashboard-ready'], description: 'Use a local SQLite file for repeatable demos and local data.', modelingModes: ['Relational'] },
      { id: 'mongo', label: 'MongoDB', family: 'databases', icon: Leaf, availability: 'beta', outputs: ['Dataset'], description: 'MongoDB remains a beta structured-source connector.', limitations: ['No production semantic publish gate yet.'], modelingModes: ['Business object'] },
      { id: 'dynamodb', label: 'DynamoDB', family: 'databases', icon: Cloud, availability: 'beta', outputs: ['Dataset'], description: 'DynamoDB remains a beta NoSQL connector path.', limitations: ['No production semantic publish gate yet.'], modelingModes: ['Business object'] },
    ]
    if (databricksTileVisible) {
      baseOptions.push({
        id: 'databricks',
        label: 'Databricks',
        family: 'warehouses',
        icon: Database,
        availability: 'available',
        outputs: ['Dataset', 'Semantic-ready', 'Dashboard-ready'],
        description: 'Wrap the existing Databricks OAuth and catalog picker as a Source.',
        modelingModes: ['Warehouse'],
      })
    }

    const connectorOptions = connectorDefinitions.map<AddSourceOption>(item => {
      const family = connectorCategoryFamily(item.category)
      const availability = item.availability
      return {
        id: availability === 'planned' ? `planned:${item.id}` : `connector:${item.id}`,
        label: item.display_name,
        family,
        icon: family === 'object_storage' ? HardDrive : family === 'business_docs' ? FileText : Cloud,
        availability,
        outputs: family === 'business_docs'
          ? ['Context', 'Dataset']
          : family === 'object_storage'
            ? ['Context', 'Dataset']
            : [],
        description: item.description || 'Connector is listed in the commercial catalog.',
        limitations: item.limitations,
        modelingModes: item.modeling_modes.map(connectorModeLabel),
        connector: item,
      }
    })

    return [...baseOptions, ...connectorOptions]
  }, [connectorDefinitions, databricksTileVisible])
  const selectedFamilyMeta = addSourceFamilies.find(item => item.id === selectedFamily) || addSourceFamilies[0]
  const currentFamilyOptions = addSourceOptions.filter(item => item.family === selectedFamily)
  const selectedConcreteOption = currentFamilyOptions.find(option => !isPlannedSourceOption(option.id) && option.id === selectedType)
  const hasActiveSetupForm = !selectedPlannedOption && !!selectedConcreteOption

  const formatDbType = (type: string): string => {
    switch (type) {
      case 'pg':
        return 'PostgreSQL'
      case 'mongo':
        return 'MongoDB'
      case 'mysql':
        return 'MySQL'
      case 'sqlite':
        return 'SQLite'
      case 'mssql':
        return 'SQL Server'
      case 'oracle':
        return 'Oracle'
      case 'dynamodb':
        return 'DynamoDB'
      case 'databricks':
        return 'Databricks'
      case 'csv':
        return 'CSV File'
      case 'excel':
        return 'Excel File'
      case 'parquet':
        return 'Parquet File'
    case 'json':
      return 'JSON File'
    case 'pdf':
      return 'PDF'
    case 'web':
      return 'Web Page'
    case 'feishu_doc':
      return 'Feishu Doc'
    case 'feishu_wiki':
      return 'Feishu Wiki'
    case 'feishu_sheet':
      return 'Feishu Sheet'
    case 'feishu_base':
      return 'Feishu Base'
    case 'tos_bucket':
      return 'TOS Bucket'
    case 'tos_prefix':
      return 'TOS Prefix'
    case 'tos_object':
      return 'TOS Object'
    case 'extracted_table':
      return 'Extracted Table'
    case 'duckdb':
      return 'DuckDB File Dataset'
    default:
      return type.toUpperCase()
  }
}

  const isNeedsAttention = (source: SourceOverviewItem) =>
    needsAttentionStates.has(source.attention_state) || !['Ready', 'Pending', 'Syncing', 'Analyzing'].includes(source.status)

  const sourceTypeLabel = (source: SourceOverviewItem): string => {
    if (source.resource_type) return formatDbType(source.resource_type)
    switch (source.family) {
      case 'documents':
        return 'Business docs'
      case 'warehouses':
        return 'Warehouse'
      case 'object_storage':
        return 'Object storage'
      default:
        return source.family.replace(/_/g, ' ')
    }
  }

  const sourceOwnerLabel = (source: SourceOverviewItem): string => {
    if (source.owner?.name) return source.owner.name
    if (source.owner?.id) return source.owner.id.slice(0, 8)
    return 'Workspace'
  }

  const parsedAssetsLabel = (source: SourceOverviewItem): string => {
    const counts = source.parsed_asset_counts
    const parts = [
      counts.files > 0 ? `${counts.files} file${counts.files === 1 ? '' : 's'}` : null,
      counts.tables > 0 ? `${counts.tables} table${counts.tables === 1 ? '' : 's'}` : null,
      counts.evidence > 0 ? `${counts.evidence} evidence` : null,
    ].filter(Boolean)
    return parts.length > 0 ? parts.join(' · ') : 'None'
  }

  const consumerLabel = (source: SourceOverviewItem): string => {
    const counts = source.consumer_counts
    const parts = [
      `${counts.semantic_models} semantic`,
      `${counts.dashboards} dashboard`,
      `${counts.notebooks} notebook`,
    ]
    return parts.join(' · ')
  }

  const primaryNextAction = (source: SourceOverviewItem): string | null => {
    const action = source.next_actions?.[0]
    return action ? action : null
  }

  const statusClassName = (source: SourceOverviewItem): string => {
    if (source.status === 'Ready') return 'bg-green-500/15 text-green-300 border-green-500/25'
    if (source.status === 'Pending' || source.status === 'Syncing' || source.status === 'Analyzing') {
      return 'bg-blue-500/15 text-blue-300 border-blue-500/25'
    }
    if (source.attention_state === 'auth' || source.attention_state === 'permission') {
      return 'bg-red-500/15 text-red-300 border-red-500/25'
    }
    return 'bg-amber-500/15 text-amber-300 border-amber-500/25'
  }

  const freshnessClassName = (source: SourceOverviewItem): string => {
    if (source.freshness_status === 'fresh') return 'text-green-300'
    if (source.freshness_status === 'stale') return 'text-amber-300'
    return 'text-gray-400'
  }

  const contextClassName = (source: SourceOverviewItem): string => {
    if (source.context_index_status === 'indexed') return 'text-green-300'
    if (source.context_index_status === 'failed') return 'text-red-300'
    if (source.context_index_status === 'indexing' || source.context_index_status === 'pending') return 'text-blue-300'
    return 'text-gray-500'
  }

  const datasourceForSource = (source: SourceOverviewItem): Datasource => {
    const existing = datasourceById.get(source.id)
    if (existing) return existing
    return {
      id: source.id,
      name: source.name,
      type: (source.resource_type || source.provider || 'duckdb') as Datasource['type'],
      source_type: source.source_kind,
      resource_type: source.resource_type as Datasource['resource_type'],
      status: source.status.toLowerCase().replace(/\s+/g, '_'),
      latest_snapshot_id: source.latest_snapshot_id,
      projected_dataset_id: source.projected_dataset_id,
      created_by: source.owner?.id,
      created_at: source.updated_at || source.created_at,
      is_public: source.visibility === 'team' || source.visibility === 'public',
    }
  }

  // Filter and sort sources from the commercial overview facade.
  const displaySources = (sourceOverviewResponse?.items || [])
    .filter(datasource => {
      if (inventoryTab === 'needs_attention' && !isNeedsAttention(datasource)) return false
      if (!searchQuery) return true
      const query = searchQuery.toLowerCase()
      return (
        (datasource.name || '').toLowerCase().includes(query) ||
        sourceTypeLabel(datasource).toLowerCase().includes(query) ||
        datasource.provider.toLowerCase().includes(query) ||
        datasource.status.toLowerCase().includes(query)
      )
    })
    .sort((a, b) => {
      // Sort by activity (most recent first)
      return new Date(b.updated_at || b.created_at).getTime() - new Date(a.updated_at || a.created_at).getTime()
    })
  const allSourceCount = sourceOverviewResponse?.total || 0
  const needsAttentionCount = (sourceOverviewResponse?.items || []).filter(isNeedsAttention).length

  // Validation for create form
  const isCreateFormValid = useMemo(() => {
    // Databricks wizard uses its own validation (name is auto-generated server-side).
    if (selectedType === 'databricks') {
      const signedIn = !!oauthTokens?.access_token
      const warehousePicked = !!selectedWarehouseId
      if (databricksStep === 1) return signedIn && warehousePicked
      return signedIn && warehousePicked && selectedPairs.length > 0
    }

    if (isSourceConnectorType(selectedType) || selectedType === 'pdf' || selectedType === 'web') {
      return true
    }

    // Connection name is always required
    if (!connectionConfig.name.trim()) return false

    // Validate based on connection type
    if (selectedType === 'mongo') {
      return connectionConfig.connectionString.trim().length > 0
    } else if (selectedType === 'sqlite') {
      return connectionConfig.database.trim().length > 0
    } else if (selectedType === 'dynamodb') {
      return (
        connectionConfig.region.trim().length > 0 &&
        connectionConfig.accessKeyId.trim().length > 0 &&
        connectionConfig.secretAccessKey.trim().length > 0
      )
    } else if (selectedType === 'oracle') {
      const hasServiceName = connectionConfig.oracleServiceName.trim().length > 0
      const hasSid = connectionConfig.oracleSid.trim().length > 0
      return (
        connectionConfig.host.trim().length > 0 &&
        connectionConfig.port.trim().length > 0 &&
        connectionConfig.user.trim().length > 0 &&
        connectionConfig.password.trim().length > 0 &&
        hasServiceName !== hasSid
      )
    } else {
      // PostgreSQL, MySQL, MSSQL
      return (
        connectionConfig.host.trim().length > 0 &&
        connectionConfig.port.trim().length > 0 &&
        connectionConfig.database.trim().length > 0 &&
        connectionConfig.user.trim().length > 0 &&
        connectionConfig.password.trim().length > 0
      )
    }
  }, [selectedType, connectionConfig, databricksStep, selectedPairs, oauthTokens, selectedWarehouseId])

  const resetDatabricksWizard = () => {
    if (oauthAbortRef.current) {
      oauthAbortRef.current.abort()
      oauthAbortRef.current = null
    }
    const pendingState = oauthStateRef.current
    if (pendingState) {
      ApiService.cancelDatabricksOAuth(pendingState).catch(() => {})
    }
    oauthStateRef.current = null
    setDatabricksStep(1)
    setDiscoveredCatalogs(null)
    setDiscovering(false)
    setDiscoverError(null)
    setSelectedPairs([])
    setExpandedCatalogs(new Set())
    setDatabricksNamePrefix('')
    setBatchProgress(null)
    setDatabricksCatalogFilter('')
    setOauthTokens(null)
    setOauthError(null)
    setOauthSigningIn(false)
    setWarehouses(null)
    setSelectedWarehouseId(null)
    setLoadingWarehouses(false)
  }

  useEffect(() => {
    return () => {
      if (oauthAbortRef.current) {
        oauthAbortRef.current.abort()
        oauthAbortRef.current = null
      }
      const pendingState = oauthStateRef.current
      if (pendingState) {
        ApiService.cancelDatabricksOAuth(pendingState).catch(() => {})
        oauthStateRef.current = null
      }
    }
  }, [])

  const loadWarehouses = async (host: string, token: string) => {
    setLoadingWarehouses(true)
    try {
      const ws = await ApiService.listDatabricksWarehouses(host, token)
      setWarehouses(ws)
      if (ws.length === 1) setSelectedWarehouseId(ws[0].id)
    } catch (err: any) {
      setOauthError(err?.message || 'Failed to list warehouses')
    } finally {
      setLoadingWarehouses(false)
    }
  }

  const normalizeDatabricksHost = (raw: string): string => {
    let h = raw.trim()
    const schemeIdx = h.indexOf('://')
    if (schemeIdx !== -1) h = h.slice(schemeIdx + 3)
    h = h.split('/')[0].split('?')[0]
    return h.trim().replace(/\.+$/, '')
  }

  const handleCancelDatabricksSignIn = () => {
    const pendingState = oauthStateRef.current
    if (oauthAbortRef.current) {
      oauthAbortRef.current.abort()
      oauthAbortRef.current = null
    }
    if (pendingState) {
      ApiService.cancelDatabricksOAuth(pendingState).catch(() => {})
    }
    oauthStateRef.current = null
    setOauthSigningIn(false)
    setOauthError(null)
  }

  const handleDatabricksSignIn = async () => {
    const normalizedHost = normalizeDatabricksHost(connectionConfig.serverHostname)
    if (!normalizedHost) {
      setOauthError('Enter your Databricks workspace URL first')
      return
    }
    if (normalizedHost !== connectionConfig.serverHostname) {
      setConnectionConfig(prev => ({ ...prev, serverHostname: normalizedHost }))
    }
    if (oauthAbortRef.current) {
      oauthAbortRef.current.abort()
    }
    const controller = new AbortController()
    oauthAbortRef.current = controller
    const { signal } = controller
    setOauthError(null)
    setOauthSigningIn(true)
    try {
      const { auth_url, state } = await ApiService.startDatabricksOAuth(normalizedHost)
      if (signal.aborted) return
      oauthStateRef.current = state
      await openExternalUrl(auth_url)
      if (signal.aborted) return

      const sleep = (ms: number) => new Promise<void>((resolve, reject) => {
        const timer = setTimeout(() => {
          signal.removeEventListener('abort', onAbort)
          resolve()
        }, ms)
        const onAbort = () => {
          clearTimeout(timer)
          reject(new DOMException('aborted', 'AbortError'))
        }
        signal.addEventListener('abort', onAbort, { once: true })
      })

      const deadline = Date.now() + 5 * 60 * 1000
      while (Date.now() < deadline) {
        await sleep(2000)
        if (signal.aborted) return
        try {
          const res = await ApiService.pollDatabricksOAuthResult(state)
          if (signal.aborted) return
          if (res.status === 'success' && res.tokens) {
            oauthStateRef.current = null
            setOauthTokens(res.tokens)
            setConnectionConfig(prev => ({ ...prev, serverHostname: res.tokens!.server_hostname }))
            await loadWarehouses(res.tokens.server_hostname, res.tokens.access_token)
            return
          }
        } catch (err: any) {
          if (signal.aborted) return
          console.warn('OAuth poll failed:', err?.message)
        }
      }
      if (!signal.aborted) setOauthError('Sign-in timed out. Please try again.')
    } catch (err: any) {
      if (err?.name === 'AbortError' || signal.aborted) return
      setOauthError(err?.message || 'Failed to start Databricks sign-in')
    } finally {
      if (!signal.aborted) {
        setOauthSigningIn(false)
      }
      if (oauthAbortRef.current === controller) {
        oauthAbortRef.current = null
      }
    }
  }

  const togglePair = (pair: DatabricksPair) => {
    setSelectedPairs(prev => {
      const key = pairKey(pair)
      const exists = prev.some(p => pairKey(p) === key)
      if (exists) return prev.filter(p => pairKey(p) !== key)
      const cleaned = pair.schema === null
        ? prev.filter(p => p.catalog !== pair.catalog)
        : prev.filter(p => !(p.catalog === pair.catalog && p.schema === null))
      return [...cleaned, pair]
    })
  }

  const isPairSelected = (pair: DatabricksPair) =>
    selectedPairs.some(p => pairKey(p) === pairKey(pair))

  const handleDatabricksDiscover = async () => {
    if (!oauthTokens || !selectedWarehouseId) return
    const warehouse = warehouses?.find(w => w.id === selectedWarehouseId)
    if (!warehouse) return
    setDiscoverError(null)
    setDiscovering(true)
    try {
      const res = await ApiService.discoverDatabricks({
        server_hostname: oauthTokens.server_hostname,
        access_token: oauthTokens.access_token,
        http_path: warehouse.http_path,
      })
      setDiscoveredCatalogs(res.catalogs)
      setConnectionConfig(prev => ({ ...prev, httpPath: warehouse.http_path }))
      setDatabricksStep(2)
    } catch (err: any) {
      setDiscoverError(err?.message || 'Failed to discover Databricks catalogs')
    } finally {
      setDiscovering(false)
    }
  }

  const handleDatabricksBatchCreate = async () => {
    if (selectedPairs.length === 0) return
    const pairs = selectedPairs
    const failures: Array<{ pair: DatabricksPair; error: string }> = []
    let done = 0
    setBatchProgress({ done: 0, total: pairs.length, failures: [] })

    for (const pair of pairs) {
      try {
        const prefix = databricksNamePrefix.trim()
        const suffix = `${pair.catalog}.${pair.schema ?? '*'}`
        const name = prefix ? `${prefix} · ${suffix}` : ''
        if (!oauthTokens) throw new Error('Not signed in to Databricks')
        await ApiService.createConnection({
          type: 'databricks',
          name: name || undefined,
          connection_obj: {
            server_hostname: oauthTokens.server_hostname,
            http_path: connectionConfig.httpPath,
            catalog: pair.catalog,
            schema: pair.schema ?? undefined,
            oauth: {
              access_token: oauthTokens.access_token,
              refresh_token: oauthTokens.refresh_token,
              expires_at: oauthTokens.expires_at,
              scope: oauthTokens.scope,
              server_hostname: oauthTokens.server_hostname,
            },
          },
        })
      } catch (err: any) {
        failures.push({ pair, error: err?.message || 'Unknown error' })
      }
      done += 1
      setBatchProgress({ done, total: pairs.length, failures: [...failures] })
    }

    const succeededCount = pairs.length - failures.length
    if (succeededCount > 0) {
      queryClient.invalidateQueries({ queryKey: ['datasources'] })
      queryClient.invalidateQueries({ queryKey: sourceOverviewKeys.all })
      showToast.success(`Created ${succeededCount} Databricks connection${succeededCount !== 1 ? 's' : ''}`)
    }
    if (failures.length === 0) {
      setShowCreateDialog(false)
      resetForm()
    } else {
      setSelectedPairs(failures.map(f => f.pair))
      showToast.error(`${failures.length} connection${failures.length !== 1 ? 's' : ''} failed`)
    }
  }

  const handleCreateConnection = async () => {
    // Validate connection name
    if (!connectionConfig.name.trim()) {
      alert('Please provide a connection name')
      return
    }

    let connectionObj: Record<string, any>

    if (selectedType === 'mongo') {
      // MongoDB uses user-provided connection string
      connectionObj = {
        connection_string: connectionConfig.connectionString
      }
    } else if (selectedType === 'sqlite') {
      // SQLite only needs the database file path
      connectionObj = {
        database: connectionConfig.database
      }
    } else if (selectedType === 'dynamodb') {
      connectionObj = {
        region: connectionConfig.region,
        access_key_id: connectionConfig.accessKeyId,
        secret_access_key: connectionConfig.secretAccessKey,
        endpoint_url: connectionConfig.endpointUrl || '',
        query_mode: connectionConfig.queryMode,
      }
    } else if (selectedType === 'databricks') {
      if (!oauthTokens) {
        alert('Sign in to Databricks first')
        return
      }
      connectionObj = {
        server_hostname: oauthTokens.server_hostname,
        http_path: connectionConfig.httpPath,
        catalog: connectionConfig.catalog || undefined,
        schema: connectionConfig.databricksSchema || undefined,
        oauth: {
          access_token: oauthTokens.access_token,
          refresh_token: oauthTokens.refresh_token,
          expires_at: oauthTokens.expires_at,
          scope: oauthTokens.scope,
          server_hostname: oauthTokens.server_hostname,
        },
      }
    } else if (selectedType === 'oracle') {
      const serviceName = connectionConfig.oracleServiceName.trim()
      const sid = connectionConfig.oracleSid.trim()
      if ((serviceName.length > 0) === (sid.length > 0)) {
        alert('Provide either an Oracle service name or SID, not both')
        return
      }
      connectionObj = {
        host: connectionConfig.host,
        port: parseInt(connectionConfig.port),
        service_name: serviceName || undefined,
        sid: sid || undefined,
        schema: connectionConfig.oracleSchema.trim() || undefined,
        user: connectionConfig.user,
        password: connectionConfig.password
      }
    } else {
      // PostgreSQL, MySQL, MSSQL - send components, backend builds URL with driver
      connectionObj = {
        host: connectionConfig.host,
        port: parseInt(connectionConfig.port),
        database: connectionConfig.database,
        user: connectionConfig.user,
        password: connectionConfig.password
      }
    }

    const connectionData: ConnectionCreateRequest = {
      type: selectedType as ConnectionType,
      name: connectionConfig.name,
      connection_obj: connectionObj
    }

    createMutation.mutate(connectionData, {
      onSuccess: () => {
        setShowCreateDialog(false)
        resetForm()
      }
    })
  }

  const resetForm = () => {
    setSelectedFamily('files')
    setSelectedPlannedOption(null)
    setSelectedType('upload')
    setConnectionConfig({
      name: '',
      host: 'localhost',
      port: '5432',
      database: '',
      user: '',
      password: '',
      oracleServiceName: '',
      oracleSid: '',
      oracleSchema: '',
      connectionString: '',
      region: '',
      accessKeyId: '',
      secretAccessKey: '',
      endpointUrl: '',
      queryMode: 'partiql',
      serverHostname: '',
      httpPath: '',
      accessToken: '',
      catalog: '',
      databricksSchema: '',
    })
    resetCSVForm()
    resetUploadForm()
    resetDatabricksWizard()
  }

  const handleDeleteClick = (datasource: Datasource) => {
    setConnectionToDelete(datasource)
    setDeleteDialogOpen(true)
  }

  const confirmDelete = async () => {
    if (!connectionToDelete) return

    // Handle deletion based on source type
    if (connectionToDelete.source_type === 'connection') {
      deleteMutation.mutate(connectionToDelete.connection_id!, {
        onSuccess: () => {
          // Invalidate notebook connections so it refetch
          queryClient.invalidateQueries({ queryKey: ['notebook-connections'] })
          setDeleteDialogOpen(false)
          setConnectionToDelete(null)
        },
      })
    } else if (connectionToDelete.source_type === 'source_resource') {
      try {
        await ApiService.deleteSourceResource(connectionToDelete.id)
        setDeleteDialogOpen(false)
        setConnectionToDelete(null)
        queryClient.invalidateQueries({ queryKey: ['datasources'] })
        queryClient.invalidateQueries({ queryKey: sourceOverviewKeys.all })
        showToast.success('Source resource deleted successfully')
      } catch (error: any) {
        console.error('Error deleting source resource:', error)
        showToast.error(`Failed to delete source resource: ${error.message}`)
      }
    } else {
      // Delete dataset
      try {
        await ApiService.deleteDataset(connectionToDelete.id)
        setDeleteDialogOpen(false)
        setConnectionToDelete(null)
        // Invalidate queries to refresh the list
        queryClient.invalidateQueries({ queryKey: ['datasources'] })
        queryClient.invalidateQueries({ queryKey: sourceOverviewKeys.all })
        // Invalidate notebook connections so it refetch
        queryClient.invalidateQueries({ queryKey: ['notebook-connections'] })
        showToast.success('File source deleted successfully')
      } catch (error: any) {
        console.error('Error deleting dataset:', error)
        showToast.error(`Failed to delete source: ${error.message}`)
      }
    }
  }

  const cancelDelete = () => {
    setDeleteDialogOpen(false)
    setConnectionToDelete(null)
  }

  const handleEditClick = (datasource: Datasource) => {
    if (datasource.source_type === 'source_resource') {
      return
    }
    setSelectedDatasource(datasource.id)
    setActiveSection('database')
    openSidebar('database')
  }

  const handleQuickToggleVisibility = async (datasource: Datasource) => {
    const newIsPublic = !datasource.is_public
    setTogglingVisibility(datasource.id)

    try {
      await ApiService.updateDatasourceVisibility(datasource.id, newIsPublic)
      queryClient.invalidateQueries({ queryKey: ['datasources'] })
      queryClient.invalidateQueries({ queryKey: sourceOverviewKeys.all })
      showToast.success(newIsPublic ? 'Source shared with team' : 'Source set to private')
    } catch (error: any) {
      console.error('Error toggling visibility:', error)
      showToast.error(`Failed to update visibility: ${error.message}`)
    } finally {
      setTogglingVisibility(null)
    }
  }

  const handleFamilyChange = (family: AddSourceFamilyId) => {
    setSelectedFamily(family)
    setSelectedPlannedOption(null)
    const firstAvailable = addSourceOptions.find(item => item.family === family && item.availability !== 'planned')
    if (firstAvailable && !isPlannedSourceOption(firstAvailable.id)) {
      handleTypeChange(firstAvailable.id)
      return
    }
    const firstPlanned = addSourceOptions.find(item => item.family === family && item.availability === 'planned')
    if (firstPlanned) {
      resetDatabricksWizard()
      setSelectedPlannedOption(firstPlanned)
    }
  }

  const handleSourceOptionChange = (option: AddSourceOption) => {
    if (isPlannedSourceOption(option.id) || option.availability === 'planned') {
      resetDatabricksWizard()
      setSelectedPlannedOption(option)
      return
    }
    setSelectedPlannedOption(null)
    handleTypeChange(option.id)
  }

  const handleTypeChange = (newType: DatasourceCreateType) => {
    resetDatabricksWizard()
    setSelectedType(newType)
    const defaultPorts: Record<string, string> = {
      pg: '5432',
      mysql: '3306',
      mssql: '1433',
      oracle: '1521',
      sqlite: '',
      mongo: '27017',
      dynamodb: '',
      csv: '',
      excel: '',
      parquet: '',
      json: '',
      pdf: '',
      web: '',
      upload: '',
      url: '',
    }
    setConnectionConfig(prev => ({
      ...prev,
      port: defaultPorts[newType] || '',
      connectionString: ''
    }))
  }

  const handleCSVFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = Array.from(e.target.files || [])

    if (selectedFiles.length === 0) return

    const allowedExtensions: Record<'csv' | 'excel' | 'parquet' | 'json', string[]> = {
      csv: ['.csv'],
      excel: ['.xlsx', '.xls'],
      parquet: ['.parquet'],
      json: ['.json']
    }
    const extensions = allowedExtensions[fileType]
    const typeLabel = fileType.toUpperCase()

    // Validate each file
    for (const file of selectedFiles) {
      const isValidExtension = extensions.some(ext => file.name.toLowerCase().endsWith(ext))
      if (!isValidExtension) {
        alert(`File "${file.name}" is not a ${typeLabel} file. Allowed extensions: ${extensions.join(', ')}`)
        return
      }
    }

    // If single file, use legacy single-file upload
    if (selectedFiles.length === 1) {
      setCsvFile(selectedFiles[0])
      setCsvFiles([])
      setFileAliases({})
    } else {
      // Multiple files - use multi-file upload
      setCsvFile(null)
      setCsvFiles(selectedFiles)

      // Auto-generate aliases from filenames
      const aliases: Record<string, string> = {}
      selectedFiles.forEach(file => {
        let alias = file.name
        extensions.forEach(ext => {
          if (alias.toLowerCase().endsWith(ext)) {
            alias = alias.slice(0, -ext.length)
          }
        })
        aliases[file.name] = alias
      })
      setFileAliases(aliases)
    }
  }

  const resetCSVForm = () => {
    setCsvFile(null)
    setCsvFiles([])
    setFileAliases({})
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
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

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
  }

  const truncateFilename = (filename: string, maxLength: number = 25): string => {
    if (filename.length <= maxLength) return filename
    const extension = filename.split('.').pop() || ''
    const nameWithoutExt = filename.substring(0, filename.lastIndexOf('.'))
    const truncatedName = nameWithoutExt.substring(0, maxLength - extension.length - 4) + '...'
    return extension ? `${truncatedName}.${extension}` : truncatedName
  }

  // Upload dialog handlers
  const handleUploadFilesDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(false)

    const droppedFiles = Array.from(e.dataTransfer.files)
    handleUploadFilesSelection(droppedFiles)
  }

  const handleUploadFilesChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = Array.from(e.target.files || [])
    handleUploadFilesSelection(selectedFiles)
  }

  const detectFileType = (filename: string): 'csv' | 'excel' | 'parquet' | 'json' | null => {
    const lowerName = filename.toLowerCase()
    if (lowerName.endsWith('.csv')) return 'csv'
    if (lowerName.endsWith('.xlsx') || lowerName.endsWith('.xls')) return 'excel'
    if (lowerName.endsWith('.parquet')) return 'parquet'
    if (lowerName.endsWith('.json')) return 'json'
    return null
  }

  const handleUploadFilesSelection = (selectedFiles: File[]) => {
    if (selectedFiles.length === 0) return

    const allowedExtensions: Record<'csv' | 'excel' | 'parquet' | 'json', string[]> = {
      csv: ['.csv'],
      excel: ['.xlsx', '.xls'],
      parquet: ['.parquet'],
      json: ['.json']
    }

    // Auto-detect file type from first file if no files uploaded yet
    let currentFileType = uploadFileType
    if (uploadFiles.length === 0 && selectedFiles.length > 0) {
      const detectedType = detectFileType(selectedFiles[0].name)
      if (detectedType) {
        currentFileType = detectedType
        setUploadFileType(detectedType)
      } else {
        alert(`Unable to detect file type from "${selectedFiles[0].name}". Supported: .csv, .xlsx, .xls, .parquet, .json`)
        return
      }
    }

    // Validate we have a file type
    if (!currentFileType) {
      alert('Please upload files to detect type')
      return
    }

    const extensions = allowedExtensions[currentFileType as 'csv' | 'excel' | 'parquet' | 'json']
    const typeLabel = currentFileType.toUpperCase()

    // Check for duplicate file names
    const existingFileNames = new Set(uploadFiles.map(f => f.name))
    const duplicates: string[] = []

    // Validate each file
    for (const file of selectedFiles) {
      const isValidExtension = extensions.some(ext => file.name.toLowerCase().endsWith(ext))
      if (!isValidExtension) {
        alert(`File "${file.name}" doesn't match detected type (${typeLabel}). All files must be ${extensions.join(' or ')} files.`)
        return
      }
      if (existingFileNames.has(file.name)) {
        duplicates.push(file.name)
      }
    }

    if (duplicates.length > 0) {
      alert(`The following file(s) are already added: ${duplicates.join(', ')}`)
      return
    }

    // Add files to existing files (instead of replacing)
    setUploadFiles(prev => [...prev, ...selectedFiles])

    // Auto-populate datasource name from first file if currently empty
    if (uploadConnectionName === '' && uploadFiles.length === 0) {
      let autoName = selectedFiles[0].name
      extensions.forEach(ext => {
        if (autoName.toLowerCase().endsWith(ext)) {
          autoName = autoName.slice(0, -ext.length)
        }
      })
      setUploadConnectionName(autoName)
    }

    // Auto-generate aliases from filenames and merge with existing aliases
    const newAliases: Record<string, string> = {}
    selectedFiles.forEach(file => {
      let alias = file.name
      extensions.forEach(ext => {
        if (alias.toLowerCase().endsWith(ext)) {
          alias = alias.slice(0, -ext.length)
        }
      })
      newAliases[file.name] = alias
    })
    setUploadFileAliases(prev => ({ ...prev, ...newAliases }))
  }

  const handleCreateDialogSubmit = async () => {
    if (!uploadConnectionName.trim()) {
      alert('Please provide a source name')
      return
    }

    if (selectedType === 'upload') {
      // File upload mode
      if (uploadFiles.length === 0) {
        alert('Please select at least one file')
        return
      }

      if (!uploadFileType) {
        alert('Please select files to detect type')
        return
      }

      uploadMultipleFilesMutation.mutate(
        { files: uploadFiles, name: uploadConnectionName, aliases: uploadFileAliases, fileType: uploadFileType as FileType },
        {
          onSuccess: () => {
            setShowCreateDialog(false)
            resetUploadForm()
          }
        }
      )
    } else if (selectedType === 'url') {
      // URL upload mode
      const validURLs = uploadURLs.filter(url => url.trim().length > 0)
      if (validURLs.length === 0) {
        alert('Please provide at least one URL')
        return
      }

      uploadFromURLMutation.mutate(
        {
          urls: validURLs,
          name: uploadConnectionName,
          fileType: uploadFileType || undefined,
        },
        {
          onSuccess: () => {
            setShowCreateDialog(false)
            resetUploadForm()
          }
        }
      )
    }
  }

  const handleUploadFilesSubmit = async () => {
    if (!uploadConnectionName.trim()) {
      alert('Please provide a connection name')
      return
    }

    if (uploadMode === 'file') {
      // File upload mode
      if (uploadFiles.length === 0) {
        alert('Please select at least one file')
        return
      }

      if (!uploadFileType) {
        alert('Please select files to detect type')
        return
      }

      uploadMultipleFilesMutation.mutate(
        { files: uploadFiles, name: uploadConnectionName, aliases: uploadFileAliases, fileType: uploadFileType as FileType },
        {
          onSuccess: () => {
            setShowUploadDialog(false)
            resetUploadForm()
          }
        }
      )
    } else {
      // URL upload mode
      const validURLs = uploadURLs.filter(url => url.trim().length > 0)
      if (validURLs.length === 0) {
        alert('Please provide at least one URL')
        return
      }

      // Create abort controller for this download
      const controller = new AbortController()
      setUrlAbortController(controller)

      uploadFromURLMutation.mutate(
        {
          urls: validURLs,
          name: uploadConnectionName,
          fileType: uploadFileType || undefined,
          signal: controller.signal
        },
        {
          onSuccess: () => {
            setShowUploadDialog(false)
            resetUploadForm()
            setUrlAbortController(null)
          },
          onError: () => {
            setUrlAbortController(null)
          }
        }
      )
    }
  }

  const resetUploadForm = () => {
    setUploadFiles([])
    setUploadFileAliases({})
    setUploadFileType('')
    setUploadConnectionName('')
    setUploadMode('file')
    setUploadURLs([''])
    setPdfSourceFile(null)
    setWebSourceUrl('')
    setDirectSourceResult(null)
    if (uploadFileInputRef.current) {
      uploadFileInputRef.current.value = ''
    }
    if (sourceResourceFileInputRef.current) {
      sourceResourceFileInputRef.current.value = ''
    }
  }

  const handlePdfSourceFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] || null
    if (!file) {
      setPdfSourceFile(null)
      return
    }
    if (!/\.(pdf|csv|xlsx|xlsm|docx|pptx)$/i.test(file.name)) {
      alert('Please select a PDF, CSV, Excel (.xlsx/.xlsm), Docx or PPTX file')
      event.target.value = ''
      setPdfSourceFile(null)
      return
    }
    setPdfSourceFile(file)
    if (!uploadConnectionName.trim()) {
      setUploadConnectionName(file.name.replace(/\.(pdf|csv|xlsx|xlsm|docx|pptx)$/i, ''))
    }
  }

  const handleCreateSourceResourceSubmit = async () => {
    if (!uploadConnectionName.trim()) {
      alert('Please provide a source name')
      return
    }
    if (selectedType === 'pdf') {
      if (!pdfSourceFile) {
        alert('Please select a PDF, CSV, Excel (.xlsx/.xlsm), Docx or PPTX file')
        return
      }
      createPdfSourceResourceMutation.mutate(
        { file: pdfSourceFile, name: uploadConnectionName.trim() },
        {
          onSuccess: (resource) => {
            setDirectSourceResult(resource)
            setPdfSourceFile(null)
            if (sourceResourceFileInputRef.current) {
              sourceResourceFileInputRef.current.value = ''
            }
          },
        },
      )
      return
    }
    if (selectedType === 'web') {
      if (!webSourceUrl.trim()) {
        alert('Please provide a public web page URL')
        return
      }
      createSourceResourceMutation.mutate(
        {
          resource_type: 'web',
          name: uploadConnectionName.trim(),
          source_url: webSourceUrl.trim(),
        },
        {
          onSuccess: (resource) => {
            setDirectSourceResult(resource)
          },
        },
      )
    }
  }

  return (
    <div className="bg-[#0d0d0d] w-full h-full flex flex-col">
      {/* Header Section */}
      <div className="w-full px-8 pt-[50px] pb-8">
        <div className="max-w-[850px] mx-auto">
          {/* Title and Buttons */}
          <div className="flex flex-wrap items-center justify-between gap-3 mb-8">
            <h1 className="text-2xl font-bold text-white tracking-tight">Sources</h1>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                asChild
                variant="outline"
                className="border-gray-700 bg-transparent text-white hover:bg-[#1f1f1f] hover:text-white"
              >
                <Link to="/data-models">
                  <Network className="w-4 h-4" />
                  Generate Data Model
                </Link>
              </Button>
              {canCreateDatasource && (
                <Button
                  variant="brand-primary"
                  onClick={() => setShowCreateDialog(true)}
                  disabled={createMutation.isPending}
                  className="font-medium px-5 py-2.5 rounded-md text-sm"
                >
                  + Add source
                </Button>
              )}
            </div>
          </div>

          {/* Search Bar */}
          <div className="relative">
            <Search className="absolute left-4 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-500" />
            <Input
              type="text"
              placeholder="Search sources..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-12 pr-4 py-6 bg-transparent border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-brand-orange focus:ring-1 focus:ring-brand-orange/50"
            />
          </div>
        </div>
      </div>

      {/* Scrollable Content Section */}
      <div className="flex-1 overflow-y-auto custom-scrollbar min-h-0">
        <div className="w-full px-8 pb-6">
          {/* Error must win over loading so a failed bootstrap never leaves an infinite spinner. */}
          {error ? (
            <div className="max-w-[850px] mx-auto">
              <Card className="p-10 text-center bg-[#1a1a1a] border-red-500/40">
                <AlertCircle className="w-10 h-10 text-red-400 mx-auto mb-4" />
                <h3 className="text-lg font-semibold text-white mb-2">Workspace could not be loaded</h3>
                <p className="text-gray-400 mb-6">{error.message || 'An error occurred while loading sources.'}</p>
                <Button
                  variant="brand-primary"
                  onClick={() => queryClient.invalidateQueries({ queryKey: sourceOverviewKeys.all })}
                >
                  Retry
                </Button>
              </Card>
            </div>
          ) : loading ? (
            <div className="text-center py-12">
              <div className="animate-spin w-8 h-8 border-2 border-brand-orange border-t-transparent rounded-full mx-auto mb-4"></div>
              <p className="text-gray-400">Loading sources...</p>
            </div>
          ) : (
            <>
              {/* Empty State */}
              {allSourceCount === 0 ? (
                <div className="max-w-[850px] mx-auto">
                  <Card className="p-12 text-center bg-[#1a1a1a] border-gray-800">
                    <div className="max-w-md mx-auto">
                      <div className="w-16 h-16 bg-brand-orange/10 rounded-full flex items-center justify-center mx-auto mb-4">
                        <Database className="w-8 h-8 text-brand-orange" />
                      </div>
                      <h3 className="text-xl font-semibold text-white mb-2">No Sources</h3>
                      <p className="text-gray-400 mb-6">
                        Get started by adding files, business docs, web pages, databases, warehouses, or object storage.
                      </p>
                    </div>
                  </Card>
                </div>
              ) : displaySources.length === 0 ? (
                <div className="max-w-6xl mx-auto">
                  <div className="mb-4 flex items-center gap-2">
                    <button
                      onClick={() => setInventoryTab('all')}
                      className={`rounded-md px-3 py-1.5 text-sm ${inventoryTab === 'all' ? 'bg-white/10 text-white' : 'text-gray-400 hover:text-white'}`}
                    >
                      All {allSourceCount}
                    </button>
                    <button
                      onClick={() => setInventoryTab('needs_attention')}
                      className={`rounded-md px-3 py-1.5 text-sm ${inventoryTab === 'needs_attention' ? 'bg-amber-500/15 text-amber-200' : 'text-gray-400 hover:text-white'}`}
                    >
                      Needs attention {needsAttentionCount}
                    </button>
                  </div>
                  <Card className="p-10 text-center bg-[#1a1a1a] border-gray-800">
                    <ShieldAlert className="w-9 h-9 text-gray-500 mx-auto mb-3" />
                    <h3 className="text-lg font-semibold text-white mb-2">No sources match this view</h3>
                    <p className="text-gray-400">Try a different search or switch back to all sources.</p>
                  </Card>
                </div>
              ) : (
                <div className="max-w-6xl mx-auto">
                  <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => setInventoryTab('all')}
                        className={`rounded-md px-3 py-1.5 text-sm ${inventoryTab === 'all' ? 'bg-white/10 text-white' : 'text-gray-400 hover:text-white'}`}
                      >
                        All {allSourceCount}
                      </button>
                      <button
                        onClick={() => setInventoryTab('needs_attention')}
                        className={`rounded-md px-3 py-1.5 text-sm ${inventoryTab === 'needs_attention' ? 'bg-amber-500/15 text-amber-200' : 'text-gray-400 hover:text-white'}`}
                      >
                        Needs attention {needsAttentionCount}
                      </button>
                    </div>
                    {sourceOverviewResponse?.counts_partial && (
                      <span className="text-xs text-gray-500">Consumer counts are partial</span>
                    )}
                  </div>

                  <div className="hidden overflow-x-auto rounded-lg border border-gray-800 bg-[#151515] lg:block">
                    <table className="min-w-[1160px] w-full table-fixed text-left">
                      <thead className="border-b border-gray-800 bg-[#1a1a1a] text-xs uppercase text-gray-500">
                        <tr>
                          <th className="w-[20%] px-4 py-3 font-medium">Source</th>
                          <th className="w-[12%] px-3 py-3 font-medium">Status</th>
                          <th className="w-[10%] px-3 py-3 font-medium">Freshness</th>
                          <th className="w-[14%] px-3 py-3 font-medium">Parsed assets</th>
                          <th className="w-[10%] px-3 py-3 font-medium">Context</th>
                          <th className="w-[8%] px-3 py-3 font-medium">Semantic</th>
                          <th className="w-[8%] px-3 py-3 font-medium">Dashboards</th>
                          <th className="w-[8%] px-3 py-3 font-medium">Owner</th>
                          <th className="w-[10%] px-3 py-3 text-right font-medium">Actions</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-800">
                        {displaySources.map(source => {
                          const datasource = datasourceForSource(source)
                          const canEdit = datasource.source_type !== 'source_resource' && canEditDatasource(datasource.created_by)
                          const canDelete = canDeleteDatasource(datasource.created_by)
                          const sourceDetailHref = `/sources/${source.id}`
                          return (
                            <tr key={source.id} className="group hover:bg-white/[0.03]">
                              <td className="px-4 py-4 align-top">
                                <div className="min-w-0">
                                  <Link
                                    to={sourceDetailHref}
                                    className="block max-w-full truncate text-left text-sm font-medium text-white hover:text-brand-orange"
                                    title={source.name}
                                  >
                                    {source.name}
                                  </Link>
                                  <div className="mt-1 flex items-center gap-2 text-xs text-gray-500">
                                    <span>{sourceTypeLabel(source)}</span>
                                    <span>·</span>
                                    <span>{source.family.replace(/_/g, ' ')}</span>
                                  </div>
                                </div>
                              </td>
                              <td className="px-3 py-4 align-top">
                                <span className={`inline-flex max-w-full rounded border px-2 py-1 text-xs ${statusClassName(source)}`}>
                                  <span className="truncate">{source.status}</span>
                                </span>
                              </td>
                              <td className="px-3 py-4 align-top">
                                <div className={`text-sm capitalize ${freshnessClassName(source)}`}>{source.freshness_status}</div>
                                <div className="mt-1 text-xs text-gray-500">
                                  {source.last_synced_at ? formatTimeAgo(source.last_synced_at) : 'No sync'}
                                </div>
                              </td>
                              <td className="px-3 py-4 align-top text-sm text-gray-300">
                                <span className="line-clamp-2">{parsedAssetsLabel(source)}</span>
                              </td>
                              <td className="px-3 py-4 align-top">
                                <span className={`text-sm capitalize ${contextClassName(source)}`}>
                                  {source.context_index_status.replace(/_/g, ' ')}
                                </span>
                                <div className="mt-1 text-xs text-gray-500 capitalize">{source.parse_status}</div>
                              </td>
                              <td className="px-3 py-4 align-top text-sm text-gray-300">
                                {source.consumer_counts.semantic_models}
                              </td>
                              <td className="px-3 py-4 align-top text-sm text-gray-300">
                                {source.consumer_counts.dashboards}
                              </td>
                              <td className="px-3 py-4 align-top">
                                <div className="truncate text-sm text-gray-300" title={sourceOwnerLabel(source)}>
                                  {sourceOwnerLabel(source)}
                                </div>
                                <div className="mt-1 text-xs capitalize text-gray-500">{source.visibility}</div>
                              </td>
                              <td className="px-3 py-4 align-top">
                                <div className="flex justify-end gap-1" onClick={(e) => e.stopPropagation()}>
                                  {primaryNextAction(source) && (
                                    <span
                                      className="mr-1 hidden max-w-[150px] truncate rounded border border-[#444444] px-2 py-1 text-xs text-gray-300 xl:inline-block"
                                      title={(source.next_actions || []).join(' · ')}
                                    >
                                      {primaryNextAction(source)}
                                    </span>
                                  )}
                                  {datasource.source_type !== 'source_resource' && showSharingFeatures && canEdit && (
                                    <Button
                                      size="sm"
                                      variant="ghost"
                                      onClick={() => handleQuickToggleVisibility(datasource)}
                                      disabled={togglingVisibility === datasource.id}
                                      className={`${datasource.is_public ? 'text-green-400 hover:text-green-300' : 'text-gray-400 hover:text-white'} hover:bg-gray-800`}
                                      title={datasource.is_public ? 'Make private' : 'Share with team'}
                                    >
                                      {togglingVisibility === datasource.id ? <Loader2 className="w-4 h-4 animate-spin" /> : datasource.is_public ? <Users className="w-4 h-4" /> : <Lock className="w-4 h-4" />}
                                    </Button>
                                  )}
                                  {canEdit && (
                                    <Button
                                      size="sm"
                                      variant="ghost"
                                      onClick={() => handleEditClick(datasource)}
                                      className="text-gray-400 hover:text-white hover:bg-gray-800"
                                      title="Edit source"
                                    >
                                      <Pencil className="w-4 h-4" />
                                    </Button>
                                  )}
                                  <Button
                                    asChild
                                    size="sm"
                                    variant="ghost"
                                    className="text-gray-400 hover:text-white hover:bg-gray-800"
                                    title="Open source detail"
                                  >
                                    <Link to={sourceDetailHref}>
                                      <FileText className="w-4 h-4" />
                                    </Link>
                                  </Button>
                                  {datasource.source_type !== 'source_resource' && (
                                    <Button
                                      asChild
                                      size="sm"
                                      variant="ghost"
                                      className="text-gray-400 hover:text-white hover:bg-gray-800"
                                      title="Generate Data Model"
                                    >
                                      <Link to="/data-models" onClick={(e) => e.stopPropagation()}>
                                        <Network className="w-4 h-4" />
                                      </Link>
                                    </Button>
                                  )}
                                  {canDelete && (
                                    <Button
                                      size="sm"
                                      variant="ghost"
                                      onClick={() => handleDeleteClick(datasource)}
                                      disabled={deleteMutation.isPending}
                                      className="text-gray-400 hover:text-red-400 hover:bg-gray-800"
                                      title="Delete source"
                                    >
                                      <Trash2 className="w-4 h-4" />
                                    </Button>
                                  )}
                                </div>
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>

                  <div className="grid grid-cols-1 gap-4 lg:hidden">
                    {displaySources.map(source => {
                      const datasource = datasourceForSource(source)
                      const canEdit = datasource.source_type !== 'source_resource' && canEditDatasource(datasource.created_by)
                      const canDelete = canDeleteDatasource(datasource.created_by)
                      const sourceDetailHref = `/sources/${source.id}`
                      return (
                        <Card
                          key={source.id}
                          className="p-5 bg-[#1a1a1a] border-gray-800"
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0 flex-1">
                              <Link to={sourceDetailHref} className="block truncate text-base font-medium text-white hover:text-brand-orange" title={source.name}>
                                {source.name}
                              </Link>
                              <p className="mt-1 text-sm text-gray-400">{sourceTypeLabel(source)}</p>
                            </div>
                            <span className={`rounded border px-2 py-1 text-xs ${statusClassName(source)}`}>
                              {source.status}
                            </span>
                          </div>
                          <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                            <div>
                              <div className="text-xs text-gray-500">Freshness</div>
                              <div className={freshnessClassName(source)}>{source.freshness_status}</div>
                            </div>
                            <div>
                              <div className="text-xs text-gray-500">Context</div>
                              <div className={contextClassName(source)}>{source.context_index_status.replace(/_/g, ' ')}</div>
                            </div>
                            <div className="col-span-2">
                              <div className="text-xs text-gray-500">Parsed assets</div>
                              <div className="text-gray-300">{parsedAssetsLabel(source)}</div>
                            </div>
                            <div className="col-span-2">
                              <div className="text-xs text-gray-500">Consumers</div>
                              <div className="text-gray-300">{consumerLabel(source)}</div>
                            </div>
                            {primaryNextAction(source) && (
                              <div className="col-span-2">
                                <div className="text-xs text-gray-500">Next action</div>
                                <div className="text-gray-300">{primaryNextAction(source)}</div>
                              </div>
                            )}
                          </div>
                          <div className="mt-4 flex justify-end gap-2">
                            {canEdit && (
                              <Button size="sm" variant="ghost" onClick={() => handleEditClick(datasource)} className="text-gray-400 hover:text-white hover:bg-gray-800">
                                <Pencil className="w-4 h-4" />
                              </Button>
                            )}
                            <Button asChild size="sm" variant="ghost" className="text-gray-400 hover:text-white hover:bg-gray-800">
                              <Link to={sourceDetailHref}>
                                <FileText className="w-4 h-4" />
                              </Link>
                            </Button>
                            {canDelete && (
                              <Button size="sm" variant="ghost" onClick={() => handleDeleteClick(datasource)} className="text-gray-400 hover:text-red-400 hover:bg-gray-800">
                                <Trash2 className="w-4 h-4" />
                              </Button>
                            )}
                          </div>
                        </Card>
                      )
                    })}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>

        {/* Create Dialog with Sidebar */}
        <Dialog open={showCreateDialog} onOpenChange={(open) => {
          if (!open && isCreatingAnyDatasource) return
          setShowCreateDialog(open)
          if (!open) resetForm()
        }}>
          <DialogContent className="max-w-4xl bg-[#2a2a2a] border-[#444444] p-0 gap-0">
            <DialogHeader className="px-6 pt-6 pb-4 border-b border-[#444444]">
              <DialogTitle className="text-white text-xl">Add Source</DialogTitle>
            </DialogHeader>

            <div className="flex h-[600px]">
              {/* Sidebar */}
              <div className="w-72 bg-[#1a1a1a] border-r border-[#444444] p-3 overflow-y-auto custom-scrollbar">
                <div className="space-y-4">
                  <div>
                    <div className="px-2 pb-2 text-[11px] uppercase tracking-wide text-gray-500">Choose family</div>
                    <div className="space-y-1">
                      {addSourceFamilies.map(family => {
                        const Icon = family.icon
                        const active = selectedFamily === family.id
                        const optionCount = addSourceOptions.filter(option => option.family === family.id).length
                        return (
                          <button
                            key={family.id}
                            type="button"
                            onClick={() => handleFamilyChange(family.id)}
                            disabled={isCreatingAnyDatasource}
                            className={`w-full flex items-start gap-3 rounded-md px-3 py-2.5 text-left transition-all ${
                              active
                                ? 'bg-brand-orange/10 text-white border-l-3 border-brand-orange'
                                : 'text-gray-400 hover:text-white hover:bg-[#2a2a2a]'
                            } ${isCreatingAnyDatasource ? 'opacity-50 cursor-not-allowed' : ''}`}
                          >
                            <Icon className={`mt-0.5 h-4 w-4 flex-shrink-0 ${active ? 'text-brand-orange' : ''}`} />
                            <span className="min-w-0 flex-1">
                              <span className="block text-sm font-medium">{family.label}</span>
                              <span className="block truncate text-xs text-gray-500">{family.description}</span>
                            </span>
                            <span className="text-xs text-gray-500">{optionCount}</span>
                          </button>
                        )
                      })}
                    </div>
                  </div>

                  <div className="border-t border-[#444444] pt-3">
                    <div className="px-2 pb-2 text-[11px] uppercase tracking-wide text-gray-500">{selectedFamilyMeta.label}</div>
                    <div className="space-y-1">
                      {connectorDefinitionsQuery.isLoading && selectedFamily !== 'files' && (
                        <div className="flex items-center gap-2 px-3 py-2 text-xs text-gray-500">
                          <Loader2 className="w-3 h-3 animate-spin" />
                          Loading connectors
                        </div>
                      )}
                      {currentFamilyOptions.length === 0 && (
                        <div className="rounded-md border border-dashed border-[#444444] px-3 py-4 text-sm text-gray-500">
                          No connectors in this family yet.
                        </div>
                      )}
                      {currentFamilyOptions.map(option => {
                        const Icon = option.icon
                        const active = isPlannedSourceOption(option.id)
                          ? selectedPlannedOption?.id === option.id
                          : selectedType === option.id && !selectedPlannedOption
                        return (
                          <button
                            key={option.id}
                            type="button"
                            onClick={() => handleSourceOptionChange(option)}
                            disabled={isCreatingAnyDatasource}
                            className={`w-full flex items-start gap-3 rounded-md px-3 py-2.5 text-left transition-all ${
                              active
                                ? 'bg-white/10 text-white'
                                : 'text-gray-400 hover:text-white hover:bg-[#2a2a2a]'
                            } ${isCreatingAnyDatasource ? 'opacity-50 cursor-not-allowed' : ''}`}
                          >
                            <Icon className={`mt-0.5 h-4 w-4 flex-shrink-0 ${active ? 'text-brand-orange' : option.availability === 'planned' ? 'text-gray-500' : ''}`} />
                            <span className="min-w-0 flex-1">
                              <span className="block truncate text-sm font-medium">{option.label}</span>
                              <span className="block line-clamp-2 text-xs text-gray-500">{option.description}</span>
                              {option.outputs.length > 0 && (
                                <span className="mt-1.5 flex flex-wrap gap-1">
                                  {option.outputs.map(output => (
                                    <span key={output} className="rounded border border-[#444444] px-1.5 py-0.5 text-[10px] leading-none text-gray-400">
                                      {output}
                                    </span>
                                  ))}
                                </span>
                              )}
                              {option.modelingModes && option.modelingModes.length > 0 && (
                                <span className="mt-1.5 flex flex-wrap gap-1">
                                  {option.modelingModes.map(mode => (
                                    <span key={mode} className="rounded border border-blue-500/20 bg-blue-500/10 px-1.5 py-0.5 text-[10px] leading-none text-blue-200">
                                      {mode}
                                    </span>
                                  ))}
                                </span>
                              )}
                              {option.limitations && option.limitations.length > 0 && (
                                <span className="mt-1 block line-clamp-1 text-[11px] text-amber-200/70">
                                  {option.limitations[0]}
                                </span>
                              )}
                              {option.connector && readinessGateSummary(option.connector) && (
                                <span className="mt-1 block text-[11px] text-gray-500">
                                  Readiness: {readinessGateSummary(option.connector)}
                                </span>
                              )}
                            </span>
                            <span className={`mt-0.5 text-[10px] uppercase ${
                              option.availability === 'available'
                                ? 'text-green-400'
                                : option.availability === 'beta'
                                  ? 'text-amber-300'
                                  : 'text-gray-500'
                            }`}>
                              {option.availability}
                            </span>
                          </button>
                        )
                      })}
                    </div>
	                  </div>
	                </div>
	              </div>

              {/* Form Content Area */}
              <div className="flex-1 flex flex-col overflow-hidden">
                <div className="flex-1 overflow-y-auto custom-scrollbar p-6">
                  <div className="space-y-4">
                    {selectedPlannedOption && (
                      <div className="rounded-lg border border-dashed border-amber-700/50 bg-amber-950/20 p-5">
                        <div className="flex items-start gap-3">
                          <ShieldAlert className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-300" />
                          <div className="space-y-2">
                            <div>
                              <div className="text-sm font-medium text-amber-100">{selectedPlannedOption.label} is planned</div>
                              <p className="mt-1 text-sm text-amber-100/75">
                                This catalog entry is on the roadmap, but it is not a supported production connector in the commercial beta.
                              </p>
                            </div>
                            <p className="text-xs text-amber-100/60">
                              {selectedPlannedOption.limitations?.[0] || 'Planned connectors cannot open a setup form until they pass the commercial readiness gates: tenant-isolated authorization, resource picker or import contract, immutable snapshots, parser artifacts, context indexing status, source detail, and clear delete/revoke/reindex behavior.'}
                            </p>
                            {selectedPlannedOption.connector?.resource_picker_type && (
                              <div className="flex flex-wrap gap-2 pt-1 text-[11px] text-amber-100/70">
                                <span className="rounded border border-amber-700/40 px-2 py-1">
                                  Picker: {selectedPlannedOption.connector.resource_picker_type}
                                </span>
                                <span className="rounded border border-amber-700/40 px-2 py-1">
                                  Status: {selectedPlannedOption.connector.status}
                                </span>
                                {readinessGateSummary(selectedPlannedOption.connector) && (
                                  <span className="rounded border border-amber-700/40 px-2 py-1">
                                    Readiness: {readinessGateSummary(selectedPlannedOption.connector)}
                                  </span>
                                )}
                              </div>
                            )}
                            {missingReadinessGates(selectedPlannedOption.connector).length > 0 && (
                              <div className="pt-2">
                                <div className="text-[11px] uppercase text-amber-100/50">Missing readiness gates</div>
                                <ul className="mt-1 space-y-1 text-xs text-amber-100/70">
                                  {missingReadinessGates(selectedPlannedOption.connector).slice(0, 5).map(gate => (
                                    <li key={gate.key}>{gate.label}</li>
                                  ))}
                                </ul>
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Connection/Source Name - hidden for OAuth/picker connectors and Databricks wizard */}
                    {hasActiveSetupForm && selectedType !== 'databricks' && !isSourceConnectorType(selectedType) && (
                      <div>
                        <Label htmlFor="connection-name" className="text-white">
                          {selectedType === 'upload' || selectedType === 'url' || isDirectSourceResourceType(selectedType) ? 'Source Name' : 'Connection Name'} <span className="text-red-400">*</span>
                        </Label>
                        <Input
                          id="connection-name"
                          value={selectedType === 'upload' || selectedType === 'url' || isDirectSourceResourceType(selectedType) ? uploadConnectionName : connectionConfig.name}
                          onChange={(e) => {
                            if (selectedType === 'upload' || selectedType === 'url' || isDirectSourceResourceType(selectedType)) {
                              setUploadConnectionName(e.target.value)
                            } else {
                              setConnectionConfig(prev => ({ ...prev, name: e.target.value }))
                            }
                          }}
                          placeholder={selectedType === 'upload' || selectedType === 'url' || isDirectSourceResourceType(selectedType) ? 'My Source' : 'My Database Connection'}
                          disabled={isCreatingAnyDatasource}
                          className="mt-1 bg-[#1a1a1a] border-[#555555] text-white placeholder-[#888888]"
                        />
                      </div>
                    )}

                    {hasActiveSetupForm && isSourceConnectorType(selectedType) && (
                      <SourceConnectorImportPanel
                        provider={sourceConnectorId(selectedType) === 'volcengine_tos' ? 'volcengine_tos' : 'feishu'}
                        definition={selectedConnectorDefinition}
                        disabled={isCreatingAnyDatasource}
                        onImported={() => {
                          queryClient.invalidateQueries({ queryKey: ['datasources'] })
                          queryClient.invalidateQueries({ queryKey: sourceOverviewKeys.all })
                        }}
                      />
                    )}

                    {/* Upload Files Form */}
                    {hasActiveSetupForm && selectedType === 'upload' && (
                      <>
                        {/* Progress Indicator */}
                        {uploadMultipleFilesMutation.isPending && (
                          <div className="bg-orange-900/20 border border-brand-orange rounded-lg p-4">
                            <div className="flex items-center gap-3">
                              <Loader2 className="w-5 h-5 text-brand-orange animate-spin flex-shrink-0" />
                              <div className="flex-1">
                                <p className="text-sm font-medium text-brand-orange">Uploading files...</p>
                                <p className="text-xs text-gray-400 mt-1">
                                  Uploading {uploadFiles.length} file(s). Please wait.
                                </p>
                              </div>
                            </div>
                          </div>
                        )}

                        {/* File Type Display (Auto-detected) */}
                        {uploadFiles.length > 0 && uploadFileType && (
                          <div className="bg-[#1a1a1a] border border-[#555555] rounded-md px-4 py-2 flex items-center justify-between">
                            <span className="text-sm text-white">
                              File Type: <span className="font-medium">{uploadFileType.toUpperCase()}</span>
                            </span>
                            <span className="text-sm text-gray-400">
                              {uploadFiles.length} file{uploadFiles.length !== 1 ? 's' : ''}
                            </span>
                          </div>
                        )}

                        {/* Drag and Drop Area */}
                        <div
                          className={`border-2 border-dashed rounded-lg transition-colors ${
                            isDragging
                              ? 'border-brand-orange bg-brand-orange/10'
                              : 'border-[#555555] hover:border-[#777777] hover:bg-[#333333]'
                          } ${uploadMultipleFilesMutation.isPending ? 'opacity-50 cursor-not-allowed' : ''}`}
                          onDragOver={(e) => {
                            if (!uploadMultipleFilesMutation.isPending) {
                              e.preventDefault()
                              setIsDragging(true)
                            }
                          }}
                          onDragLeave={(e) => {
                            e.preventDefault()
                            setIsDragging(false)
                          }}
                          onDrop={(e) => {
                            if (!uploadMultipleFilesMutation.isPending) {
                              handleUploadFilesDrop(e)
                            }
                          }}
                        >
                          <input
                            ref={uploadFileInputRef}
                            type="file"
                            accept=".csv,.xlsx,.xls,.parquet,.json"
                            multiple
                            onChange={handleUploadFilesChange}
                            disabled={uploadMultipleFilesMutation.isPending}
                            className="hidden"
                          />

                          {/* Upload Prompt */}
                          <div
                            className={`p-6 text-center ${uploadMultipleFilesMutation.isPending ? 'cursor-not-allowed' : 'cursor-pointer'}`}
                            onClick={() => {
                              if (!uploadMultipleFilesMutation.isPending) {
                                uploadFileInputRef.current?.click()
                              }
                            }}
                          >
                            <Upload className={`${uploadFiles.length > 0 ? 'w-8 h-8' : 'w-12 h-12'} mx-auto mb-3 text-brand-orange`} />
                            <p className={`text-white font-medium ${uploadFiles.length > 0 ? 'text-sm mb-1' : 'mb-2'}`}>
                              {uploadFiles.length > 0
                                ? `Drag & drop more ${uploadFileType.toUpperCase()} files here`
                                : 'Drag & drop your data files here'}
                            </p>
                            <p className={`text-gray-400 ${uploadFiles.length > 0 ? 'text-xs mb-2' : 'text-sm mb-4'}`}>
                              or click to browse
                            </p>
                            <p className="text-xs text-gray-500">
                              {uploadFiles.length > 0
                                ? 'All files must be the same type'
                                : 'Supported: CSV, Excel, Parquet, JSON • Type auto-detected'}
                            </p>
                          </div>

                          {/* Uploaded Files List */}
                          {uploadFiles.length > 0 && (
                            <div className="px-6 pb-6">
                              <div className="flex items-center justify-between mb-3 pb-3 border-t border-[#555555] pt-3">
                                <Label className="text-white text-sm">{uploadFiles.length} file(s) selected</Label>
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    setUploadFiles([])
                                    setUploadFileAliases({})
                                    setUploadFileType('')
                                    if (uploadFileInputRef.current) {
                                      uploadFileInputRef.current.value = ''
                                    }
                                  }}
                                  disabled={uploadMultipleFilesMutation.isPending}
                                  className="text-red-400 hover:text-red-300 hover:bg-red-900/20 h-7 text-xs"
                                >
                                  Clear All
                                </Button>
                              </div>

                              <div className="max-h-[200px] overflow-y-auto custom-scrollbar space-y-2 pr-1">
                                {uploadFiles.map((file, index) => (
                                  <div
                                    key={index}
                                    className="p-3 bg-[#1a1a1a] border border-[#555555] rounded-md"
                                    onClick={(e) => e.stopPropagation()}
                                  >
                                    <div className="flex items-center justify-between gap-3">
                                      <div className="flex items-center gap-2 flex-1 min-w-0">
                                        <FileText className="w-4 h-4 text-brand-orange flex-shrink-0" />
                                        <p className="text-sm text-white font-medium flex-1 truncate" title={file.name}>
                                          {truncateFilename(file.name)}
                                        </p>
                                        <p className="text-xs text-gray-400 flex-shrink-0">
                                          {formatFileSize(file.size)}
                                        </p>
                                      </div>
                                      <Button
                                        size="sm"
                                        variant="ghost"
                                        onClick={(e) => {
                                          e.stopPropagation()
                                          const newFiles = uploadFiles.filter((_, i) => i !== index)
                                          setUploadFiles(newFiles)
                                          const newAliases = { ...uploadFileAliases }
                                          delete newAliases[file.name]
                                          setUploadFileAliases(newAliases)
                                          // Reset file type if no files left
                                          if (newFiles.length === 0) {
                                            setUploadFileType('')
                                          }
                                        }}
                                        disabled={uploadMultipleFilesMutation.isPending}
                                        className="text-red-400 hover:text-red-300 hover:bg-red-900/20 h-8 w-8 p-0 flex-shrink-0"
                                      >
                                        <X className="w-4 h-4" />
                                      </Button>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      </>
                    )}

                    {/* Import from URL Form */}
	                    {hasActiveSetupForm && selectedType === 'url' && (
                      <>
                        {/* Progress Indicator */}
                        {uploadFromURLMutation.isPending && (
                          <div className="bg-orange-900/20 border border-brand-orange rounded-lg p-4">
                            <div className="flex items-center gap-3">
                              <Loader2 className="w-5 h-5 text-brand-orange animate-spin flex-shrink-0" />
                              <div className="flex-1">
                                <p className="text-sm font-medium text-brand-orange">
                                  Downloading files from URLs...
                                </p>
                                <p className="text-xs text-gray-400 mt-1">
                                  Downloading {uploadURLs.filter(u => u.trim()).length} file(s). This may take a while for large files.
                                </p>
                              </div>
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => {
                                  if (urlAbortController) {
                                    urlAbortController.abort()
                                    setUrlAbortController(null)
                                  }
                                  uploadFromURLMutation.reset()
                                }}
                                className="text-red-400 hover:text-red-300 hover:bg-red-900/20 h-8 w-8 p-0 flex-shrink-0"
                                title="Cancel download"
                              >
                                <X className="w-4 h-4" />
                              </Button>
                            </div>
                          </div>
                        )}

                        <div className="space-y-3">
                          <Label className="text-white">File URLs</Label>
                          {uploadURLs.map((url, index) => (
                            <div key={index} className="flex gap-2">
                              <Input
                                value={url}
                                onChange={(e) => {
                                  const newURLs = [...uploadURLs]
                                  newURLs[index] = e.target.value
                                  if (index === 0 && !uploadFileType && e.target.value) {
                                    const urlFileName = e.target.value.split('/').pop() || ''
                                    const detectedType = detectFileType(urlFileName)
                                    if (detectedType) {
                                      setUploadFileType(detectedType)
                                    }
                                  }
                                  setUploadURLs(newURLs)
                                }}
                                placeholder={`https://example.com/data${uploadFileType ? '.' + (uploadFileType === 'excel' ? 'xlsx' : uploadFileType) : ''}`}
                                disabled={uploadFromURLMutation.isPending}
                                className="flex-1 bg-[#1a1a1a] border-[#555555] text-white placeholder-[#888888]"
                              />
                              {uploadURLs.length > 1 && (
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  onClick={() => {
                                    setUploadURLs(uploadURLs.filter((_, i) => i !== index))
                                  }}
                                  disabled={uploadFromURLMutation.isPending}
                                  className="text-red-400 hover:text-red-300 hover:bg-red-900/20"
                                >
                                  <X className="w-4 h-4" />
                                </Button>
                              )}
                            </div>
                          ))}
                          <Button
                            type="button"
                            variant="outline"
                            onClick={() => setUploadURLs([...uploadURLs, ''])}
                            disabled={uploadFromURLMutation.isPending}
                            className="w-full border-[#555555] text-white hover:bg-[#3a3a3a]"
                          >
                            + Add Another URL
                          </Button>
                          <p className="text-xs text-gray-400">
                            Enter public URLs to data files (CSV, Excel, Parquet, JSON) or ZIP archives of these types.
                          </p>
                        </div>
	                      </>
	                    )}

	                    {hasActiveSetupForm && selectedType === 'pdf' && (
	                      <div className="space-y-4">
	                        {createPdfSourceResourceMutation.isPending && (
	                          <div className="bg-orange-900/20 border border-brand-orange rounded-lg p-4">
	                            <div className="flex items-center gap-3">
	                              <Loader2 className="w-5 h-5 text-brand-orange animate-spin flex-shrink-0" />
	                              <div>
	                                <p className="text-sm font-medium text-brand-orange">Capturing file snapshot...</p>
	                                <p className="text-xs text-gray-400 mt-1">Byaan stores the raw file snapshot before parsing it into evidence and optional projections.</p>
	                              </div>
	                            </div>
	                          </div>
	                        )}
	                        <div className="rounded-lg border border-[#444444] bg-[#1a1a1a] p-4">
	                          <Label className="text-white">Source file</Label>
	                          <input
	                            ref={sourceResourceFileInputRef}
	                            type="file"
	                            accept=".pdf,.csv,.xlsx,.xlsm,.docx,.pptx,application/pdf,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.openxmlformats-officedocument.presentationml.presentation"
	                            onChange={handlePdfSourceFileChange}
	                            disabled={createPdfSourceResourceMutation.isPending}
	                            className="mt-2 block w-full text-sm text-gray-300 file:mr-4 file:rounded file:border-0 file:bg-brand-orange file:px-3 file:py-2 file:text-sm file:font-medium file:text-white hover:file:bg-brand-orange/90"
	                          />
	                          {pdfSourceFile && (
	                            <div className="mt-3 flex items-center justify-between rounded border border-[#555555] bg-[#101010] px-3 py-2">
	                              <div className="min-w-0">
	                                <p className="truncate text-sm text-white">{pdfSourceFile.name}</p>
	                                <p className="text-xs text-gray-400">{formatFileSize(pdfSourceFile.size)}</p>
	                              </div>
	                              <Button
	                                size="sm"
	                                variant="ghost"
	                                onClick={() => setPdfSourceFile(null)}
	                                disabled={createPdfSourceResourceMutation.isPending}
	                                className="text-red-400 hover:text-red-300 hover:bg-red-900/20"
	                              >
	                                <X className="w-4 h-4" />
	                              </Button>
	                            </div>
	                          )}
	                          <p className="mt-3 text-xs text-gray-400">
	                            PDF, Docx and PPTX enter as context evidence. CSV and .xlsx/.xlsm Excel files also create a reviewed dataset projection for semantic modeling handoff.
	                          </p>
	                        </div>
	                        {directSourceResult && (
	                          <DirectSourceProcessingPanel
	                            resource={directSourceResult}
	                            onAddAnother={() => {
	                              setDirectSourceResult(null)
	                              resetUploadForm()
	                              setSelectedFamily('files')
	                              setSelectedType('pdf')
	                            }}
	                          />
	                        )}
	                      </div>
	                    )}

	                    {hasActiveSetupForm && selectedType === 'web' && (
	                      <div className="space-y-4">
	                        {createSourceResourceMutation.isPending && (
	                          <div className="bg-orange-900/20 border border-brand-orange rounded-lg p-4">
	                            <div className="flex items-center gap-3">
	                              <Loader2 className="w-5 h-5 text-brand-orange animate-spin flex-shrink-0" />
	                              <div>
	                                <p className="text-sm font-medium text-brand-orange">Capturing public web page...</p>
	                                <p className="text-xs text-gray-400 mt-1">The backend applies SSRF checks, redirect limits and content-size limits before storing a snapshot.</p>
	                              </div>
	                            </div>
	                          </div>
	                        )}
	                        <div>
	                          <Label htmlFor="web-source-url" className="text-white">Public web page URL <span className="text-red-400">*</span></Label>
	                          <Input
	                            id="web-source-url"
	                            value={webSourceUrl}
	                            onChange={(event) => {
	                              const value = event.target.value
	                              setWebSourceUrl(value)
	                              if (!uploadConnectionName.trim()) {
	                                setUploadConnectionName(value.replace(/^https?:\/\//, '').split(/[/?#]/)[0] || 'Web page')
	                              }
	                            }}
	                            placeholder="https://example.com/report"
	                            disabled={createSourceResourceMutation.isPending}
	                            className="mt-1 bg-[#1a1a1a] border-[#555555] text-white placeholder-[#888888]"
	                          />
	                          <p className="mt-2 text-xs text-gray-400">
	                            Supports public HTTP/HTTPS pages. Localhost, private networks and cloud metadata addresses are blocked by the backend.
	                          </p>
	                        </div>
	                        {directSourceResult && (
	                          <DirectSourceProcessingPanel
	                            resource={directSourceResult}
	                            onAddAnother={() => {
	                              setDirectSourceResult(null)
	                              resetUploadForm()
	                              setSelectedFamily('web')
	                              setSelectedType('web')
	                            }}
	                          />
	                        )}
	                      </div>
	                    )}

	                    {/* Database Connection Forms */}
                    {hasActiveSetupForm && selectedType === 'mongo' && (
                      <div>
                        <Label htmlFor="conn-string" className="text-white">
                          Connection String <span className="text-red-400">*</span>
                        </Label>
                        <Input
                          id="conn-string"
                          placeholder="mongodb://username:password@host:port/database"
                          value={connectionConfig.connectionString}
                          onChange={(e) => setConnectionConfig(prev => ({ ...prev, connectionString: e.target.value }))}
                          disabled={createMutation.isPending}
                          className="mt-1 bg-[#1a1a1a] border-[#555555] text-white font-mono text-sm"
                        />
                      </div>
                    )}

                    {hasActiveSetupForm && selectedType === 'sqlite' && (
                      <div>
                        <Label htmlFor="database" className="text-white">
                          Database File Path <span className="text-red-400">*</span>
                        </Label>
                        <Input
                          id="database"
                          placeholder="/path/to/database.db"
                          value={connectionConfig.database}
                          onChange={(e) => setConnectionConfig(prev => ({ ...prev, database: e.target.value }))}
                          disabled={createMutation.isPending}
                          className="mt-1 bg-[#1a1a1a] border-[#555555] text-white font-mono text-sm"
                        />
                        <p className="text-xs text-gray-400 mt-1">Enter the full path to your SQLite database file</p>
                      </div>
                    )}

                    {hasActiveSetupForm && selectedType === 'dynamodb' && (
                      <div className="space-y-4">
                        <div>
                          <Label htmlFor="region" className="text-white">AWS Region <span className="text-red-400">*</span></Label>
                          <Input
                            id="region"
                            placeholder="us-east-1"
                            value={connectionConfig.region}
                            onChange={(e) => setConnectionConfig(prev => ({ ...prev, region: e.target.value }))}
                            disabled={createMutation.isPending}
                            className="mt-1 bg-[#1a1a1a] border-[#555555] text-white font-mono text-sm"
                          />
                        </div>
                        <div>
                          <Label htmlFor="accessKeyId" className="text-white">Access Key ID <span className="text-red-400">*</span></Label>
                          <Input
                            id="accessKeyId"
                            placeholder="AKIA..."
                            value={connectionConfig.accessKeyId}
                            onChange={(e) => setConnectionConfig(prev => ({ ...prev, accessKeyId: e.target.value }))}
                            disabled={createMutation.isPending}
                            className="mt-1 bg-[#1a1a1a] border-[#555555] text-white font-mono text-sm"
                          />
                        </div>
                        <div>
                          <Label htmlFor="secretAccessKey" className="text-white">Secret Access Key <span className="text-red-400">*</span></Label>
                          <Input
                            id="secretAccessKey"
                            type="password"
                            placeholder="Secret access key"
                            value={connectionConfig.secretAccessKey}
                            onChange={(e) => setConnectionConfig(prev => ({ ...prev, secretAccessKey: e.target.value }))}
                            disabled={createMutation.isPending}
                            className="mt-1 bg-[#1a1a1a] border-[#555555] text-white font-mono text-sm"
                          />
                        </div>
                        <div>
                          <Label htmlFor="endpointUrl" className="text-white">Endpoint URL <span className="text-gray-500">(optional)</span></Label>
                          <Input
                            id="endpointUrl"
                            placeholder="http://localhost:8000 (for local DynamoDB)"
                            value={connectionConfig.endpointUrl}
                            onChange={(e) => setConnectionConfig(prev => ({ ...prev, endpointUrl: e.target.value }))}
                            disabled={createMutation.isPending}
                            className="mt-1 bg-[#1a1a1a] border-[#555555] text-white font-mono text-sm"
                          />
                          <p className="text-xs text-gray-400 mt-1">Only needed for local DynamoDB or custom endpoints</p>
                        </div>
                        <div>
                          <Label htmlFor="queryMode" className="text-white">Query Mode <span className="text-red-400">*</span></Label>
                          <select
                            id="queryMode"
                            value={connectionConfig.queryMode}
                            onChange={(e) => setConnectionConfig(prev => ({ ...prev, queryMode: e.target.value as 'partiql' | 'native' }))}
                            disabled={createMutation.isPending}
                            className="mt-1 w-full rounded-md bg-[#1a1a1a] border border-[#555555] text-white px-3 py-2 text-sm"
                          >
                            <option value="partiql">PartiQL (SQL-like syntax)</option>
                            <option value="native">Native API (scan/query/get)</option>
                          </select>
                          <p className="text-xs text-gray-400 mt-1">PartiQL uses SQL-like syntax. Native API uses JSON-based operations.</p>
                        </div>
                      </div>
                    )}

                    {hasActiveSetupForm && selectedType === 'databricks' && (
                      <div className="mb-4 flex items-center gap-3">
                        <div className="flex items-center gap-2 flex-1">
                          <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold ${databricksStep === 1 ? 'bg-brand-orange text-white' : 'bg-green-600/20 text-green-400 border border-green-600/40'}`}>
                            {databricksStep === 1 ? '1' : <CheckCircle2 className="w-4 h-4" />}
                          </div>
                          <span className={`text-sm font-medium ${databricksStep === 1 ? 'text-white' : 'text-gray-400'}`}>Credentials</span>
                        </div>
                        <div className={`h-px flex-1 ${databricksStep === 2 ? 'bg-brand-orange' : 'bg-[#444444]'}`} />
                        <div className="flex items-center gap-2 flex-1 justify-end">
                          <span className={`text-sm font-medium ${databricksStep === 2 ? 'text-white' : 'text-gray-500'}`}>Pick catalogs & schemas</span>
                          <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold ${databricksStep === 2 ? 'bg-brand-orange text-white' : 'bg-[#2a2a2a] text-gray-500 border border-[#444444]'}`}>2</div>
                        </div>
                      </div>
                    )}

                    {hasActiveSetupForm && selectedType === 'databricks' && databricksStep === 1 && isSelfHosted && !databricksOAuthConfigured && !databricksOAuthCanConfigure && (
                      <div className="bg-amber-900/20 border border-amber-700/40 rounded-md p-3 text-sm text-amber-200">
                        Databricks OAuth isn't configured for this workspace. Ask your admin to register a custom OAuth app in the Databricks Account Console and add the credentials in Settings.
                      </div>
                    )}

                    {hasActiveSetupForm && selectedType === 'databricks' && databricksStep === 1 && isSelfHosted && !databricksOAuthConfigured && databricksOAuthCanConfigure && (
                      <div className="space-y-3">
                        <div className="bg-amber-900/20 border border-amber-700/40 rounded-md p-3 text-sm text-amber-200">
                          Databricks OAuth isn't configured yet. Register Byaan as a custom OAuth app in the Databricks Account Console and paste the credentials below. After saving, every user can sign in with Databricks.
                        </div>
                        <DatabricksOAuthSettings onConfigChanged={refreshDatabricksAuthStatus} />
                      </div>
                    )}

                    {hasActiveSetupForm && selectedType === 'databricks' && databricksStep === 1 && databricksOAuthConfigured && (
                      <div className="space-y-4">
                        <div className="flex items-start justify-between gap-3">
                          <p className="text-xs text-gray-400 flex-1">
                            Sign in with your Databricks account. Byaan will list available warehouses, then catalogs and schemas to pick from.
                          </p>
                          {databricksOAuthCanConfigure && (
                            <button
                              type="button"
                              onClick={() => setShowManageDatabricksOAuth(v => !v)}
                              className="text-xs text-brand-orange hover:underline whitespace-nowrap"
                            >
                              {showManageDatabricksOAuth ? 'Hide OAuth settings' : 'Manage OAuth credentials'}
                            </button>
                          )}
                        </div>
                        {showManageDatabricksOAuth && databricksOAuthCanConfigure && (
                          <DatabricksOAuthSettings onConfigChanged={refreshDatabricksAuthStatus} />
                        )}
                        <div>
                          <Label htmlFor="serverHostname" className="text-white">Workspace URL <span className="text-red-400">*</span></Label>
                          <Input
                            id="serverHostname"
                            placeholder="adb-1234.azuredatabricks.net"
                            value={connectionConfig.serverHostname}
                            onChange={(e) => setConnectionConfig(prev => ({ ...prev, serverHostname: e.target.value }))}
                            disabled={oauthSigningIn || !!oauthTokens}
                            className="mt-1 bg-[#1a1a1a] border-[#555555] text-white font-mono text-sm"
                          />
                          <p className="text-xs text-gray-400 mt-1">
                            Enter the <strong>Server hostname</strong> only — no <code>https://</code>, no path. Example: <code>adb-1234.azuredatabricks.net</code>.
                          </p>
                        </div>

                        {!oauthTokens ? (
                          oauthSigningIn ? (
                            <div className="flex gap-2">
                              <Button
                                disabled
                                className="flex-1 bg-brand-orange/70 hover:bg-brand-orange/70 cursor-default"
                              >
                                <Loader2 className="w-4 h-4 mr-2 animate-spin" /> Waiting for sign-in…
                              </Button>
                              <Button
                                type="button"
                                onClick={handleCancelDatabricksSignIn}
                                className="bg-[#2a2a2a] hover:bg-[#3a3a3a] border border-[#555555] text-white"
                              >
                                Cancel
                              </Button>
                            </div>
                          ) : (
                            <Button
                              onClick={handleDatabricksSignIn}
                              disabled={!connectionConfig.serverHostname.trim()}
                              className="w-full bg-brand-orange hover:bg-brand-orange/90"
                            >
                              Sign in with Databricks
                            </Button>
                          )
                        ) : (
                          <div className="flex items-start gap-2 bg-green-900/20 border border-green-700/50 rounded-md p-3 text-sm text-green-200">
                            <CheckCircle2 className="w-4 h-4 mt-0.5 flex-shrink-0" />
                            <div className="flex-1">
                              <div className="font-medium">Signed in to {oauthTokens.server_hostname}</div>
                              <button
                                type="button"
                                onClick={resetDatabricksWizard}
                                className="text-xs text-green-300/80 hover:underline mt-0.5"
                              >
                                Sign out
                              </button>
                            </div>
                          </div>
                        )}

                        {oauthTokens && (
                          <div>
                            <Label className="text-white">SQL Warehouse <span className="text-red-400">*</span></Label>
                            {loadingWarehouses ? (
                              <div className="mt-2 flex items-center gap-2 text-sm text-gray-400">
                                <Loader2 className="w-4 h-4 animate-spin" /> Loading warehouses…
                              </div>
                            ) : warehouses && warehouses.length > 0 ? (
                              <div className="mt-1 border border-[#444444] rounded-md divide-y divide-[#3a3a3a] max-h-[220px] overflow-y-auto custom-scrollbar">
                                {warehouses.map(w => (
                                  <button
                                    key={w.id}
                                    type="button"
                                    onClick={() => setSelectedWarehouseId(w.id)}
                                    className={`w-full text-left px-3 py-2 text-sm hover:bg-[#2a2a2a] ${selectedWarehouseId === w.id ? 'bg-[#2a2a2a] border-l-2 border-brand-orange' : ''}`}
                                  >
                                    <div className="flex items-center justify-between">
                                      <span className="text-white font-medium">{w.name || w.id}</span>
                                      <span className="text-xs text-gray-400">{w.state}{w.size ? ` · ${w.size}` : ''}</span>
                                    </div>
                                    <div className="text-xs text-gray-500 font-mono mt-0.5">{w.http_path}</div>
                                  </button>
                                ))}
                              </div>
                            ) : (
                              <div className="mt-1 p-3 text-sm text-gray-400 border border-[#444444] rounded-md">
                                No SQL warehouses visible to this account.
                              </div>
                            )}
                          </div>
                        )}

                        {(oauthError || discoverError) && (
                          <div className="flex items-start gap-2 bg-red-900/20 border border-red-700/50 rounded-md p-3 text-sm text-red-200">
                            <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                            <span>{oauthError || discoverError}</span>
                          </div>
                        )}
                      </div>
                    )}

                    {hasActiveSetupForm && selectedType === 'databricks' && databricksStep === 2 && discoveredCatalogs && (
                      <div className="space-y-4">
                        {batchProgress ? (
                          <div className="bg-[#1a1a1a] border border-[#444444] rounded-lg p-5 space-y-4">
                            <div className="flex items-center gap-3">
                              {batchProgress.done < batchProgress.total ? (
                                <Loader2 className="w-5 h-5 animate-spin text-brand-orange" />
                              ) : batchProgress.failures.length === 0 ? (
                                <CheckCircle2 className="w-5 h-5 text-green-400" />
                              ) : (
                                <AlertCircle className="w-5 h-5 text-red-400" />
                              )}
                              <div className="flex-1">
                                <div className="text-sm text-white font-medium">
                                  {batchProgress.done < batchProgress.total
                                    ? 'Creating connections…'
                                    : batchProgress.failures.length === 0
                                      ? 'All connections created'
                                      : `${batchProgress.total - batchProgress.failures.length} of ${batchProgress.total} created · ${batchProgress.failures.length} failed`}
                                </div>
                                <div className="text-xs text-gray-400 mt-0.5">{batchProgress.done} / {batchProgress.total} processed</div>
                              </div>
                            </div>
                            <div className="w-full h-2 bg-[#333333] rounded overflow-hidden">
                              <div
                                className={`h-2 rounded transition-all ${batchProgress.failures.length > 0 && batchProgress.done === batchProgress.total ? 'bg-red-500' : 'bg-brand-orange'}`}
                                style={{ width: `${(batchProgress.done / batchProgress.total) * 100}%` }}
                              />
                            </div>
                            {batchProgress.failures.length > 0 && (
                              <div className="space-y-1 max-h-[180px] overflow-y-auto custom-scrollbar pr-1">
                                {batchProgress.failures.map((f, i) => (
                                  <div key={i} className="flex items-start gap-2 bg-red-900/20 border border-red-700/40 rounded px-2 py-1.5 text-xs">
                                    <AlertCircle className="w-3 h-3 mt-0.5 text-red-400 flex-shrink-0" />
                                    <div className="flex-1">
                                      <div className="font-mono text-red-200">{f.pair.catalog}.{f.pair.schema ?? '*'}</div>
                                      <div className="text-red-300/80">{f.error}</div>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        ) : (
                          <>
                            <div className="grid grid-cols-2 gap-3">
                              <div>
                                <Label htmlFor="databricksNamePrefix" className="text-white text-sm">Name prefix <span className="text-gray-500">(optional)</span></Label>
                                <Input
                                  id="databricksNamePrefix"
                                  placeholder="My Workspace"
                                  value={databricksNamePrefix}
                                  onChange={(e) => setDatabricksNamePrefix(e.target.value)}
                                  className="mt-1 bg-[#1a1a1a] border-[#555555] text-white text-sm"
                                />
                              </div>
                              <div>
                                <Label htmlFor="databricksFilter" className="text-white text-sm">Filter catalogs</Label>
                                <div className="relative mt-1">
                                  <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500" />
                                  <Input
                                    id="databricksFilter"
                                    placeholder="Search…"
                                    value={databricksCatalogFilter}
                                    onChange={(e) => setDatabricksCatalogFilter(e.target.value)}
                                    className="bg-[#1a1a1a] border-[#555555] text-white text-sm pl-8"
                                  />
                                </div>
                              </div>
                            </div>
                            <p className="text-xs text-gray-400 -mt-2">Each pick becomes its own connection sharing this access token. Rotate later by editing each.</p>

                            <div className="border border-[#444444] rounded-md divide-y divide-[#3a3a3a] max-h-[300px] overflow-y-auto custom-scrollbar">
                              {discoveredCatalogs.length === 0 && (
                                <div className="p-6 text-sm text-gray-400 text-center">No catalogs visible to this token.</div>
                              )}
                              {discoveredCatalogs
                                .filter(c => !databricksCatalogFilter.trim() || c.name.toLowerCase().includes(databricksCatalogFilter.toLowerCase().trim()))
                                .map(cat => {
                                  const isExpanded = expandedCatalogs.has(cat.name)
                                  const allPair: DatabricksPair = { catalog: cat.name, schema: null }
                                  const allSelected = isPairSelected(allPair)
                                  const specificCount = selectedPairs.filter(p => p.catalog === cat.name && p.schema !== null).length
                                  const isCatalogActive = allSelected || specificCount > 0
                                  return (
                                    <div key={cat.name} className={`${isCatalogActive ? 'bg-brand-orange/5' : 'bg-[#1a1a1a]'} transition-colors`}>
                                      <div className="flex items-center gap-2 px-3 py-2.5">
                                        <button
                                          type="button"
                                          onClick={() => setExpandedCatalogs(prev => {
                                            const next = new Set(prev)
                                            if (next.has(cat.name)) next.delete(cat.name)
                                            else next.add(cat.name)
                                            return next
                                          })}
                                          className="text-gray-400 hover:text-white"
                                        >
                                          {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                                        </button>
                                        <Database className="w-3.5 h-3.5 text-red-400 flex-shrink-0" />
                                        <span className="text-white text-sm font-mono flex-1 truncate">{cat.name}</span>
                                        {specificCount > 0 && !allSelected && (
                                          <span className="text-[10px] uppercase tracking-wide bg-brand-orange/15 text-brand-orange px-1.5 py-0.5 rounded">{specificCount} picked</span>
                                        )}
                                        <label className="flex items-center gap-1.5 text-xs text-gray-300 cursor-pointer hover:text-white">
                                          <input
                                            type="checkbox"
                                            checked={allSelected}
                                            onChange={() => togglePair(allPair)}
                                            className="accent-brand-orange"
                                          />
                                          All ({cat.schemas.length})
                                        </label>
                                      </div>
                                      {isExpanded && (
                                        <div className="px-3 pb-2.5 pl-11 grid grid-cols-2 gap-x-3 gap-y-1">
                                          {cat.schemas.length === 0 && <div className="text-xs text-gray-500 col-span-2">No accessible schemas.</div>}
                                          {cat.schemas.map(s => {
                                            const pair: DatabricksPair = { catalog: cat.name, schema: s }
                                            const checked = isPairSelected(pair)
                                            return (
                                              <label key={s} className={`flex items-center gap-2 text-sm cursor-pointer py-0.5 ${allSelected ? 'text-gray-500' : checked ? 'text-brand-orange' : 'text-gray-200 hover:text-white'}`}>
                                                <input
                                                  type="checkbox"
                                                  checked={checked}
                                                  disabled={allSelected}
                                                  onChange={() => togglePair(pair)}
                                                  className="accent-brand-orange"
                                                />
                                                <span className="font-mono truncate">{s}</span>
                                              </label>
                                            )
                                          })}
                                        </div>
                                      )}
                                    </div>
                                  )
                                })}
                            </div>

                            <div className="flex items-center justify-between bg-[#1a1a1a] border border-[#444444] rounded-md px-3 py-2 text-sm">
                              <span className="text-gray-300">
                                {selectedPairs.length === 0
                                  ? <span className="text-gray-500">No selection yet — pick at least one catalog or schema</span>
                                  : <><span className="text-white font-semibold">{selectedPairs.length}</span> connection{selectedPairs.length !== 1 ? 's' : ''} will be created</>}
                              </span>
                              {selectedPairs.length > 0 && (
                                <button type="button" onClick={() => setSelectedPairs([])} className="text-xs text-gray-400 hover:text-white">Clear</button>
                              )}
                            </div>
                          </>
                        )}
                      </div>
                    )}

                    {hasActiveSetupForm && (selectedType === 'pg' || selectedType === 'mysql' || selectedType === 'mssql') && (
                      <div className="space-y-4">
                        <div className="grid grid-cols-2 gap-3">
                          <div>
                            <Label htmlFor="host" className="text-white">Host <span className="text-red-400">*</span></Label>
                            <Input
                              id="host"
                              placeholder="localhost"
                              value={connectionConfig.host}
                              onChange={(e) => setConnectionConfig(prev => ({ ...prev, host: e.target.value }))}
                              disabled={createMutation.isPending}
                              className="mt-1 bg-[#1a1a1a] border-[#555555] text-white"
                            />
                          </div>
                          <div>
                            <Label htmlFor="port" className="text-white">Port <span className="text-red-400">*</span></Label>
                            <Input
                              id="port"
                              placeholder={selectedType === 'mysql' ? '3306' : selectedType === 'mssql' ? '1433' : '5432'}
                              value={connectionConfig.port}
                              onChange={(e) => setConnectionConfig(prev => ({ ...prev, port: e.target.value }))}
                              disabled={createMutation.isPending}
                              className="mt-1 bg-[#1a1a1a] border-[#555555] text-white"
                            />
                          </div>
                        </div>

                        <div>
                          <Label htmlFor="database" className="text-white">Database <span className="text-red-400">*</span></Label>
                          <Input
                            id="database"
                            placeholder="database name"
                            value={connectionConfig.database}
                            onChange={(e) => setConnectionConfig(prev => ({ ...prev, database: e.target.value }))}
                            disabled={createMutation.isPending}
                            className="mt-1 bg-[#1a1a1a] border-[#555555] text-white"
                          />
                        </div>

                        <div className="grid grid-cols-2 gap-3">
                          <div>
                            <Label htmlFor="user" className="text-white">User <span className="text-red-400">*</span></Label>
                            <Input
                              id="user"
                              placeholder="user"
                              value={connectionConfig.user}
                              onChange={(e) => setConnectionConfig(prev => ({ ...prev, user: e.target.value }))}
                              disabled={createMutation.isPending}
                              className="mt-1 bg-[#1a1a1a] border-[#555555] text-white"
                            />
                          </div>
                          <div>
                            <Label htmlFor="password" className="text-white">Password <span className="text-red-400">*</span></Label>
                            <Input
                              id="password"
                              type="password"
                              placeholder="password"
                              value={connectionConfig.password}
                              onChange={(e) => setConnectionConfig(prev => ({ ...prev, password: e.target.value }))}
                              disabled={createMutation.isPending}
                              className="mt-1 bg-[#1a1a1a] border-[#555555] text-white"
                            />
                          </div>
                        </div>
                      </div>
                    )}

                    {hasActiveSetupForm && selectedType === 'oracle' && (
                      <div className="space-y-4">
                        <div className="grid grid-cols-2 gap-3">
                          <div>
                            <Label htmlFor="oracle-host" className="text-white">Host <span className="text-red-400">*</span></Label>
                            <Input
                              id="oracle-host"
                              placeholder="oracle.example.com"
                              value={connectionConfig.host}
                              onChange={(e) => setConnectionConfig(prev => ({ ...prev, host: e.target.value }))}
                              disabled={createMutation.isPending}
                              className="mt-1 bg-[#1a1a1a] border-[#555555] text-white"
                            />
                          </div>
                          <div>
                            <Label htmlFor="oracle-port" className="text-white">Port <span className="text-red-400">*</span></Label>
                            <Input
                              id="oracle-port"
                              placeholder="1521"
                              value={connectionConfig.port}
                              onChange={(e) => setConnectionConfig(prev => ({ ...prev, port: e.target.value }))}
                              disabled={createMutation.isPending}
                              className="mt-1 bg-[#1a1a1a] border-[#555555] text-white"
                            />
                          </div>
                        </div>

                        <div className="grid grid-cols-2 gap-3">
                          <div>
                            <Label htmlFor="oracle-service-name" className="text-white">Service Name</Label>
                            <Input
                              id="oracle-service-name"
                              placeholder="FREEPDB1"
                              value={connectionConfig.oracleServiceName}
                              onChange={(e) => setConnectionConfig(prev => ({ ...prev, oracleServiceName: e.target.value }))}
                              disabled={createMutation.isPending || connectionConfig.oracleSid.trim().length > 0}
                              className="mt-1 bg-[#1a1a1a] border-[#555555] text-white font-mono text-sm"
                            />
                          </div>
                          <div>
                            <Label htmlFor="oracle-sid" className="text-white">SID</Label>
                            <Input
                              id="oracle-sid"
                              placeholder="ORCL"
                              value={connectionConfig.oracleSid}
                              onChange={(e) => setConnectionConfig(prev => ({ ...prev, oracleSid: e.target.value }))}
                              disabled={createMutation.isPending || connectionConfig.oracleServiceName.trim().length > 0}
                              className="mt-1 bg-[#1a1a1a] border-[#555555] text-white font-mono text-sm"
                            />
                          </div>
                        </div>
                        <p className="text-xs text-gray-400 -mt-2">Provide exactly one of service name or SID.</p>

                        <div>
                          <Label htmlFor="oracle-schema" className="text-white">Schema <span className="text-gray-500">(optional)</span></Label>
                          <Input
                            id="oracle-schema"
                            placeholder="Defaults to user schema"
                            value={connectionConfig.oracleSchema}
                            onChange={(e) => setConnectionConfig(prev => ({ ...prev, oracleSchema: e.target.value }))}
                            disabled={createMutation.isPending}
                            className="mt-1 bg-[#1a1a1a] border-[#555555] text-white font-mono text-sm"
                          />
                        </div>

                        <div className="grid grid-cols-2 gap-3">
                          <div>
                            <Label htmlFor="oracle-user" className="text-white">User <span className="text-red-400">*</span></Label>
                            <Input
                              id="oracle-user"
                              placeholder="user"
                              value={connectionConfig.user}
                              onChange={(e) => setConnectionConfig(prev => ({ ...prev, user: e.target.value }))}
                              disabled={createMutation.isPending}
                              className="mt-1 bg-[#1a1a1a] border-[#555555] text-white"
                            />
                          </div>
                          <div>
                            <Label htmlFor="oracle-password" className="text-white">Password <span className="text-red-400">*</span></Label>
                            <Input
                              id="oracle-password"
                              type="password"
                              placeholder="password"
                              value={connectionConfig.password}
                              onChange={(e) => setConnectionConfig(prev => ({ ...prev, password: e.target.value }))}
                              disabled={createMutation.isPending}
                              className="mt-1 bg-[#1a1a1a] border-[#555555] text-white"
                            />
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* Action Buttons */}
                <div className="border-t border-[#444444] p-6 flex justify-end gap-2">
                  {selectedPlannedOption || !hasActiveSetupForm ? (
                    <Button
                      variant="outline"
                      onClick={() => {
                        setShowCreateDialog(false)
                        resetForm()
                      }}
                      disabled={isCreatingAnyDatasource}
                      className="border-[#555555] text-white hover:bg-[#3a3a3a]"
                    >
                      Close
                    </Button>
                  ) : selectedType === 'databricks' ? (
                    <>
                      <Button
                        variant="outline"
                        onClick={() => {
                          if (batchProgress && batchProgress.done < batchProgress.total) return
                          if (databricksStep === 2) {
                            setDatabricksStep(1)
                            setBatchProgress(null)
                          } else {
                            setShowCreateDialog(false)
                            resetForm()
                          }
                        }}
                        disabled={!!(batchProgress && batchProgress.done < batchProgress.total) || discovering}
                        className="border-[#555555] text-white hover:bg-[#3a3a3a]"
                      >
                        {databricksStep === 2 ? 'Back' : 'Cancel'}
                      </Button>
                      {databricksStep === 1 ? (
                        <Button
                          onClick={handleDatabricksDiscover}
                          disabled={!isCreateFormValid || discovering}
                          className={`${isCreateFormValid && !discovering ? 'bg-brand-orange hover:bg-brand-orange/90' : 'bg-gray-500 cursor-not-allowed'} flex items-center gap-2`}
                        >
                          {discovering && <Loader2 className="w-4 h-4 animate-spin" />}
                          Next →
                        </Button>
                      ) : (
                        <Button
                          onClick={handleDatabricksBatchCreate}
                          disabled={!isCreateFormValid || !!(batchProgress && batchProgress.done < batchProgress.total)}
                          className={`${isCreateFormValid && !batchProgress ? 'bg-brand-orange hover:bg-brand-orange/90' : 'bg-gray-500 cursor-not-allowed'} flex items-center gap-2`}
                        >
                          {batchProgress && batchProgress.done < batchProgress.total && <Loader2 className="w-4 h-4 animate-spin" />}
                          {batchProgress && batchProgress.failures.length > 0 && batchProgress.done === batchProgress.total
                            ? `Retry ${batchProgress.failures.length} failed`
                            : `Create ${selectedPairs.length} connection${selectedPairs.length !== 1 ? 's' : ''}`}
                        </Button>
                      )}
                    </>
                  ) : isSourceConnectorType(selectedType) ? (
                    <Button
                      variant="outline"
                      onClick={() => {
                        setShowCreateDialog(false)
                        resetForm()
                      }}
                      disabled={isCreatingAnyDatasource}
                      className="border-[#555555] text-white hover:bg-[#3a3a3a]"
                    >
                      Close
                    </Button>
                  ) : (
                    <>
                      <Button
                        variant="outline"
                        onClick={() => {
                          setShowCreateDialog(false)
                          resetForm()
                        }}
                        disabled={isCreatingAnyDatasource}
                        className="border-[#555555] text-white hover:bg-[#3a3a3a]"
                      >
                        Cancel
                      </Button>
                      <Button
                        onClick={() => {
                          if (selectedType === 'upload' || selectedType === 'url') {
                            handleCreateDialogSubmit()
                          } else if (isDirectSourceResourceType(selectedType)) {
                            handleCreateSourceResourceSubmit()
                          } else {
                            handleCreateConnection()
                          }
                        }}
                        disabled={
                          (selectedType === 'upload' && (!uploadConnectionName.trim() || !uploadFileType || uploadFiles.length === 0)) ||
                          (selectedType === 'url' && (!uploadConnectionName.trim() || uploadURLs.filter(u => u.trim()).length === 0)) ||
                          (selectedType === 'pdf' && (!uploadConnectionName.trim() || !pdfSourceFile)) ||
                          (selectedType === 'web' && (!uploadConnectionName.trim() || !webSourceUrl.trim())) ||
                          (selectedType !== 'upload' && selectedType !== 'url' && !isCreateFormValid) ||
                          isCreatingAnyDatasource ||
                          !!directSourceResult
                        }
                        className={`${
                          ((selectedType === 'upload' && uploadConnectionName.trim() && uploadFileType && uploadFiles.length > 0) ||
                            (selectedType === 'url' && uploadConnectionName.trim() && uploadURLs.filter(u => u.trim()).length > 0) ||
                            (selectedType === 'pdf' && uploadConnectionName.trim() && pdfSourceFile) ||
                            (selectedType === 'web' && uploadConnectionName.trim() && webSourceUrl.trim()) ||
                            (selectedType !== 'upload' && selectedType !== 'url' && !isDirectSourceResourceType(selectedType) && isCreateFormValid)) &&
                          !isCreatingAnyDatasource &&
                          !directSourceResult
                            ? 'bg-brand-orange hover:bg-brand-orange/90'
                            : 'bg-gray-500 cursor-not-allowed'
                        } flex items-center gap-2`}
                      >
                        {isCreatingAnyDatasource && (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        )}
                        {isCreatingAnyDatasource ? 'Creating...' : directSourceResult ? 'Processing source' : 'Create Source'}
                      </Button>
                    </>
                  )}
                </div>
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
              <DialogTitle className="text-white">Delete Source?</DialogTitle>
            </DialogHeader>
            
            <div className="space-y-4">
              <p className="text-sm text-[#aaaaaa]">
              This action will permanently delete <span className="font-semibold text-white">"{connectionToDelete?.name}"</span>.
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
                  className="bg-red-800 hover:bg-red-900 text-white"
                >
                  <Trash2 className="mr-2 h-4 w-4" />
                  {deleteMutation.isPending ? 'Deleting...' : 'Delete'}
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>

        {/* Upload Files Dialog */}
        <Dialog open={showUploadDialog} onOpenChange={(open) => {
          if (!open && (uploadMultipleFilesMutation.isPending || uploadFromURLMutation.isPending)) return
          setShowUploadDialog(open)
          if (!open) resetUploadForm()
        }}>
          <DialogContent className="max-w-2xl bg-[#2a2a2a] border-[#444444]">
            <DialogHeader>
              <DialogTitle className="text-white">Upload Data Files</DialogTitle>
            </DialogHeader>

            <div className="space-y-4">
              {/* Progress Indicator - Only show for URL downloads */}
              {uploadFromURLMutation.isPending && (
                <div className="bg-orange-900/20 border border-brand-orange rounded-lg p-4">
                  <div className="flex items-center gap-3">
                    <Loader2 className="w-5 h-5 text-brand-orange animate-spin flex-shrink-0" />
                    <div className="flex-1">
                      <p className="text-sm font-medium text-brand-orange">
                        Downloading files from URLs...
                      </p>
                      <p className="text-xs text-gray-400 mt-1">
                        Downloading {uploadURLs.filter(u => u.trim()).length} file(s). This may take a while for large files.
                      </p>
                    </div>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        // Abort the ongoing request
                        if (urlAbortController) {
                          urlAbortController.abort()
                          setUrlAbortController(null)
                        }
                        uploadFromURLMutation.reset()
                        // Don't close dialog, just reset to initial state
                      }}
                      className="text-red-400 hover:text-red-300 hover:bg-red-900/20 h-8 w-8 p-0 flex-shrink-0"
                      title="Cancel download"
                    >
                      <X className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              )}

              {/* Connection Name */}
              <div>
                <Label htmlFor="upload-connection-name" className="text-white">
                  Source Name <span className="text-red-400">*</span>
                </Label>
                <Input
                  id="upload-connection-name"
                  value={uploadConnectionName}
                  onChange={(e) => setUploadConnectionName(e.target.value)}
                  placeholder="My File Source"
                  disabled={uploadMultipleFilesMutation.isPending || uploadFromURLMutation.isPending}
                  className="mt-1 bg-[#1a1a1a] border-[#555555] text-white placeholder-[#888888]"
                />
              </div>

              {/* File Type Display (Auto-detected) */}
              {uploadFiles.length > 0 && uploadFileType && (
                <div className="bg-[#1a1a1a] border border-[#555555] rounded-md px-4 py-2 flex items-center justify-between">
                  <span className="text-sm text-white">
                    File Type: <span className="font-medium">{uploadFileType.toUpperCase()}</span>
                  </span>
                  <span className="text-sm text-gray-400">
                    {uploadFiles.length} file{uploadFiles.length !== 1 ? 's' : ''}
                  </span>
                </div>
              )}

              {/* Upload Mode Toggle */}
              <div>
                <Label className="text-white">Upload Method</Label>
                <div className="flex gap-2 mt-2">
                  <Button
                    type="button"
                    variant={uploadMode === 'file' ? 'default' : 'outline'}
                    onClick={() => setUploadMode('file')}
                    disabled={uploadMultipleFilesMutation.isPending || uploadFromURLMutation.isPending}
                    className="flex-1"
                  >
                    Upload Files
                  </Button>
                  <Button
                    type="button"
                    variant={uploadMode === 'url' ? 'default' : 'outline'}
                    onClick={() => setUploadMode('url')}
                    disabled={uploadMultipleFilesMutation.isPending || uploadFromURLMutation.isPending}
                    className="flex-1"
                  >
                    From URL
                  </Button>
                </div>
              </div>

              {/* Conditional Rendering based on mode */}
              {uploadMode === 'file' ? (
              /* Drag and Drop Area with Files Inside */
              <div
                className={`border-2 border-dashed rounded-lg transition-colors ${
                  isDragging
                    ? 'border-brand-orange bg-brand-orange/10'
                    : 'border-[#555555] hover:border-[#777777] hover:bg-[#333333]'
                } ${uploadMultipleFilesMutation.isPending ? 'opacity-50 cursor-not-allowed' : ''}`}
                onDragOver={(e) => {
                  if (!uploadMultipleFilesMutation.isPending) {
                    e.preventDefault()
                    setIsDragging(true)
                  }
                }}
                onDragLeave={(e) => {
                  e.preventDefault()
                  setIsDragging(false)
                }}
                onDrop={(e) => {
                  if (!uploadMultipleFilesMutation.isPending) {
                    handleUploadFilesDrop(e)
                  }
                }}
              >
                <input
                  ref={uploadFileInputRef}
                  type="file"
                  accept=".csv,.xlsx,.xls,.parquet,.json"
                  multiple
                  onChange={handleUploadFilesChange}
                  disabled={uploadMultipleFilesMutation.isPending}
                  className="hidden"
                />

                {/* Upload Prompt - Clickable area at top */}
                <div
                  className={`p-6 text-center ${uploadMultipleFilesMutation.isPending ? 'cursor-not-allowed' : 'cursor-pointer'}`}
                  onClick={() => {
                    if (!uploadMultipleFilesMutation.isPending) {
                      uploadFileInputRef.current?.click()
                    }
                  }}
                >
                  <Upload className={`${uploadFiles.length > 0 ? 'w-8 h-8' : 'w-12 h-12'} mx-auto mb-3 text-brand-orange`} />
                  <p className={`text-white font-medium ${uploadFiles.length > 0 ? 'text-sm mb-1' : 'mb-2'}`}>
                    {uploadFiles.length > 0
                      ? `Drag & drop more ${uploadFileType.toUpperCase()} files here`
                      : 'Drag & drop your data files here'}
                  </p>
                  <p className={`text-gray-400 ${uploadFiles.length > 0 ? 'text-xs mb-2' : 'text-sm mb-4'}`}>
                    or click to browse
                  </p>
                  <p className="text-xs text-gray-500">
                    {uploadFiles.length > 0
                      ? 'All files must be the same type'
                      : 'Supported: CSV, Excel, Parquet, JSON • Type auto-detected'}
                  </p>
                </div>

                {/* Uploaded Files List - Inside dotted area */}
                {uploadFiles.length > 0 && (
                  <div className="px-6 pb-6">
                    {/* Header with file count and clear button */}
                    <div className="flex items-center justify-between mb-3 pb-3 border-t border-[#555555] pt-3">
                      <Label className="text-white text-sm">{uploadFiles.length} file(s) selected</Label>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={(e) => {
                          e.stopPropagation()
                          setUploadFiles([])
                          setUploadFileAliases({})
                          if (uploadFileInputRef.current) {
                            uploadFileInputRef.current.value = ''
                          }
                        }}
                        disabled={uploadMultipleFilesMutation.isPending}
                        className="text-red-400 hover:text-red-300 hover:bg-red-900/20 h-7 text-xs"
                      >
                        Clear All
                      </Button>
                    </div>

                    {/* Files list with scroll */}
                    <div className="max-h-[200px] overflow-y-auto custom-scrollbar space-y-2 pr-1">
                      {uploadFiles.map((file, index) => (
                        <div
                          key={index}
                          className="p-3 bg-[#1a1a1a] border border-[#555555] rounded-md"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <div className="flex items-center justify-between gap-3">
                            <div className="flex items-center gap-2 flex-1 min-w-0">
                              <FileText className="w-4 h-4 text-brand-orange flex-shrink-0" />
                              <p className="text-sm text-white font-medium flex-1 truncate" title={file.name}>
                                {truncateFilename(file.name)}
                              </p>
                              <p className="text-xs text-gray-400 flex-shrink-0">
                                {formatFileSize(file.size)}
                              </p>
                            </div>
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={(e) => {
                                e.stopPropagation()
                                const newFiles = uploadFiles.filter((_, i) => i !== index)
                                setUploadFiles(newFiles)
                                const newAliases = { ...uploadFileAliases }
                                delete newAliases[file.name]
                                setUploadFileAliases(newAliases)
                              }}
                              disabled={uploadMultipleFilesMutation.isPending}
                              className="text-red-400 hover:text-red-300 hover:bg-red-900/20 h-8 w-8 p-0 flex-shrink-0"
                            >
                              <X className="w-4 h-4" />
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
              ) : (
              /* URL Input Mode */
              <div className="space-y-3">
                <Label className="text-white">File URLs</Label>
                {uploadURLs.map((url, index) => (
                  <div key={index} className="flex gap-2">
                    <Input
                      value={url}
                      onChange={(e) => {
                        const newURLs = [...uploadURLs]
                        newURLs[index] = e.target.value
                        // Try to detect file type from URL
                        if (index === 0 && !uploadFileType && e.target.value) {
                          const urlFileName = e.target.value.split('/').pop() || ''
                          const detectedType = detectFileType(urlFileName)
                          if (detectedType) {
                            setUploadFileType(detectedType)
                          }
                        }
                        setUploadURLs(newURLs)
                      }}
                      placeholder={`https://example.com/data${uploadFileType ? '.' + (uploadFileType === 'excel' ? 'xlsx' : uploadFileType) : ''}`}
                      disabled={uploadFromURLMutation.isPending}
                      className="flex-1 bg-[#1a1a1a] border-[#555555] text-white placeholder-[#888888]"
                    />
                    {uploadURLs.length > 1 && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          setUploadURLs(uploadURLs.filter((_, i) => i !== index))
                        }}
                        disabled={uploadFromURLMutation.isPending}
                        className="text-red-400 hover:text-red-300 hover:bg-red-900/20"
                      >
                        <X className="w-4 h-4" />
                      </Button>
                    )}
                  </div>
                ))}
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setUploadURLs([...uploadURLs, ''])}
                  disabled={uploadFromURLMutation.isPending}
                  className="w-full border-[#555555] text-white hover:bg-[#3a3a3a]"
                >
                  + Add Another URL
                </Button>
                <p className="text-xs text-gray-400">
                  Enter public URLs to data files (CSV, Excel, Parquet, JSON) or ZIP archives of these types.
                </p>
              </div>
              )}

              {/* Action Buttons */}
              <div className="flex justify-end gap-2 mt-6">
                <Button
                  variant="outline"
                  onClick={() => {
                    setShowUploadDialog(false)
                    resetUploadForm()
                  }}
                  disabled={uploadMultipleFilesMutation.isPending || uploadFromURLMutation.isPending}
                  className="border-[#555555] text-white hover:bg-[#3a3a3a]"
                >
                  Cancel
                </Button>
                <Button
                  onClick={handleUploadFilesSubmit}
                  disabled={
                    !uploadConnectionName.trim() ||
                    (uploadMode === 'file' && (!uploadFileType || uploadFiles.length === 0)) ||
                    (uploadMode === 'url' && uploadURLs.filter(u => u.trim()).length === 0) ||
                    uploadMultipleFilesMutation.isPending ||
                    uploadFromURLMutation.isPending
                  }
                  className={`${
                    uploadConnectionName.trim() &&
                    ((uploadMode === 'file' && uploadFileType && uploadFiles.length > 0) ||
                     (uploadMode === 'url' && uploadURLs.filter(u => u.trim()).length > 0)) &&
                    !uploadMultipleFilesMutation.isPending &&
                    !uploadFromURLMutation.isPending
                      ? 'bg-brand-orange hover:bg-brand-orange/90'
                      : 'bg-gray-500 cursor-not-allowed'
                  } flex items-center gap-2`}
                >
                  {(uploadMultipleFilesMutation.isPending || uploadFromURLMutation.isPending) && (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  )}
                  {uploadMultipleFilesMutation.isPending || uploadFromURLMutation.isPending ? 'Creating...' : 'Create Source'}
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>
  )
}

function DirectSourceProcessingPanel({
  resource,
  onAddAnother,
}: {
  resource: SourceResource
  onAddAnother: () => void
}) {
  const processingQuery = useSourceResourceProcessing(resource.id, resource.status === 'ready')
  const processing = processingQuery.data
  const progressIndex = directSourceProgressIndex(resource, processing)
  const tone = directSourceProcessingTone(resource, processing)
  const errorMessage = processing?.last_error?.message
  const nextActions = processing?.next_actions || []
  const semanticMode = resource.projected_dataset_id ? 'Projection-ready dataset' : 'Context-assisted source'

  return (
    <div className="rounded-lg border border-[#444444] bg-[#1a1a1a] p-4">
      <div className="flex items-start gap-3">
        {tone === 'failed' ? (
          <AlertCircle className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-400" />
        ) : tone === 'ready' ? (
          <CheckCircle2 className="mt-0.5 h-5 w-5 flex-shrink-0 text-green-400" />
        ) : (
          <Loader2 className="mt-0.5 h-5 w-5 flex-shrink-0 animate-spin text-brand-orange" />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate text-sm font-medium text-white">{resource.name}</span>
            <span className="rounded bg-[#101010] px-2 py-0.5 text-[10px] uppercase text-gray-400">
              {directSourceResourceLabel(resource.resource_type)}
            </span>
            <span className="rounded bg-[#101010] px-2 py-0.5 text-[10px] text-gray-400">
              {semanticMode}
            </span>
          </div>
          <p className={`mt-1 text-xs ${tone === 'failed' ? 'text-red-300' : tone === 'ready' ? 'text-green-300' : 'text-gray-300'}`}>
            {tone === 'failed'
              ? errorMessage || 'Source processing failed.'
              : processing?.message || `Snapshot ${resource.latest_snapshot_id || 'created'}${resource.projected_dataset_id ? ` · dataset ${resource.projected_dataset_id}` : ''}`}
          </p>

          <div className="mt-4 grid grid-cols-7 gap-1">
            {directSourceProcessingSteps.map((step, index) => {
              const complete = tone !== 'failed' && index <= progressIndex
              const current = tone === 'processing' && index === Math.max(progressIndex + 1, 0)
              return (
                <div key={step.id} className="min-w-0">
                  <div className={`h-1.5 rounded-full ${complete ? 'bg-green-500' : current ? 'bg-brand-orange' : tone === 'failed' && index === 0 ? 'bg-red-500' : 'bg-[#444444]'}`} />
                  <div className={`mt-1 truncate text-[10px] ${complete ? 'text-green-300' : current ? 'text-brand-orange' : 'text-gray-500'}`} title={step.label}>
                    {step.label}
                  </div>
                </div>
              )
            })}
          </div>

          {(processingQuery.isLoading || processingQuery.isFetching) && tone !== 'failed' && (
            <div className="mt-2 text-[11px] text-gray-500">Refreshing processing state...</div>
          )}

          {nextActions.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {nextActions.slice(0, 3).map(action => (
                <span key={action} className="rounded border border-[#444444] px-2 py-1 text-[11px] text-gray-300">
                  {action}
                </span>
              ))}
            </div>
          )}

          <div className="mt-4 flex flex-wrap gap-2">
            <Button asChild size="sm" className="bg-brand-orange hover:bg-brand-orange/90">
              <Link to={`/sources/${resource.id}`}>Open source</Link>
            </Button>
            <Button asChild size="sm" variant="outline" className="border-[#555555] text-white hover:bg-[#3a3a3a]">
              <Link to={`/sources/${resource.id}#evidence`}>Search evidence</Link>
            </Button>
            <Button asChild size="sm" variant="outline" className="border-[#555555] text-white hover:bg-[#3a3a3a]">
              <Link to="/data-models">Create model</Link>
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={onAddAnother} className="text-gray-300 hover:text-white">
              Add another source
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
