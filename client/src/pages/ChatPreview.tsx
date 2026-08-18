import React, { useState, useRef, useEffect, useCallback, useMemo, memo } from 'react'
import { useParams, useLocation, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { Eye, Check, Trash2, ArrowLeft, ArrowUp, Sparkles, Pencil, X, ImagePlus, Clock, Calendar, ChevronDown, FileCode2, LineChart, LockKeyhole, MessageSquareText, Network, Plus, ShieldCheck, AtSign, Table } from 'lucide-react'
import { toast } from 'react-toastify'
import type { Message } from "../types/chat"
import { useStore } from "../stores/useStore"
import { MAX_QUEUE_SIZE } from "../stores/slices/chatSlice"
import MessageComponent from "../components/Message"
import LoadingIndicator from "../components/LoadingIndicator"
import { ModelSelector } from "../components/ModelSelector"
import { DatabaseConnectionDialog } from "../components/DatabaseConnectionDialog"
import { ConfirmationModal } from "../components/ConfirmationModal"
import { TableMentionInput } from "../components/TableMentionInput"
import { ApiService, type LLMConnection, type AgentRequest, type ErrorDetail, type NestedSchemaNode, type Datasource, type ConnectionCreateRequest, type HtmlEditDetectedEvent, type HtmlEditPatchEvent, type HtmlEditCompleteEvent, type HtmlContextRefreshEvent, type DatasourceSelectedEvent, type DashboardFilterDefinition, type BatchFilterPreflightResponse, type PlanStatusEvent, type SemanticModelSummary, type SemanticQueryResultEvent, type NotebookAssetRead } from "../services/api"
import { type LLMProvider } from "../types/llm"
import { showToast } from "../utils/toast"
import ConnectionValidator from "../utils/connectionValidator"
import { DashboardPreviewPanel } from "../components/DashboardPreviewPanel"
import { DashboardFilterSidebar } from "../components/DashboardFilterSidebar"
import { FilterPreflightPanel } from "../components/FilterPreflightPanel"
import { ActiveFiltersBar } from "../components/ActiveFiltersBar"
import FullscreenPreviewModal from "../components/FullscreenPreviewModal"
import ShareModal from "../components/ShareModal"
import ShareDashboardToFolderModal from "../components/ShareDashboardToFolderModal"
import ShareNotebookToFolderModal from "../components/ShareNotebookToFolderModal"
import { useNotebooks, useRenameNotebook } from '../hooks/useNotebooks'
import { useDatasources, useCreateDBConnection, useUploadMultipleFiles, useUploadFromURL } from '../hooks/useDBConnections'
import { useScopes } from '../hooks/useScopes'
import type { ColumnInfo } from "../hooks/useTableMentions"
import { useAppConfig } from '../hooks/useAppConfig'
import { ErrorLogModal, type IframeError } from "../components/ErrorLogModal"
import { injectErrorCaptureScript } from "../utils/iframeErrorCapture"
import { toggleDevTools, isTauriApp, saveBlobToFile } from '../lib/tauri-api'
import { ensureBaseHref, rewriteDashboardHtmlForBackend, getBackendUrlForHtmlProcessing, injectViewerConfig } from '../utils/dashboardHtml'
import '../styles/chat-preview.css'
import { applyFindReplacePreview, applyHtmlPatchPreview, applySearchReplacePreview } from '../utils/dashboardEditing'
import { DatasourceFooterSelector } from '../components/DatasourceFooterSelector'
import { ScheduleBanner } from '../components/schedules/ScheduleBanner'
import { ScheduleConfigPanel } from '../components/schedules/ScheduleConfigPanel'
import { useSchedules, useCreateSchedule, useUpdateSchedule, useDeleteSchedule } from '../hooks/useSchedules'
import type { ScheduleCreate, ScheduleUpdate } from '../services/api'
import {
  buildPreflightQueriesWithFilters,
  countActiveFilterValues,
  getAllowedFilterKeys,
  parseStoredFilterValues,
} from '../utils/dashboardFilters'
import { buildActiveFilterChips, removeActiveFilterChip } from '../utils/filterDisplay'
import PlanDisplay from '../components/PlanDisplay'
import PlanModeToggle from '../components/PlanModeToggle'
import { ResizableSplitPanel } from '../components/ResizableSplitPanel'
import { EMBEDDED_KNOWLEDGE_CENTER_BASE } from '../contexts/EmbeddedModeContext'

type ScheduleFrequency = 'daily' | 'weekly' | 'custom'
const CHAT_PREFLIGHT_DEBUG_STORAGE_KEY = 'chat_preview_filter_preflight_debug'
const ACTIVE_PREVIEW_NOTEBOOK_KEY = 'byaan:active-preview-notebook-id'

function parseCronToScheduleConfig(cron: string): {
  frequency: ScheduleFrequency
  hour: string
  minute: string
  dayOfWeek: string
  customCron: string
} {
  const parts = cron.split(' ')
  if (parts.length !== 5) {
    return { frequency: 'custom', hour: '9', minute: '0', dayOfWeek: '1', customCron: cron }
  }
  const [minute, hour, dayOfMonth, month, dayOfWeek] = parts
  if (dayOfMonth === '*' && month === '*') {
    if (dayOfWeek === '*') {
      return { frequency: 'daily', hour, minute, dayOfWeek: '1', customCron: cron }
    }
    return { frequency: 'weekly', hour, minute, dayOfWeek, customCron: cron }
  }
  return { frequency: 'custom', hour: '9', minute: '0', dayOfWeek: '1', customCron: cron }
}

const getDatasourceDbType = (datasource?: Datasource | null) => {
  if (!datasource) return null
  const sourceType = datasource.source_type as string
  if (sourceType === 'dataset' || sourceType === 'file') {
    return 'duckdb'
  }
  return datasource.type || null
}

const semanticModelLabel = (model: SemanticModelSummary) => model.name || model.id

const compactSemanticLabel = (value: string) => {
  const words = value.trim().split(/\s+/)
  return words
    .filter((word, index) => index === 0 || word.toLocaleLowerCase() !== words[index - 1].toLocaleLowerCase())
    .join(' ')
}

const contextualDimensionLabel = (value: string, metricName: string) => {
  const dimensionName = compactSemanticLabel(value)
  const prefix = `${metricName.toLocaleLowerCase()} `
  return dimensionName.toLocaleLowerCase().startsWith(prefix)
    ? dimensionName.slice(metricName.length).trim()
    : dimensionName
}

const governedSemanticBinding = (assets: NotebookAssetRead[]) => (
  assets.find(
    asset => asset.asset_type === 'semantic_model' && asset.usage_policy_json?.purpose === 'governed_ask_data',
  ) ?? assets.find(asset => asset.asset_type === 'semantic_model')
)

const formatEvidenceTime = (value?: string | null) => {
  if (!value) return 'Not reported'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

const lineageLabel = (item: unknown, index: number) => {
  if (typeof item === 'string') return item
  if (!item || typeof item !== 'object') return `Reference ${index + 1}`
  const record = item as Record<string, unknown>
  return String(
    record.name ||
    record.title ||
    record.table ||
    record.ref ||
    record.source_snapshot_id ||
    record.id ||
    `Reference ${index + 1}`
  )
}

const generateSemanticExamples = (model?: SemanticModelSummary) => {
  if (!model) return []
  const examples: string[] = []
  for (const metric of model.metrics.slice(0, 2)) {
    const metricName = compactSemanticLabel(metric.businessName || metric.name || metric.id)
    const allowedDimensionIds = metric.dimensions?.length
      ? new Set(metric.dimensions)
      : new Set(model.dimensions.map(item => item.id))
    const dimensions = model.dimensions.filter(item => allowedDimensionIds.has(item.id))
    if (dimensions[0]) examples.push(`Show ${metricName} by ${contextualDimensionLabel(dimensions[0].name, metricName)}`)
    examples.push(`What is ${metricName}, and how is it defined?`)
    if (dimensions[1]) examples.push(`Compare ${metricName} across ${contextualDimensionLabel(dimensions[1].name, metricName)}`)
  }
  return Array.from(new Set(examples)).slice(0, 4)
}

function SemanticModelPicker({
  models,
  selectedModel,
  value,
  locked,
  loading,
  error,
  onChange,
  onManage,
}: {
  models: SemanticModelSummary[]
  selectedModel?: SemanticModelSummary
  value: string
  locked: boolean
  loading: boolean
  error: string | null
  onChange: (value: string) => void
  onManage: () => void
}) {
  return (
    <div className="relative flex min-w-0 items-center gap-2">
      <div className="relative min-w-0">
        <Network className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-emerald-400" />
        <select
          aria-label="Semantic Model"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          disabled={locked || loading || models.length === 0}
          className="h-8 w-[min(17rem,calc(100vw-6rem))] appearance-none truncate rounded-md border border-[#343d47] bg-[#161b21] py-0 pl-8 pr-8 text-xs text-[#e7ecf1] outline-none transition-colors hover:border-[#46515d] focus:border-emerald-500/70 disabled:cursor-not-allowed disabled:opacity-70 sm:w-[clamp(11rem,24vw,17rem)]"
        >
          <option value="">{loading ? 'Loading models...' : models.length ? 'Select Semantic Model' : 'No published models'}</option>
          {models.map((model) => (
            <option key={model.id} value={model.id}>{semanticModelLabel(model)} · {model.publishedVersion}</option>
          ))}
        </select>
        {locked ? (
          <LockKeyhole className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#8f9aa6]" />
        ) : (
          <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#8f9aa6]" />
        )}
      </div>
      {selectedModel && (
        <span className="hidden items-center gap-1 text-[11px] text-[#87939f] xl:flex">
          <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
          Published {selectedModel.publishedVersion}
        </span>
      )}
      {!loading && models.length === 0 && (
        <button type="button" onClick={onManage} className="h-8 whitespace-nowrap rounded-md border border-[#343d47] px-2.5 text-xs text-[#d2d9e0] hover:bg-[#1b2128]">
          Publish model
        </button>
      )}
      {error && <span className="sr-only">{error}</span>}
    </div>
  )
}

function SemanticEvidencePanel({
  event,
  dashboardAvailable,
  busy,
  onCreateDashboard,
}: {
  event: SemanticQueryResultEvent | null
  dashboardAvailable: boolean
  busy: boolean
  onCreateDashboard: () => void
}) {
  if (!event) return null
  const result = event.result || ({} as SemanticQueryResultEvent['result'])
  const lineage = Array.isArray(result.lineage) ? result.lineage : []
  const snapshotLabel = result.snapshotId || result.snapshot?.id || result.snapshotHash || result.snapshot?.hash
  const sqlEvidence = result.evidence?.find(item => item.kind === 'sql')
  const sql = result.sql || (typeof sqlEvidence?.content === 'string' ? sqlEvidence.content : '')

  return (
    <div className="mx-auto mb-2 flex w-full max-w-3xl flex-col gap-2 px-4 sm:flex-row sm:items-start sm:px-6 min-[1440px]:max-w-4xl min-[2560px]:max-w-[1400px]">
    <details className="min-w-0 flex-1">
      <summary className="flex min-h-9 cursor-pointer list-none items-center justify-between gap-3 rounded-md border border-[#29333d] bg-[#12171c] px-3 text-xs text-[#c5ced7] hover:border-[#3b4854]">
        <span className="flex min-w-0 items-center gap-2">
          <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-emerald-400" />
          <span className="truncate">Governed evidence · {result.resolvedMetric || 'Semantic metric'}</span>
        </span>
        <span className="shrink-0 text-[11px] text-[#7f8b96]">{result.modelVersion || 'Published'} · {result.policyDecision || 'checked'}</span>
      </summary>
      <div className="grid gap-px overflow-hidden rounded-b-md border border-t-0 border-[#29333d] bg-[#29333d] text-xs sm:grid-cols-2 lg:grid-cols-4">
        <div className="bg-[#12171c] p-3"><div className="text-[#77838e]">Freshness</div><div className="mt-1 break-words text-[#d7dee5]">{formatEvidenceTime(result.dataThrough || result.freshness)}</div></div>
        <div className="bg-[#12171c] p-3"><div className="text-[#77838e]">Snapshot</div><div className="mt-1 truncate text-[#d7dee5]" title={String(snapshotLabel || '')}>{snapshotLabel || 'Published contract'}</div></div>
        <div className="bg-[#12171c] p-3"><div className="text-[#77838e]">Lineage</div><div className="mt-1 text-[#d7dee5]">{lineage.length} reference{lineage.length === 1 ? '' : 's'}</div></div>
        <div className="bg-[#12171c] p-3"><div className="text-[#77838e]">Policy</div><div className="mt-1 text-emerald-400">{result.policyDecision === 'allowed' ? 'Allowed by model' : result.policyDecision || 'Checked'}</div></div>
        {result.metricDefinition && (
          <div className="bg-[#12171c] p-3 sm:col-span-2 lg:col-span-4">
            <div className="text-[#77838e]">Metric definition</div>
            <div className="mt-1 leading-relaxed text-[#d7dee5]">{result.metricDefinition}</div>
          </div>
        )}
        {lineage.length > 0 && (
          <div className="bg-[#12171c] p-3 sm:col-span-2 lg:col-span-4">
            <div className="mb-2 flex items-center gap-1.5 text-[#77838e]"><Network className="h-3.5 w-3.5" />Lineage</div>
            <div className="flex flex-wrap gap-1.5">
              {lineage.map((item, index) => (
                <span key={`${lineageLabel(item, index)}-${index}`} className="rounded border border-[#303b45] bg-[#0f1419] px-2 py-1 text-[11px] text-[#bdc7d0]">
                  {lineageLabel(item, index)}
                </span>
              ))}
            </div>
          </div>
        )}
        {sql && (
          <div className="bg-[#0d1115] p-3 sm:col-span-2 lg:col-span-4">
            <div className="mb-2 flex items-center gap-1.5 text-[#77838e]"><FileCode2 className="h-3.5 w-3.5" />Compiled SQL</div>
            <pre className="max-h-32 overflow-auto whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-[#b9c4ce]">{sql}</pre>
          </div>
        )}
      </div>
    </details>
    {!dashboardAvailable && (
      <button
        type="button"
        onClick={onCreateDashboard}
        disabled={busy}
        className="flex h-9 shrink-0 items-center justify-center gap-1.5 rounded-md border border-[#34404b] px-3 text-xs text-[#c9d2da] hover:border-emerald-500/50 hover:bg-emerald-500/[0.08] hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
        title="Create a dashboard from this governed result"
      >
        <LineChart className="h-3.5 w-3.5 text-emerald-400" />
        Create dashboard
      </button>
    )}
    </div>
  )
}

// Memoized message list component
const MessageList = memo(function MessageList({
  notebookId,
  handleCodeInject,
  currentActivity,
}: {
  notebookId: string | undefined
  handleCodeInject: (data: { query: string; connectionId?: string }) => void
  currentActivity: string
}) {
  const messages = useStore(state => state.currentMessages)
  const notebookStreamingState = useStore(state => state.notebookStreamingState)
  const messageQueue = useStore(state => state.messageQueue)
  const activePlan = useStore(state => state.activePlans[notebookId || ''])
  const isNotebookStreaming = notebookId ? notebookStreamingState[notebookId] || false : false
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const userHasScrolledUp = useRef(false)
  const isAutoScrolling = useRef(false)
  const lastScrollTop = useRef(0)
  const scrollTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const userScrollDetectedRef = useRef(false)

  // Scroll handling logic (same as before)
  const handleScroll = useCallback(() => {
    const container = scrollContainerRef.current
    if (!container) return

    const { scrollTop, scrollHeight, clientHeight } = container
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight

    if (scrollTimeoutRef.current) {
      clearTimeout(scrollTimeoutRef.current)
    }

    if (!isAutoScrolling.current && scrollTop < lastScrollTop.current) {
      userScrollDetectedRef.current = true
      userHasScrolledUp.current = true
    }

    if (distanceFromBottom <= 50) {
      userHasScrolledUp.current = false
      userScrollDetectedRef.current = false
    }

    lastScrollTop.current = scrollTop

    scrollTimeoutRef.current = setTimeout(() => {
      userScrollDetectedRef.current = false
    }, 150)
  }, [])

  useEffect(() => {
    const container = scrollContainerRef.current
    if (!container) return

    container.addEventListener('scroll', handleScroll, { passive: true })
    return () => {
      container.removeEventListener('scroll', handleScroll)
      if (scrollTimeoutRef.current) {
        clearTimeout(scrollTimeoutRef.current)
      }
    }
  }, [handleScroll])

  useEffect(() => {
    const container = scrollContainerRef.current
    const messagesEnd = messagesEndRef.current

    if (!container || !messagesEnd || messages.length === 0) return

    // Get the last and second-to-last messages
    const lastMessage = messages[messages.length - 1]
    const secondLastMessage = messages.length > 1 ? messages[messages.length - 2] : null

    // Check if this is a new user message being sent
    // This happens when: last message is from user OR (last is empty assistant + second-to-last is user)
    const isNewUserMessage =
      lastMessage?.role === 'user' ||
      (lastMessage?.role === 'assistant' && lastMessage.content === '' && secondLastMessage?.role === 'user')

    if (isNewUserMessage) {
      // Check if already in view
      const containerRect = container.getBoundingClientRect()
      const messageEndRect = messagesEnd.getBoundingClientRect()

      // Calculate if the bottom of messages is visible
      const isAlreadyVisible = messageEndRect.bottom >= containerRect.top &&
                               messageEndRect.top <= containerRect.bottom

      if (!isAlreadyVisible) {
        // Smooth scroll to bring the latest message into view
        messagesEnd.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
      }
      return
    }

    // For assistant messages (streaming), use the existing auto-scroll logic
    if (userScrollDetectedRef.current || userHasScrolledUp.current) {
      return
    }

    if (messagesEnd) {
      isAutoScrolling.current = true
      messagesEnd.scrollIntoView({ behavior: "auto", block: "end" })
      setTimeout(() => {
        isAutoScrolling.current = false
      }, 100)
    }

    if (!isNotebookStreaming && !userHasScrolledUp.current) {
      userHasScrolledUp.current = false
    }
  }, [messages, isNotebookStreaming, messageQueue])

  return (
    <div ref={scrollContainerRef} className="flex-1 overflow-y-auto [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">
      {messages.length === 0 ? (
        <div className="flex items-center justify-center h-full max-w-3xl min-[1440px]:max-w-4xl min-[2560px]:max-w-[1400px] mx-auto w-full">
          <div className="text-center text-[#888888]">
            <p className="text-sm">Start a conversation</p>
            <p className="text-xs text-[#666666] mt-1">Ask me anything about your data!</p>
          </div>
        </div>
      ) : (
        <div className="px-4 sm:px-6 py-6 space-y-3 max-w-3xl min-[1440px]:max-w-4xl min-[2560px]:max-w-[1400px] mx-auto w-full">
          {messages.map((message) => (
            <div key={message.id}>
              <MessageComponent message={message} onCodeInject={handleCodeInject} />
            </div>
          ))}

          {isNotebookStreaming && <LoadingIndicator text={currentActivity || 'Thinking'} />}
          {activePlan && (
            <PlanDisplay
              plan={activePlan}
              onDismiss={() => useStore.getState().clearPlan(notebookId || 'temp')}
            />
          )}

          {messageQueue.map((queuedMsg) => (
            <div key={queuedMsg.id} className="opacity-60">
              <MessageComponent
                message={{
                  id: queuedMsg.id,
                  role: 'user',
                  content: queuedMsg.content,
                  timestamp: queuedMsg.timestamp,
                  attachments: queuedMsg.attachments,
                }}
                onCodeInject={handleCodeInject}
              />
              <div className="flex items-center gap-1 ml-2 mt-1">
                <div className="w-2 h-2 bg-yellow-500 rounded-full animate-pulse" />
                <span className="text-xs text-[#888888]">Queued</span>
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>
      )}
    </div>
  )
})

// Memoized chat input component (same as before)
const ChatInput = memo(function ChatInput({
  notebookId,
  datasources,
  tableNames,
  getTableColumns,
  onSubmit,
  selectedProvider,
  selectedModel,
  handleCancelGeneration,
  selectedDatasourceIds,
  onDatasourceChange,
  onUploadFiles,
  onAddNewConnection,
  agentSelectedDatasourceId,
  onSchedule,
  hasSchedule,
  isScheduleMode,
  onCancelSchedule,
  onInputChange,
  grabbedElementText,
  embedded = false,
  semanticModelReady = true,
}: {
  notebookId: string | undefined
  datasources: Array<{ id: string; name: string; tables: Record<string, any> }>
  tableNames: string[]
  getTableColumns: (tableName: string, datasourceName?: string) => any[]
  onSubmit: (messageContent: string, attachments?: Array<{file_name: string, mime_type: "image/png" | "image/jpeg" | "image/webp", file_data: string}>) => Promise<void>
  selectedProvider: any
  selectedModel: any
  handleCancelGeneration: () => void
  selectedDatasourceIds: string[]
  onDatasourceChange: (ids: string[]) => void
  onUploadFiles: (files: File[], fileType: string) => void
  onAddNewConnection: () => void
  agentSelectedDatasourceId?: string | null
  onSchedule?: () => void
  hasSchedule?: boolean
  isScheduleMode?: boolean
  onCancelSchedule?: () => void
  onInputChange?: (value: string) => void
  grabbedElementText?: string
  embedded?: boolean
  semanticModelReady?: boolean
}) {
  const [input, setInput] = useState("")
  const [attachedImages, setAttachedImages] = useState<Array<{file_name: string, mime_type: "image/png" | "image/jpeg" | "image/webp", file_data: string}>>([])
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [, setInputHeight] = useState(36)

  const notebookStreamingState = useStore(state => state.notebookStreamingState)
  const messageQueue = useStore(state => state.messageQueue)
  const isStreaming = notebookId ? notebookStreamingState[notebookId] || false : false
  const isQueueFull = messageQueue.length >= MAX_QUEUE_SIZE
  const isLoading = isQueueFull
  const prevIsLoadingRef = useRef(isStreaming)

  const handleInputChange = useCallback((value: string) => {
    setInput(value)
    if (onInputChange) {
      onInputChange(value)
    }
  }, [onInputChange])

  useEffect(() => {
    if (prevIsLoadingRef.current && !isStreaming) {
      inputRef.current?.focus()
    }
    prevIsLoadingRef.current = isStreaming
  }, [isStreaming])

  const prevGrabbedTextRef = useRef<string>("")

  useEffect(() => {
    if (grabbedElementText && grabbedElementText !== prevGrabbedTextRef.current) {
      setInput(prev => prev ? `${prev}\n\n${grabbedElementText}` : grabbedElementText)
      setTimeout(() => inputRef.current?.focus(), 100)
      prevGrabbedTextRef.current = grabbedElementText
    }
  }, [grabbedElementText])

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files || files.length === 0) return

    const MAX_IMAGES = 5
    const currentCount = attachedImages.length
    const availableSlots = MAX_IMAGES - currentCount

    if (availableSlots <= 0) {
      showToast.error(`Maximum ${MAX_IMAGES} images allowed per message`)
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
      return
    }

    const fileArray = Array.from(files)
    if (fileArray.length > availableSlots) {
      showToast.warning(`Only ${availableSlots} more image${availableSlots > 1 ? 's' : ''} can be added (max ${MAX_IMAGES})`)
    }

    const newAttachments: Array<{file_name: string, mime_type: "image/png" | "image/jpeg" | "image/webp", file_data: string}> = []
    let skippedDueToFormat = 0
    let skippedDueToSize = 0

    for (const file of fileArray.slice(0, availableSlots)) {
      if (!file.type.match(/image\/(png|jpeg|webp)/)) {
        skippedDueToFormat++
        continue
      }

      if (file.size > 5 * 1024 * 1024) {
        skippedDueToSize++
        continue
      }

      try {
        const reader = new FileReader()
        await new Promise<void>((resolve, reject) => {
          reader.onload = () => {
            const base64 = (reader.result as string).split(',')[1]
            newAttachments.push({
              file_name: file.name,
              mime_type: file.type as "image/png" | "image/jpeg" | "image/webp",
              file_data: base64
            })
            resolve()
          }
          reader.onerror = reject
          reader.readAsDataURL(file)
        })
      } catch {
        showToast.error(`Failed to process ${file.name}`)
      }
    }

    if (skippedDueToFormat > 0) {
      showToast.error(`${skippedDueToFormat} file${skippedDueToFormat > 1 ? 's' : ''} skipped (unsupported format - use PNG, JPEG, or WEBP)`)
    }

    if (skippedDueToSize > 0) {
      showToast.error(`${skippedDueToSize} file${skippedDueToSize > 1 ? 's' : ''} skipped (exceeds 5MB limit)`)
    }

    if (newAttachments.length > 0) {
      setAttachedImages(prev => [...prev, ...newAttachments])
    }

    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const handleRemoveAttachment = (index: number) => {
    setAttachedImages(prev => prev.filter((_, i) => i !== index))
  }

  const handlePaste = async (e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items
    if (!items) return

    const imageItems: File[] = []

    for (let i = 0; i < items.length; i++) {
      const item = items[i]
      // Check if the item is an image (png, jpeg, webp)
      if (item.type.match(/^image\/(png|jpeg|webp)$/)) {
        const file = item.getAsFile()
        if (file) {
          imageItems.push(file)
        }
      }
    }

    if (imageItems.length === 0) return

    // Prevent default paste behavior for images (don't paste file path as text)
    e.preventDefault()

    // Check if adding these images would exceed the limit
    const MAX_IMAGES = 5
    const currentCount = attachedImages.length
    const availableSlots = MAX_IMAGES - currentCount

    if (availableSlots <= 0) {
      showToast.error(`Maximum ${MAX_IMAGES} images allowed per message`)
      return
    }

    if (imageItems.length > availableSlots) {
      showToast.warning(`Only ${availableSlots} more image${availableSlots > 1 ? 's' : ''} can be added (max ${MAX_IMAGES})`)
    }

    // Process images using existing validation logic
    const newAttachments: Array<{file_name: string, mime_type: "image/png" | "image/jpeg" | "image/webp", file_data: string}> = []
    let skippedDueToSize = 0

    for (const file of imageItems.slice(0, availableSlots)) {
      // Validate file size (5MB limit)
      if (file.size > 5 * 1024 * 1024) {
        skippedDueToSize++
        continue
      }

      // Convert to base64
      try {
        const base64 = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader()
          reader.onload = () => {
            const result = reader.result as string
            // Remove data URI prefix to get just the base64 data
            const base64Data = result.split(',')[1]
            resolve(base64Data)
          }
          reader.onerror = reject
          reader.readAsDataURL(file)
        })

        newAttachments.push({
          file_name: file.name || `pasted-image-${Date.now()}.${file.type.split('/')[1]}`,
          mime_type: file.type as "image/png" | "image/jpeg" | "image/webp",
          file_data: base64,
        })
      } catch {
        showToast.error('Failed to process pasted image')
      }
    }

    if (skippedDueToSize > 0) {
      showToast.error(`${skippedDueToSize} image${skippedDueToSize > 1 ? 's' : ''} skipped (exceeds 5MB limit)`)
    }

    if (newAttachments.length > 0) {
      setAttachedImages(prev => [...prev, ...newAttachments])
    }
  }
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (isLoading) return

    const messageContent = input.trim()
    if (!messageContent && attachedImages.length === 0) return

    setInput("")
    const attachmentsToSend = attachedImages.length > 0 ? attachedImages : undefined
    setAttachedImages([])
    await onSubmit(messageContent || " ", attachmentsToSend)
  }

  const hasInput = input.trim().length > 0

  return (
    <div className="px-4 py-3 sm:px-6">
      {isScheduleMode && (
        <div className="flex items-center justify-between px-4 py-2.5 mb-0 bg-brand-orange/10 border border-brand-orange/30 rounded-t-2xl border-b-0">
          <div className="flex items-center gap-2">
            <Calendar className="w-4 h-4 text-brand-orange" />
            <span className="text-sm font-medium text-brand-orange">SCHEDULE MODE</span>
            <span className="text-xs text-gray-400 ml-2">Describe what this notebook should report on each scheduled run</span>
          </div>
          <button onClick={onCancelSchedule} className="p-1 hover:bg-[#2a2a2a] rounded transition-colors">
            <X className="w-4 h-4 text-gray-400 hover:text-white" />
          </button>
        </div>
      )}
      <div
        className={`${embedded ? 'rounded-md border-[#343e48] bg-[#151a20] focus-within:border-emerald-500/60 focus-within:ring-emerald-500/20' : 'border-[#333333] bg-[#262626] focus-within:border-brand-orange focus-within:ring-brand-orange/30'} border px-4 pb-2 pt-2 shadow-sm transition-all focus-within:ring-1 ${isScheduleMode ? 'rounded-b-2xl rounded-t-none border-t-0' : embedded ? 'rounded-md' : 'rounded-2xl'}`}
        onPaste={handlePaste}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          multiple
          onChange={handleFileSelect}
          className="hidden"
        />
        {attachedImages.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-2">
            {attachedImages.map((img, index) => (
              <div key={index} className="relative group">
                <img
                  src={`data:${img.mime_type};base64,${img.file_data}`}
                  alt={img.file_name}
                  className="w-12 h-12 object-cover rounded-lg border border-[#3a3a3a]"
                />
                <button
                  onClick={() => handleRemoveAttachment(index)}
                  className="absolute -top-1.5 -right-1.5 w-5 h-5 bg-red-500 hover:bg-red-600 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                  title="Remove image"
                >
                  <X className="w-3 h-3 text-white" />
                </button>
              </div>
            ))}
          </div>
        )}
        <TableMentionInput
          ref={inputRef}
          value={input}
          datasources={datasources}
          tableNames={tableNames}
          getTableColumns={getTableColumns}
          singleLine
          onHeightChange={setInputHeight}
          onValueChange={handleInputChange}
          onSubmit={() => {
            if (!isQueueFull) {
              const event = new Event('submit') as any
              handleSubmit(event)
            }
          }}
          placeholder={!semanticModelReady ? "Select a published Semantic Model first" : !selectedProvider || !selectedModel ? "Configure your AI model first" : isQueueFull ? "Message queue full (max 3)..." : isScheduleMode ? "What should I report each time this runs?" : embedded ? "Ask a business question..." : "Type your message..."}
          disabled={!selectedProvider || !selectedModel || !semanticModelReady}
          className={`w-full text-[#e5e5e5] text-sm min-h-[56px]`}
        />
        {/* Bottom toolbar */}
        <div className="flex items-center justify-between mt-2">
          {/* Left side - Data selector and attachment */}
          <div className="flex items-center gap-1">
            {!embedded && (
              <DatasourceFooterSelector
                selectedDatasourceIds={selectedDatasourceIds}
                onDatasourceChange={onDatasourceChange}
                onUploadFiles={onUploadFiles}
                onAddConnector={onAddNewConnection}
                agentSelectedDatasourceId={agentSelectedDatasourceId}
                disabled={isQueueFull}
              />
            )}
            {!embedded && (
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={!selectedProvider || !selectedModel || isQueueFull}
                className={`w-8 h-8 rounded-lg transition-all flex items-center justify-center ${
                  selectedProvider && selectedModel && !isQueueFull
                    ? 'text-gray-400 hover:text-gray-300 hover:bg-[#333333] cursor-pointer'
                    : 'text-gray-600 cursor-not-allowed'
                }`}
                title="Attach image"
              >
                <ImagePlus className="w-4 h-4" />
              </button>
            )}
            {!embedded && notebookId && <PlanModeToggle notebookId={notebookId} />}
          </div>
          {/* Right side - Schedule + Send buttons */}
          <div className="flex items-center gap-2">
            {!embedded && onSchedule && notebookId && (
              <button
                onClick={onSchedule}
                disabled={isQueueFull}
                className={`w-8 h-8 rounded-lg transition-all flex items-center justify-center ${
                  isQueueFull
                    ? 'text-gray-600 cursor-not-allowed'
                    : hasSchedule
                      ? 'text-brand-orange hover:bg-brand-orange/10'
                      : 'text-gray-400 hover:text-gray-300 hover:bg-[#333333]'
                }`}
                title={hasSchedule ? "Edit schedule" : "Schedule this notebook"}
              >
                <Clock className="w-4 h-4" />
              </button>
            )}
            {isStreaming && (
              <button
                onClick={handleCancelGeneration}
                className="w-8 h-8 bg-red-500 hover:bg-red-600 rounded-lg transition-all shadow-lg hover:shadow-xl flex items-center justify-center"
                title="Stop generation"
              >
                <div className="w-3 h-3 bg-white rounded-sm"></div>
              </button>
            )}
            <button
              onClick={(e) => {
                if (!isQueueFull) {
                  const event = new Event('submit') as any
                  handleSubmit(event)
                }
              }}
              disabled={(!hasInput && attachedImages.length === 0) || !selectedProvider || !selectedModel || !semanticModelReady || isQueueFull}
              className={`w-8 h-8 rounded-lg transition-all flex items-center justify-center ${
                (hasInput || attachedImages.length > 0) && selectedProvider && selectedModel && semanticModelReady && !isQueueFull
                  ? embedded
                    ? 'bg-emerald-500 text-[#07110c] hover:bg-emerald-400 cursor-pointer'
                    : 'bg-brand-orange hover:bg-brand-orange-hover text-white shadow-lg hover:shadow-xl hover:glow-orange-sm cursor-pointer'
                  : 'bg-[#333333] text-gray-600 cursor-not-allowed'
              }`}
              title={isQueueFull ? "Queue full (max 3 messages)" : (hasInput || attachedImages.length > 0) ? "Send message" : "Type a message or attach an image"}
            >
              <ArrowUp className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
})

type HtmlEditTimelineStage = 'start' | 'patch' | 'complete' | 'context'

type HtmlEditTimelineItem = {
  id: string
  sessionId: string
  toolName: string
  stage: HtmlEditTimelineStage
  message: string
  timestamp: number
}

interface ChatPreviewProps {
  embedded?: boolean
}

export default function ChatPreview({ embedded = false }: ChatPreviewProps) {
  const { id: notebookId } = useParams<{ id: string }>()
  const location = useLocation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { canShareExternally } = useScopes()
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const abortControllerRef = useRef<AbortController | null>(null)
  const manualCancellationRef = useRef(false)
  const htmlEditInProgressRef = useRef(false)
  const htmlEditHappenedRef = useRef(false)
  const createdNotebookIdRef = useRef<string | null>(null)
  const emptyStateInputRef = useRef<HTMLTextAreaElement>(null)
  const [, setEmptyInputHeight] = useState(36)

  const embeddedAskBase = `${EMBEDDED_KNOWLEDGE_CENTER_BASE}/ask`
  const isNewNotebook = embedded
    ? location.pathname === embeddedAskBase || location.pathname === `${embeddedAskBase}/`
    : location.pathname === '/notebook/new'
  const isPreviewRoute = embedded
    ? new RegExp(`^${embeddedAskBase}/[^/]+/preview/?$`).test(location.pathname)
    : /^\/notebook\/[^/]+\/preview\/?$/.test(location.pathname)
  const conversationHomePath = embedded ? embeddedAskBase : '/'
  const datasourceHomePath = embedded ? `${EMBEDDED_KNOWLEDGE_CENTER_BASE}/sources` : '/databases'
  const notebookPath = (id: string, preview = false) => (
    embedded
      ? `${embeddedAskBase}/${id}${preview ? '/preview' : ''}`
      : `/notebook/${id}${preview ? '/preview' : ''}`
  )
  const viewportHeightClass = embedded ? 'h-full' : 'h-screen'
  const { isSelfHosted, features } = useAppConfig()

  // State for new notebook datasource selection
  const [selectedDatasourceId, setSelectedDatasourceId] = useState<string | null>(null)
  const [selectedDatasourceType, setSelectedDatasourceType] = useState<string | null>(null)
  const { data: datasourcesResponse, isLoading: isDatasourcesLoading } = useDatasources()
  const datasources = datasourcesResponse?.items || []
  const sortedDatasources = useMemo(() => {
    return [...datasources].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
  }, [datasources])
  const firstDatasourceId = sortedDatasources[0]?.id
  const sortedDatasourcesRef = useRef<typeof sortedDatasources>([])
  sortedDatasourcesRef.current = sortedDatasources
  const [pendingDatasourceId, setPendingDatasourceId] = useState<string>('')
  const [pendingDatasourceIds, setPendingDatasourceIds] = useState<string[]>([])  // Multi-db support
  const pendingDatasourceIdsRef = useRef<string[]>([])  // Ref to access current value in async callbacks
  const [agentSelectedDatasourceId, setAgentSelectedDatasourceId] = useState<string | null>(null)
  const [isDatasourceModalOpen, setIsDatasourceModalOpen] = useState(false)
  const [datasourceDialogMode, setDatasourceDialogMode] = useState<'select' | 'create'>(sortedDatasources.length > 0 ? 'select' : 'create')
  const selectedDatasourceInfo = useMemo(() => {
    return sortedDatasources.find(ds => ds.id === selectedDatasourceId) || null
  }, [sortedDatasources, selectedDatasourceId])
  const createConnectionMutation = useCreateDBConnection()
  const uploadMultipleFilesMutation = useUploadMultipleFiles()
  const uploadFromURLMutation = useUploadFromURL()
  const isDatasourceActionPending = createConnectionMutation.isPending || uploadMultipleFilesMutation.isPending || uploadFromURLMutation.isPending

  const { data: notebooks = [] } = useNotebooks()
  const currentNotebook = notebooks.find(n => n.id === notebookId)
  const renameNotebookMutation = useRenameNotebook()

  // Keep refs in sync with state for async callback access
  useEffect(() => {
    pendingDatasourceIdsRef.current = pendingDatasourceIds
  }, [pendingDatasourceIds])

  useEffect(() => {
    sortedDatasourcesRef.current = sortedDatasources
  }, [sortedDatasources])

  // Fetch schemas for pending datasources when they change
  useEffect(() => {
    if (!isNewNotebook || pendingDatasourceIds.length === 0) {
      setPendingDatasourceSchemas({})
      return
    }

    const fetchSchemas = async () => {
      const schemas: Record<string, any> = {}

      for (const datasourceId of pendingDatasourceIds) {
        try {
          const schemaResponse = await ApiService.getDatasourceSchema(datasourceId)
          schemas[datasourceId] = schemaResponse
        } catch (error) {
          console.error(`Failed to fetch schema for datasource ${datasourceId}:`, error)
          schemas[datasourceId] = null
        }
      }

      setPendingDatasourceSchemas(schemas)
    }

    fetchSchemas()
  }, [isNewNotebook, pendingDatasourceIds])

  // Dataset selection is now optional for new notebooks - no auto-open modal
  // Users can add datasets via the UI button; agent discovers data sources dynamically

  useEffect(() => {
    if (!isNewNotebook) return
    if (!firstDatasourceId) return
    setPendingDatasourceId(prev => prev || firstDatasourceId)
  }, [isNewNotebook, firstDatasourceId])

  useEffect(() => {
    if (!isNewNotebook || !selectedDatasourceId) return
    setPendingDatasourceId(selectedDatasourceId)
  }, [isNewNotebook, selectedDatasourceId])

  // Note: Dataset selection is now optional for new notebooks
  // Users can add datasets later via the UI button
  // The agent will use discovery tools to find relevant datasets

  // Notebook name editing state
  const [isEditingName, setIsEditingName] = useState(false)
  const [editedName, setEditedName] = useState("")
  const nameInputRef = useRef<HTMLInputElement>(null)

  // Get messages from store
  const messages = useStore(state => state.currentMessages)
  const notebookStreamingState = useStore(state => state.notebookStreamingState)

  // Empty state input management
  const [input, setInput] = useState("")
  const [isInitialLoading, setIsInitialLoading] = useState(false)
  const [emptyStateAttachedImages, setEmptyStateAttachedImages] = useState<Array<{file_name: string, mime_type: "image/png" | "image/jpeg" | "image/webp", file_data: string}>>([])
  const emptyFileInputRef = useRef<HTMLInputElement>(null)

  // Model selection state
  const [selectedProvider, setSelectedProvider] = useState<LLMProvider | undefined>()
  const [selectedModel, setSelectedModel] = useState<string | undefined>()
  const [selectedConnectionId, setSelectedConnectionId] = useState<string | undefined>()
  const [availableConnections, setAvailableConnections] = useState<LLMConnection[]>([])
  const [availableModels, setAvailableModels] = useState<Record<string, string[]>>({})
  const [llmDataLoaded, setLlmDataLoaded] = useState(false)
  const [isLoadingLLMData, setIsLoadingLLMData] = useState(true)
  const [semanticModels, setSemanticModels] = useState<SemanticModelSummary[]>([])
  const [selectedSemanticModelId, setSelectedSemanticModelId] = useState('')
  const [boundSemanticModelId, setBoundSemanticModelId] = useState('')
  const [isLoadingSemanticModels, setIsLoadingSemanticModels] = useState(embedded)
  const [semanticModelsError, setSemanticModelsError] = useState<string | null>(null)
  const [latestSemanticEvidence, setLatestSemanticEvidence] = useState<SemanticQueryResultEvent | null>(null)
  const selectedSemanticModel = useMemo(
    () => semanticModels.find(model => model.id === selectedSemanticModelId),
    [semanticModels, selectedSemanticModelId],
  )
  const semanticExamples = useMemo(() => generateSemanticExamples(selectedSemanticModel), [selectedSemanticModel])
  const semanticModelReady = !embedded || Boolean(selectedSemanticModelId && selectedSemanticModel)
  const assistantReady = Boolean(selectedProvider && selectedModel && selectedConnectionId)

  // Preferred model from store
  const preferredProvider = useStore(state => state.preferredProvider)
  const preferredModel = useStore(state => state.preferredModel)
  const fetchPreferredModel = useStore(state => state.fetchPreferredModel)
  const setPreferredModelAction = useStore(state => state.setPreferredModel)
  const clearPreferredModelAction = useStore(state => state.clearPreferredModel)

  // HTML preview state
  const [previewPanelTab, setPreviewPanelTab] = useState<"preview" | "code" | "queries">("preview")
  const [htmlContent, setHtmlContent] = useState("")
  const [processedHtmlContent, setProcessedHtmlContent] = useState("")
  const [dashboardFilters, setDashboardFilters] = useState<DashboardFilterDefinition[]>([])
  const [isDashboardFiltersLoaded, setIsDashboardFiltersLoaded] = useState(false)
  const [dashboardFilterValues, setDashboardFilterValues] = useState<Record<string, unknown>>({})
  const [isFilterPreflightLoading, setIsFilterPreflightLoading] = useState(false)
  const [filterPreflightResponse, setFilterPreflightResponse] = useState<BatchFilterPreflightResponse | null>(null)
  const [filterPreflightError, setFilterPreflightError] = useState<string | null>(null)
  const [showFilterPreflightDebug, setShowFilterPreflightDebug] = useState<boolean>(() => {
    if (typeof window === 'undefined') {
      return false
    }
    return window.localStorage.getItem(CHAT_PREFLIGHT_DEBUG_STORAGE_KEY) === '1'
  })
  const filterPreflightRequestSeqRef = useRef(0)
  const [generatedCode, setGeneratedCode] = useState("")
  const [dashboardAvailable, setDashboardAvailable] = useState(false)
  const [copied, setCopied] = useState(false)
  const [isExportingPdf, setIsExportingPdf] = useState(false)
  const [isExportingHtml, setIsExportingHtml] = useState(false)
  const [isShareModalOpen, setIsShareModalOpen] = useState(false)
  const [isDashboardFolderModalOpen, setIsDashboardFolderModalOpen] = useState(false)
  const [isNotebookFolderModalOpen, setIsNotebookFolderModalOpen] = useState(false)
  const [isPreviewOpen, setIsPreviewOpen] = useState(() => {
    if (typeof window === 'undefined' || !notebookId) return false
    if (isPreviewRoute) return true
    return localStorage.getItem(ACTIVE_PREVIEW_NOTEBOOK_KEY) === notebookId
  })
  const userClosedPreviewRef = useRef(false)
  const [status, setStatus] = useState("")
  const [grabbedElementText, setGrabbedElementText] = useState<string>("")
  const [injectedQuery, setInjectedQuery] = useState<string | undefined>()
  const [injectedQueryVersion, setInjectedQueryVersion] = useState(0)
  const [injectedConnectionId, setInjectedConnectionId] = useState<string | undefined>()
  const [currentActivity, setCurrentActivity] = useState<string>("")
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [iframeErrors, setIframeErrors] = useState<IframeError[]>([])
  const [isHtmlBeingEdited, setIsHtmlBeingEdited] = useState(false)
  const [isHtmlGenerationAnimationActive, setIsHtmlGenerationAnimationActive] = useState(false)
  const [iframeKey, setIframeKey] = useState(0)
  const [hasAttemptedAutoFix, setHasAttemptedAutoFix] = useState(false)
  const [htmlEditTimeline, setHtmlEditTimeline] = useState<HtmlEditTimelineItem[]>([])
  const [liveHtmlCode, setLiveHtmlCode] = useState<string | null>(null)
  const [isLiveHtmlStreamEnabled, setIsLiveHtmlStreamEnabled] = useState(true)
  const editSessionIdRef = useRef<string | null>(null)
  const setNotebookStreaming = useStore.getState().setNotebookStreaming
  const getNotebookStreaming = useStore.getState().getNotebookStreaming
  const isNotebookStreaming = notebookId ? notebookStreamingState[notebookId] || false : false

  // Modals
  const [showPreviewModal, setShowPreviewModal] = useState(false)
  const [showConfirmModal, setShowConfirmModal] = useState(false)

  // Schedules - In-notebook UX
  const { data: notebookSchedules = [] } = useSchedules(notebookId)
  const createScheduleMutation = useCreateSchedule()
  const updateScheduleMutation = useUpdateSchedule()
  const deleteScheduleMutation = useDeleteSchedule()
  const existingSchedule = notebookSchedules.length > 0 ? notebookSchedules[0] : null

  // Schedule mode state
  const [isScheduleMode, setIsScheduleMode] = useState(false)
  const [scheduleInstruction, setScheduleInstruction] = useState('')
  const [scheduleConfig, setScheduleConfig] = useState({
    frequency: 'daily' as 'daily' | 'weekly' | 'custom',
    hour: '9',
    minute: '0',
    dayOfWeek: '1',
    customCron: '0 9 * * *',
    slackChannelId: '',
  })
  const [slackChannelNames, setSlackChannelNames] = useState<Record<string, string>>({})

  // Load slack channel names for banner display
  useEffect(() => {
    if (existingSchedule?.slack_channel_id) {
      ApiService.getSlackChannels()
        .then(channels => {
          const channelMap: Record<string, string> = {}
          channels.forEach(c => { channelMap[c.id] = c.name })
          setSlackChannelNames(channelMap)
        })
        .catch(() => {})
    }
  }, [existingSchedule?.slack_channel_id])
  
  // Standalone notebooks keep the legacy preview behavior. Embedded Ask Data only
  // exposes a Dashboard result after the blank version-1 template has been edited.
  const showDashboardCard = !!notebookId
  const hasHtmlContent = !!(processedHtmlContent || generatedCode)
  const dashboardReady = dashboardAvailable && !isNotebookStreaming && !isHtmlBeingEdited && !isHtmlGenerationAnimationActive
  const canOpenDashboard = embedded ? dashboardReady : hasHtmlContent

  useEffect(() => {
    if (!notebookId) {
      setIsPreviewOpen(false)
      return
    }
    if (isPreviewRoute && (!embedded || canOpenDashboard)) {
      setIsPreviewOpen(true)
      userClosedPreviewRef.current = false
      localStorage.setItem(ACTIVE_PREVIEW_NOTEBOOK_KEY, notebookId)
      return
    }
    if (embedded) {
      setIsPreviewOpen(false)
      return
    }
    const stored = localStorage.getItem(ACTIVE_PREVIEW_NOTEBOOK_KEY)
    setIsPreviewOpen(stored === notebookId)
  }, [canOpenDashboard, embedded, notebookId, isPreviewRoute])

  const clearStoredPreviewIfCurrent = useCallback(() => {
    if (!notebookId) return
    if (localStorage.getItem(ACTIVE_PREVIEW_NOTEBOOK_KEY) === notebookId) {
      localStorage.removeItem(ACTIVE_PREVIEW_NOTEBOOK_KEY)
    }
  }, [notebookId])

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isPreviewOpen) {
        setIsPreviewOpen(false)
        userClosedPreviewRef.current = true
        clearStoredPreviewIfCurrent()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isPreviewOpen, clearStoredPreviewIfCurrent])

  const handleClosePreview = useCallback(() => {
    setIsPreviewOpen(false)
    userClosedPreviewRef.current = true
    clearStoredPreviewIfCurrent()
  }, [clearStoredPreviewIfCurrent])

  const handleOpenPreview = useCallback(() => {
    setIsPreviewOpen(true)
    userClosedPreviewRef.current = false
    if (notebookId) {
      localStorage.setItem(ACTIVE_PREVIEW_NOTEBOOK_KEY, notebookId)
    }
  }, [notebookId])

  // Dashboard versioning state
  const [availableVersions, setAvailableVersions] = useState<import('../services/api').DashboardVersion[]>([])
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null)
  const [currentSessionVersion, setCurrentSessionVersion] = useState<number | null>(null)
  const [latestVersionNum, setLatestVersionNum] = useState<number>(1)

  useEffect(() => {
    if (!embedded && availableVersions.length > 1 && !userClosedPreviewRef.current) {
      handleOpenPreview()
    }
  }, [availableVersions, embedded, handleOpenPreview])

  const activeDashboardId = useMemo(() => {
    const versionToUse = selectedVersion ?? latestVersionNum
    const match = availableVersions.find(v => v.version_num === versionToUse)
    return match?.id
  }, [availableVersions, selectedVersion, latestVersionNum])
  const filterStorageKey = useMemo(
    () => (notebookId ? `chat_preview_filters_${notebookId}` : null),
    [notebookId],
  )
  const dashboardFilterLoadSeqRef = useRef(0)

  useEffect(() => {
    const storedValues = parseStoredFilterValues(filterStorageKey, 'dashboard filter values')
    setDashboardFilterValues(storedValues)
  }, [filterStorageKey])

  useEffect(() => {
    if (!filterStorageKey || typeof window === 'undefined') {
      return
    }
    window.localStorage.setItem(filterStorageKey, JSON.stringify(dashboardFilterValues))
  }, [dashboardFilterValues, filterStorageKey])

  useEffect(() => {
    if (typeof window === 'undefined') {
      return
    }
    window.localStorage.setItem(
      CHAT_PREFLIGHT_DEBUG_STORAGE_KEY,
      showFilterPreflightDebug ? '1' : '0',
    )
  }, [showFilterPreflightDebug])

  // Listen for react-grab postMessage from dashboard iframe
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (event.data?.type === 'REACT_GRAB_COPY') {
        const { htmlContent, elements } = event.data.payload

        if (!elements || elements.length === 0) {
          return
        }

        const element = elements[0]

        // Format the grabbed element context for AI
        const grabbedContext = `[Grabbed Element from Dashboard]

I want to modify this specific element:
- Tag: <${element.tagName.toLowerCase()}${element.className ? ` class="${element.className}"` : ''}${element.id ? ` id="${element.id}"` : ''}>
- Location: ${element.className ? `Element with classes "${element.className}"` : 'Dashboard element'}

\`\`\`html
${htmlContent}
\`\`\`

Please modify this element to: `

        // Set grabbed text for ChatInput to pick up
        setGrabbedElementText(grabbedContext)

        // Also update empty state input
        setInput(prevInput => {
          const newValue = prevInput ? `${prevInput}\n\n${grabbedContext}` : grabbedContext
          return newValue
        })

        showToast.success('Element context copied.')
      }
    }

    window.addEventListener('message', handleMessage)
    return () => window.removeEventListener('message', handleMessage)
  }, [])

  // Handle element grabbed from dashboard via button (not postMessage)
  const handleElementGrabbed = useCallback((htmlContent: string, elementInfo: Array<{ tagName: string; className: string; id: string; textContent: string }>) => {
    if (!elementInfo || elementInfo.length === 0) {
      return
    }

    const element = elementInfo[0]

    const grabbedContext = `[Grabbed Element from Dashboard]

I want to modify this specific element:
- Tag: <${element.tagName.toLowerCase()}${element.className ? ` class="${element.className}"` : ''}${element.id ? ` id="${element.id}"` : ''}>
- Location: ${element.className ? `Element with classes "${element.className}"` : 'Dashboard element'}

\`\`\`html
${htmlContent}
\`\`\`

Please modify this element to: `

    // Set grabbed text for ChatInput to pick up
    setGrabbedElementText(grabbedContext)

    // Also update empty state input
    setInput(prevInput => {
      const newValue = prevInput ? `${prevInput}\n\n${grabbedContext}` : grabbedContext
      return newValue
    })
  }, [])

  const loadDashboardFilters = useCallback(async () => {
    const loadSeq = ++dashboardFilterLoadSeqRef.current
    if (!notebookId || isNewNotebook) {
      setDashboardFilters([])
      setIsDashboardFiltersLoaded(true)
      return
    }

    setIsDashboardFiltersLoaded(false)
    try {
      const config = await ApiService.getNotebookDashboardFilters(notebookId)
      if (loadSeq !== dashboardFilterLoadSeqRef.current) {
        return
      }
      setDashboardFilters(config.filters || [])
      setIsDashboardFiltersLoaded(true)
    } catch (error) {
      if (loadSeq !== dashboardFilterLoadSeqRef.current) {
        return
      }
      setDashboardFilters([])
      setIsDashboardFiltersLoaded(true)
      console.warn('Failed to load notebook filters config', error)
    }
  }, [isNewNotebook, notebookId])

  useEffect(() => {
    void loadDashboardFilters()
  }, [loadDashboardFilters, latestVersionNum])

  useEffect(() => {
    if (!isDashboardFiltersLoaded) {
      return
    }

    const allowedKeys = getAllowedFilterKeys(dashboardFilters)
    if (allowedKeys.size === 0) {
      setDashboardFilterValues({})
      return
    }

    setDashboardFilterValues((previous) => {
      const next: Record<string, unknown> = {}
      for (const [key, value] of Object.entries(previous)) {
        if (allowedKeys.has(key)) {
          next[key] = value
        }
      }
      return next
    })
  }, [dashboardFilters, isDashboardFiltersLoaded])

  const activeFilterValueCount = useMemo(
    () => countActiveFilterValues(dashboardFilterValues),
    [dashboardFilterValues],
  )
  const activeFilterChips = useMemo(
    () => buildActiveFilterChips(dashboardFilters, dashboardFilterValues),
    [dashboardFilters, dashboardFilterValues],
  )

  const preflightQueriesWithFilters = useMemo(
    () => buildPreflightQueriesWithFilters(dashboardFilters, dashboardFilterValues),
    [dashboardFilters, dashboardFilterValues],
  )

  useEffect(() => {
    if (!showFilterPreflightDebug) {
      setIsFilterPreflightLoading(false)
      setFilterPreflightError(null)
      setFilterPreflightResponse(null)
      return
    }

    if (!notebookId || isNewNotebook || !isDashboardFiltersLoaded) {
      setIsFilterPreflightLoading(false)
      setFilterPreflightError(null)
      setFilterPreflightResponse(null)
      return
    }

    if (isNotebookStreaming || isHtmlBeingEdited) {
      return
    }

    if (preflightQueriesWithFilters.length === 0) {
      setIsFilterPreflightLoading(false)
      setFilterPreflightError(null)
      setFilterPreflightResponse(null)
      return
    }

    const requestSeq = ++filterPreflightRequestSeqRef.current
    const timeoutId = window.setTimeout(async () => {
      setIsFilterPreflightLoading(true)
      setFilterPreflightError(null)
      try {
        const payload = {
          queries_with_filters: preflightQueriesWithFilters,
          max_parallel: 5,
        }
        const response = await ApiService.preflightNotebookQueryFilters(payload)

        if (requestSeq !== filterPreflightRequestSeqRef.current) {
          return
        }
        setFilterPreflightResponse(response)
      } catch (error) {
        if (requestSeq !== filterPreflightRequestSeqRef.current) {
          return
        }
        const message = error instanceof Error ? error.message : 'Failed to validate dashboard filters'
        setFilterPreflightError(message)
        setFilterPreflightResponse(null)
      } finally {
        if (requestSeq === filterPreflightRequestSeqRef.current) {
          setIsFilterPreflightLoading(false)
        }
      }
    }, 350)

    return () => window.clearTimeout(timeoutId)
  }, [
    isDashboardFiltersLoaded,
    isHtmlBeingEdited,
    isNewNotebook,
    isNotebookStreaming,
    notebookId,
    preflightQueriesWithFilters,
    showFilterPreflightDebug,
  ])

  const postFiltersToPreviewIframe = useCallback(
    (values: Record<string, unknown>, reload: boolean) => {
      const iframeWindow = iframeRef.current?.contentWindow
      if (!iframeWindow) {
        return
      }
      iframeWindow.postMessage(
        {
          type: 'dashboard.filters.update.v1',
          dashboardId: activeDashboardId ?? null,
          filterValues: values,
          filterDefinitions: dashboardFilters,
          reload,
        },
        '*',
      )
    },
    [activeDashboardId, dashboardFilters],
  )

  const handlePreviewIframeLoad = useCallback(() => {
    postFiltersToPreviewIframe(dashboardFilterValues, false)
  }, [dashboardFilterValues, postFiltersToPreviewIframe])

  const skipInitialAutoApplyRef = useRef(false)
  useEffect(() => {
    skipInitialAutoApplyRef.current = false
  }, [activeDashboardId])

  useEffect(() => {
    if (!activeDashboardId) {
      return
    }
    if (!skipInitialAutoApplyRef.current) {
      skipInitialAutoApplyRef.current = true
      return
    }
    const timeoutId = window.setTimeout(() => {
      postFiltersToPreviewIframe(dashboardFilterValues, true)
    }, 300)
    return () => window.clearTimeout(timeoutId)
  }, [activeDashboardId, dashboardFilterValues, postFiltersToPreviewIframe])

  useEffect(() => {
    if (!activeDashboardId) {
      return
    }
    postFiltersToPreviewIframe(dashboardFilterValues, false)
  }, [activeDashboardId, dashboardFilters, dashboardFilterValues, postFiltersToPreviewIframe])

  // Database connection state
  const [allNotebookConnections, setAllNotebookConnections] = useState<any[]>([])
  const [notebookConnection, setNotebookConnection] = useState<any>(null)

  // Initialize pendingDatasourceIds from notebook connections when loading existing notebook
  useEffect(() => {
    if (!isNewNotebook && allNotebookConnections.length > 0) {
      const connectionIds = allNotebookConnections
        .map(c => c.connection_id || c.dataset_id)
        .filter(Boolean)
      setPendingDatasourceIds(prev => {
        const merged = [...new Set([...connectionIds, ...prev])]
        return merged
      })
    }
  }, [isNewNotebook, allNotebookConnections])

  // Schemas for pending datasources in new notebooks
  const [pendingDatasourceSchemas, setPendingDatasourceSchemas] = useState<Record<string, any>>({})

  // Use Zustand store - ONLY subscribe to schema for this component
  const schema = useStore(state => state.schema)
  const loadSchema = useStore(state => state.loadSchema)

  // Extract stable function references (these don't change, so they won't trigger re-renders)
  const addMessage = useStore.getState().addMessage
  const updateMessage = useStore.getState().updateMessage
  const setIsStreaming = useStore.getState().setIsStreaming
  const setMessages = useStore.getState().setMessages
  const setSchemaNotebook = useStore.getState().setCurrentNotebook
  const cacheSchema = useStore.getState().cacheSchema
  const setSchemaLoading = useStore.getState().setSchemaLoading
  const setSchemaError = useStore.getState().setSchemaError
  const updateNotebook = useStore.getState().updateNotebook
  const clearQueue = useStore.getState().clearQueue
  const wasDashboardGenerationActiveRef = useRef(false)

  useEffect(() => {
    const isGenerationActive = isNotebookStreaming || isHtmlBeingEdited
    const wasActive = wasDashboardGenerationActiveRef.current
    wasDashboardGenerationActiveRef.current = isGenerationActive

    if (!wasActive || isGenerationActive) {
      return
    }

    void loadDashboardFilters()
  }, [isNotebookStreaming, isHtmlBeingEdited, loadDashboardFilters])

  // Get datasources from schema (supports both single and multiple databases)
  type SchemaDataset = {
    id: string
    name: string
    tables: Record<string, any>
  }

  const schemaDatasets = useMemo<SchemaDataset[]>(() => {
    if (isNewNotebook && pendingDatasourceIds.length > 0 && Object.keys(pendingDatasourceSchemas).length > 0) {
      const result = pendingDatasourceIds
        .map(datasourceId => {
          const datasource = datasources.find(ds => ds.id === datasourceId)
          const schema = pendingDatasourceSchemas[datasourceId]

          if (!datasource || !schema) return null

          let tables = {}

          // Extract tables from schema response
          // Schema can be nested: schema.schema.schema (for datasource responses with database_type wrapper)
          if (schema.schema && typeof schema.schema === 'object') {
            const innerSchema = schema.schema
            if (innerSchema.schema && typeof innerSchema.schema === 'object') {
              tables = innerSchema.schema
            } else {
              tables = innerSchema
            }
          } else if (schema.databases && Array.isArray(schema.databases)) {
            tables = schema.databases[0]?.schema || {}
          }

          return {
            id: datasource.id,
            name: datasource.name,
            tables
          }
        })
        .filter((ds): ds is { id: string; name: string; tables: Record<string, any> } => ds !== null)

      return result
    }

    if (allNotebookConnections && allNotebookConnections.length > 1) {
      const result = allNotebookConnections.map((conn: any) => {
        let tables = {}

        if (conn.database_schema && typeof conn.database_schema === 'object') {
          const dbSchema = conn.database_schema
          if (dbSchema.schema && typeof dbSchema.schema === 'object') {
            tables = dbSchema.schema
          }
        } else if (conn.schema && typeof conn.schema === 'object') {
          if (conn.schema.schema && typeof conn.schema.schema === 'object') {
            tables = conn.schema.schema
          } else {
            tables = conn.schema
          }
        }

        return {
          id: conn.id,
          name: conn.name,
          tables: tables
        }
      })
      return result
    }

    if (!schema) return []

    // Check for multi-database schema
    const isMultiDB = 'databases' in schema && Array.isArray((schema as any).databases)

    if (isMultiDB) {
      // Multiple databases - create structured datasources array
      const multiSchema = schema as any
      const result = multiSchema.databases.map((db: any) => ({
        id: db.connection_id || db.connection_name,
        name: db.connection_name,
        tables: db.schema || {}
      }))
      return result
    } else {
      // Single database - wrap in datasource structure
      const rawSchema = (schema as any).schema
      const schemaData = rawSchema && typeof rawSchema === 'object'
        ? (rawSchema.schema && typeof rawSchema.schema === 'object' ? rawSchema.schema : rawSchema)
        : {}

      const tables = Object.fromEntries(
        Object.entries(schemaData).filter(([, value]) => value && typeof value === 'object')
      ) as Record<string, any>

      const result = [{
        id: (schema as any).connection_id || (schema as any).datasource_name || 'default',
        name: (schema as any).connection_name || (schema as any).datasource_name || 'Default',
        tables
      }]
      return result
    }
  }, [schema, allNotebookConnections, isNewNotebook, pendingDatasourceIds, pendingDatasourceSchemas, datasources])

  const tableNames = useMemo(() => {
    return schemaDatasets.flatMap(ds =>
      Object.keys(ds.tables).map(tableName => `${ds.name}:${tableName}`)
    )
  }, [schemaDatasets])

  // Function to get columns for a specific table
  const getSchemaTypeLabel = useCallback((schema?: NestedSchemaNode | null) => {
    if (!schema) return 'mixed'
    const baseType = schema.type
    if (Array.isArray(baseType)) {
      return baseType.join(' | ')
    }
    return baseType || 'mixed'
  }, [])

  const getChildProperties = useCallback((schema?: NestedSchemaNode | null) => {
    if (!schema) return undefined
    if (schema.properties) return schema.properties
    if (schema.items && schema.items.properties) return schema.items.properties
    return undefined
  }, [])

  const getTableColumns = useCallback((tableName: string, datasourceName?: string): ColumnInfo[] => {
    let tableData: any = null

    if (datasourceName) {
      const datasource = schemaDatasets.find(ds => ds.name === datasourceName)
      if (datasource && datasource.tables[tableName]) {
        tableData = datasource.tables[tableName]
      }
    } else {
      if (tableName.includes(':')) {
        const [dsName, tName] = tableName.split(':')
        const datasource = schemaDatasets.find(ds => ds.name === dsName)
        if (datasource && datasource.tables[tName]) {
          tableData = datasource.tables[tName]
        }
      } else {
        for (const datasource of schemaDatasets) {
          if (datasource.tables[tableName]) {
            tableData = datasource.tables[tableName]
            break
          }
        }
      }
    }

    if (!tableData || typeof tableData !== 'object') {
      return []
    }

    // Handle MongoDB collections
    if ('sample_fields' in tableData && tableData.sample_fields) {
      const nestedSchema = tableData.nested_schema as NestedSchemaNode | undefined
      const properties = getChildProperties(nestedSchema)
      const seen = new Set<string>()
      const columns: ColumnInfo[] = []

      if (properties) {
        for (const [fieldName, fieldSchema] of Object.entries(properties)) {
          seen.add(fieldName)
          columns.push({
            name: fieldName,
            type: getSchemaTypeLabel(fieldSchema),
            nullable: true,
            nestedSchema: fieldSchema
          })
        }
      }

      for (const field of tableData.sample_fields as string[]) {
        if (!seen.has(field)) {
          columns.push({
            name: field,
            type: 'mixed',
            nullable: true
          })
        }
      }

      return columns
    }

    // Handle SQL tables
    if ('columns' in tableData && tableData.columns) {
      const columns = tableData.columns.map((col: any) => {
        const nestedSchema = (col.nested_schema ?? null) as NestedSchemaNode | null
        return {
          name: col.name,
          type: col.type,
          nullable: col.nullable !== false,
          nestedSchema: nestedSchema ?? undefined
        }
      })
      return columns
    }
    return []
  }, [schemaDatasets, getChildProperties, getSchemaTypeLabel])

  useEffect(() => {
    if (!isNewNotebook) return

    if (!selectedDatasourceId) {
      setSchemaNotebook(null)
      return
    }

    const virtualNotebookId = `datasource-${selectedDatasourceId}`
    setSchemaNotebook(virtualNotebookId)

    let isActive = true

    const loadDatasourceSchema = async () => {
      setSchemaError(null)
      setSchemaLoading(true)

      try {
        const schemaResponse = await ApiService.getDatasourceSchema(selectedDatasourceId)
        if (isActive) {
          cacheSchema(schemaResponse)
        }
      } catch (error) {
        if (!isActive) return
        const errorMessage = error instanceof Error ? error.message : 'Failed to load datasource schema'
        setSchemaError(errorMessage)
        showToast.error(errorMessage)
      } finally {
        if (isActive) {
          setSchemaLoading(false)
        }
      }
    }

    loadDatasourceSchema()

    return () => {
      isActive = false
    }
  }, [isNewNotebook, selectedDatasourceId])

  useEffect(() => {
    let cancelled = false

    if (!htmlContent) {
      setProcessedHtmlContent('')
      return () => {
        cancelled = true
      }
    }

    const prepareHtml = async () => {
      const fallbackRewritten = rewriteDashboardHtmlForBackend(htmlContent)
      const fallbackWithViewer = injectViewerConfig(
        fallbackRewritten,
        activeDashboardId,
        '/api/viewer',
        'same-origin',
        null,
        dashboardFilterValues,
        dashboardFilters,
      )
      const fallbackWithScript = injectErrorCaptureScript(fallbackWithViewer)
      const fallbackWithBase = ensureBaseHref(fallbackWithScript)
      setProcessedHtmlContent(fallbackWithBase)

      try {
        const backendUrl = await getBackendUrlForHtmlProcessing()
        if (cancelled) {
          return
        }

        const rewritten = rewriteDashboardHtmlForBackend(htmlContent, backendUrl)
        const viewerApiBase = backendUrl ? `${backendUrl}/api/viewer` : undefined
        const tenantId = viewerApiBase && typeof window !== 'undefined'
          ? localStorage.getItem('byaan_active_tenant')
          : null
        const withViewer = injectViewerConfig(
          rewritten,
          activeDashboardId,
          viewerApiBase ?? '/api/viewer',
          viewerApiBase ? 'include' : 'same-origin',
          tenantId,
          dashboardFilterValues,
          dashboardFilters,
        )
        const withScript = injectErrorCaptureScript(withViewer)
        const withBase = ensureBaseHref(withScript, backendUrl)
        if (!cancelled) {
          setProcessedHtmlContent(withBase)
        }
      } catch (error) {
        console.error('Failed to prepare dashboard HTML for preview', error)
      }
    }

    prepareHtml()

    return () => {
      cancelled = true
    }
  }, [htmlContent, activeDashboardId, dashboardFilterValues, dashboardFilters])

  // Load LLM data
  const loadLLMData = useCallback(async (forceReload = false) => {
    if (llmDataLoaded && !forceReload) return

    setIsLoadingLLMData(true)
    try {
      const [connectionsResponse, modelsResponse] = await Promise.all([
        ApiService.listLLMConnections(),
        ApiService.getAvailableModels()  // Now includes Azure/Bedrock user-provided models
      ])

      setAvailableConnections(connectionsResponse.items)

      const models = 'models_by_provider' in modelsResponse
        ? { ...modelsResponse.models_by_provider }
        : { [modelsResponse.provider]: [...modelsResponse.models] }

      // An OpenAI-compatible connection may use a custom model that is not in
      // Byaan's built-in catalog (for example Volcengine Ark). Treat its saved
      // model as authoritative and make it selectable immediately.
      for (const connection of connectionsResponse.items) {
        const configuredModel = connection.config?.model
        if (typeof configuredModel !== 'string' || !configuredModel.trim()) continue

        const modelId = configuredModel.trim()
        const providerModels = models[connection.type] || []
        const isPinnedOpenAICompatibleModel =
          connection.type === 'openai' &&
          typeof connection.config?.api_base === 'string' &&
          connection.config.api_base.trim().length > 0

        // A connection with a custom OpenAI-compatible endpoint has one
        // explicitly configured model. Built-in OpenAI catalog entries are not
        // evidence that the custom endpoint serves those models, so do not
        // offer them in the selector.
        models[connection.type] = isPinnedOpenAICompatibleModel
          ? [modelId]
          : providerModels.includes(modelId)
            ? providerModels
            : [modelId, ...providerModels]
      }

      setAvailableModels(models)
      setLlmDataLoaded(true)
      // Model selection is now handled by a separate unified useEffect
    } catch (error) {
      console.error('Failed to load LLM data:', error)
      showToast.error('Failed to load AI models')
    } finally {
      setIsLoadingLLMData(false)
    }
  }, [llmDataLoaded, notebookId, isNewNotebook])

  useEffect(() => {
    if (!embedded) return
    let cancelled = false

    const loadSemanticWorkspace = async () => {
      setIsLoadingSemanticModels(true)
      setSemanticModelsError(null)
      try {
        const [modelsResponse, assetsResponse] = await Promise.all([
          ApiService.listSemanticModels(),
          notebookId ? ApiService.getNotebookAssets(notebookId) : Promise.resolve(null),
        ])
        if (cancelled) return
        const published = modelsResponse.items
          .filter(model => model.publishedVersion && model.publishedVersion !== 'v0')
          .sort((left, right) => new Date(right.updatedAt).getTime() - new Date(left.updatedAt).getTime())
        const binding = governedSemanticBinding(assetsResponse?.items || [])
        const bindingId = binding?.asset_id || ''
        setSemanticModels(published)
        setBoundSemanticModelId(bindingId)
        setSelectedSemanticModelId(current => {
          if (bindingId && published.some(model => model.id === bindingId)) return bindingId
          if (current && published.some(model => model.id === current)) return current
          return published.length === 1 ? published[0].id : ''
        })
        const storedEvidence = binding?.usage_policy_json?.latest_query
        if (storedEvidence && typeof storedEvidence === 'object') {
          setLatestSemanticEvidence({
            type: 'semantic_query_result',
            model_id: bindingId,
            result: storedEvidence as SemanticQueryResultEvent['result'],
          })
        } else {
          setLatestSemanticEvidence(null)
        }
      } catch (error) {
        if (cancelled) return
        setSemanticModelsError(error instanceof Error ? error.message : 'Could not load Semantic Models')
        setSemanticModels([])
      } finally {
        if (!cancelled) setIsLoadingSemanticModels(false)
      }
    }

    loadSemanticWorkspace()
    return () => {
      cancelled = true
    }
  }, [embedded, notebookId])

  useEffect(() => {
    setLlmDataLoaded(false)
  }, [notebookId])

  useEffect(() => {
    loadLLMData()
  }, [loadLLMData])

  // Fetch preferred model on mount
  useEffect(() => {
    fetchPreferredModel()
  }, [fetchPreferredModel])

  // Unified model selection: waits for all data before making any selection
  // This prevents race conditions between LLM data loading and notebook data loading
  useEffect(() => {
  if (!llmDataLoaded || availableConnections.length === 0) return

  // Try to select preferred model if available
  const selectPreferred = () => {
    if (preferredProvider && preferredModel) {
      const connection = availableConnections.find(c => c.type === preferredProvider)
      const models = availableModels[preferredProvider] || []
      if (connection && models.includes(preferredModel)) {
        setSelectedProvider(preferredProvider as LLMProvider)
        setSelectedModel(preferredModel)
        setSelectedConnectionId(connection.id)
        return true
      }
    }
    return false
  }

  const autoSelect = () => {
    // First try preferred model
    if (selectPreferred()) return

    // Fallback to first available
    for (const connection of availableConnections) {
      const models = availableModels[connection.type] || []
      if (models.length > 0) {
        setSelectedProvider(connection.type as LLMProvider)
        setSelectedModel(models[0])
        setSelectedConnectionId(connection.id)
        return
      }
    }
  }

  // New notebook → use preferred model or replace a stale/unsupported
  // selection. This matters when a custom OpenAI-compatible endpoint pins a
  // model that is not part of Byaan's built-in OpenAI catalog.
  if (isNewNotebook) {
    const selectionIsValid = ConnectionValidator.validateSelection(
      selectedProvider,
      selectedModel,
      selectedConnectionId,
      availableConnections,
      availableModels,
    ).isValid
    if (!selectionIsValid) autoSelect()
    return
  }

  // Existing notebook → wait for notebook data
  if (!currentNotebook) return

  const savedProvider = currentNotebook.last_used_provider as LLMProvider | undefined
  const savedModel = currentNotebook.last_used_model

  // Try to restore saved values
  if (savedProvider && savedModel) {
    const connection = availableConnections.find(c => c.type === savedProvider)
    const models = availableModels[savedProvider] || []

    if (connection && models.includes(savedModel)) {
      setSelectedProvider(savedProvider)
      setSelectedModel(savedModel)
      setSelectedConnectionId(connection.id)
      return
    }
  }

    // The saved selection may refer to a model that the configured endpoint
    // does not serve. Always resolve a valid fallback in that case.
    autoSelect()
  }, [
    llmDataLoaded,
    isNewNotebook,
    currentNotebook,
    availableConnections,
    availableModels,
    preferredProvider,
    preferredModel,
  ])

  // DevTools keyboard shortcut (Cmd/Ctrl+Shift+I)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key === 'I') {
        e.preventDefault()
        toggleDevTools()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  // Load HTML content and messages on component mount
  useEffect(() => {
    // For new notebooks, clear ALL state for fresh start
    if (isNewNotebook) {
      setMessages([])  // Clear any existing messages
      clearQueue()  // Clear queued messages
      setSelectedDatasourceId(null)  // Clear datasource selection
      setSelectedDatasourceType(null)
      setPendingDatasourceIds([])  // Clear multi-select
      setCurrentActivity("")
      setIsHtmlBeingEdited(false)
      setHtmlContent("")
      setGeneratedCode("")
      setDashboardAvailable(false)
      setProcessedHtmlContent("")
      setIframeErrors([])
      setStatus("")
      setPreviewPanelTab("preview")
      setAvailableVersions([])
      setCurrentSessionVersion(null)
      setSelectedVersion(null)
      setLatestVersionNum(1)
      setNotebookConnection(null)
      setSchemaNotebook(null)
      setIsInitialLoading(false)
      useStore.getState().setPlanMode('new', false)
      return
    }

    // For existing notebooks, we need a valid notebookId
    if (!notebookId || notebookId === 'undefined') return

    // Check if this notebook is currently streaming (just created)
    const isCurrentlyStreaming = getNotebookStreaming(notebookId)

    // If streaming (just created), don't show loading or fetch data
    if (isCurrentlyStreaming) {
      // Just set the schema and connection, but don't reset state or load messages
      setSchemaNotebook(notebookId)
      loadNotebookConnection()
      setIsInitialLoading(false)
      return
    }

    // For existing notebooks that aren't streaming, show loading and fetch data
    setIsInitialLoading(true)

    // Clear messages and queue for fresh load
    setMessages([])
    clearQueue()

    // Reset all state when switching notebooks
    setCurrentActivity("")
    setIsHtmlBeingEdited(false)
    setHtmlContent("")
    setGeneratedCode("")
    setDashboardAvailable(false)
    setProcessedHtmlContent("")
    setIframeErrors([])
    setStatus("")
    setPreviewPanelTab("preview")
    createdNotebookIdRef.current = null
    setAvailableVersions([])
    setCurrentSessionVersion(null)
    setSelectedVersion(null)
    setLatestVersionNum(1)
    setNotebookConnection(null)

    setSchemaNotebook(notebookId)
    loadHtmlContentForNotebook()
    loadDashboardVersions()
    loadNotebookConnection()

    // Load messages from backend
    loadNotebookMessages()

    // Cleanup function - clear schema and queue when leaving
    return () => {
      setSchemaNotebook(null)
      clearQueue()
    }
  }, [notebookId, isNewNotebook])

  useEffect(() => {
    const stored = sessionStorage.getItem('injectedQuery')
    if (stored) {
      setInjectedQuery(stored)
      setInjectedQueryVersion(prev => prev + 1)
      setPreviewPanelTab('queries')
      setIsPreviewOpen(true)
      sessionStorage.removeItem('injectedQuery')
    }
  }, [notebookId])

  // Set initial loading to false after data is loaded
  useEffect(() => {
    if (notebookId && (availableVersions.length >= 0 || messages.length >= 0)) {
      // Give a small delay to prevent flash
      const timer = setTimeout(() => {
        setIsInitialLoading(false)
      }, 300)
      return () => clearTimeout(timer)
    }
  }, [notebookId, availableVersions.length, messages.length])

  // Load notebook messages
  const loadNotebookMessages = async () => {
    if (!notebookId) return
    try {
      const messagesData = await ApiService.getNotebookMessages(notebookId)
      const convertedMessages: Message[] = messagesData.map(msg => ({
        id: msg.id,
        role: msg.role as "user" | "assistant",
        content: msg.content,
        timestamp: new Date(msg.created_at),
        attachments: msg.attachments || [],
      }))
      setMessages(convertedMessages)
    } catch (error) {
      console.error('Failed to load notebook messages:', error)
    }
  }

  // Load notebook connection
  const loadNotebookConnection = useCallback(async (explicitNotebookId?: string) => {
    const targetNotebookId = explicitNotebookId || notebookId || createdNotebookIdRef.current
    if (!targetNotebookId) return
    if (!explicitNotebookId && isNewNotebook && !createdNotebookIdRef.current) return
    try {
      const connections = await ApiService.getNotebookConnectionsWithDetails(targetNotebookId)
      setAllNotebookConnections(connections)

      if (connections.length > 0) {
        const notebookConn = connections[0]
        setNotebookConnection(notebookConn)

        // Backend will return unified multi-database schema
        await loadSchema(targetNotebookId)
      } else {
        console.warn('[ChatPreview] No connections found for notebook')
        setAllNotebookConnections([])
        setNotebookConnection(null)
      }
    } catch (e) {
      console.error("[ChatPreview] Failed to load notebook connection:", e)
      showToast.error(`Failed to load connection: ${e instanceof Error ? e.message : 'Unknown error'}`)
      setAllNotebookConnections([])
      setNotebookConnection(null)
    }
  }, [notebookId, isNewNotebook, loadSchema])

  const loadHtmlContentForNotebook = async () => {
    if (!notebookId || notebookId === 'undefined') return;
    try {
      const content = await ApiService.getNotebookHtml(notebookId)
      setIframeErrors([])
      setHasAttemptedAutoFix(false)
      setHtmlContent(content || '')
      setGeneratedCode(content || '')
      setIframeKey(prev => prev + 1)
      if (content) {
        setStatus('Notebook HTML loaded successfully')
      } else {
        setStatus('No HTML content yet')
      }
    } catch (error) {
      console.error('Error loading HTML:', error)
      setStatus('Error loading HTML content')
    }
  }

  const loadCurrentFile = async () => {
    if (!notebookId) return;
    setIsRefreshing(true);
    setStatus('Refreshing dashboard...');

    try {
      const versions = await ApiService.getNotebookDashboardVersions(notebookId)
      setAvailableVersions(versions)
      setDashboardAvailable(versions.some(version => version.version_num > 1))

      const latestNum = versions.length > 0 ? Math.max(...versions.map(v => v.version_num)) : undefined
      if (latestNum) setLatestVersionNum(latestNum)

      const versionToLoad = selectedVersion ?? latestNum
      const content = await ApiService.getNotebookHtml(notebookId, versionToLoad)
      if (content) {
        setGeneratedCode(content)
        setHtmlContent(content)
        setIframeErrors([])
        setHasAttemptedAutoFix(false)
        setIframeKey(prev => prev + 1)
        setStatus('Dashboard refreshed successfully')
        showToast.success('Dashboard refreshed')
      } else {
        setStatus('No HTML content available')
        showToast.info('No HTML content to load')
      }
    } catch (error) {
      setStatus('Error loading HTML content')
      showToast.error('Could not load HTML content')
    } finally {
      setIsRefreshing(false);
    }
  };

  const loadDashboardVersions = async () => {
    if (!notebookId || notebookId === 'undefined') return;
    try {
      const versions = await ApiService.getNotebookDashboardVersions(notebookId)
      setAvailableVersions(versions)
      setDashboardAvailable(versions.some(version => version.version_num > 1))
      if (versions.length > 0) {
        const latest = Math.max(...versions.map(v => v.version_num))
        setLatestVersionNum(latest)
      }
    } catch (error) {
      console.error('Error loading dashboard versions:', error)
    }
  }

  async function handleVersionChange(versionNum: number | null) {
    if (!notebookId || notebookId === 'undefined') return;
    setSelectedVersion(versionNum)
    try {
      if (versionNum === null) {
        // Load latest version
        await loadHtmlContentForNotebook()
      } else {
        // Load specific version
        const content = await ApiService.getNotebookHtmlVersion(notebookId, versionNum)
        setHtmlContent(content)
        setGeneratedCode(content)
        setIframeErrors([])
        setHasAttemptedAutoFix(false)
        setIframeKey(prev => prev + 1)
        setStatus(`Viewing version ${versionNum}`)
      }
    } catch (error) {
      console.error('Error switching version:', error)
      showToast.error('Failed to load version')
    }
  }

  const appendHtmlTimelineEntry = useCallback((entry: Omit<HtmlEditTimelineItem, 'id' | 'timestamp'>) => {
    setHtmlEditTimeline(prev => {
      const nextEntry: HtmlEditTimelineItem = {
        ...entry,
        id: `${entry.sessionId}-${entry.stage}-${Date.now()}`,
        timestamp: Date.now()
      }
      const updated = [...prev, nextEntry]
      return updated.slice(-30)
    })
  }, [])

  const getVersionForEdit = () => {
    if (typeof selectedVersion === 'number') {
      return selectedVersion
    }

    if (currentSessionVersion) {
      return currentSessionVersion
    }

    return latestVersionNum
  }

  // Centralized callback when HTML edit is detected
  const handleHtmlEditDetected = (event?: HtmlEditDetectedEvent) => {
    console.log('[ChatPreview] HTML edit detected - showing loading indicators')
    setIsHtmlBeingEdited(true)
    setIsHtmlGenerationAnimationActive(true)
    if (!embedded) setIsPreviewOpen(true)
    setPreviewPanelTab("code")
    setCurrentActivity("Applying changes to HTML...")
    htmlEditInProgressRef.current = true
    htmlEditHappenedRef.current = true
    const sessionId = event?.edit_session_id || editSessionIdRef.current || `session-${Date.now()}`
    editSessionIdRef.current = sessionId
    setLiveHtmlCode(prev => {
      if (prev && prev.trim().length > 0) return prev
      const seed = (generatedCode || htmlContent || '').trim()
      return seed.length > 0 ? (generatedCode || htmlContent || '') : null
    })
    appendHtmlTimelineEntry({
      sessionId,
      toolName: event?.tool_name || 'unknown',
      stage: 'start',
      message: event?.message || 'HTML edit detected'
    })
  }

  // Centralized callback when HTML edit is complete
  const handleHtmlEditComplete = async (event?: HtmlEditCompleteEvent) => {
    console.log('[ChatPreview] HTML edit complete - hiding loading indicators and refreshing preview')
    setIsHtmlBeingEdited(false)
    htmlEditInProgressRef.current = false
    setCurrentActivity("")
    if (event?.edit_session_id) {
      appendHtmlTimelineEntry({
        sessionId: event.edit_session_id,
        toolName: event.tool_name || 'unknown',
        stage: 'complete',
        message: event.message || 'HTML edit applied successfully'
      })
    }
    setLiveHtmlCode(null)
    editSessionIdRef.current = null

    try {
      if (notebookId) {
        let versions = await ApiService.getNotebookDashboardVersions(notebookId)

        // Retry once if the version list hasn't updated yet (race with DB commit)
        if (versions.length > 0) {
          const fetchedLatest = Math.max(...versions.map(v => v.version_num))
          if (fetchedLatest <= (latestVersionNum ?? 0)) {
            await new Promise(resolve => setTimeout(resolve, 800))
            versions = await ApiService.getNotebookDashboardVersions(notebookId)
          }
        }

        setAvailableVersions(versions)
        setDashboardAvailable(versions.some(version => version.version_num > 1))

        if (versions.length > 0) {
          const latest = Math.max(...versions.map(v => v.version_num))
          setLatestVersionNum(latest)
          setSelectedVersion(latest)

          if (!currentSessionVersion) {
            setCurrentSessionVersion(latest)
          }

          // Fetch HTML for the confirmed latest version directly
          const content = await ApiService.getNotebookHtmlVersion(notebookId, latest)
          if (content) {
            setIframeErrors([])
            setHasAttemptedAutoFix(false)
            setHtmlContent(content)
            setGeneratedCode(content)
          }
        }
      }
    } catch (error) {
      console.error('[ChatPreview] Failed to finalize HTML edit:', error)
      setStatus('Error finalizing HTML update')
    } finally {
      setIframeKey(prev => prev + 1)
      setPreviewPanelTab("preview")
      setCurrentActivity("")
    }
  }

  const getPatchedHtmlPreview = useCallback((currentHtml: string, event: HtmlEditPatchEvent): string | null => {
    const payload = event.payload || {}
    switch (payload.type) {
      case 'search_replace':
        return applySearchReplacePreview(currentHtml, payload.diff_content)
      case 'patch':
        return applyHtmlPatchPreview(currentHtml, payload.patch_text)
      case 'find_replace':
        return applyFindReplacePreview(currentHtml, payload.find_text_full, payload.replace_text_full)
      case 'full_html':
        return typeof payload.html_full === 'string' ? payload.html_full : null
      default:
        return null
    }
  }, [])

  const describePatchEvent = (event: HtmlEditPatchEvent): string => {
    const payload = event.payload || {}
    switch (payload.type) {
      case 'search_replace':
        return `Applied ${payload.block_count || 1} search-replace block${(payload.block_count || 1) > 1 ? 's' : ''}`
      case 'patch':
        return 'Applied structured patch'
      case 'find_replace':
        return 'Updating snippet via find/replace'
      case 'full_html':
        return 'Replacing full dashboard HTML'
      default:
        return 'Applying HTML update'
    }
  }

  const handleHtmlEditPatch = (event: HtmlEditPatchEvent) => {
    if (!event) return
    const sessionId = event.edit_session_id || editSessionIdRef.current || `session-${Date.now()}`
    editSessionIdRef.current = sessionId
    appendHtmlTimelineEntry({
      sessionId,
      toolName: event.tool_name || 'unknown',
      stage: 'patch',
      message: describePatchEvent(event)
    })

    if (!isLiveHtmlStreamEnabled) return
    setLiveHtmlCode(prev => {
      const base = (prev ?? generatedCode ?? htmlContent ?? '') || ''
      const updated = getPatchedHtmlPreview(base, event)
      const next = updated ?? base
      if (!next || next.trim().length === 0) {
        return null
      }
      return next
    })
  }

  const handleHtmlContextEvent = useCallback((event?: HtmlContextRefreshEvent) => {
    if (!event) return
    const sessionId = event.context_id || `context-${Date.now()}`
    const message =
      event.message ||
      (event.stage === 'start'
        ? 'Fetching latest dashboard HTML...'
        : 'Dashboard HTML refreshed')

    appendHtmlTimelineEntry({
      sessionId,
      toolName: event.tool_name || 'get_existing_html',
      stage: 'context',
      message,
    })

    if (event.stage === 'start') {
      setCurrentActivity(message)
    } else if (!htmlEditInProgressRef.current) {
      setCurrentActivity("")
    }
  }, [appendHtmlTimelineEntry])

  // Centralized callback when query is saved
  const handleQuerySaved = () => {
    useStore.getState().triggerQuerySaved()
    useStore.getState().triggerNotebookDatasourcesChanged()
  }

  const handleToggleLiveHtmlStream = () => {
    setIsLiveHtmlStreamEnabled(prev => {
      const next = !prev
      if (next) {
        setLiveHtmlCode(current => current ?? (generatedCode || htmlContent || ''))
      }
      return next
    })
  }

  const dashboardGenerationIndicator = useMemo(() => {
    if (!isHtmlGenerationAnimationActive) {
      return { show: false, message: '' }
    }

    if (isHtmlBeingEdited) {
      return {
        show: true,
        message: isLiveHtmlStreamEnabled ? 'Streaming HTML edits in real time' : 'Applying dashboard updates'
      }
    }

    return {
      show: true,
      message: currentActivity || 'Finalizing dashboard updates...'
    }
  }, [
    isHtmlGenerationAnimationActive,
    isHtmlBeingEdited,
    isLiveHtmlStreamEnabled,
    currentActivity,
  ])

  const handleExportPdf = async () => {
    if (!notebookId) {
      showToast.error('No notebook selected');
      return;
    }

    setIsExportingPdf(true);
    try {
      // Use the selected version, or latest if none selected
      const versionToExport = selectedVersion ?? latestVersionNum;

      // Generate filename with timestamp to ensure uniqueness
      const notebookName = currentNotebook?.notebook_name || 'notebook';
      const sanitizedName = notebookName.replace(/[^a-z0-9]/gi, '_').toLowerCase();
      const versionSuffix = selectedVersion ? `_v${selectedVersion}` : '';
      const now = new Date();
      const timestamp = now.toISOString().slice(0, 10) + '_' +
                       now.toTimeString().slice(0, 8).replace(/:/g, '');
      const fileName = `${sanitizedName}${versionSuffix}_${timestamp}.pdf`;

      // Generate PDF via backend (worker-based rendering with Puppeteer)
      const pdfBlob = await ApiService.exportNotebookPdf(notebookId, versionToExport);

      // Save PDF using Tauri or browser download
      if (isTauriApp()) {
        const filePath = await saveBlobToFile(pdfBlob, fileName);
        useStore.getState().addDownload({
          fileName,
          fileType: 'pdf',
          filePath,
          status: 'success',
        });
      } else {
        // Browser download
        const url = URL.createObjectURL(pdfBlob);
        const a = document.createElement('a');
        a.href = url;
        a.download = fileName;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        useStore.getState().addDownload({
          fileName,
          fileType: 'pdf',
          status: 'success',
        });
      }
    } catch (error) {
      console.error('Failed to export PDF:', error);
      showToast.error(`Failed to export PDF: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setIsExportingPdf(false);
    }
  };

  const handleExportCompiledHtml = async () => {
    if (!notebookId) {
      showToast.error('No notebook selected');
      return;
    }

    setIsExportingHtml(true);
    try {
      // Use the selected version, or latest if none selected
      const versionToExport = selectedVersion ?? latestVersionNum;
      const blob = await ApiService.exportNotebookCompiledHtml(notebookId, versionToExport);

      const fileName = `notebook_${notebookId.slice(0, 8)}_compiled.html`;

      // Check if running in Tauri
      if (isTauriApp()) {
        try {
          // Save file using Tauri and get the path
          const filePath = await saveBlobToFile(blob, fileName);

          // Add to download notification
          useStore.getState().addDownload({
            fileName,
            fileType: 'html',
            filePath,
            status: 'success',
          });
        } catch (error) {
          console.error('Failed to save file with Tauri:', error);
          showToast.error('Failed to save HTML file');
        }
      } else {
        // Web browser: Use traditional download
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = fileName;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        // Add to download notification (without filePath for web)
        useStore.getState().addDownload({
          fileName,
          fileType: 'html',
          status: 'success',
        });
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to export compiled HTML';
      showToast.error(errorMessage);
    } finally {
      setIsExportingHtml(false);
    }
  };

  const handleShare = () => {
    if (!notebookId) {
      showToast.error('No notebook selected');
      return;
    }
    setIsShareModalOpen(true);
  };

  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (!iframeRef.current || event.source !== iframeRef.current.contentWindow) {
        return
      }

      const data = event.data as { type?: string; error?: Record<string, unknown> } | null
      if (!data || typeof data !== 'object') {
        return
      }

      // Handle error capture script ready signal
      if (data.type === 'iframe-error-capture-ready') {
        // Script is loaded and ready - we can now expect error messages
        return
      }

      if (data.type === 'dashboard.filters.ready.v1') {
        const targetWindow = iframeRef.current?.contentWindow
        if (targetWindow) {
          targetWindow.postMessage(
            {
              type: 'dashboard.filters.update.v1',
              dashboardId: activeDashboardId ?? null,
              filterValues: dashboardFilterValues,
              reload: false,
            },
            '*',
          )
        }
        return
      }

      if (data.type === 'iframe-error' && data.error) {
        const errorData = data.error as Record<string, unknown>
        const rawType = typeof errorData.type === 'string' ? errorData.type : 'error'
        const normalizedType: IframeError['type'] = rawType === 'unhandledRejection'
          ? 'unhandledRejection'
          : rawType === 'console'
            ? 'console'
            : 'error'

        const message = rawType === 'resource'
          ? `Resource load failure${errorData.tag ? ` (${String(errorData.tag)})` : ''}${errorData.url ? `: ${String(errorData.url)}` : ''}`
          : typeof errorData.message === 'string'
            ? errorData.message
            : 'Unknown error'

        setIframeErrors(prev => [{
          id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
          timestamp: new Date(),
          type: normalizedType,
          message,
          source: typeof errorData.source === 'string'
            ? errorData.source
            : typeof errorData.url === 'string'
              ? errorData.url
              : undefined,
          lineno: typeof errorData.lineno === 'number' ? errorData.lineno : undefined,
          colno: typeof errorData.colno === 'number' ? errorData.colno : undefined,
          stack: typeof errorData.stack === 'string' ? errorData.stack : undefined
        }, ...prev].slice(0, 50))
      }
    }

    window.addEventListener('message', handleMessage)
    return () => {
      window.removeEventListener('message', handleMessage)
    }
  }, [activeDashboardId, dashboardFilterValues])

  // Check if auto-fix conditions are met (silent check - no toasts)
  const canAutoFix = () => {
    // Don't auto-fix if streaming or editing is in progress
    if (isNotebookStreaming || isHtmlBeingEdited) {
      return false
    }
    // Don't auto-fix if prerequisites aren't configured
    if (!selectedProvider || !selectedModel || !selectedConnectionId || !notebookId) {
      return false
    }
    return true
  }

  // Auto-fix iframe rendering errors when detected
  useEffect(() => {
    // Only auto-fix if:
    // 1. We have errors
    // 2. We haven't already attempted auto-fix for this HTML
    // 3. We have HTML content to fix
    // 4. The assistant is not currently streaming (avoid interruption)
    // 5. HTML edit is not in progress
    // 6. All prerequisites are met (provider, model, connection, notebook)
    if (
      iframeErrors.length > 0 &&
      !hasAttemptedAutoFix &&
      htmlContent &&
      canAutoFix()
    ) {
      setHasAttemptedAutoFix(true)
      handleFixPreviewErrors(iframeErrors)
    }
  }, [iframeErrors, hasAttemptedAutoFix, htmlContent, isNotebookStreaming, isHtmlBeingEdited, selectedProvider, selectedModel, selectedConnectionId, notebookId])

  const ensureAssistantReady = () => {
    if (embedded && !selectedSemanticModelId) {
      showToast.error("Select a published Semantic Model first")
      return false
    }
    if (!selectedProvider || !selectedModel || !selectedConnectionId) {
      showToast.error("Please configure your LLM connection first")
      return false
    }
    // For new notebooks, no datasource required - agent can discover datasets
    if (isNewNotebook) {
      return true
    }
    // For existing notebooks, we need a notebook ID
    if (!notebookId) {
      showToast.error('No notebook selected')
      return false
    }
    return true
  }

  const handleCancelGeneration = () => {
    const controller = abortControllerRef.current
    if (!controller) return

    manualCancellationRef.current = true
    controller.abort()
    abortControllerRef.current = null
    setIsStreaming(false)
    setCurrentActivity("")
    setIsHtmlBeingEdited(false)
    setIsHtmlGenerationAnimationActive(false)
    htmlEditInProgressRef.current = false

    const activeNotebookId = notebookId || createdNotebookIdRef.current
    if (activeNotebookId) {
      setNotebookStreaming(activeNotebookId, false)
      ApiService.abortGeneration(activeNotebookId).catch(() => {})
    }

    showToast.info('Generation cancelled')
  }

  const streamAssistantResponse = async (
    messageContent: string,
    attachments?: Array<{file_name: string, mime_type: "image/png" | "image/jpeg" | "image/webp", file_data: string}>
  ) => {
    // For new notebooks, we'll use a temporary ID until the real one is created
    const tempNotebookId = createdNotebookIdRef.current || notebookId || 'temp'
    let createdNotebookId: string | null = null

    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: messageContent,
      timestamp: new Date(),
      attachments: attachments,
    }

    addMessage(userMessage)
    setIsStreaming(true)
    setNotebookStreaming(tempNotebookId, true)
    userClosedPreviewRef.current = false

    const assistantMessageId = (Date.now() + 1).toString()
    const assistantMessage: Message = {
      id: assistantMessageId,
      role: "assistant",
      content: "",
      timestamp: new Date(),
    }
    addMessage(assistantMessage)

    // Create new abort controller for this request
    const controller = new AbortController()
    abortControllerRef.current = controller
    manualCancellationRef.current = false
    const { signal } = controller

    setHtmlEditTimeline([])
    setLiveHtmlCode(null)
    editSessionIdRef.current = null
    htmlEditHappenedRef.current = false

    let accumulatedContent = ""

    try {
      const shouldCreateNotebook = isNewNotebook && !createdNotebookIdRef.current

      const planMode = useStore.getState().getPlanMode(
        createdNotebookIdRef.current || notebookId || 'new'
      )

      const request: AgentRequest = {
        message: messageContent,
        attachments: attachments,
        notebook_id: shouldCreateNotebook ? undefined : (createdNotebookIdRef.current || notebookId),
        llm_connection_id: selectedConnectionId!,
        model:
          selectedProvider === 'openai'
            ? selectedModel!.startsWith('openai/openai/')
              ? selectedModel!
              : `openai/${selectedModel!}`
            : selectedModel!,
        db_type: shouldCreateNotebook ? selectedDatasourceType || undefined : (notebookConnection?.connection_obj?.dataset_type === 'file' ? 'duckdb' : notebookConnection?.type || undefined),
        current_version: getVersionForEdit(),
        create_notebook: shouldCreateNotebook,
        datasource_ids: shouldCreateNotebook ? pendingDatasourceIdsRef.current : undefined,
        semantic_model_id: embedded ? selectedSemanticModelId : undefined,
        plan_mode: planMode,
      }

      if (embedded) {
        setBoundSemanticModelId(selectedSemanticModelId)
      }

      await ApiService.streamAgent(request, {
        signal,
        onChunk: (chunk: string) => {
          accumulatedContent += chunk
          updateMessage(assistantMessageId, accumulatedContent)
        },
        onNotebookCreated: async (newNotebookId: string, notebookName: string) => {
          // Navigate to the newly created notebook preview
          console.log('Notebook created:', newNotebookId, notebookName)
          // Store the created notebook ID for cleanup in finally block
          createdNotebookId = newNotebookId
          createdNotebookIdRef.current = newNotebookId
          const planModeState = useStore.getState().getPlanMode('new')
          if (planModeState) {
            useStore.getState().setPlanMode(newNotebookId, true)
            useStore.getState().setPlanMode('new', false)
          }
          // Clear pending datasources since they're now associated with the notebook
          pendingDatasourceIdsRef.current = []
          // Update streaming flag for the real notebook ID
          setNotebookStreaming(newNotebookId, true)
          // Clear the temp streaming flag
          setNotebookStreaming(tempNotebookId, false)
          // Update store with notebook ID
          setSchemaNotebook(newNotebookId)

          // Save current model selection for the newly created notebook
          if (selectedProvider && selectedModel) {
            await ApiService.updateNotebook(newNotebookId, {
              last_used_provider: selectedProvider,
              last_used_model: selectedModel,
            })
          }

          // Invalidate notebooks query so the list refreshes when user goes back to home page
          queryClient.invalidateQueries({ queryKey: ['notebooks'] })

          // Navigate after updating state
          navigate(notebookPath(newNotebookId, false), { replace: true })

          // Immediately try to load HTML content and versions
          // This ensures tabs show up right away with proper state
          try {
            const content = await ApiService.getNotebookHtml(newNotebookId)
            if (content) {
              setHtmlContent(content || '')
              setGeneratedCode(content || '')
              setIframeKey(prev => prev + 1)
            }

            // Load dashboard versions
            const versions = await ApiService.getNotebookDashboardVersions(newNotebookId)
            setAvailableVersions(versions)
            setDashboardAvailable(versions.some(version => version.version_num > 1))
            if (versions.length > 0) {
              const latest = Math.max(...versions.map(v => v.version_num))
              setLatestVersionNum(latest)
              setSelectedVersion(latest)
            }
          } catch (error) {
            console.log('HTML not ready yet, will load when generation completes')
          }
        },
        onDone: async () => {
          setCurrentActivity("")
          setAgentSelectedDatasourceId(null)
          if (htmlEditInProgressRef.current) {
            await handleHtmlEditComplete()
          } else if (!htmlEditHappenedRef.current) {
            setIsHtmlBeingEdited(false)
            const currentNotebookId = notebookId || createdNotebookId
            if (currentNotebookId) {
              try {
                const content = await ApiService.getNotebookHtml(currentNotebookId)
                setIframeErrors([])
                setHasAttemptedAutoFix(false)
                setHtmlContent(content || '')
                setGeneratedCode(content || '')
                setIframeKey(prev => prev + 1)
                if (content) {
                  setStatus('Dashboard generated successfully')
                }

                const versions = await ApiService.getNotebookDashboardVersions(currentNotebookId)
                setAvailableVersions(versions)
                setDashboardAvailable(versions.some(version => version.version_num > 1))
                if (versions.length > 0) {
                  const latest = Math.max(...versions.map(v => v.version_num))
                  setLatestVersionNum(latest)
                  setSelectedVersion(latest)
                  if (!currentSessionVersion) {
                    setCurrentSessionVersion(latest)
                  }
                }
              } catch (error) {
                console.error('Error loading HTML after generation:', error)
                setStatus('Error loading dashboard content')
              }
            }
          }
          // If HTML edits happened during this response, ensure preview is showing
          if (!embedded && htmlEditHappenedRef.current && !userClosedPreviewRef.current) {
            setIsPreviewOpen(true)
            setPreviewPanelTab("preview")
          }
          setIsHtmlGenerationAnimationActive(false)
        },
        onToolCall: (_toolName: string, description: string) => {
          setCurrentActivity(`${description}...`)
        },
        onToolOutput: () => {
          setCurrentActivity("")
        },
        onHtmlEditDetected: handleHtmlEditDetected,
        onHtmlEditPatch: handleHtmlEditPatch,
        onHtmlEditComplete: handleHtmlEditComplete,
        onHtmlContextEvent: handleHtmlContextEvent,
        onDatasourceSelected: async (event: DatasourceSelectedEvent) => {
          setPendingDatasourceIds(prev =>
            prev.includes(event.datasource_id) ? prev : [...prev, event.datasource_id]
          )
          const targetNotebookId = notebookId || createdNotebookIdRef.current
          if (targetNotebookId && event.datasource_id) {
            await handleDatasourceSelect(event.datasource_id, targetNotebookId)
          }
          setAgentSelectedDatasourceId(event.datasource_id)
        },
        onSemanticQueryResult: (event: SemanticQueryResultEvent) => {
          setLatestSemanticEvidence(event)
          if (event.model_id) setBoundSemanticModelId(event.model_id)
        },
        onQuerySaved: handleQuerySaved,
        onInstructionUpdated: () => {
          useStore.getState().loadPreferencesFromBackend()
        },
        onLearningUpdated: () => {
          useStore.getState().loadLearnings()
        },
        onPlanStatus: (event: PlanStatusEvent) => {
          const nbId = createdNotebookIdRef.current || notebookId
          if (nbId) {
            useStore.getState().handlePlanStatus(nbId, event)
          }
        },
        onTitleGenerated: (title: string, notebookId: string) => {
          updateNotebook(notebookId, { notebook_name: title })
          queryClient.invalidateQueries({ queryKey: ['notebooks'] })
        }
      })

      if (!accumulatedContent) {
        if (signal.aborted || manualCancellationRef.current) {
          updateMessage(assistantMessageId, "[Response interrupted]")
          return
        }

        if (htmlEditHappenedRef.current) {
          if (htmlEditInProgressRef.current) {
            await handleHtmlEditComplete()
          }
          if (!embedded && !userClosedPreviewRef.current) {
            setIsPreviewOpen(true)
            setPreviewPanelTab("preview")
          }
          updateMessage(assistantMessageId, "Dashboard updated.")
          return
        }

        throw new Error("No response received from the assistant")
      }

      if (embedded) {
        const targetNotebookId = createdNotebookIdRef.current || notebookId
        if (targetNotebookId) {
          try {
            const assets = await ApiService.getNotebookAssets(targetNotebookId)
            const binding = governedSemanticBinding(assets.items)
            const storedEvidence = binding?.usage_policy_json?.latest_query
            if (binding?.asset_id) setBoundSemanticModelId(binding.asset_id)
            if (storedEvidence && typeof storedEvidence === 'object') {
              setLatestSemanticEvidence({
                type: 'semantic_query_result',
                model_id: binding?.asset_id || selectedSemanticModelId,
                result: storedEvidence as SemanticQueryResultEvent['result'],
              })
            }
          } catch (error) {
            console.warn('Could not refresh governed query evidence:', error)
          }
        }
      }
    } catch (error) {
      const isAbortError =
        (typeof DOMException !== 'undefined' && error instanceof DOMException && error.name === 'AbortError') ||
        (error instanceof Error && error.name === 'AbortError')

      if (isAbortError) {
        if (!accumulatedContent) {
          updateMessage(assistantMessageId, "[Response interrupted]")
        }
        return
      }

      if (htmlEditHappenedRef.current) {
        console.warn('Agent stream ended after dashboard update:', error)
        if (htmlEditInProgressRef.current) {
          await handleHtmlEditComplete()
        }
        if (!embedded && !userClosedPreviewRef.current) {
          setIsPreviewOpen(true)
          setPreviewPanelTab("preview")
        }
        updateMessage(assistantMessageId, accumulatedContent || "Dashboard updated.")
        return
      }

      const errorMessage = error instanceof Error ? error.message : 'Failed to get response'
      showToast.error(errorMessage)

      updateMessage(assistantMessageId, `Sorry, I encountered an error: ${errorMessage}`)
    } finally {
      setIsStreaming(false)
      // Clear streaming state for temp notebook ID
      if (tempNotebookId) {
        setNotebookStreaming(tempNotebookId, false)
      }
      // Clear streaming state for the real created notebook ID
      if (createdNotebookId) {
        setNotebookStreaming(createdNotebookId, false)
      }
      setCurrentActivity("")
      setIsHtmlBeingEdited(false)
      setIsHtmlGenerationAnimationActive(false)
      htmlEditInProgressRef.current = false
      setLiveHtmlCode(null)
      editSessionIdRef.current = null
      abortControllerRef.current = null
      manualCancellationRef.current = false

      // Process next queued message if any
      const { getNextQueuedMessage, removeFromQueue } = useStore.getState()
      const nextMessage = getNextQueuedMessage()
      if (nextMessage) {
        removeFromQueue(nextMessage.id)
        setTimeout(() => {
          streamAssistantResponse(nextMessage.content, nextMessage.attachments)
        }, 100)
      }
    }
  }

  const handleCopy = async () => {
    if (!generatedCode) return

    try {
      await navigator.clipboard.writeText(generatedCode)
      setCopied(true)
      showToast.success("Code copied to clipboard")
      setTimeout(() => setCopied(false), 2000)
    } catch (error) {
      showToast.error("Failed to copy code")
    }
  }

  const handleClearConversation = async () => {
    if (!notebookId) return

    try {
      await ApiService.clearNotebookConversation(notebookId)
      setMessages([])
      setShowConfirmModal(false)
      showToast.success("Conversation cleared successfully")
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to clear conversation'
      showToast.error(errorMessage)
      setShowConfirmModal(false)
    }
  }

  const openConfirmModal = () => {
    setShowConfirmModal(true)
  }

  // Notebook name editing handlers
  const handleStartEditingName = () => {
    if (currentNotebook?.notebook_name) {
      setEditedName(currentNotebook.notebook_name)
      setIsEditingName(true)
    }
  }

  const handleCancelEditingName = () => {
    setIsEditingName(false)
    setEditedName("")
  }

  const handleSaveNotebookName = async () => {
    if (!notebookId || !editedName.trim()) {
      handleCancelEditingName()
      return
    }

    // Don't save if name hasn't changed
    if (editedName.trim() === currentNotebook?.notebook_name) {
      handleCancelEditingName()
      return
    }

    try {
      await renameNotebookMutation.mutateAsync({
        notebookId,
        newName: editedName.trim()
      })
      setIsEditingName(false)
      setEditedName("")
    } catch (error) {
      console.error('Error renaming notebook:', error)
      // The error toast is already shown by the mutation
    }
  }

  const handleNameKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleSaveNotebookName()
    } else if (e.key === 'Escape') {
      e.preventDefault()
      handleCancelEditingName()
    }
  }

  // Focus the input when editing starts
  useEffect(() => {
    if (isEditingName && nameInputRef.current) {
      nameInputRef.current.focus()
      nameInputRef.current.select()
    }
  }, [isEditingName])

  // Handle model selection change from ModelSelector - shared by both instances
  const handleModelSelectionChange = useCallback(async (selection: { provider: LLMProvider; model: string; connectionId: string } | undefined) => {
    if (selection) {
      setSelectedProvider(selection.provider)
      setSelectedModel(selection.model)
      setSelectedConnectionId(selection.connectionId)
      // Set as preferred model
      await setPreferredModelAction(selection.provider, selection.model)
      // Save model preference for existing notebooks to database
      if (notebookId && !isNewNotebook) {
        await ApiService.updateNotebook(notebookId, {
          last_used_provider: selection.provider,
          last_used_model: selection.model,
        })
        // Invalidate notebooks query to refresh the cached data
        queryClient.invalidateQueries({ queryKey: ['notebooks'] })
      }
    } else {
      setSelectedProvider(undefined)
      setSelectedModel(undefined)
      setSelectedConnectionId(undefined)
    }
  }, [notebookId, isNewNotebook, queryClient, setPreferredModelAction])

  // Handle setting a model as preferred
  const handleSetPreferredModel = useCallback(async (provider: string, model: string) => {
    try {
      await setPreferredModelAction(provider, model)
      showToast.success(`Set ${model} as preferred model`)
    } catch (error) {
      showToast.error('Failed to set preferred model')
    }
  }, [setPreferredModelAction])

  // Handle clearing the preferred model
  const handleClearPreferredModel = useCallback(async () => {
    try {
      await clearPreferredModelAction()
      showToast.success('Preferred model cleared')
    } catch (error) {
      showToast.error('Failed to clear preferred model')
    }
  }, [clearPreferredModelAction])

  const handleSubmitMessage = useCallback(async (
    messageContent: string,
    attachments?: Array<{file_name: string, mime_type: "image/png" | "image/jpeg" | "image/webp", file_data: string}>
  ) => {
    const { getNotebookStreaming, addToQueue, isQueueFull, clearPlan, activePlans } = useStore.getState()
    const currentNotebookId = notebookId || 'temp'
    const isCurrentlyStreaming = getNotebookStreaming(currentNotebookId)

    const existingPlan = activePlans[currentNotebookId]
    if (existingPlan) {
      const allStepsDone = existingPlan.steps.length > 0
        && existingPlan.steps.every((s) => s.status === 'completed')
      if (existingPlan.isComplete || allStepsDone) {
        clearPlan(currentNotebookId)
      }
    }

    // If streaming, add to queue instead of blocking
    if (isCurrentlyStreaming) {
      if (isQueueFull()) {
        showToast.error('Message queue is full (max 3 messages)')
        return
      }
      addToQueue({
        id: Date.now().toString(),
        content: messageContent,
        attachments,
        timestamp: new Date(),
      })
      return
    }

    // Only check assistant ready when not streaming
    if (!ensureAssistantReady()) {
      return
    }

    await streamAssistantResponse(messageContent, attachments)
  }, [ensureAssistantReady, streamAssistantResponse, notebookId])

  const handleEmptyStateFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files || files.length === 0) return

    const MAX_IMAGES = 5
    const currentCount = emptyStateAttachedImages.length
    const availableSlots = MAX_IMAGES - currentCount

    if (availableSlots <= 0) {
      showToast.error(`Maximum ${MAX_IMAGES} images allowed per message`)
      if (emptyFileInputRef.current) {
        emptyFileInputRef.current.value = ''
      }
      return
    }

    const fileArray = Array.from(files)
    if (fileArray.length > availableSlots) {
      showToast.warning(`Only ${availableSlots} more image${availableSlots > 1 ? 's' : ''} can be added (max ${MAX_IMAGES})`)
    }

    const newAttachments: Array<{file_name: string, mime_type: "image/png" | "image/jpeg" | "image/webp", file_data: string}> = []
    let skippedDueToFormat = 0
    let skippedDueToSize = 0

    for (const file of fileArray.slice(0, availableSlots)) {
      // Validate image format (png, jpeg, webp)
      if (!file.type.match(/image\/(png|jpeg|webp)/)) {
        skippedDueToFormat++
        continue
      }

      // Validate file size (max 5MB)
      if (file.size > 5 * 1024 * 1024) {
        skippedDueToSize++
        continue
      }

      // Convert to base64
      try {
        const reader = new FileReader()
        await new Promise<void>((resolve, reject) => {
          reader.onload = () => {
            const base64 = (reader.result as string).split(',')[1]
            newAttachments.push({
              file_name: file.name,
              mime_type: file.type as "image/png" | "image/jpeg" | "image/webp",
              file_data: base64
            })
            resolve()
          }
          reader.onerror = reject
          reader.readAsDataURL(file)
        })
      } catch {
        showToast.error(`Failed to process ${file.name}`)
      }
    }

    if (skippedDueToFormat > 0) {
      showToast.error(`${skippedDueToFormat} file${skippedDueToFormat > 1 ? 's' : ''} skipped (unsupported format - use PNG, JPEG, or WEBP)`)
    }

    if (skippedDueToSize > 0) {
      showToast.error(`${skippedDueToSize} file${skippedDueToSize > 1 ? 's' : ''} skipped (exceeds 5MB limit)`)
    }

    if (newAttachments.length > 0) {
      setEmptyStateAttachedImages(prev => [...prev, ...newAttachments])
    }

    // Clear input for re-selection
    if (emptyFileInputRef.current) {
      emptyFileInputRef.current.value = ''
    }
  }

  const handleEmptyStateRemoveAttachment = (index: number) => {
    setEmptyStateAttachedImages(prev => prev.filter((_, i) => i !== index))
  }

  // Helper: Map placeholder connection_id to real UUID based on database type
  const resolveConnectionId = useCallback((placeholderId?: string): string | undefined => {
    if (!placeholderId) return undefined

    // Pattern: conn-{type}-{number} (e.g., "conn-pg-123", "conn-mongo-456")
    const match = placeholderId.match(/^conn-([a-z]+)-/)
    if (match) {
      const dbType = match[1] // Extract "pg", "mongo", etc.
      const connection = allNotebookConnections.find(c => c.type === dbType)
      if (connection) {
        return connection.id
      } else {
        console.warn(`No connection found for type "${dbType}" from placeholder "${placeholderId}"`)
      }
    }

    const connectionByConnectionId = allNotebookConnections.find(c => c.connection_id === placeholderId)
    if (connectionByConnectionId) {
      return connectionByConnectionId.id
    }

    return placeholderId
  }, [allNotebookConnections])

  const handleEmptyStatePaste = async (e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items
    if (!items) return

    const imageItems: File[] = []

    for (let i = 0; i < items.length; i++) {
      const item = items[i]
      // Check if the item is an image (png, jpeg, webp)
      if (item.type.match(/^image\/(png|jpeg|webp)$/)) {
        const file = item.getAsFile()
        if (file) {
          imageItems.push(file)
        }
      }
    }

    if (imageItems.length === 0) return

    // Prevent default paste behavior for images
    e.preventDefault()

    // Check if adding these images would exceed the limit
    const MAX_IMAGES = 5
    const currentCount = emptyStateAttachedImages.length
    const availableSlots = MAX_IMAGES - currentCount

    if (availableSlots <= 0) {
      showToast.error(`Maximum ${MAX_IMAGES} images allowed per message`)
      return
    }

    if (imageItems.length > availableSlots) {
      showToast.warning(`Only ${availableSlots} more image${availableSlots > 1 ? 's' : ''} can be added (max ${MAX_IMAGES})`)
    }

    const newAttachments: Array<{file_name: string, mime_type: "image/png" | "image/jpeg" | "image/webp", file_data: string}> = []
    let skippedDueToSize = 0

    for (const file of imageItems.slice(0, availableSlots)) {
      // Validate file size (5MB limit)
      if (file.size > 5 * 1024 * 1024) {
        skippedDueToSize++
        continue
      }

      // Convert to base64
      try {
        const base64 = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader()
          reader.onload = () => {
            const result = reader.result as string
            const base64Data = result.split(',')[1]
            resolve(base64Data)
          }
          reader.onerror = reject
          reader.readAsDataURL(file)
        })

        newAttachments.push({
          file_name: file.name || `pasted-image-${Date.now()}.${file.type.split('/')[1]}`,
          mime_type: file.type as "image/png" | "image/jpeg" | "image/webp",
          file_data: base64,
        })
      } catch {
        showToast.error('Failed to process pasted image')
      }
    }

    if (skippedDueToSize > 0) {
      showToast.error(`${skippedDueToSize} image${skippedDueToSize > 1 ? 's' : ''} skipped (exceeds 5MB limit)`)
    }

    if (newAttachments.length > 0) {
      setEmptyStateAttachedImages(prev => [...prev, ...newAttachments])
    }
  }

  const handleCodeInject = useCallback((data: { query: string; connectionId?: string }) => {
    if (embedded) return
    const resolvedConnectionId = resolveConnectionId(data.connectionId)

    setInjectedQuery(data.query)
    setInjectedConnectionId(resolvedConnectionId)
    setInjectedQueryVersion(prev => prev + 1)
    setPreviewPanelTab('queries')
    setIsPreviewOpen(true)
  }, [embedded, resolveConnectionId])

  const handleFixPreviewErrors = async (errors: IframeError[]) => {
    if (errors.length === 0) {
      showToast.info('No preview errors to send')
      return
    }

    const { getNotebookStreaming, addToQueue, isQueueFull, clearPlan, activePlans } = useStore.getState()
    const currentNotebookId = notebookId || 'temp'
    const isCurrentlyStreaming = getNotebookStreaming(currentNotebookId)

    const existingPlan = activePlans[currentNotebookId]
    if (existingPlan) {
      const allStepsDone = existingPlan.steps.length > 0
        && existingPlan.steps.every((s) => s.status === 'completed')
      if (existingPlan.isComplete || allStepsDone) {
        clearPlan(currentNotebookId)
      }
    }

    const maxErrorsToInclude = 5
    const formattedErrors = errors.slice(0, maxErrorsToInclude).map((error, index) => {
      const location = error.source
        ? `${error.source}${error.lineno ? `:${error.lineno}` : ''}${error.colno ? `:${error.colno}` : ''}`
        : undefined
      const stackPreview = error.stack
        ? error.stack.split('\n').slice(0, 3).join('\n')
        : undefined

      return `(${index + 1}) [${error.type}] ${error.message}${location ? `\nLocation: ${location}` : ''}${stackPreview ? `\nStack:\n${stackPreview}` : ''}`
    }).join('\n\n')

    const moreErrorsSuffix = errors.length > maxErrorsToInclude
      ? `\n\n...and ${errors.length - maxErrorsToInclude} more logged error${errors.length - maxErrorsToInclude === 1 ? '' : 's'}.`
      : ''

    const messageContent = `We are unable to render the HTML dashboard properly. Here are the errors that occurred during rendering:${formattedErrors ? `\n\n${formattedErrors}` : ''}${moreErrorsSuffix}\n\nPlease analyze these errors and provide specific fixes to resolve the dashboard rendering issues. Focus on the root causes and provide concrete code solutions.`

    // If streaming, add to queue
    if (isCurrentlyStreaming) {
      if (isQueueFull()) {
        showToast.error('Message queue is full (max 3 messages)')
        return
      }
      addToQueue({
        id: Date.now().toString(),
        content: messageContent,
        timestamp: new Date(),
      })
      return
    }

    if (!ensureAssistantReady()) {
      return
    }

    await streamAssistantResponse(messageContent)
  }

  const handleDebugWithAssistant = async (query: string, error: string, errorDetail?: ErrorDetail) => {
    // Check if model is selected
    if (!selectedProvider || !selectedModel || !selectedConnectionId) {
      showToast.error("Please configure your LLM connection first")
      return
    }

    // Create a debug message for the assistant
    const debugMessage = `I got an error when running this query:

\`\`\`${notebookConnection?.type === 'mongo' ? 'javascript' : 'sql'}
${query}
\`\`\`

Error: ${error}
${errorDetail ? `\nError Category: ${errorDetail.category}\nSeverity: ${errorDetail.severity}` : ''}

Can you help me fix this query?`

    await streamAssistantResponse(debugMessage)
  }

  const handleConfirmDatasourceSelection = () => {
    // Multi-select mode
    if (pendingDatasourceIds.length > 0) {
      const firstDatasource = sortedDatasources.find(ds => ds.id === pendingDatasourceIds[0])
      if (!firstDatasource) {
        showToast.error('Unable to find the selected datasource')
        return
      }
      setSelectedDatasourceId(firstDatasource.id)
      setSelectedDatasourceType(getDatasourceDbType(firstDatasource))
      setIsDatasourceModalOpen(false)
      return
    }

    // Single select fallback
    if (!pendingDatasourceId) {
      showToast.error('Please select a datasource')
      return
    }
    const datasource = sortedDatasources.find(ds => ds.id === pendingDatasourceId)
    if (!datasource) {
      showToast.error('Unable to find the selected datasource')
      return
    }
    setSelectedDatasourceId(datasource.id)
    setSelectedDatasourceType(getDatasourceDbType(datasource))
    setIsDatasourceModalOpen(false)
  }

  const handleCreateDatasource = async (data: {
    type: any
    name: string
    connectionObj?: any
    files?: File[]
    aliases?: Record<string, string>
    fileType?: 'csv' | 'excel' | 'parquet' | 'json'
    urls?: string[]
  }) => {
    const loadingToastId = showToast.loading('Creating datasource...')

    try {
      if (data.type === 'upload') {
        if (!data.files || data.files.length === 0 || !data.fileType) {
          throw new Error('Please provide files to upload')
        }
        const response = await uploadMultipleFilesMutation.mutateAsync({
          files: data.files,
          name: data.name,
          fileType: data.fileType,
          aliases: data.aliases,
          notebookId: notebookId,
        })
        if (response?.dataset_id) {
          setSelectedDatasourceId(response.dataset_id)
          setSelectedDatasourceType('duckdb')
          setPendingDatasourceId(response.dataset_id)
        }
      } else if (data.type === 'url') {
        if (!data.urls || data.urls.length === 0) {
          throw new Error('Please provide at least one URL')
        }
        const response = await uploadFromURLMutation.mutateAsync({
          urls: data.urls,
          name: data.name,
          fileType: data.fileType,
          notebookId: notebookId,
        })
        if (response?.dataset_id) {
          setSelectedDatasourceId(response.dataset_id)
          setSelectedDatasourceType('duckdb')
          setPendingDatasourceId(response.dataset_id)
        }
      } else {
        const connectionPayload: ConnectionCreateRequest = {
          type: data.type,
          name: data.name,
          connection_obj: data.connectionObj,
        }
        const response = await createConnectionMutation.mutateAsync(connectionPayload)
        if (response?.id) {
          // response.id is the Connection ID, we need to find the Dataset ID
          // Fetch fresh datasources to find the newly created Dataset wrapper
          const freshDatasources = await ApiService.listAllDatasources()
          const newDatasource = freshDatasources.items.find(
            (ds: Datasource) => ds.source_type === 'connection' && ds.connection_id === response.id
          )
          if (newDatasource) {
            setSelectedDatasourceId(newDatasource.id)
            setSelectedDatasourceType(response.type || null)
            setPendingDatasourceId(newDatasource.id)
          }
        }
      }

      toast.dismiss(loadingToastId)
      setIsDatasourceModalOpen(false)
    } catch (error) {
      toast.dismiss(loadingToastId)
      const errorMessage = error instanceof Error ? error.message : 'Failed to create datasource'
      showToast.error(errorMessage)
    }
  }

  const handleDatasourceSelect = async (datasourceId: string, explicitNotebookId?: string) => {
    const targetNotebookId = explicitNotebookId || notebookId || createdNotebookIdRef.current
    if (!targetNotebookId) return

    try {
      const datasourcesResponse = await ApiService.listAllDatasources()
      const selectedDatasource = datasourcesResponse.items.find(
        (d: any) => d.id === datasourceId || d.connection_id === datasourceId
      )

      if (selectedDatasource?.source_type === 'connection') {
        await ApiService.associateNotebookConnection(targetNotebookId, {
          connection_id: selectedDatasource.connection_id!
        })
      } else if (selectedDatasource?.source_type === 'dataset') {
        await ApiService.associateDatasetWithNotebook(selectedDatasource.id, targetNotebookId)
      } else {
        await ApiService.associateNotebookConnection(targetNotebookId, {
          connection_id: datasourceId
        })
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to connect datasource'
      const isAlreadyAssociated = errorMessage.toLowerCase().includes('already associated')
      if (!isAlreadyAssociated) {
        showToast.error(errorMessage)
      }
    } finally {
      queryClient.invalidateQueries({ queryKey: ['datasources'] })
      await loadNotebookConnection(targetNotebookId)
      useStore.getState().triggerNotebookDatasourcesChanged()
    }
  }

  const handleAddNewConnection = () => {
    navigate(datasourceHomePath)
  }

  const handleDatasourceChange = async (ids: string[]) => {
    const previousIds = pendingDatasourceIds
    setPendingDatasourceIds(ids)

    if (!isNewNotebook && notebookId) {
      const addedIds = ids.filter(id => !previousIds.includes(id))
      const removedIds = previousIds.filter(id => !ids.includes(id))

      for (const id of addedIds) {
        if (!allNotebookConnections.some(c => (c.connection_id || c.dataset_id) === id)) {
          await handleDatasourceSelect(id)
        }
      }

      const processedConnections = new Set()
      for (const id of removedIds) {
        const connection = allNotebookConnections.find(c =>
          c.connection_id === id || c.dataset_id === id
        )
        if (connection) {
          const uniqueKey = connection.dataset_id || connection.connection_id
          if (processedConnections.has(uniqueKey)) continue
          processedConnections.add(uniqueKey)

          try {
            if (connection.dataset_id) {
              await ApiService.dissociateDatasetFromNotebook(connection.dataset_id, notebookId)
            } else if (connection.connection_id) {
              await ApiService.removeNotebookConnection(notebookId, connection.connection_id)
            }
          } catch (error) {
            console.error('Failed to remove datasource:', error)
          }
        }
      }

      if (removedIds.length > 0) {
        await loadNotebookConnection()
        useStore.getState().triggerNotebookDatasourcesChanged()
      }
    }
  }

  // Schedule mode handlers
  const handleEnterScheduleMode = useCallback(() => {
    if (existingSchedule) {
      setScheduleInstruction(existingSchedule.instruction || '')
      const parsed = parseCronToScheduleConfig(existingSchedule.cron_expression)
      setScheduleConfig({
        ...parsed,
        slackChannelId: existingSchedule.slack_channel_id || '',
      })
    } else {
      setScheduleInstruction('')
      setScheduleConfig({
        frequency: 'daily',
        hour: '9',
        minute: '0',
        dayOfWeek: '1',
        customCron: '0 9 * * *',
        slackChannelId: '',
      })
    }
    setIsScheduleMode(true)
  }, [existingSchedule])

  const handleCancelScheduleMode = useCallback(() => {
    setIsScheduleMode(false)
    setScheduleInstruction('')
  }, [])

  const buildCronExpression = useCallback((config: typeof scheduleConfig): string => {
    if (config.frequency === 'custom') return config.customCron
    if (config.frequency === 'daily') return `${config.minute} ${config.hour} * * *`
    return `${config.minute} ${config.hour} * * ${config.dayOfWeek}`
  }, [])

  const handleSaveSchedule = useCallback(async () => {
    if (!notebookId || !scheduleInstruction.trim()) return

    const cronExpression = buildCronExpression(scheduleConfig)
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'

    try {
      if (existingSchedule) {
        const updateData: ScheduleUpdate = {
          cron_expression: cronExpression,
          timezone,
          is_enabled: true,
          slack_channel_id: scheduleConfig.slackChannelId || null,
          instruction: scheduleInstruction.trim(),
        }
        await updateScheduleMutation.mutateAsync({
          scheduleId: existingSchedule.id,
          data: updateData,
        })
      } else {
        const createData: ScheduleCreate = {
          name: `Schedule for ${currentNotebook?.notebook_name || 'notebook'}`,
          cron_expression: cronExpression,
          timezone,
          is_enabled: true,
          slack_channel_id: scheduleConfig.slackChannelId || null,
          instruction: scheduleInstruction.trim(),
        }
        await createScheduleMutation.mutateAsync({
          notebookId,
          data: createData,
        })
      }
      handleCancelScheduleMode()
    } catch {
      // Error handled by mutation
    }
  }, [notebookId, scheduleInstruction, scheduleConfig, existingSchedule, currentNotebook, buildCronExpression, createScheduleMutation, updateScheduleMutation, handleCancelScheduleMode])

  const handleToggleSchedule = useCallback(async (enabled: boolean) => {
    if (!existingSchedule) return
    try {
      await updateScheduleMutation.mutateAsync({
        scheduleId: existingSchedule.id,
        data: { is_enabled: enabled },
      })
    } catch {
      // Error handled by mutation
    }
  }, [existingSchedule, updateScheduleMutation])

  const handleDeleteSchedule = useCallback(async () => {
    if (!existingSchedule) return
    try {
      await deleteScheduleMutation.mutateAsync(existingSchedule.id)
    } catch {
      // Error handled by mutation
    }
  }, [existingSchedule, deleteScheduleMutation])

  const handleUploadFilesForChat = async (files: File[], fileType: string) => {
    try {
      const name = files[0]?.name.replace(/\.[^/.]+$/, '') || 'Uploaded file'
      const result = await uploadMultipleFilesMutation.mutateAsync({
        files,
        name,
        fileType: fileType as 'csv' | 'excel' | 'parquet' | 'json'
      })
      if (result?.dataset_id) {
        setPendingDatasourceIds(prev => [...prev, result.dataset_id])
        showToast.success('File uploaded successfully')
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to upload files'
      showToast.error(errorMessage)
    }
  }

  const handleRemoveDatasource = async () => {
    if (!notebookId || !notebookConnection) return

    try {
      // Check if it's a dataset or connection
      if (notebookConnection.dataset_id) {
        // Remove dataset association
        await ApiService.dissociateDatasetFromNotebook(notebookConnection.dataset_id, notebookId)
      } else if (notebookConnection.connection_id) {
        // For now, we'll need to add a dissociate connection API if it doesn't exist
        // Or we can just reload after manual removal
        showToast.info('Please remove the connection from the databases page')
        return
      }

      showToast.success('Datasource removed successfully')
      // Reload the connection
      await loadNotebookConnection()
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to remove datasource'
      showToast.error(errorMessage)
    }
  }

  // Toggle selection for multi-select mode
  const toggleDatasourceSelection = (id: string) => {
    setPendingDatasourceIds(prev => {
      if (prev.includes(id)) {
        return prev.filter(dsId => dsId !== id)
      } else {
        return [...prev, id]
      }
    })
  }

  const datasourceModal = (
    <DatabaseConnectionDialog
      open={isDatasourceModalOpen}
      onOpenChange={(open) => setIsDatasourceModalOpen(open)}
      mode={datasourceDialogMode}
      datasources={sortedDatasources}
      selectedConnectionId={pendingDatasourceId}
      selectedConnectionIds={pendingDatasourceIds}
      onConnectionSelect={toggleDatasourceSelection}
      onConfirmConnection={handleConfirmDatasourceSelection}
      onCreateConnection={handleCreateDatasource}
      showPreviousConnectionsOption={sortedDatasources.length > 0}
      isLoading={isDatasourceActionPending}
      onSwitchToCreate={() => setDatasourceDialogMode('create')}
      onSwitchToSelect={() => setDatasourceDialogMode('select')}
      submitButtonText={
        pendingDatasourceIds.length > 0
          ? `Use ${pendingDatasourceIds.length} Datasource(s)`
          : datasourceDialogMode === 'select'
            ? 'Use Datasource'
            : 'Create Datasource'
      }
      title="Connect data to start chatting"
      multiSelect={true}
    />
  )

  // Show loading state while initial data is being fetched
  if (isInitialLoading) {
    return (
      <React.Fragment>
        <div className={`flex ${viewportHeightClass} bg-[#1a1a1a] text-white items-center justify-center`}>
          <div className="flex flex-col items-center gap-4">
            <div className="w-8 h-8 border-2 border-brand-orange border-t-transparent rounded-full animate-spin"></div>
            <span className="text-sm text-gray-400">Loading notebook...</span>
          </div>
        </div>
        {datasourceModal}
      </React.Fragment>
    )
  }

  // Empty state: centered text + input until first chat message.
  // A direct /preview URL still needs the split layout so the dashboard pane is visible.
  if (!embedded && messages.length === 0 && !isPreviewOpen) {
    return (
      <React.Fragment>
        <div className={`flex ${viewportHeightClass} bg-[#1a1a1a] text-white`}>
          <div className="flex flex-col flex-1">
            {/* Simplified Header with Input */}
            <div className="flex flex-col h-full">
              {/* Top Navigation Bar */}
              <div className="flex items-center justify-between px-5 h-12 bg-[#1a1a1a] flex-shrink-0 border-b border-[#2a2a2a]">
                {/* Left Side: Back Arrow + Notebook Name */}
                <div className="flex items-center gap-3 min-w-0 flex-1">
                  <button
                    onClick={() => navigate(conversationHomePath)}
                    className="p-1 hover:bg-[#2a2a2a] rounded-lg transition-colors flex-shrink-0"
                    title="Go back to Notebooks"
                  >
                    <ArrowLeft className="w-4 h-4 text-white" />
                  </button>

                  {/* Notebook Name - Always visible */}
                  {isEditingName ? (
                    <div className="flex items-center gap-1.5">
                      <input
                        ref={nameInputRef}
                        type="text"
                        value={editedName}
                        onChange={(e) => setEditedName(e.target.value)}
                        onKeyDown={handleNameKeyDown}
                        onBlur={handleSaveNotebookName}
                        className="text-xs font-medium text-white bg-[#2a2a2a] border border-[#404040] rounded px-2 py-1 focus:outline-none focus:border-brand-orange min-w-0"
                        maxLength={100}
                      />
                      <button
                        onClick={handleSaveNotebookName}
                        className="p-1 hover:bg-[#2a2a2a] rounded transition-colors flex-shrink-0"
                        title="Save name"
                      >
                        <Check className="w-3.5 h-3.5 text-green-400" />
                      </button>
                      <button
                        onClick={handleCancelEditingName}
                        className="p-1 hover:bg-[#2a2a2a] rounded transition-colors flex-shrink-0"
                        title="Cancel"
                      >
                        <X className="w-3.5 h-3.5 text-red-400" />
                      </button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-xs font-medium text-white truncate">
                        {isNewNotebook ? 'New Notebook' : (currentNotebook?.notebook_name || 'Chat Assistant')}
                      </span>
                      {!isNewNotebook && (
                        <>
                          <button
                            onClick={handleStartEditingName}
                            className="p-1 hover:bg-[#2a2a2a] rounded-lg transition-colors flex-shrink-0 opacity-70 hover:opacity-100"
                            title="Rename notebook"
                          >
                            <Pencil className="w-3 h-3 text-white" />
                          </button>
                        </>
                      )}
                    </div>
                  )}
                </div>

                {/* Right Side: Model Selector + Connection */}
                <div className="flex items-center gap-3">
                  {isLoadingLLMData ? (
                    <div className="flex items-center justify-center h-7 px-2 py-1 border border-[#404040] rounded-lg bg-[#262626]">
                      <span className="text-gray-400 text-[11px]">Loading...</span>
                    </div>
                  ) : (
                    <ModelSelector
                      selectedProvider={selectedProvider}
                      selectedModel={selectedModel}
                      selectedConnectionId={selectedConnectionId}
                      connections={availableConnections}
                      availableModels={availableModels}
                      compact
                      onSelectionChange={handleModelSelectionChange}
                      onConnectionCreated={() => loadLLMData(true)}
                      placeholder="Select AI model..."
                      className={availableConnections.length > 0 ? 'w-52 h-7 px-2 py-1 text-xs' : 'h-7 px-2 py-1 text-xs'}
                      preferredProvider={preferredProvider}
                      preferredModel={preferredModel}
                      onSetPreferred={handleSetPreferredModel}
                      onClearPreferred={handleClearPreferredModel}
                    />
                )}

                <button
                  onClick={() => useStore.getState().openSidebar('instructions')}
                  className="p-1.5 hover:bg-[#2a2a2a] rounded-lg transition-colors flex-shrink-0"
                  title="Context"
                  >
                    <Sparkles className="w-4 h-4 text-brand-orange" />
                  </button>
                </div>
              </div>

              {/* Centered Content Area */}
              <div className="flex-1 flex items-center justify-center px-8 relative overflow-hidden">
                {/* Gradient Background Orbs */}
                <div className="absolute top-0 left-1/4 w-[600px] h-[600px] bg-brand-orange/5 rounded-full blur-3xl animate-pulse"></div>
                <div className="absolute bottom-0 right-1/4 w-[500px] h-[500px] bg-purple-500/5 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '1s' }}></div>

                <div className="w-full max-w-3xl 2xl:max-w-4xl relative z-10">
                  {/* Main Title with Icon */}
                  <div className="flex items-center justify-center gap-3 mb-3">
                    <Sparkles className="w-7 h-7 text-brand-orange" />
                    <h1 className="text-4xl font-bold bg-gradient-to-r from-white via-gray-200 to-gray-400 bg-clip-text text-transparent">
                      Let's Byaan the data!
                    </h1>
                    <Sparkles className="w-7 h-7 text-brand-orange" />
                  </div>

                  {/* Subtitle */}
                  <p className="text-center text-gray-400 mb-4 text-sm">
                    Ask questions, explore your data, and create beautiful visualizations
                  </p>

                  {/* Large Input Area with Better Padding */}
                  <div className="mb-6">
                    <div
                      className={`bg-[#1f1f1f] border-2 border-[#333333] rounded-3xl px-5 pt-4 pb-3 shadow-2xl transition-all duration-300 focus-within:border-brand-orange focus-within:ring-2 focus-within:ring-brand-orange/20 focus-within:shadow-brand-orange/10`}
                      onPaste={handleEmptyStatePaste}
                    >
                      {/* Hidden file input */}
                      <input
                        ref={emptyFileInputRef}
                        type="file"
                        accept="image/png,image/jpeg,image/webp"
                        multiple
                        onChange={handleEmptyStateFileSelect}
                        className="hidden"
                      />
                      {/* Image preview section */}
                      {emptyStateAttachedImages.length > 0 && (
                        <div className="flex flex-wrap gap-2 mb-3">
                          {emptyStateAttachedImages.map((img, index) => (
                            <div key={index} className="relative group">
                              <img
                                src={`data:${img.mime_type};base64,${img.file_data}`}
                                alt={img.file_name}
                                className="w-16 h-16 object-cover rounded-lg border border-[#3a3a3a]"
                              />
                              <button
                                onClick={() => handleEmptyStateRemoveAttachment(index)}
                                className="absolute -top-1.5 -right-1.5 w-5 h-5 bg-red-500 hover:bg-red-600 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                                title="Remove image"
                              >
                                <X className="w-3 h-3 text-white" />
                              </button>
                            </div>
                          ))}
                        </div>
                      )}
                      <TableMentionInput
                        ref={emptyStateInputRef}
                        value={input}
                        datasources={schemaDatasets}
                        tableNames={tableNames}
                        getTableColumns={getTableColumns}
                        singleLine={false}
                        onHeightChange={setEmptyInputHeight}
                        onValueChange={setInput}
                        onSubmit={() => {
                          if (!isNotebookStreaming && (input.trim() || emptyStateAttachedImages.length > 0)) {
                            const message = input
                            const attachments = emptyStateAttachedImages.length > 0 ? emptyStateAttachedImages : undefined
                            setInput("")
                            setEmptyStateAttachedImages([])
                            handleSubmitMessage(message || " ", attachments)
                          }
                        }}
                        placeholder={
                          !selectedProvider || !selectedModel
                            ? "Configure your LLM connection first!"
                            : isNotebookStreaming
                              ? "Stop generation to send message..."
                              : "Ask me anything..."
                        }
                        disabled={!selectedProvider || !selectedModel}
                        className={`w-full text-white text-base min-h-[52px] leading-relaxed`}
                      />
                      {/* Bottom toolbar */}
                      <div className="flex items-center justify-between mt-3 pt-2">
                        {/* Left side - Data selector and attachment */}
                        <div className="flex items-center gap-1">
                          <DatasourceFooterSelector
                            selectedDatasourceIds={pendingDatasourceIds}
                            onDatasourceChange={handleDatasourceChange}
                            onUploadFiles={handleUploadFilesForChat}
                            onAddConnector={handleAddNewConnection}
                            agentSelectedDatasourceId={agentSelectedDatasourceId}
                            disabled={isNotebookStreaming}
                          />
                          <button
                            onClick={() => emptyFileInputRef.current?.click()}
                            disabled={!selectedProvider || !selectedModel || isNotebookStreaming}
                            className={`w-9 h-9 rounded-xl transition-all flex items-center justify-center ${
                              selectedProvider && selectedModel && !isNotebookStreaming
                                ? 'text-gray-400 hover:text-gray-300 hover:bg-[#333333] cursor-pointer'
                                : 'text-gray-600 cursor-not-allowed'
                            }`}
                            title="Attach image"
                          >
                            <ImagePlus className="w-5 h-5" />
                          </button>
                          <PlanModeToggle notebookId={createdNotebookIdRef.current || notebookId || 'new'} />
                        </div>
                        {/* Right side - Send button */}
                        {isNotebookStreaming ? (
                          <button
                            onClick={handleCancelGeneration}
                            className="w-10 h-10 bg-brand-orange hover:bg-brand-orange-hover rounded-xl transition-all shadow-lg hover:shadow-xl hover:glow-orange-sm flex items-center justify-center"
                            title="Stop generation"
                          >
                            <div className="w-3.5 h-3.5 bg-white rounded-sm"></div>
                          </button>
                        ) : (
                          <button
                            onClick={async () => {
                              if (!isNotebookStreaming && (input.trim() || emptyStateAttachedImages.length > 0)) {
                                const message = input
                                const attachments = emptyStateAttachedImages.length > 0 ? emptyStateAttachedImages : undefined
                                setInput("")
                                setEmptyStateAttachedImages([])
                                await handleSubmitMessage(message || " ", attachments)
                              }
                            }}
                            disabled={(!input.trim() && emptyStateAttachedImages.length === 0) || !selectedProvider || !selectedModel || isNotebookStreaming}
                            className={`w-10 h-10 rounded-xl transition-all flex items-center justify-center ${
                              (input.trim() || emptyStateAttachedImages.length > 0) && selectedProvider && selectedModel && !isNotebookStreaming
                                ? 'bg-brand-orange hover:bg-brand-orange-hover text-white shadow-lg hover:shadow-xl hover:glow-orange-sm cursor-pointer'
                                : 'bg-[#333333] text-gray-600 cursor-not-allowed'
                            }`}
                            title={
                              isNotebookStreaming
                                ? "Stop generation to send message"
                                : (input.trim() || emptyStateAttachedImages.length > 0)
                                  ? "Send message"
                                  : "Type a message or attach an image"
                            }
                          >
                            <ArrowUp className="w-5 h-5" />
                          </button>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Helpful Tips */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-3xl 2xl:max-w-4xl mx-auto">
                    {/* Tip 1: @ Mentions */}
                    <div className="group bg-[#1a1a1a] border border-[#2a2a2a] rounded-xl p-4 hover:border-brand-orange/30 transition-all hover:bg-[#1f1f1f]">
                      <div className="flex items-start gap-3">
                        <div className="w-9 h-9 rounded-lg bg-brand-orange/10 flex items-center justify-center flex-shrink-0 group-hover:bg-brand-orange/20 transition-colors">
                          <AtSign className="w-5 h-5 text-brand-orange" />
                        </div>
                        <div>
                          <h3 className="text-sm font-semibold text-white mb-1">Use @ mentions</h3>
                          <p className="text-xs text-gray-400 leading-relaxed">
                            Type <code className="px-1.5 py-0.5 bg-[#2a2a2a] rounded text-brand-orange">@</code> to reference tables and collections in your queries
                          </p>
                        </div>
                      </div>
                    </div>

                    {/* Tip 2: Example Queries */}
                    <div className="group bg-[#1a1a1a] border border-[#2a2a2a] rounded-xl p-4 hover:border-purple-500/30 transition-all hover:bg-[#1f1f1f]">
                      <div className="flex items-start gap-3">
                        <div className="w-9 h-9 rounded-lg bg-purple-500/10 flex items-center justify-center flex-shrink-0 group-hover:bg-purple-500/20 transition-colors">
                          <Table className="w-5 h-5 text-purple-400" />
                        </div>
                        <div>
                          <h3 className="text-sm font-semibold text-white mb-1">Natural language queries</h3>
                          <p className="text-xs text-gray-400 leading-relaxed">
                            Ask questions like "Show me sales by region" or "What's the average order value?"
                          </p>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        {datasourceModal}
      </React.Fragment>
    )
  }

  if (embedded && messages.length === 0 && !isPreviewOpen) {
    const canAsk = semanticModelReady && assistantReady && !isNotebookStreaming
    return (
      <div className={`flex ${viewportHeightClass} min-w-0 flex-col overflow-hidden bg-[#0f1115] text-white`} data-ask-data-workspace="empty">
        <div className="flex min-h-12 shrink-0 flex-wrap items-center justify-between gap-2 border-b border-[#29313a] bg-[#101418] px-3 py-2 sm:h-12 sm:flex-nowrap sm:px-4 sm:py-0">
          <div className="flex min-w-0 items-center gap-2.5">
            {!isNewNotebook && (
              <button type="button" onClick={() => navigate(conversationHomePath)} className="grid h-7 w-7 shrink-0 place-items-center rounded-md text-[#9ba7b2] hover:bg-[#1b2128] hover:text-white" title="New question">
                <Plus className="h-4 w-4" />
              </button>
            )}
            <SemanticModelPicker
              models={semanticModels}
              selectedModel={selectedSemanticModel}
              value={selectedSemanticModelId}
              locked={Boolean(boundSemanticModelId)}
              loading={isLoadingSemanticModels}
              error={semanticModelsError}
              onChange={setSelectedSemanticModelId}
              onManage={() => navigate(`${EMBEDDED_KNOWLEDGE_CENTER_BASE}/data-models`)}
            />
          </div>
          <div className="hidden shrink-0 items-center gap-1.5 text-[11px] text-[#7f8a95] sm:flex">
            <ShieldCheck className={`h-3.5 w-3.5 ${assistantReady ? 'text-emerald-400' : 'text-amber-400'}`} />
            {isLoadingLLMData ? 'Loading workspace AI...' : assistantReady ? 'Workspace AI ready' : 'Admin setup required'}
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-8 sm:px-6 sm:py-12">
          <div className="mx-auto flex min-h-full w-full max-w-3xl flex-col justify-center min-[1440px]:max-w-4xl">
            <div className="mb-6">
              <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-[#eef2f6]">
                <LineChart className="h-4 w-4 text-emerald-400" />
                Ask Data
              </div>
              <h1 className="text-2xl font-semibold leading-tight text-[#f4f7f9] sm:text-3xl">What do you need to know?</h1>
              <p className="mt-2 max-w-2xl text-sm leading-relaxed text-[#8d99a5]">
                {selectedSemanticModel
                  ? `Answers use the published ${semanticModelLabel(selectedSemanticModel)} contract. Metric definitions, SQL, lineage, freshness, and policy evidence stay available for review.`
                  : isLoadingSemanticModels
                    ? 'Loading published metrics and dimensions...'
                    : semanticModelsError
                      ? 'Published Semantic Models could not be loaded.'
                      : 'Select a published Semantic Model to start a governed conversation.'}
              </p>
            </div>

            <div className="border border-[#343e48] bg-[#151a20] p-3 shadow-[0_12px_30px_rgba(0,0,0,0.24)] focus-within:border-emerald-500/60">
              <TableMentionInput
                ref={emptyStateInputRef}
                value={input}
                datasources={[]}
                tableNames={[]}
                getTableColumns={() => []}
                singleLine={false}
                onHeightChange={setEmptyInputHeight}
                onValueChange={setInput}
                onSubmit={() => {
                  if (canAsk && input.trim()) {
                    const message = input.trim()
                    setInput('')
                    handleSubmitMessage(message)
                  }
                }}
                placeholder={semanticModelReady ? 'Ask a business question about the published metrics...' : 'Select a published Semantic Model first'}
                disabled={!canAsk}
                className="min-h-[76px] w-full text-sm leading-relaxed text-white"
              />
              <div className="mt-2 flex items-center justify-between border-t border-[#29313a] pt-2">
                <div className="flex items-center gap-1.5 text-[11px] text-[#78848f]">
                  <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
                  Published metrics only
                </div>
                <button
                  type="button"
                  onClick={async () => {
                    if (!canAsk || !input.trim()) return
                    const message = input.trim()
                    setInput('')
                    await handleSubmitMessage(message)
                  }}
                  disabled={!canAsk || !input.trim()}
                  className="grid h-8 w-8 place-items-center rounded-md bg-emerald-500 text-[#07110c] hover:bg-emerald-400 disabled:cursor-not-allowed disabled:bg-[#283139] disabled:text-[#65717c]"
                  title="Send question"
                >
                  <ArrowUp className="h-4 w-4" />
                </button>
              </div>
            </div>

            {!isLoadingLLMData && !assistantReady && (
              <div className="mt-3 flex items-center justify-between gap-3 border border-amber-500/25 bg-amber-500/[0.06] px-3 py-2 text-xs text-amber-100">
                <span>Ask Data needs an organization AI connection configured by a Data Studio administrator.</span>
                <a href="/llm-connections" target="_blank" rel="noreferrer" className="shrink-0 font-medium text-amber-300 hover:text-amber-200">
                  Configure in Data Studio
                </a>
              </div>
            )}

            {semanticExamples.length > 0 && (
              <div className="mt-4 grid gap-2 sm:grid-cols-2">
                {semanticExamples.map(example => (
                  <button
                    key={example}
                    type="button"
                    onClick={() => setInput(example)}
                    className="min-h-10 border border-[#29313a] bg-[#11161b] px-3 py-2 text-left text-xs leading-relaxed text-[#b9c3cc] hover:border-[#3c4955] hover:bg-[#151b21] hover:text-white"
                  >
                    {example}
                  </button>
                ))}
              </div>
            )}

            {!isLoadingSemanticModels && semanticModels.length === 0 && (
              <button type="button" onClick={() => navigate(`${EMBEDDED_KNOWLEDGE_CENTER_BASE}/data-models`)} className="mt-4 w-fit text-xs font-medium text-emerald-400 hover:text-emerald-300">
                Open Data Models to publish a contract
              </button>
            )}
          </div>
        </div>
      </div>
    )
  }

  // Main chat view with messages - SPLIT LAYOUT
  return (
    <React.Fragment>
      <div className={`relative flex min-w-0 flex-col ${viewportHeightClass} ${embedded ? 'bg-[#0f1115]' : 'bg-[#1a1a1a]'} overflow-hidden text-white`} data-ask-data-workspace={embedded ? 'conversation' : undefined}>
      {!embedded && (
        <>
          <div className="absolute top-0 left-1/4 w-[600px] h-[600px] bg-brand-orange/5 rounded-full blur-3xl animate-pulse pointer-events-none"></div>
          <div className="absolute bottom-0 right-1/4 w-[500px] h-[500px] bg-purple-500/5 rounded-full blur-3xl animate-pulse pointer-events-none" style={{ animationDelay: '1s' }}></div>
        </>
      )}
      {/* Top Navigation Bar */}
      <div className={`z-10 flex h-12 min-w-0 flex-shrink-0 items-center justify-between gap-2 border-b px-3 sm:gap-3 sm:px-5 ${embedded ? 'bg-[#101418] border-[#29313a]' : 'bg-[#1a1a1a] border-[#2a2a2a]'}`}>
        {/* Left Side: Back Arrow + Notebook Name */}
        <div className="flex min-w-0 flex-1 items-center gap-2 sm:gap-3">
          <button
            onClick={() => navigate(conversationHomePath)}
            className="p-1 hover:bg-[#2a2a2a] rounded-lg transition-colors flex-shrink-0"
            title={embedded ? 'New question' : 'Go back to Notebooks'}
          >
            {embedded ? <Plus className="w-4 h-4 text-white" /> : <ArrowLeft className="w-4 h-4 text-white" />}
          </button>

          {/* The embedded workspace prioritizes the governed model over notebook metadata. */}
          {!embedded && (isEditingName ? (
            <div className="flex items-center gap-1.5">
              <input
                ref={nameInputRef}
                type="text"
                value={editedName}
                onChange={(e) => setEditedName(e.target.value)}
                onKeyDown={handleNameKeyDown}
                onBlur={handleSaveNotebookName}
                className="text-xs font-medium text-white bg-[#2a2a2a] border border-[#404040] rounded px-2 py-1 focus:outline-none focus:border-brand-orange min-w-0"
                maxLength={100}
              />
              <button
                onClick={handleSaveNotebookName}
                className="p-1 hover:bg-[#2a2a2a] rounded transition-colors flex-shrink-0"
                title="Save name"
              >
                <Check className="w-3.5 h-3.5 text-green-400" />
              </button>
              <button
                onClick={handleCancelEditingName}
                className="p-1 hover:bg-[#2a2a2a] rounded transition-colors flex-shrink-0"
                title="Cancel"
              >
                <X className="w-3.5 h-3.5 text-red-400" />
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-xs font-medium text-white truncate">
                {currentNotebook?.notebook_name || 'Chat Assistant'}
              </span>
              <button
                onClick={handleStartEditingName}
                className="p-1 hover:bg-[#2a2a2a] rounded-lg transition-colors flex-shrink-0 opacity-70 hover:opacity-100"
                title="Rename notebook"
              >
                <Pencil className="w-3 h-3 text-white" />
              </button>
            </div>
          ))}

          {embedded && (
            <SemanticModelPicker
              models={semanticModels}
              selectedModel={selectedSemanticModel}
              value={selectedSemanticModelId}
              locked={Boolean(boundSemanticModelId)}
              loading={isLoadingSemanticModels}
              error={semanticModelsError}
              onChange={setSelectedSemanticModelId}
              onManage={() => navigate(`${EMBEDDED_KNOWLEDGE_CENTER_BASE}/data-models`)}
            />
          )}

          {/* Clear Button - Only shows when there are messages */}
          {messages.length > 0 && notebookId && (
            <button
              onClick={openConfirmModal}
              className={`${embedded ? 'grid h-8 w-8 place-items-center text-[#8f9ba6] hover:bg-[#1b2128] hover:text-red-300' : 'ml-3 flex items-center gap-1.5 px-2.5 py-1 text-red-400 hover:text-red-300 border border-[#404040] hover:border-red-400'} flex-shrink-0 rounded-md bg-transparent text-xs transition-colors`}
              title="Clear conversation"
            >
              <Trash2 className="h-3.5 w-3.5" />
              {!embedded && 'Clear'}
            </button>
          )}
        </div>

        {/* Right Side: Model Selector + Connection */}
        {embedded && dashboardReady && notebookId && (
          <button
            type="button"
            onClick={() => {
              if (isPreviewOpen) {
                handleClosePreview()
                navigate(notebookPath(notebookId), { replace: true })
              } else {
                handleOpenPreview()
                navigate(notebookPath(notebookId, true), { replace: true })
              }
            }}
            className="flex h-8 shrink-0 items-center gap-1.5 rounded-md border border-[#303a44] px-2.5 text-xs text-[#c5ced7] hover:border-[#43515e] hover:bg-[#171d23] hover:text-white"
            title={isPreviewOpen ? 'Return to answer' : 'View generated dashboard'}
          >
            {isPreviewOpen ? <MessageSquareText className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
            <span className="hidden sm:inline">{isPreviewOpen ? 'Answer' : 'Dashboard'}</span>
          </button>
        )}

        <div className={`flex shrink-0 items-center ${embedded ? 'hidden' : ''} gap-3`}>
          {isLoadingLLMData ? (
            <div className="flex items-center justify-center h-7 px-2 py-1 border border-[#404040] rounded-lg bg-[#262626]">
              <span className="text-gray-400 text-[11px]">Loading...</span>
            </div>
          ) : (
            <ModelSelector
              selectedProvider={selectedProvider}
              selectedModel={selectedModel}
              selectedConnectionId={selectedConnectionId}
              connections={availableConnections}
              availableModels={availableModels}
              compact
              onSelectionChange={handleModelSelectionChange}
              onConnectionCreated={() => loadLLMData(true)}
              placeholder="Select AI model..."
              className={availableConnections.length > 0 ? 'w-52 h-7 px-2 py-1 text-xs' : 'h-7 px-2 py-1 text-xs'}
              preferredProvider={preferredProvider}
              preferredModel={preferredModel}
              onSetPreferred={handleSetPreferredModel}
              onClearPreferred={handleClearPreferredModel}
            />
        )}


          {!embedded && <button
            onClick={isPreviewOpen ? handleClosePreview : handleOpenPreview}
            className={`p-1.5 rounded-lg transition-colors flex-shrink-0 ${
              isPreviewOpen
                ? 'bg-brand-orange/20 text-brand-orange'
                : 'hover:bg-[#2a2a2a] text-gray-400 hover:text-white'
            }`}
            title={isPreviewOpen ? 'Hide preview' : 'Show preview'}
          >
            <Eye className="w-4 h-4" />
          </button>}

          {!embedded && <button
            onClick={() => useStore.getState().openSidebar('instructions')}
            className="p-1.5 hover:bg-[#2a2a2a] rounded-lg transition-colors flex-shrink-0"
            title="Context"
          >
            <Sparkles className="w-4 h-4 text-brand-orange" />
          </button>}
        </div>
      </div>

      {/* Centered Chat + Resizable Preview Layout */}
      <div className="flex-1 overflow-hidden flex">
        <ResizableSplitPanel
          isRightPanelOpen={isPreviewOpen}
          leftPanel={
            <div className={`chat-area flex flex-col h-full ${isPreviewOpen ? 'chat-area-with-preview' : 'chat-area-centered'}`}>
                <div className="flex flex-col h-full w-full">
                  {!embedded && existingSchedule && !isScheduleMode && (
                    <div className="max-w-3xl min-[1440px]:max-w-4xl min-[2560px]:max-w-[1400px] mx-auto w-full">
                      <ScheduleBanner
                        schedule={existingSchedule}
                        onEdit={handleEnterScheduleMode}
                        onToggle={handleToggleSchedule}
                        onDelete={handleDeleteSchedule}
                        slackChannelName={existingSchedule.slack_channel_id ? slackChannelNames[existingSchedule.slack_channel_id] : undefined}
                      />
                    </div>
                  )}

                  <MessageList
                    notebookId={notebookId}
                    handleCodeInject={handleCodeInject}
                    currentActivity={currentActivity}
                  />

                  <div className="max-w-3xl min-[1440px]:max-w-4xl min-[2560px]:max-w-[1400px] mx-auto w-full">
                    {embedded && !isLoadingLLMData && !assistantReady && (
                      <div className="mx-4 mb-2 flex items-center justify-between gap-3 border border-amber-500/25 bg-amber-500/[0.06] px-3 py-2 text-xs text-amber-100 sm:mx-6">
                        <span>Ask Data needs an organization AI connection configured by an administrator.</span>
                        <a href="/llm-connections" target="_blank" rel="noreferrer" className="shrink-0 font-medium text-amber-300 hover:text-amber-200">
                          Configure
                        </a>
                      </div>
                    )}
                    {embedded && (
                      <SemanticEvidencePanel
                        event={latestSemanticEvidence}
                        dashboardAvailable={dashboardAvailable}
                        busy={isNotebookStreaming}
                        onCreateDashboard={() => {
                          void handleSubmitMessage('Create a dashboard from the latest governed result.')
                        }}
                      />
                    )}
                    <ChatInput
                      notebookId={notebookId}
                      datasources={schemaDatasets}
                      tableNames={tableNames}
                      getTableColumns={getTableColumns}
                      onSubmit={async (msg, attachments) => {
                        if (isScheduleMode) {
                          setScheduleInstruction(msg)
                        }
                        await handleSubmitMessage(msg, attachments)
                      }}
                      selectedProvider={selectedProvider}
                      selectedModel={selectedModel}
                      handleCancelGeneration={handleCancelGeneration}
                      selectedDatasourceIds={pendingDatasourceIds}
                      onDatasourceChange={handleDatasourceChange}
                      onUploadFiles={handleUploadFilesForChat}
                      onAddNewConnection={handleAddNewConnection}
                      agentSelectedDatasourceId={agentSelectedDatasourceId}
                      onSchedule={embedded || isScheduleMode ? undefined : handleEnterScheduleMode}
                      hasSchedule={!!existingSchedule}
                      isScheduleMode={isScheduleMode}
                      onCancelSchedule={handleCancelScheduleMode}
                      onInputChange={setScheduleInstruction}
                      grabbedElementText={grabbedElementText}
                      embedded={embedded}
                      semanticModelReady={semanticModelReady}
                    />

                    {!embedded && isScheduleMode && !isNotebookStreaming && messages.length > 0 && (
                      <ScheduleConfigPanel
                        config={scheduleConfig}
                        onConfigChange={setScheduleConfig}
                        onCancel={handleCancelScheduleMode}
                        onSave={handleSaveSchedule}
                        isSaving={createScheduleMutation.isPending || updateScheduleMutation.isPending}
                        existingScheduleId={existingSchedule?.id}
                        instruction={scheduleInstruction}
                      />
                    )}
                  </div>
                </div>
              </div>
            }
            rightPanel={
              <div className="preview-panel preview-panel-open">
                <div className="flex flex-col h-full">
                  {showDashboardCard ? (
                    <DashboardPreviewPanel
                      processedHtmlContent={processedHtmlContent}
                      iframeKey={iframeKey}
                      generatedCode={generatedCode}
                      isRefreshing={isRefreshing}
                      onRefresh={loadCurrentFile}
                      availableVersions={availableVersions}
                      selectedVersion={selectedVersion}
                      latestVersionNum={latestVersionNum}
                      onVersionChange={handleVersionChange}
                      isExportingPdf={isExportingPdf}
                      onExportPdf={features.external_sharing_enabled ? handleExportPdf : undefined}
                      isExportingHtml={isExportingHtml}
                      onExportHtml={handleExportCompiledHtml}
                      onShare={isSelfHosted || isTauriApp() ? handleShare : undefined}
                      onOpenFullscreen={() => setShowPreviewModal(true)}
                      onOpenQueryPanel={() => { setPreviewPanelTab('queries'); setIsPreviewOpen(true) }}
                      onClose={handleClosePreview}
                      notebookId={notebookId}
                      onDebugWithAssistant={handleDebugWithAssistant}
                      injectedQuery={injectedQuery}
                      injectedQueryVersion={injectedQueryVersion}
                      injectedConnectionId={injectedConnectionId || agentSelectedDatasourceId || pendingDatasourceIds[0] || undefined}
                      isCodeLoading={isHtmlBeingEdited}
                      codeLoadingMessage={currentActivity || undefined}
                      iframeErrors={iframeErrors}
                      activeTab={previewPanelTab}
                      onActiveTabChange={setPreviewPanelTab}
                      iframeRef={iframeRef}
                      onIframeLoad={handlePreviewIframeLoad}
                      htmlEditTimeline={htmlEditTimeline}
                      liveCodeOverride={liveHtmlCode}
                      isLiveStreamEnabled={isLiveHtmlStreamEnabled}
                      onToggleLiveStream={handleToggleLiveHtmlStream}
                      showGenerationIndicator={dashboardGenerationIndicator.show}
                      generationIndicatorMessage={dashboardGenerationIndicator.message}
                      activeFiltersBar={
                        <ActiveFiltersBar
                          chips={activeFilterChips}
                          onRemoveChip={(chip) =>
                            setDashboardFilterValues((previous) =>
                              removeActiveFilterChip(previous, chip),
                            )
                          }
                          onClearAll={() => setDashboardFilterValues({})}
                        />
                      }
                      filterSidebar={
                        <DashboardFilterSidebar
                          filters={dashboardFilters}
                          values={dashboardFilterValues}
                          onChange={setDashboardFilterValues}
                          storageKey={notebookId ? `chat_preview_filter_sidebar_${notebookId}` : 'chat_preview_filter_sidebar'}
                          actions={
                            <button
                              type="button"
                              onClick={() => setShowFilterPreflightDebug((prev) => !prev)}
                              className="h-7 rounded-md border border-[#39414c] bg-[#13171c] px-2.5 text-[10px] uppercase tracking-[0.08em] text-gray-400 transition-colors hover:border-brand-orange/50 hover:text-brand-orange"
                            >
                              {showFilterPreflightDebug ? 'Hide Debug' : 'Debug Preflight'}
                            </button>
                          }
                          diagnosticsPanel={showFilterPreflightDebug ? (
                            <FilterPreflightPanel
                              loading={isFilterPreflightLoading}
                              response={filterPreflightResponse}
                              error={filterPreflightError}
                              activeFilterCount={activeFilterValueCount}
                            />
                          ) : null}
                        />
                      }
                      onElementGrabbed={handleElementGrabbed}
                    />
                  ) : null}
                </div>
              </div>
            }
          defaultLeftWidth={34}
          minLeftWidth={30}
          maxLeftWidth={58}
        />
      </div>

      {/* Query Panel Overlay */}
      {/* Modals */}
      <FullscreenPreviewModal
        open={showPreviewModal}
        onOpenChange={setShowPreviewModal}
        title={currentNotebook?.notebook_name || 'Dashboard Preview'}
        processedHtmlContent={processedHtmlContent}
        iframeKey={iframeKey}
        isRefreshing={isRefreshing}
        onRefresh={loadCurrentFile}
        isExportingPdf={isExportingPdf}
        onExportPdf={handleExportPdf}
        isExportingHtml={isExportingHtml}
        onExportHtml={handleExportCompiledHtml}
        onShare={isSelfHosted || isTauriApp() ? handleShare : undefined}
        isTauri={isTauriApp()}
        onToggleDevTools={() => toggleDevTools()}
      />

      <ConfirmationModal
        isOpen={showConfirmModal}
        onClose={() => setShowConfirmModal(false)}
        onConfirm={handleClearConversation}
        title="Clear Conversation"
        message="Are you sure you want to clear the entire conversation? This action cannot be undone and will permanently delete all messages in this notebook."
        confirmText="Clear Conversation"
        cancelText="Cancel"
        type="danger"
      />

      <ErrorLogModal
        errors={iframeErrors}
        onClearErrors={() => setIframeErrors([])}
        onFixWithAssistant={handleFixPreviewErrors}
        />

      {notebookId && (
        <ShareModal
          open={isShareModalOpen}
          onOpenChange={setIsShareModalOpen}
          notebookId={notebookId}
          dashboardId={availableVersions.find(v => v.version_num === (selectedVersion ?? latestVersionNum))?.id}
          version={selectedVersion ?? latestVersionNum}
          onShareDashboardToFolder={isSelfHosted ? () => setIsDashboardFolderModalOpen(true) : undefined}
          onShareNotebookToFolder={isSelfHosted ? () => setIsNotebookFolderModalOpen(true) : undefined}
          canShareExternally={canShareExternally}
        />
      )}

      {/* Dashboard to Folder sharing modal - only in hosted mode */}
      {isSelfHosted && (() => {
        const currentVersion = selectedVersion ?? latestVersionNum
        const dashboardVersion = availableVersions.find(v => v.version_num === currentVersion)
        return dashboardVersion?.id ? (
          <ShareDashboardToFolderModal
            open={isDashboardFolderModalOpen}
            onOpenChange={setIsDashboardFolderModalOpen}
            dashboardId={dashboardVersion.id}
            dashboardVersion={currentVersion}
            notebookId={currentNotebook?.id || undefined}
            notebookName={currentNotebook?.notebook_name || undefined}
          />
        ) : null
      })()}

      {/* Notebook to Folder sharing modal - only in hosted mode */}
      {isSelfHosted && notebookId && (
        <ShareNotebookToFolderModal
          open={isNotebookFolderModalOpen}
          onOpenChange={setIsNotebookFolderModalOpen}
          notebookId={notebookId}
          notebookName={currentNotebook?.notebook_name}
        />
      )}

    </div>
    {datasourceModal}
    </React.Fragment>
  )
}
