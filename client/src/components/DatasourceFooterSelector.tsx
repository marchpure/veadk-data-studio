import { useState, useRef, useEffect, useMemo } from 'react'
import { Database, Upload, Plus, X, Search, ChevronUp } from 'lucide-react'
import { useDatasources } from '../hooks/useDBConnections'
import { Input } from './ui/input'

interface DatasourceFooterSelectorProps {
  selectedDatasourceIds: string[]
  onDatasourceChange: (ids: string[]) => void
  onUploadFiles: (files: File[], fileType: string) => void
  onAddConnector: () => void
  agentSelectedDatasourceId?: string | null
  disabled?: boolean
}

export function DatasourceFooterSelector({
  selectedDatasourceIds,
  onDatasourceChange,
  onUploadFiles,
  onAddConnector,
  agentSelectedDatasourceId,
  disabled = false
}: DatasourceFooterSelectorProps) {
  const { data: datasourcesResponse, isLoading } = useDatasources()
  const allDatasources = datasourcesResponse?.items || []

  const [isOpen, setIsOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const dropdownRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const filteredDatasources = useMemo(() => {
    return allDatasources.filter(ds =>
      ds.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      ds.type?.toLowerCase().includes(searchQuery.toLowerCase())
    )
  }, [allDatasources, searchQuery])

  const selectedDatasources = useMemo(() => {
    return allDatasources.filter(ds =>
      selectedDatasourceIds.includes(ds.id) ||
      (ds.connection_id && selectedDatasourceIds.includes(ds.connection_id))
    )
  }, [allDatasources, selectedDatasourceIds])

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [isOpen])

  useEffect(() => {
    if (isOpen && inputRef.current) {
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [isOpen])

  const handleToggleDatasource = (datasourceId: string, connectionId?: string) => {
    const isCurrentlySelected = selectedDatasourceIds.includes(datasourceId) ||
      (connectionId && selectedDatasourceIds.includes(connectionId))

    if (isCurrentlySelected) {
      onDatasourceChange(selectedDatasourceIds.filter(id =>
        id !== datasourceId && id !== connectionId
      ))
    } else {
      onDatasourceChange([...selectedDatasourceIds, datasourceId])
    }
  }

  const handleRemoveDatasource = (datasourceId: string, connectionId?: string, e?: React.MouseEvent) => {
    e?.stopPropagation()
    onDatasourceChange(selectedDatasourceIds.filter(id =>
      id !== datasourceId && id !== connectionId
    ))
  }

  const handleAddNew = () => {
    setIsOpen(false)
    onAddConnector()
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files || files.length === 0) return

    const fileArray = Array.from(files)
    const firstFile = fileArray[0]
    let fileType = 'csv'

    if (firstFile.name.endsWith('.xlsx') || firstFile.name.endsWith('.xls')) {
      fileType = 'excel'
    } else if (firstFile.name.endsWith('.parquet')) {
      fileType = 'parquet'
    } else if (firstFile.name.endsWith('.json')) {
      fileType = 'json'
    }

    onUploadFiles(fileArray, fileType)
    setIsOpen(false)

    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  return (
    <div className="relative" ref={dropdownRef}>
      <input
        ref={fileInputRef}
        type="file"
        accept=".csv,.xlsx,.xls,.parquet,.json"
        multiple
        onChange={handleFileChange}
        className="hidden"
      />

      <div className="flex items-center gap-2 flex-wrap">
        {selectedDatasources.map((ds) => {
          const isAgentSelected = agentSelectedDatasourceId === ds.id ||
            (ds.connection_id && agentSelectedDatasourceId === ds.connection_id)
          return (
            <div
              key={ds.id}
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs transition-all ${
                isAgentSelected
                  ? 'bg-brand-orange/20 border border-brand-orange text-white animate-pulse'
                  : 'bg-[#2a2a2a] border border-[#3a3a3a] text-gray-300'
              }`}
            >
              {ds.source_type === 'dataset' ? (
                <Upload className="w-3 h-3 text-brand-orange" />
              ) : (
                <Database className="w-3 h-3 text-brand-orange" />
              )}
              <span className="max-w-[100px] truncate">{ds.name || 'Unnamed'}</span>
              <button
                onClick={(e) => handleRemoveDatasource(ds.id, ds.connection_id, e)}
                className="p-0.5 hover:bg-[#444444] rounded-full transition-colors"
                title="Remove datasource"
              >
                <X className="w-3 h-3 text-gray-400 hover:text-white" />
              </button>
            </div>
          )
        })}


        <button
          onClick={() => !disabled && setIsOpen(!isOpen)}
          disabled={disabled}
          className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs transition-all ${
            disabled
              ? 'bg-[#1a1a1a] text-gray-600 cursor-not-allowed'
              : isOpen
                ? 'bg-brand-orange/10 border border-brand-orange text-brand-orange'
                : 'bg-[#262626] border border-[#3a3a3a] text-gray-300 hover:border-brand-orange/50 hover:text-white'
          }`}
        >
          <Database className="w-3.5 h-3.5" />
          <span>Data</span>
          <ChevronUp className={`w-3 h-3 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
        </button>
      </div>

      {isOpen && (
        <div className="absolute bottom-full left-0 mb-2 bg-[#1f1f1f] border border-[#3a3a3a] rounded-xl shadow-2xl z-50 w-80 max-h-96 flex flex-col overflow-hidden">
          <div className="p-3 border-b border-[#2a2a2a]">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
              <Input
                ref={inputRef}
                type="text"
                placeholder="Search datasources..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9 bg-[#262626] border-[#3a3a3a] text-white text-sm h-9 focus:border-brand-orange focus:ring-1 focus:ring-brand-orange/30"
              />
            </div>
          </div>

          <div className="flex-1 overflow-y-auto custom-scrollbar">
            <div className="p-2 border-b border-[#2a2a2a]">
              <button
                onClick={() => fileInputRef.current?.click()}
                className="w-full px-3 py-2.5 text-left hover:bg-[#2a2a2a] rounded-lg transition-colors flex items-center gap-3"
              >
                <div className="w-8 h-8 rounded-lg bg-emerald-500/10 flex items-center justify-center flex-shrink-0">
                  <Upload className="w-4 h-4 text-emerald-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-white">Upload from computer</div>
                  <div className="text-xs text-gray-500">CSV, Excel, Parquet, JSON</div>
                </div>
              </button>
            </div>

            <div className="p-2">
              <div className="px-3 py-1.5 text-[10px] uppercase tracking-wider text-gray-500 font-medium">
                Data Sources
              </div>

              {isLoading ? (
                <div className="px-3 py-4 text-center text-sm text-gray-500">
                  Loading datasources...
                </div>
              ) : filteredDatasources.length === 0 ? (
                <div className="px-3 py-4 text-center text-sm text-gray-500">
                  {searchQuery ? 'No datasources match your search' : 'No datasources available'}
                </div>
              ) : (
                filteredDatasources.map((datasource) => {
                  const isSelected = selectedDatasourceIds.includes(datasource.id) ||
                    (datasource.connection_id && selectedDatasourceIds.includes(datasource.connection_id))
                  const isAgentSelected = agentSelectedDatasourceId === datasource.id ||
                    (datasource.connection_id && agentSelectedDatasourceId === datasource.connection_id)

                  return (
                    <button
                      key={datasource.id}
                      onClick={() => handleToggleDatasource(datasource.id, datasource.connection_id)}
                      className={`w-full px-3 py-2 text-left rounded-lg transition-colors flex items-center gap-3 ${
                        isSelected
                          ? 'bg-brand-orange/10'
                          : 'hover:bg-[#2a2a2a]'
                      } ${isAgentSelected ? 'ring-1 ring-brand-orange' : ''}`}
                    >
                      <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
                        isSelected ? 'bg-brand-orange/20' : 'bg-[#262626]'
                      }`}>
                        {datasource.source_type === 'dataset' ? (
                          <Upload className={`w-4 h-4 ${isSelected ? 'text-brand-orange' : 'text-gray-400'}`} />
                        ) : (
                          <Database className={`w-4 h-4 ${isSelected ? 'text-brand-orange' : 'text-gray-400'}`} />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className={`text-sm font-medium truncate ${isSelected ? 'text-white' : 'text-gray-300'}`}>
                            {datasource.name || 'Unnamed'}
                          </span>
                        </div>
                        <div className="text-xs text-gray-500 uppercase">{datasource.type}</div>
                      </div>
                      {isSelected && (
                        <div className="w-5 h-5 rounded-full bg-brand-orange flex items-center justify-center flex-shrink-0">
                          <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                          </svg>
                        </div>
                      )}
                    </button>
                  )
                })
              )}
            </div>
          </div>

          <div className="p-2 border-t border-[#2a2a2a]">
            <button
              onClick={handleAddNew}
              className="w-full px-3 py-2.5 text-left hover:bg-[#2a2a2a] rounded-lg transition-colors flex items-center gap-3"
            >
              <div className="w-8 h-8 rounded-lg bg-brand-orange/10 flex items-center justify-center flex-shrink-0">
                <Plus className="w-4 h-4 text-brand-orange" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-brand-orange">Add data connector</div>
                <div className="text-xs text-gray-500">PostgreSQL, MongoDB, MySQL...</div>
              </div>
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
