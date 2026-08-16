import { useCallback, useEffect, useState } from 'react'
import {
  ApiService,
  type CollaborationEvent,
  type CollaborationInstallation,
  type CollaborationInstallationHealth,
  type FeishuChat,
  type FeishuDeliveryTarget,
  type FeishuExternalIdentity,
} from '../services/api'
import type { TenantMember } from '@/types/team'

interface UseFeishuIntegrationOptions {
  loadDetails?: boolean
}

export function useFeishuIntegration(enabled = true, options: UseFeishuIntegrationOptions = {}) {
  const { loadDetails = false } = options
  const [installation, setInstallation] = useState<CollaborationInstallation | null>(null)
  const [health, setHealth] = useState<CollaborationInstallationHealth | null>(null)
  const [loading, setLoading] = useState(enabled)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [chats, setChats] = useState<FeishuChat[]>([])
  const [loadingChats, setLoadingChats] = useState(false)
  const [events, setEvents] = useState<CollaborationEvent[]>([])
  const [loadingEvents, setLoadingEvents] = useState(false)
  const [deliveryTargets, setDeliveryTargets] = useState<FeishuDeliveryTarget[]>([])
  const [loadingDeliveryTargets, setLoadingDeliveryTargets] = useState(false)
  const [identities, setIdentities] = useState<FeishuExternalIdentity[]>([])
  const [loadingIdentities, setLoadingIdentities] = useState(false)
  const [teamMembers, setTeamMembers] = useState<TenantMember[]>([])
  const [loadingTeamMembers, setLoadingTeamMembers] = useState(false)

  const refresh = useCallback(async () => {
    if (!enabled) return
    try {
      setLoading(true)
      setError(null)
      const nextInstallation = await ApiService.getFeishuInstallation()
      setInstallation(nextInstallation)
      if (nextInstallation) {
        setHealth(await ApiService.getCollaborationInstallationHealth(nextInstallation.id))
      } else {
        setHealth(null)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load Feishu integration')
      setInstallation(null)
      setHealth(null)
    } finally {
      setLoading(false)
    }
  }, [enabled])

  useEffect(() => {
    refresh()
  }, [refresh])

  const refreshHealth = useCallback(async () => {
    if (!installation) return null
    const next = await ApiService.getCollaborationInstallationHealth(installation.id)
    setHealth(next)
    return next
  }, [installation])

  useEffect(() => {
    if (!enabled || !installation) return
    const interval = window.setInterval(() => {
      void ApiService.getCollaborationInstallationHealth(installation.id)
        .then(setHealth)
        .catch((err) => setError(err instanceof Error ? err.message : 'Failed to refresh Feishu health'))
    }, 5000)
    return () => window.clearInterval(interval)
  }, [enabled, installation])

  const configure = useCallback(async (data: {
    app_id: string
    app_secret?: string | null
    connection_mode: 'websocket'
    default_llm_connection_id?: string | null
    verification_token?: string | null
    encrypt_key?: string | null
  }) => {
    setSaving(true)
    try {
      const next = await ApiService.connectFeishuInstallation(data)
      setInstallation(next)
      setHealth(await ApiService.getCollaborationInstallationHealth(next.id))
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
      setHealth(null)
    } finally {
      setSaving(false)
    }
  }, [installation])

  const loadEvents = useCallback(async () => {
    if (!installation) return []
    setLoadingEvents(true)
    try {
      const next = await ApiService.listCollaborationEvents(installation.id, 10)
      setEvents(next)
      return next
    } finally {
      setLoadingEvents(false)
    }
  }, [installation])

  useEffect(() => {
    if (installation && loadDetails) {
      void loadEvents()
    } else {
      setEvents([])
    }
  }, [installation, loadDetails, loadEvents])

  const loadDeliveryTargets = useCallback(async () => {
    if (!installation) return []
    setLoadingDeliveryTargets(true)
    try {
      const next = await ApiService.listFeishuDeliveryTargets(installation.id)
      setDeliveryTargets(next)
      return next
    } finally {
      setLoadingDeliveryTargets(false)
    }
  }, [installation])

  useEffect(() => {
    if (installation && loadDetails) {
      void loadDeliveryTargets()
    } else {
      setDeliveryTargets([])
    }
  }, [installation, loadDetails, loadDeliveryTargets])

  const loadIdentities = useCallback(async () => {
    if (!installation) return []
    setLoadingIdentities(true)
    try {
      const next = await ApiService.listFeishuExternalIdentities(installation.id)
      setIdentities(next)
      return next
    } finally {
      setLoadingIdentities(false)
    }
  }, [installation])

  useEffect(() => {
    if (installation && loadDetails) {
      void loadIdentities()
    } else {
      setIdentities([])
    }
  }, [installation, loadDetails, loadIdentities])

  const loadTeamMembers = useCallback(async () => {
    setLoadingTeamMembers(true)
    try {
      const next = await ApiService.getTeamMembers()
      setTeamMembers(next)
      return next
    } finally {
      setLoadingTeamMembers(false)
    }
  }, [])

  useEffect(() => {
    if (enabled && installation && loadDetails) {
      void loadTeamMembers()
    } else {
      setTeamMembers([])
    }
  }, [enabled, installation, loadDetails, loadTeamMembers])

  const mapIdentity = useCallback(async (identityId: string, userId: string) => {
    if (!installation) throw new Error('Feishu is not configured')
    const updated = await ApiService.mapFeishuExternalIdentity(installation.id, identityId, userId)
    setIdentities((current) => current.map((identity) => identity.id === identityId ? updated : identity))
    return updated
  }, [installation])

  const unmapIdentity = useCallback(async (identityId: string) => {
    if (!installation) throw new Error('Feishu is not configured')
    const updated = await ApiService.unmapFeishuExternalIdentity(installation.id, identityId)
    setIdentities((current) => current.map((identity) => identity.id === identityId ? updated : identity))
    return updated
  }, [installation])

  const testMessage = useCallback(async (chatId: string, text: string, rootId?: string | null) => {
    if (!installation) throw new Error('Feishu is not configured')
    const result = await ApiService.testFeishuMessage(installation.id, { chat_id: chatId, text, root_id: rootId })
    await loadEvents()
    await loadDeliveryTargets()
    return result
  }, [installation, loadEvents, loadDeliveryTargets])

  const loadChats = useCallback(async () => {
    if (!installation) throw new Error('Feishu is not configured')
    setLoadingChats(true)
    try {
      const next = await ApiService.listFeishuChats(installation.id)
      setChats(next)
      return next
    } finally {
      setLoadingChats(false)
    }
  }, [installation])

  const bindDeliveryTarget = useCallback(async (chatId: string, rootId?: string | null) => {
    if (!installation) throw new Error('Feishu is not configured')
    const selectedChat = chats.find((chat) => chat.chat_id === chatId)
    const normalizedRootId = rootId?.trim() || null
    const targetType = selectedChat?.chat_type === 'p2p' ? 'p2p' : normalizedRootId ? 'topic_group' : 'group'
    const target = await ApiService.bindFeishuDeliveryTarget(installation.id, {
      chat_id: chatId,
      root_id: targetType === 'p2p' ? null : normalizedRootId,
      target_type: targetType,
      display_name: selectedChat?.name || null,
    })
    await loadDeliveryTargets()
    return target
  }, [installation, chats, loadDeliveryTargets])

  const pauseDeliveryTarget = useCallback(async (targetId: string) => {
    if (!installation) throw new Error('Feishu is not configured')
    const target = await ApiService.pauseFeishuDeliveryTarget(installation.id, targetId)
    setDeliveryTargets((current) => current.map((item) => item.id === targetId ? target : item))
    return target
  }, [installation])

  const resumeDeliveryTarget = useCallback(async (targetId: string) => {
    if (!installation) throw new Error('Feishu is not configured')
    const target = await ApiService.resumeFeishuDeliveryTarget(installation.id, targetId)
    setDeliveryTargets((current) => current.map((item) => item.id === targetId ? target : item))
    return target
  }, [installation])

  const unbindDeliveryTarget = useCallback(async (targetId: string) => {
    if (!installation) throw new Error('Feishu is not configured')
    const target = await ApiService.unbindFeishuDeliveryTarget(installation.id, targetId)
    setDeliveryTargets((current) => current.map((item) => item.id === targetId ? target : item))
    return target
  }, [installation])

  const sendOutboundMessage = useCallback(async (targetId: string, text: string, idempotencyKey: string, confirm: boolean) => {
    if (!installation) throw new Error('Feishu is not configured')
    const result = await ApiService.sendFeishuOutboundMessage(installation.id, {
      delivery_target_id: targetId,
      text,
      idempotency_key: idempotencyKey,
      confirm,
    })
    await loadEvents()
    return result
  }, [installation, loadEvents])

  return {
    installation,
    health,
    isConnected: health?.health_status === 'connected',
    loading,
    saving,
    error,
    chats,
    loadingChats,
    events,
    loadingEvents,
    deliveryTargets,
    loadingDeliveryTargets,
    identities,
    loadingIdentities,
    teamMembers,
    loadingTeamMembers,
    refresh,
    refreshHealth,
    configure,
    probe,
    start,
    stop,
    disconnect,
    testMessage,
    loadChats,
    loadEvents,
    loadDeliveryTargets,
    bindDeliveryTarget,
    pauseDeliveryTarget,
    resumeDeliveryTarget,
    unbindDeliveryTarget,
    sendOutboundMessage,
    loadIdentities,
    loadTeamMembers,
    mapIdentity,
    unmapIdentity,
  }
}
