"use client"

import { useState, useEffect } from "react"
import { Clock, Table, Database, AlertCircle, Bug, ChevronDown, ChevronUp, Save, Download, ChevronLeft, ChevronRight } from "lucide-react"
import MarkdownRenderer from "./MarkdownRenderer"
import { Button } from "./ui/button"
import { ApiService, type ErrorDetail } from "../services/api"
import { useStore } from "../stores/useStore"
import { isTauriApp, saveBlobToFile } from "../lib/tauri-api"
import { showToast } from "../utils/toast"

const ROWS_PER_PAGE = 20

interface QueryResult {
  query: string
  results: any[]
  executionTime: string
  rowCount: number
  error?: string
  errorDetail?: ErrorDetail
  rawResult?: string
  totalCount?: number
  returnedCount?: number
  limited?: boolean
  notebookId?: string
  datasourceType?: string
  connectionId?: string
}

interface QueryResultsProps {
  queryResult: QueryResult | null
  onDebugWithAssistant?: (query: string, error: string, errorDetail?: ErrorDetail) => void
  onSaveQuery?: (query: string) => void
}

export function QueryResults({ queryResult, onDebugWithAssistant, onSaveQuery }: QueryResultsProps) {
  const [showErrorDetails, setShowErrorDetails] = useState(false)
  const [isExporting, setIsExporting] = useState(false)
  const [currentPage, setCurrentPage] = useState(1)

  // Reset to page 1 when query results change
  useEffect(() => {
    setCurrentPage(1)
  }, [queryResult?.query, queryResult?.results])

  const exportToCSV = async () => {
    if (!queryResult || !queryResult.notebookId || !queryResult.datasourceType || !queryResult.query) return

    setIsExporting(true)
    try {
      const blob = await ApiService.exportRawQueryCSV(queryResult.notebookId, queryResult.datasourceType, queryResult.query, queryResult.connectionId)
      const fileName = `query_export_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.csv`

      // Check if running in Tauri
      if (isTauriApp()) {
        try {
          // Save file using Tauri and get the path
          const filePath = await saveBlobToFile(blob, fileName)

          // Add to download notification
          useStore.getState().addDownload({
            fileName,
            fileType: 'csv',
            filePath,
            status: 'success',
          })
        } catch (error) {
          console.error('Failed to save file with Tauri:', error)
          showToast.error('Failed to save CSV file')
        }
      } else {
        // Web browser: Use traditional download
        const link = document.createElement('a')
        const url = URL.createObjectURL(blob)
        link.setAttribute('href', url)
        link.setAttribute('download', fileName)
        link.style.visibility = 'hidden'
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
        URL.revokeObjectURL(url)

        // Add to download notification (without filePath for web)
        useStore.getState().addDownload({
          fileName,
          fileType: 'csv',
          status: 'success',
        })
      }
    } catch (error) {
      console.error('Export failed:', error)
      showToast.error('Failed to export CSV')
    } finally {
      setIsExporting(false)
    }
  }
  
  const renderTable = (data: any[]) => {
    if (!data || data.length === 0) {
      return <div className="flex items-center justify-center text-[#888888]">No data found</div>
    }

    const columns = Array.from(new Set(data.flatMap((row) => Object.keys(row))))

    const renderCellValue = (value: any) => {
      if (value === null || value === undefined) return ""
      if (typeof value === "object") return JSON.stringify(value)
      return String(value)
    }

    // Calculate pagination
    const totalPages = Math.ceil(data.length / ROWS_PER_PAGE)
    const startIndex = (currentPage - 1) * ROWS_PER_PAGE
    const endIndex = startIndex + ROWS_PER_PAGE
    const paginatedData = data.slice(startIndex, endIndex)

    const handlePrevPage = () => {
      setCurrentPage((prev) => Math.max(1, prev - 1))
    }

    const handleNextPage = () => {
      setCurrentPage((prev) => Math.min(totalPages, prev + 1))
    }

    return (
      <div className="flex flex-col h-full">
        <div className="flex-1 overflow-auto custom-scrollbar">
          <table className="min-w-full text-sm table-auto">
            <thead className="bg-[#333333] border-b border-[#404040] sticky top-0 z-10">
              <tr>
                {columns.map((col) => (
                  <th
                    key={col}
                    className="text-left p-3 font-medium text-white border-r border-[#404040] last:border-r-0"
                  >
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {paginatedData.map((row, idx) => (
                <tr key={startIndex + idx} className="border-b border-[#404040] hover:bg-[#333333]/50">
                  {columns.map((col) => (
                    <td
                      key={col}
                      className="p-3 border-r border-[#404040] last:border-r-0 font-mono text-xs text-[#cccccc] whitespace-pre-wrap break-words"
                    >
                      {renderCellValue(row[col])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination Controls */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-[#404040] bg-[#2a2a2a]">
            <div className="text-sm text-[#cccccc]">
              Showing {startIndex + 1} to {Math.min(endIndex, data.length)} of {data.length} rows
            </div>
            <div className="flex items-center gap-2">
              <Button
                onClick={handlePrevPage}
                disabled={currentPage === 1}
                className="bg-[#333333] hover:bg-[#404040] disabled:opacity-50 disabled:cursor-not-allowed"
                size="sm"
              >
                <ChevronLeft className="w-4 h-4" />
              </Button>
              <span className="text-sm text-[#cccccc] px-3">
                Page {currentPage} of {totalPages}
              </span>
              <Button
                onClick={handleNextPage}
                disabled={currentPage === totalPages}
                className="bg-[#333333] hover:bg-[#404040] disabled:opacity-50 disabled:cursor-not-allowed"
                size="sm"
              >
                <ChevronRight className="w-4 h-4" />
              </Button>
            </div>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full bg-[#1a1a1a]">
      {/* Results Header */}
      {queryResult && (
        <div className="border-b border-[#404040] px-6 py-3 bg-[#2a2a2a] flex-shrink-0">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-6 text-sm text-[#cccccc]">
              <span className="flex items-center gap-2">
                <Clock className="w-4 h-4" />
                {queryResult.executionTime}
              </span>
              <span className="flex items-center gap-2">
                <Table className="w-4 h-4" />
                {queryResult.totalCount && queryResult.returnedCount ? 
                  `${queryResult.returnedCount} of ${queryResult.totalCount} rows` + (queryResult.limited ? ' (limited)' : '') :
                  `${queryResult.rowCount} rows`
                }
              </span>
              <span
                className={`flex items-center gap-2 ${queryResult.error ? "text-red-400" : "text-green-400"}`}
              >
                <div
                  className={`w-2 h-2 rounded-full ${queryResult.error ? "bg-red-400" : "bg-green-400"}`}
                />
                {queryResult.error ? "Error" : "Success"}
              </span>
            </div>
            {!queryResult.error && (
              <div className="flex items-center gap-2">
                {((queryResult.results && queryResult.results.length > 0) || (queryResult.totalCount && queryResult.totalCount > 0)) && (
                  <Button
                    variant="brand-primary"
                    onClick={exportToCSV}
                    disabled={isExporting || !queryResult.notebookId || !queryResult.datasourceType}
                    size="sm"
                  >
                    <Download className="w-4 h-4 mr-2" />
                    {isExporting ? 'Exporting...' : 'Download CSV'}
                  </Button>
                )}
                {onSaveQuery && (
                  <Button
                    onClick={() => onSaveQuery(queryResult.query)}
                    className="bg-green-600 hover:bg-green-700"
                    size="sm"
                  >
                    <Save className="w-4 h-4 mr-2" />
                    Save Query
                  </Button>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Results Content - Scrollable Section */}
      <div className="flex-grow overflow-auto custom-scrollbar min-h-0">
        {queryResult ? (
          queryResult.error ? (
            <div className="p-8">
              <div className="max-w-4xl mx-auto">
                {/* Error Header */}
                <div className="flex items-start justify-between mb-6">
                  <div className="flex items-center gap-3">
                    <div className={`w-10 h-10 rounded-full flex items-center justify-center ${
                      queryResult.errorDetail?.severity === 'critical' ? 'bg-red-900/30' :
                      queryResult.errorDetail?.severity === 'warning' ? 'bg-yellow-900/30' :
                      'bg-red-900/20'
                    }`}>
                      <AlertCircle className={`w-5 h-5 ${
                        queryResult.errorDetail?.severity === 'critical' ? 'text-red-500' :
                        queryResult.errorDetail?.severity === 'warning' ? 'text-yellow-500' :
                        'text-red-400'
                      }`} />
                    </div>
                    <div>
                      <h3 className="text-lg font-medium text-red-400">Query Error</h3>
                      {queryResult.errorDetail && (
                        <p className="text-sm text-[#888888] mt-1">
                          Category: <span className="text-white">{queryResult.errorDetail.category}</span> • 
                          Severity: <span className="text-white">{queryResult.errorDetail.severity}</span>
                          {queryResult.errorDetail.error_code && (
                            <> • Code: <span className="text-white">{queryResult.errorDetail.error_code}</span></>
                          )}
                        </p>
                      )}
                    </div>
                  </div>
                  {onDebugWithAssistant && (
                    <Button
                      variant="brand-primary"
                      onClick={() => onDebugWithAssistant(
                        queryResult.query,
                        queryResult.error || 'Query failed',
                        queryResult.errorDetail
                      )}
                    >
                      <Bug className="w-4 h-4 mr-2" />
                      Debug with Assistant
                    </Button>
                  )}
                </div>

                {/* Error Message */}
                <div className="bg-[#2a2a2a] border border-red-900/30 rounded-lg p-4 mb-4">
                  <p className="text-sm text-red-300">
                    {queryResult.errorDetail?.message || queryResult.error}
                  </p>
                </div>

                {/* Original Query */}
                {queryResult.errorDetail?.original_query && (
                  <div className="mb-4">
                    <h4 className="text-sm font-medium text-[#cccccc] mb-2">Original Query:</h4>
                    <div className="bg-[#2a2a2a] border border-[#404040] rounded-lg p-3">
                      <code className="text-xs text-[#888888] font-mono">
                        {queryResult.errorDetail.original_query}
                      </code>
                    </div>
                  </div>
                )}

                {/* Suggestions */}
                {queryResult.errorDetail?.suggestions && queryResult.errorDetail.suggestions.length > 0 && (
                  <div className="mb-4">
                    <h4 className="text-sm font-medium text-[#cccccc] mb-2">Suggestions:</h4>
                    <ul className="space-y-2">
                      {queryResult.errorDetail.suggestions.map((suggestion, idx) => (
                        <li key={idx} className="flex items-start gap-2">
                          <span className="text-green-400 mt-0.5">•</span>
                          <span className="text-sm text-[#aaaaaa]">{suggestion}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Additional Context (Collapsible) */}
                {queryResult.errorDetail?.context && Object.keys(queryResult.errorDetail.context).length > 0 && (
                  <div className="mb-4">
                    <button
                      onClick={() => setShowErrorDetails(!showErrorDetails)}
                      className="flex items-center gap-2 text-sm font-medium text-[#cccccc] hover:text-white transition-colors"
                    >
                      {showErrorDetails ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                      Additional Details
                    </button>
                    {showErrorDetails && (
                      <div className="mt-2 bg-[#2a2a2a] border border-[#404040] rounded-lg p-3">
                        <pre className="text-xs text-[#888888] font-mono overflow-x-auto custom-scrollbar">
                          {JSON.stringify(queryResult.errorDetail.context, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>
                )}

                {/* Stack Trace (Collapsible) */}
                {queryResult.errorDetail?.stack_trace && (
                  <div>
                    <button
                      onClick={() => setShowErrorDetails(!showErrorDetails)}
                      className="flex items-center gap-2 text-sm font-medium text-[#cccccc] hover:text-white transition-colors"
                    >
                      {showErrorDetails ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                      Stack Trace
                    </button>
                    {showErrorDetails && (
                      <div className="mt-2 bg-[#2a2a2a] border border-[#404040] rounded-lg p-3">
                        <pre className="text-xs text-[#888888] font-mono overflow-x-auto custom-scrollbar">
                          {queryResult.errorDetail.stack_trace}
                        </pre>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          ) : queryResult.rawResult ? (
            <div className="p-6">
              <MarkdownRenderer content={queryResult.rawResult} />
            </div>
          ) : (
            <div className="p-6">
              {renderTable(queryResult.results)}
            </div>
          )
        ) : (
          <div className="flex items-center justify-center h-full text-[#888888] p-8">
            <div className="text-center">
              <div className="w-16 h-16 bg-[#333333] rounded-full flex items-center justify-center mx-auto mb-4">
                <Database className="w-8 h-8" />
              </div>
              <p className="mb-2 text-lg font-medium text-[#cccccc]">Ready to Execute</p>
              <p className="text-sm mb-4">Ask the assistant to generate a query or write your own</p>
              <div className="text-xs text-[#888888]">Try: "Show all users" or "Get recent orders"</div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
