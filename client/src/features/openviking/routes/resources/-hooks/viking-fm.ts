import { useMemo, useState, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import {
  fetchFileContent,
  fetchFsList,
  fetchFsStat,
  fetchFsTree,
} from '../-lib/api'
import { useOpenVikingIdentityScopeKey } from '../../../hooks/use-app-connection'
import { profileScopedQueryKey } from '../../../profile-selection'
import {
  detectFileType,
  normalizeDirUri,
  shouldAutoRead,
} from '../-lib/normalize'
import type {
  VikingFsEntry,
  VikingListQueryOptions,
  VikingPreviewPolicy,
  VikingPreviewResult,
  VikingReadQueryOptions,
  VikingTreeQueryOptions,
} from '../-types/viking-fm'

const DEFAULT_QUERY_OPTS = { staleTime: 30_000 }

export function useVikingFsList(
  uri: string,
  options: VikingListQueryOptions = {},
  enabled = true,
) {
  const identityScopeKey = useOpenVikingIdentityScopeKey()
  return useQuery({
    queryKey: profileScopedQueryKey(
      'viking-fs-ls',
      identityScopeKey,
      normalizeDirUri(uri),
      options,
    ),
    queryFn: () => fetchFsList(normalizeDirUri(uri), options),
    enabled,
    ...DEFAULT_QUERY_OPTS,
  })
}

export function useVikingFsTree(
  rootUri: string,
  options: VikingTreeQueryOptions = {},
  enabled = true,
) {
  const identityScopeKey = useOpenVikingIdentityScopeKey()
  return useQuery({
    queryKey: profileScopedQueryKey(
      'viking-fs-tree',
      identityScopeKey,
      normalizeDirUri(rootUri),
      options,
    ),
    queryFn: () => fetchFsTree(normalizeDirUri(rootUri), options),
    enabled,
    ...DEFAULT_QUERY_OPTS,
  })
}

export function useVikingFilePreview(
  entry: VikingFsEntry | null,
  policy: VikingPreviewPolicy = {},
  readOptions: VikingReadQueryOptions = {},
) {
  const identityScopeKey = useOpenVikingIdentityScopeKey()
  const maxAutoReadBytes = policy.maxAutoReadBytes ?? 2 * 1024 * 1024
  const defaultReadLimit = policy.defaultReadLimit ?? 500
  const requireKnownSize = policy.requireKnownSize ?? false
  const effectiveReadOptions = useMemo(
    () => ({
      offset: readOptions.offset ?? 0,
      limit: readOptions.limit ?? defaultReadLimit,
      raw: readOptions.raw,
    }),
    [readOptions.offset, readOptions.limit, readOptions.raw, defaultReadLimit],
  )

  const autoRead = useMemo(
    () =>
      entry
        ? shouldAutoRead(entry, maxAutoReadBytes, requireKnownSize)
        : { shouldRead: false as const },
    [entry, maxAutoReadBytes, requireKnownSize],
  )

  const readQuery = useQuery({
    enabled: Boolean(entry) && autoRead.shouldRead,
    queryKey: profileScopedQueryKey(
      'viking-file-read',
      identityScopeKey,
      entry?.uri,
      entry?.modTime || '',
      effectiveReadOptions,
    ),
    queryFn: () => fetchFileContent(entry!.uri, effectiveReadOptions),
  })

  const preview = useMemo<VikingPreviewResult | null>(() => {
    if (!entry) {
      return null
    }

    const fileType = detectFileType(entry.uri)

    if (!autoRead.shouldRead) {
      return {
        entry,
        fileType,
        shouldAutoRead: false,
        reason: autoRead.reason,
        content: readQuery.data?.content || '',
        offset: readQuery.data?.offset ?? effectiveReadOptions.offset,
        limit: readQuery.data?.limit ?? effectiveReadOptions.limit,
        truncated: readQuery.data?.truncated ?? true,
      }
    }

    return {
      entry,
      fileType,
      shouldAutoRead: true,
      content: readQuery.data?.content || '',
      offset: readQuery.data?.offset ?? effectiveReadOptions.offset,
      limit: readQuery.data?.limit ?? effectiveReadOptions.limit,
      truncated: readQuery.data?.truncated ?? true,
    }
  }, [entry, autoRead, readQuery.data, effectiveReadOptions])

  return {
    ...readQuery,
    preview,
    isContentLoaded: readQuery.data !== undefined,
    canLoadContent:
      Boolean(entry) && !autoRead.shouldRead && autoRead.reason !== 'binary',
  }
}

export function useInvalidateVikingFs() {
  const identityScopeKey = useOpenVikingIdentityScopeKey()
  const queryClient = useQueryClient()

  return {
    invalidateAll: () =>
      queryClient.invalidateQueries({ queryKey: ['viking-fs'] }),
    invalidateList: (uri?: string) =>
      queryClient.invalidateQueries({
        queryKey: uri
          ? profileScopedQueryKey(
              'viking-fs-ls',
              identityScopeKey,
              normalizeDirUri(uri),
            )
          : profileScopedQueryKey('viking-fs-ls', identityScopeKey),
      }),
    invalidateTree: (uri?: string) =>
      queryClient.invalidateQueries({
        queryKey: uri
          ? profileScopedQueryKey(
              'viking-fs-tree',
              identityScopeKey,
              normalizeDirUri(uri),
            )
          : profileScopedQueryKey('viking-fs-tree', identityScopeKey),
      }),
    invalidatePreview: (uri?: string) =>
      queryClient.invalidateQueries({
        queryKey: uri
          ? profileScopedQueryKey('viking-file-read', identityScopeKey, uri)
          : profileScopedQueryKey('viking-file-read', identityScopeKey),
      }),
  }
}

export function useDebouncedValue<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}

export function useVikingFsStat(uri: string | undefined) {
  const identityScopeKey = useOpenVikingIdentityScopeKey()
  return useQuery<VikingFsEntry>({
    queryKey: profileScopedQueryKey('viking-fs-stat', identityScopeKey, uri),
    queryFn: () => fetchFsStat(uri!),
    enabled: Boolean(uri),
    staleTime: 60_000,
  })
}
