import { Table } from 'lucide-react'
import { Badge } from './ui/badge'
import MarkdownRenderer from './MarkdownRenderer'

interface MessageRendererProps {
  content: string
  type: 'user' | 'assistant'
  onCodeInject?: (data: { query: string; connectionId?: string }) => void
  tableNames?: string[]
}

interface TableMention {
  name: string
  start: number
  end: number
}

export function MessageRenderer({ content, type, onCodeInject, tableNames = [] }: MessageRendererProps) {
  // Find all @mentions in the content (including @table:column)
  const findTableMentions = (text: string): TableMention[] => {
    const mentions: TableMention[] = []
    const tableSet = new Set(tableNames)
    
    // Regular expression to find @tableName or @tableName:columnName patterns
    const mentionRegex = /@(\w+)(?::(\w+))?/g
    let match
    
    while ((match = mentionRegex.exec(text)) !== null) {
      const tableName = match[1]
      const columnName = match[2]
      
      // For @table:column, we still check if the table exists
      // For @table, we check if the table exists
      if (tableSet.has(tableName)) {
        mentions.push({
          name: columnName ? `${tableName}:${columnName}` : tableName,
          start: match.index,
          end: match.index + match[0].length
        })
      }
    }
    
    return mentions
  }

  // Render content with table mentions highlighted
  const renderWithMentions = (text: string): React.ReactNode => {
    const mentions = findTableMentions(text)
    
    if (mentions.length === 0) {
      return text
    }
    
    const parts: React.ReactNode[] = []
    let lastIndex = 0
    
    mentions.forEach((mention, index) => {
      // Add text before mention
      if (mention.start > lastIndex) {
        parts.push(text.slice(lastIndex, mention.start))
      }
      
      // Add mention as badge
      parts.push(
        <Badge 
          key={`mention-${index}-${mention.name}`}
          variant="outline" 
          className="inline-flex items-center gap-1 mx-1 bg-[#404040] text-white border-[#555555] hover:bg-[#4a4a4a] transition-colors"
        >
          <Table className="w-3 h-3" />
          {mention.name}
        </Badge>
      )
      
      lastIndex = mention.end
    })
    
    // Add remaining text
    if (lastIndex < text.length) {
      parts.push(text.slice(lastIndex))
    }
    
    return parts
  }

  if (type === 'user') {
    // For user messages, render with table mentions highlighted
    return (
      <div className="p-4 rounded-2xl text-sm bg-brand-orange text-white rounded-br-md">
        <div className="whitespace-pre-line">
          {renderWithMentions(content)}
        </div>
      </div>
    )
  } else {
    // For assistant messages, use MarkdownRenderer but also check for mentions
    return (
      <MarkdownRenderer 
        content={content} 
        onCodeInject={onCodeInject}
        tableNames={tableNames}
      />
    )
  }
}