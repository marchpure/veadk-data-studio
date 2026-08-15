import type { StateCreator } from 'zustand'
import type { StoreState } from '../useStore'
import type { ConnectionRead, ConnectionType } from '../../services/api'

export interface ConnectionWithDetails extends ConnectionRead {
  connection_obj?: Record<string, any>
  notebook_connection_id?: string
}

export interface ConnectionSlice {
  // State
  connections: ConnectionWithDetails[]
  selectedConnection: ConnectionWithDetails | null
  selectedDbType: ConnectionType | null
  isTestingConnection: boolean
  connectionTestResult: { success: boolean; message: string } | null
  
  // Actions
  setConnections: (connections: ConnectionWithDetails[]) => void
  setSelectedConnection: (connection: ConnectionWithDetails | null) => void
  setSelectedDbType: (datasourceType: ConnectionType | null) => void
  addConnection: (connection: ConnectionWithDetails) => void
  updateConnection: (id: string, connection: Partial<ConnectionWithDetails>) => void
  deleteConnection: (id: string) => void
  setIsTestingConnection: (testing: boolean) => void
  setConnectionTestResult: (result: { success: boolean; message: string } | null) => void
}

export const createConnectionSlice: StateCreator<
  StoreState,
  [],
  [],
  ConnectionSlice
> = (set) => ({
  // Initial state
  connections: [],
  selectedConnection: null,
  selectedDbType: null,
  isTestingConnection: false,
  connectionTestResult: null,
  
  // Actions
  setConnections: (connections) =>
    set(() => ({
      connections,
    })),
    
  setSelectedConnection: (connection) =>
    set(() => ({
      selectedConnection: connection,
    })),
    
  setSelectedDbType: (datasourceType) =>
    set(() => ({
      selectedDbType: datasourceType,
    })),
    
  addConnection: (connection) =>
    set((state) => ({
      connections: [...state.connections, connection],
    })),
    
  updateConnection: (id, connection) =>
    set((state) => ({
      connections: state.connections.map((conn) =>
        conn.id === id ? { ...conn, ...connection } : conn
      ),
      selectedConnection:
        state.selectedConnection?.id === id
          ? { ...state.selectedConnection, ...connection }
          : state.selectedConnection,
    })),
    
  deleteConnection: (id) =>
    set((state) => ({
      connections: state.connections.filter((conn) => conn.id !== id),
      selectedConnection:
        state.selectedConnection?.id === id ? null : state.selectedConnection,
    })),
    
  setIsTestingConnection: (testing) =>
    set(() => ({
      isTestingConnection: testing,
    })),
    
  setConnectionTestResult: (result) =>
    set(() => ({
      connectionTestResult: result,
    })),
})