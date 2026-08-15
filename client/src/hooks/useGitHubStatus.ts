import { useQuery } from '@tanstack/react-query'
import { GitHubService } from '../services/github'
import { useStore } from '../stores/useStore'

export function useGitHubStatus() {
  const setGitHubConnected = useStore(state => state.setGitHubConnected)

  return useQuery({
    queryKey: ['github-status'],
    queryFn: async () => {
      const status = await GitHubService.getStatus()
      setGitHubConnected(status.connected, status.username)
      return status
    },
    staleTime: 5 * 60 * 1000,
    gcTime: 10 * 60 * 1000,
  })
}
