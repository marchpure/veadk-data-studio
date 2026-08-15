import { useState, useRef, useEffect } from 'react'
import { Database, Upload, Plus, X, Check, ChevronDown } from 'lucide-react'
import { useDatasources } from '../hooks/useDBConnections'
import { Input } from './ui/input'

interface DataSelectorProps {
  selectedDatasourceId?: string | null
  onDatasourceSelect: (datasourceId: string) => void
  onAddNewConnection: () => void
  onRemoveDatasource?: () => void
  className?: string
}

export function DataSelector({
  selectedDatasourceId,
  onDatasourceSelect,
  onAddNewConnection,
  onRemoveDatasource,
  className = ''
}: DataSelectorProps) {
  const { data: datasourcesResponse, isLoading } = useDatasources()
  const allDatasources = datasourcesResponse?.items || []

  const [isOpen, setIsOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const dropdownRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Find the selected datasource info
  const selectedDatasourceInfo = selectedDatasourceId
    ? allDatasources.find(ds => ds.id === selectedDatasourceId)
    : null

  // Filter datasources based on search query
  const filteredDatasources = allDatasources.filter(ds =>
    ds.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    ds.type?.toLowerCase().includes(searchQuery.toLowerCase())
  )

  // Close dropdown when clicking outside
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

  // Focus input when dropdown opens
  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus()
    }
  }, [isOpen])

  const handleSelectDatasource = (datasourceId: string) => {
    onDatasourceSelect(datasourceId)
    setIsOpen(false)
    setSearchQuery('')
  }

  const handleAddNew = () => {
    setIsOpen(false)
    onAddNewConnection()
  }

  const handleRemove = (e: React.MouseEvent) => {
    e.stopPropagation()
    onRemoveDatasource?.()
  }

  // If we have a selected datasource, show compact badge
  if (selectedDatasourceInfo) {
    return (
      <div className={`inline-flex items-center gap-2 ${className}`}>
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="inline-flex items-center gap-2 px-3 py-1.5 bg-[#2a2a2a] border border-[#555555] rounded-full hover:border-brand-orange transition-colors group"
        >
          <Database className="w-3.5 h-3.5 text-brand-orange" />
          <span className="text-sm text-white font-medium">
            {selectedDatasourceInfo.name || 'Unnamed'}
          </span>
          <span className="text-xs text-gray-500 uppercase">
            {selectedDatasourceInfo.type}
          </span>
          <ChevronDown className="w-3.5 h-3.5 text-gray-400 group-hover:text-brand-orange transition-colors" />
        </button>

        {onRemoveDatasource && (
          <button
            onClick={handleRemove}
            className="p-1 hover:bg-[#2a2a2a] rounded-full transition-colors"
            title="Remove datasource"
          >
            <X className="w-3.5 h-3.5 text-gray-400 hover:text-red-400" />
          </button>
        )}

        {/* Dropdown for changing datasource */}
        {isOpen && (
          <div ref={dropdownRef} className="absolute bottom-full left-0 mb-2 bg-[#2a2a2a] border border-[#555555] rounded-lg shadow-2xl z-50 w-96 max-h-80 flex flex-col">
            {/* Header */}
            <div className="p-3 border-b border-[#555555]">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-white">Change Datasource</span>
                <button
                  onClick={() => setIsOpen(false)}
                  className="text-gray-400 hover:text-white transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
              <Input
                ref={inputRef}
                type="text"
                placeholder="Search datasources..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="bg-[#1a1a1a] border-[#555555] text-white text-sm focus:border-brand-orange focus:ring-1 focus:ring-brand-orange/50"
              />
            </div>

            {/* Options List */}
            <div className="flex-1 overflow-y-auto custom-scrollbar">
              {!isLoading && filteredDatasources.map((datasource) => (
                <button
                  key={datasource.id}
                  onClick={() => handleSelectDatasource(datasource.id)}
                  className={`w-full px-3 py-2.5 text-left hover:bg-[#333333] transition-colors flex items-center gap-3 ${
                    selectedDatasourceId === datasource.id ? 'bg-brand-orange/10' : ''
                  }`}
                >
                  <div className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 ${
                    selectedDatasourceId === datasource.id ? 'bg-brand-orange/20' : 'bg-[#1a1a1a]'
                  }`}>
                    {datasource.source_type === 'dataset' ? (
                      <Upload className={`w-5 h-5 ${selectedDatasourceId === datasource.id ? 'text-brand-orange' : 'text-gray-400'}`} />
                    ) : (
                      <Database className={`w-5 h-5 ${selectedDatasourceId === datasource.id ? 'text-brand-orange' : 'text-gray-400'}`} />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-white truncate">
                        {datasource.name || (datasource.source_type === 'dataset' ? 'Unnamed Dataset' : 'Unknown DB')}
                      </span>
                      {selectedDatasourceId === datasource.id && (
                        <Check className="w-4 h-4 text-brand-orange flex-shrink-0" />
                      )}
                    </div>
                    <div className="text-xs text-gray-400 uppercase">{datasource.type}</div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    )
  }

  // No datasource selected - show selector button
  return (
    <div className={`relative ${className}`} ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="inline-flex items-center gap-2 px-3 py-1.5 bg-[#2a2a2a] border border-[#555555] rounded-full hover:border-brand-orange transition-colors text-sm text-gray-300"
      >
        <Database className="w-3.5 h-3.5 text-gray-400" />
        <span>Select data to start analyzing</span>
        <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
      </button>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute bottom-full left-0 mb-2 bg-[#2a2a2a] border border-[#555555] rounded-lg shadow-2xl z-50 w-96 max-h-80 flex flex-col">
          {/* Header */}
          <div className="p-3 border-b border-[#555555]">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-white">Select Datasource</span>
              <button
                onClick={() => setIsOpen(false)}
                className="text-gray-400 hover:text-white transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <Input
              ref={inputRef}
              type="text"
              placeholder="Search datasources..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="bg-[#1a1a1a] border-[#555555] text-white text-sm focus:border-brand-orange focus:ring-1 focus:ring-brand-orange/50"
            />
          </div>

          {/* Options List */}
          <div className="flex-1 overflow-y-auto custom-scrollbar">
            {/* Add New Connection Option */}
            <button
              onClick={handleAddNew}
              className="w-full px-3 py-2.5 text-left hover:bg-[#333333] transition-colors border-b border-[#444444] flex items-center gap-3"
            >
              <div className="w-9 h-9 rounded-lg bg-brand-orange/10 flex items-center justify-center flex-shrink-0">
                <Plus className="w-5 h-5 text-brand-orange" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-brand-orange">Add New Connection</div>
                <div className="text-xs text-gray-400">Connect a database or upload files</div>
              </div>
            </button>

            {/* Loading State */}
            {isLoading && (
              <div className="p-4 text-center text-sm text-gray-400">
                Loading datasources...
              </div>
            )}

            {/* No Results */}
            {!isLoading && filteredDatasources.length === 0 && (
              <div className="p-4 text-center text-sm text-gray-400">
                {searchQuery ? 'No datasources match your search' : 'No datasources available'}
              </div>
            )}

            {/* Datasource Options */}
            {!isLoading && filteredDatasources.map((datasource) => (
              <button
                key={datasource.id}
                onClick={() => handleSelectDatasource(datasource.id)}
                className="w-full px-3 py-2.5 text-left hover:bg-[#333333] transition-colors flex items-center gap-3"
              >
                <div className="w-9 h-9 rounded-lg bg-[#1a1a1a] flex items-center justify-center flex-shrink-0">
                  {datasource.source_type === 'dataset' ? (
                    <Upload className="w-5 h-5 text-gray-400" />
                  ) : (
                    <Database className="w-5 h-5 text-gray-400" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-white truncate">
                    {datasource.name || (datasource.source_type === 'dataset' ? 'Unnamed Dataset' : 'Unknown DB')}
                  </div>
                  <div className="text-xs text-gray-400 uppercase">{datasource.type}</div>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
