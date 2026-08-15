"use client"

import { Badge } from "./ui/badge"
import { Database } from "lucide-react"

interface ConnectionConfig {
  type: string
  host: string
  port: string
  database: string
  user: string
  password: string
  connectionString: string
}

interface ConnectionStatusProps {
  connection?: ConnectionConfig | null
  notebookConnection?: any | null
  // New props for multi-connection support
  connections?: any[]
  notebookConnections?: any[]
}

export function ConnectionStatus({ connection, notebookConnection, connections, notebookConnections }: ConnectionStatusProps) {
  // Determine which connections to show
  const connectionsToShow = notebookConnections || connections || []
  const hasMultiple = connectionsToShow.length > 1
  const hasSingle = connectionsToShow.length === 1
  const hasLegacySingle = !connectionsToShow.length && (connection || notebookConnection)

  // Legacy single connection support
  if (hasLegacySingle) {
    const isConnected = !!connection || !!notebookConnection
    return (
      <div className="flex items-center gap-2">
        {isConnected ? (
          <>
            <Database className="w-4 h-4 text-green-400" />
            <Badge variant="outline" className="text-green-400 border-green-400 bg-green-400/10">
              Connected
            </Badge>
            <span className="text-sm text-[#888888]">
              {(() => {
                const type = notebookConnection ? notebookConnection.type : connection?.type;
                const connectionName = notebookConnection?.name || connection?.database || 'Unknown';
                return `${type}://${connectionName}`;
              })()}
            </span>
          </>
        ) : (
          <>
            <Database className="w-4 h-4 text-red-400 opacity-60" />
            <Badge variant="outline" className="text-red-400 border-red-400 bg-red-400/10">
              Not Connected
            </Badge>
          </>
        )}
      </div>
    )
  }

  // Multiple connections or single connection from array
  if (hasMultiple || hasSingle) {
    return (
      <div className="flex items-center gap-2">
        <Database className="w-4 h-4 text-green-400" />
        <Badge variant="outline" className="text-green-400 border-green-400 bg-green-400/10">
          {hasMultiple ? `${connectionsToShow.length} Databases` : 'Connected'}
        </Badge>
        {hasSingle && (
          <span className="text-sm text-[#888888]">
            {(() => {
              const conn = connectionsToShow[0];
              const type = conn.type;
              const connectionName = conn.name || conn.connection_obj?.database || 'Unknown';
              return `${type}://${connectionName}`;
            })()}
          </span>
        )}
        {hasMultiple && (
          <span className="text-sm text-[#888888]">
            {connectionsToShow.map(c => c.type).join(', ')}
          </span>
        )}
      </div>
    )
  }

  // No connections
  return (
    <div className="flex items-center gap-2">
      <Database className="w-4 h-4 text-red-400 opacity-60" />
      <Badge variant="outline" className="text-red-400 border-red-400 bg-red-400/10">
        Not Connected
      </Badge>
    </div>
  )
}