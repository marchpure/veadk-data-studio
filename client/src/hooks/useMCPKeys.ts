import { useQuery } from '@tanstack/react-query'
import { ApiService } from '@/services/api'

export interface MCPKey {
  id: string
  name: string
  key_prefix: string
  is_active: boolean
  last_used_at: string | null
  created_at: string
}

export function useMCPKeys() {
  return useQuery({
    queryKey: ['mcp-keys'],
    queryFn: async () => {
      const response = await ApiService.listMCPKeys()
      return response.data as MCPKey[]
    },
    staleTime: 30000, // 30 seconds
  })
}
