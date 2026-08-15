import { useMutation } from '@tanstack/react-query'
import { ApiService } from '../services/api'
import { showToast } from '../utils/toast'

export const useSaveQuery = () => {
  return useMutation({
    mutationFn: ({ query, connectionId, notebookId, datasourceType, name }: {
      query: string
      connectionId: string
      notebookId: string
      datasourceType: string
      name: string
    }) => ApiService.executeAndSaveQuery(query, connectionId, notebookId, datasourceType, name),
    onSuccess: (response) => {
      showToast.success('Query saved successfully')
    },
    onError: (error) => {
      console.error('Error saving query:', error)
      showToast.error('Failed to save query')
    },
  })
}