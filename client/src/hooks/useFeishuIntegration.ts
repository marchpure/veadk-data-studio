import { useCallback, useEffect, useState } from 'react'
import { ApiService, type CollaborationInstallation } from '../services/api'

export function useFeishuIntegration(enabled = true) {
  const [installation, setInstallation] = useState<CollaborationInstallation | null>(null)
  const [loading, setLoading] = useState(enabled)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    if (!enabled) return
    try {
      setLoading(true)
      setError(null)
      setInstallation(await ApiService.getFeishuInstallation())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load Feishu integration')
      setInstallation(null)
    } finally {
      setLoading(false)
    }
  }, [enabled])

  useEffect(() => {
    refresh()
  }, [refresh])

  const configure = useCallback(async (data: {
    app_id: string
    app_secret: string
    connection_mode: 'websocket' | 'webhook'
    default_llm_connection_id?: string | null
  }) => {
    setSaving(true)
    try {
      const next = await ApiService.connectFeishuInstallation(data)
      setInstallation(next)
      return next
    } finally {
      setSaving(false)
    }
  }, [])

  const probe = useCallback(async () => {
    if (!installation) throw new Error('Feishu is not configured')
    const result = await ApiService.probeCollaborationInstallation(installation.id)
    await refresh()
    return result
  }, [installation, refresh])

  const start = useCallback(async () => {
    if (!installation) throw new Error('Feishu is not configured')
    const result = await ApiService.startCollaborationInstallation(installation.id)
    await refresh()
    return result
  }, [installation, refresh])

  const stop = useCallback(async () => {
    if (!installation) throw new Error('Feishu is not configured')
    const result = await ApiService.stopCollaborationInstallation(installation.id)
    await refresh()
    return result
  }, [installation, refresh])

  const disconnect = useCallback(async () => {
    if (!installation) return
    setSaving(true)
    try {
      await ApiService.disconnectCollaborationInstallation(installation.id)
      setInstallation(null)
    } finally {
      setSaving(false)
    }
  }, [installation])

  const testMessage = useCallback(async (chatId: string, text: string, rootId?: string | null) => {
    if (!installation) throw new Error('Feishu is not configured')
    return ApiService.testFeishuMessage(installation.id, { chat_id: chatId, text, root_id: rootId })
  }, [installation])

  return {
    installation,
    isConnected: !!installation && installation.is_active,
    loading,
    saving,
    error,
    refresh,
    configure,
    probe,
    start,
    stop,
    disconnect,
    testMessage,
  }
}
