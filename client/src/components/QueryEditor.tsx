"use client"

import { useState, useRef, useEffect, useCallback } from "react"
import { Button } from "./ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select"
import { Play, Square, Maximize2, Minimize2 } from "lucide-react"
import { EditorState } from "@codemirror/state"
import { EditorView, keymap, placeholder as cmPlaceholder } from "@codemirror/view"
import { sql } from "@codemirror/lang-sql"
import { javascript } from "@codemirror/lang-javascript"
import { defaultKeymap } from "@codemirror/commands"
import { HighlightStyle, syntaxHighlighting } from "@codemirror/language"
import { tags } from "@lezer/highlight"

interface QueryListItem {
  id: string
  name: string
  query_type: string
  skill_name: string | null
}

interface QueryEditorProps {
  query: string
  onQueryChange: (query: string) => void
  onExecute: () => void
  onStop?: () => void
  isExecuting: boolean
  datasourceType?: 'pg' | 'mongo' | 'csv' | 'excel' | 'parquet' | 'json' | 'duckdb' | 'mysql' | 'mssql' | 'sqlite'
  savedQueries?: QueryListItem[]
  onLoadSavedQuery?: (query: QueryListItem) => void
  onSaveQuery?: () => void
  onClear?: () => void
  currentQueryId?: string
  currentQueryName?: string
  isExpanded?: boolean
  onExpandChange?: (expanded: boolean) => void
}

// VS Code Dark theme colors
const vsCodeColors = {
  background: "#1e1e1e",
  foreground: "#d4d4d4",
  keyword: "#569cd6",
  string: "#ce9178",
  number: "#b5cea8",
  comment: "#6a9955",
  function: "#dcdcaa",
  variable: "#9cdcfe",
  type: "#4ec9b0",
  operator: "#d4d4d4",
  punctuation: "#d4d4d4",
}

// VS Code Dark syntax highlighting
const vsCodeHighlightStyle = HighlightStyle.define([
  { tag: tags.keyword, color: vsCodeColors.keyword },
  { tag: tags.operatorKeyword, color: vsCodeColors.keyword },
  { tag: tags.modifier, color: vsCodeColors.keyword },
  { tag: tags.color, color: vsCodeColors.keyword },
  { tag: tags.constant(tags.name), color: vsCodeColors.variable },
  { tag: tags.standard(tags.name), color: vsCodeColors.variable },
  { tag: tags.definition(tags.name), color: vsCodeColors.function },
  { tag: tags.function(tags.variableName), color: vsCodeColors.function },
  { tag: tags.propertyName, color: vsCodeColors.variable },
  { tag: tags.typeName, color: vsCodeColors.type },
  { tag: tags.className, color: vsCodeColors.type },
  { tag: tags.labelName, color: vsCodeColors.variable },
  { tag: tags.namespace, color: vsCodeColors.type },
  { tag: tags.macroName, color: vsCodeColors.function },
  { tag: tags.literal, color: vsCodeColors.number },
  { tag: tags.string, color: vsCodeColors.string },
  { tag: tags.special(tags.string), color: vsCodeColors.string },
  { tag: tags.number, color: vsCodeColors.number },
  { tag: tags.bool, color: vsCodeColors.keyword },
  { tag: tags.null, color: vsCodeColors.keyword },
  { tag: tags.atom, color: vsCodeColors.keyword },
  { tag: tags.comment, color: vsCodeColors.comment, fontStyle: "italic" },
  { tag: tags.variableName, color: vsCodeColors.variable },
  { tag: tags.operator, color: vsCodeColors.operator },
  { tag: tags.punctuation, color: vsCodeColors.punctuation },
  { tag: tags.bracket, color: vsCodeColors.punctuation },
  { tag: tags.meta, color: vsCodeColors.foreground },
])

// VS Code Dark editor theme
const vsCodeTheme = EditorView.theme({
  "&": {
    backgroundColor: vsCodeColors.background,
    color: vsCodeColors.foreground,
    fontSize: "14px",
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
    height: "100%",
    maxHeight: "100%",
  },
  "&.cm-editor": {
    height: "100%",
  },
  ".cm-content": {
    caretColor: "#aeafad",
    padding: "16px",
  },
  ".cm-cursor": {
    borderLeftColor: "#aeafad",
  },
  "&.cm-focused .cm-cursor": {
    borderLeftColor: "#aeafad",
  },
  ".cm-gutters": {
    backgroundColor: "#1e1e1e",
    color: "#858585",
    border: "none",
    borderRight: "1px solid #404040",
  },
  ".cm-activeLineGutter": {
    backgroundColor: "#2a2a2a",
  },
  ".cm-activeLine": {
    backgroundColor: "rgba(255, 255, 255, 0.05)",
  },
  "&.cm-focused .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection": {
    backgroundColor: "#264f78",
  },
  ".cm-selectionMatch": {
    backgroundColor: "#add6ff26",
  },
  ".cm-placeholder": {
    color: "#6b6b6b",
  },
  ".cm-scroller": {
    overflow: "auto !important",
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
  },
}, { dark: true })

export function QueryEditor({
  query,
  onQueryChange,
  onExecute,
  onStop,
  isExecuting,
  datasourceType = 'pg',
  savedQueries = [],
  onLoadSavedQuery,
  onSaveQuery,
  onClear,
  currentQueryId,
  currentQueryName,
  isExpanded = false,
  onExpandChange,
}: QueryEditorProps) {
  const [selectedQueryId, setSelectedQueryId] = useState<string | undefined>(undefined)
  const editorRef = useRef<HTMLDivElement>(null)
  const viewRef = useRef<EditorView | null>(null)
  const isUpdatingRef = useRef(false)

  const queryLanguage = datasourceType === 'mongo' ? 'javascript' : 'sql'

  // Sync dropdown selection with currentQueryId prop
  useEffect(() => {
    setSelectedQueryId(currentQueryId)
  }, [currentQueryId])

  const getPlaceholder = useCallback(() => {
    if (datasourceType === 'mongo') {
      return "Enter your MongoDB query here... e.g., db.collection.find({ status: 'active' }).limit(10)"
    }
    if (['duckdb', 'csv', 'excel', 'parquet', 'json'].includes(datasourceType)) {
      return "Enter your DuckDB SQL query here... e.g., SELECT * FROM \"orders\" WHERE amount > 100"
    }
    return "Enter your SQL query here... e.g., SELECT * FROM users LIMIT 10"
  }, [datasourceType])

  const handleQuerySelect = useCallback((value: string) => {
    const selectedQuery = savedQueries.find(q => q.id === value)
    if (selectedQuery && onLoadSavedQuery) {
      onLoadSavedQuery(selectedQuery)
    }
  }, [savedQueries, onLoadSavedQuery])

  // Initialize CodeMirror
  useEffect(() => {
    if (!editorRef.current) return

    const updateListener = EditorView.updateListener.of((update) => {
      if (update.docChanged && !isUpdatingRef.current) {
        const newValue = update.state.doc.toString()
        onQueryChange(newValue)
      }
    })

    // Execute on Cmd/Ctrl+Enter
    const executeKeymap = keymap.of([{
      key: "Mod-Enter",
      run: () => {
        if (!isExecuting && query.trim()) {
          onExecute()
        }
        return true
      }
    }])

    const extensions = [
      queryLanguage === 'javascript' ? javascript() : sql(),
      vsCodeTheme,
      syntaxHighlighting(vsCodeHighlightStyle),
      cmPlaceholder(getPlaceholder()),
      keymap.of(defaultKeymap),
      executeKeymap,
      updateListener,
      EditorView.lineWrapping,
    ]

    const state = EditorState.create({
      doc: query,
      extensions,
    })

    const view = new EditorView({
      state,
      parent: editorRef.current,
    })

    viewRef.current = view

    return () => {
      view.destroy()
      viewRef.current = null
    }
  }, [queryLanguage, getPlaceholder]) // Only recreate when language changes

  // Sync external query changes to editor
  useEffect(() => {
    const view = viewRef.current
    if (!view) return

    const currentContent = view.state.doc.toString()
    if (currentContent !== query) {
      isUpdatingRef.current = true
      view.dispatch({
        changes: {
          from: 0,
          to: currentContent.length,
          insert: query,
        },
      })
      isUpdatingRef.current = false
    }
  }, [query])

  const lineCount = query.split("\n").length
  const charCount = query.length

  return (
    <div className="bg-[#1e1e1e] border-b border-[#404040] p-6 h-full flex flex-col">
      <div className="flex items-center justify-between mb-4 flex-shrink-0">
        <div className="flex items-center gap-4">
          <span className="text-sm font-medium text-white">Query Editor</span>

          {savedQueries.length > 0 && (
            <Select value={selectedQueryId ?? ""} onValueChange={handleQuerySelect}>
              <SelectTrigger className="w-48 bg-[#2d2d2d] border-[#404040] text-white">
                <SelectValue placeholder="Load saved query..." />
              </SelectTrigger>
              <SelectContent className="bg-[#2d2d2d] border-[#404040]">
                {savedQueries.map((q) => (
                  <SelectItem
                    key={q.id}
                    value={q.id}
                    className="text-white hover:bg-[#404040] focus:bg-[#404040]"
                  >
                    <div className="flex items-center gap-2">
                      {q.query_type === 'skill_api' ? (
                        <span className="text-xs bg-purple-600 px-1.5 py-0.5 rounded">
                          {q.skill_name || 'API'}
                        </span>
                      ) : (
                        <span className="text-xs bg-blue-600 px-1.5 py-0.5 rounded">
                          {q.query_type === 'duckdb' ? 'File' : 'SQL'}
                        </span>
                      )}
                      <span>{q.name}</span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>
        <div className="flex gap-2">
          {isExecuting ? (
            <Button
              onClick={onStop}
              size="sm"
              className="bg-red-600 hover:bg-red-700 text-white"
            >
              <Square className="w-4 h-4 mr-2" />
              Stop
            </Button>
          ) : (
            <Button
              onClick={onExecute}
              disabled={!query.trim()}
              size="sm"
              className="bg-[#0e639c] hover:bg-[#1177bb] text-white disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Play className="w-4 h-4 mr-2" />
              Execute
            </Button>
          )}

          {onSaveQuery && (
            <Button
              onClick={onSaveQuery}
              disabled={!query.trim() || isExecuting}
              size="sm"
              variant="outline"
              className="border-[#404040] text-[#cccccc] hover:bg-[#2d2d2d] disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {currentQueryId ? 'Update' : 'Save'}
            </Button>
          )}

          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              onQueryChange("")
              onClear?.()
            }}
            disabled={isExecuting}
            className="border-[#404040] text-[#cccccc] hover:bg-[#2d2d2d] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Clear
          </Button>
        </div>
      </div>

      <div className="relative flex-1 min-h-0">
        <div
          ref={editorRef}
          className="h-full border border-[#404040] rounded-lg overflow-auto focus-within:border-[#007acc] [&_.cm-scroller]:custom-scrollbar"
        />
        <div className="absolute bottom-3 right-3 flex items-center gap-3 bg-[#1e1e1e] px-2 py-0.5 rounded z-10">
          <div className="text-xs text-[#858585] pointer-events-none">
            {lineCount} lines • {charCount} chars
          </div>
          <button
            onClick={() => onExpandChange?.(!isExpanded)}
            className="flex items-center justify-center w-5 h-5 hover:bg-[#2d2d2d] rounded transition-colors text-gray-400 hover:text-white pointer-events-auto"
            title={isExpanded ? 'Collapse editor' : 'Expand editor'}
          >
            {isExpanded ? (
              <Minimize2 className="w-3.5 h-3.5" />
            ) : (
              <Maximize2 className="w-3.5 h-3.5" />
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
