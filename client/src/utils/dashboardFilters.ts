import type {
  DashboardFilterDefinition,
  QueryWithFilterValuesPayload,
} from "../services/api"

export const parseStoredFilterValues = (
  storageKey: string | null,
  warningContext: string = "dashboard filter values",
): Record<string, unknown> => {
  if (!storageKey || typeof window === "undefined") {
    return {}
  }

  try {
    const raw = window.localStorage.getItem(storageKey)
    if (!raw) {
      return {}
    }

    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === "object" ? parsed : {}
  } catch (error) {
    console.warn(`Failed to parse saved ${warningContext}`, error)
    return {}
  }
}

export const getAllowedFilterKeys = (filters: DashboardFilterDefinition[]): Set<string> => {
  const keys = new Set<string>()

  for (const filter of filters) {
    keys.add(filter.id)
    if (filter.filter_type === "date_range") {
      keys.add(`${filter.id}_start`)
      keys.add(`${filter.id}_end`)
    }
    if (filter.filter_type === "number_range") {
      keys.add(`${filter.id}_min`)
      keys.add(`${filter.id}_max`)
    }
  }

  return keys
}

export const isEmptyFilterValue = (value: unknown): boolean => {
  if (value === null || value === undefined) return true
  if (typeof value === "string") return value.trim() === ""
  if (Array.isArray(value)) return value.length === 0
  return false
}

const getFilterBaseKey = (key: string): string =>
  String(key)
    .replace(/_start$/, "")
    .replace(/_end$/, "")
    .replace(/_min$/, "")
    .replace(/_max$/, "")

export const countActiveFilterValues = (values: Record<string, unknown>): number =>
  Object.values(values).filter((value) => !isEmptyFilterValue(value)).length

export const buildPreflightQueriesWithFilters = (
  filters: DashboardFilterDefinition[],
  values: Record<string, unknown>,
): QueryWithFilterValuesPayload[] => {
  if (!filters.length) {
    return []
  }

  const filterIdToQueryIds = new Map<string, Set<string>>()
  for (const filter of filters) {
    const normalizedQueryId = String(filter.query_id || "").trim()
    const normalizedFilterId = String(filter.id || "").trim()
    if (!normalizedQueryId || !normalizedFilterId) {
      continue
    }

    if (!filterIdToQueryIds.has(normalizedFilterId)) {
      filterIdToQueryIds.set(normalizedFilterId, new Set())
    }
    filterIdToQueryIds.get(normalizedFilterId)?.add(normalizedQueryId)
  }

  const byQuery = new Map<string, Record<string, unknown>>()
  for (const [rawKey, rawValue] of Object.entries(values)) {
    if (isEmptyFilterValue(rawValue)) {
      continue
    }

    const baseKey = getFilterBaseKey(rawKey)
    const queryIds = filterIdToQueryIds.get(baseKey)
    if (!queryIds || queryIds.size === 0) {
      continue
    }

    for (const queryId of queryIds) {
      const scopedValues = byQuery.get(queryId) ?? {}
      scopedValues[rawKey] = rawValue
      byQuery.set(queryId, scopedValues)
    }
  }

  return Array.from(byQuery.entries()).map(([queryId, filterValues]) => ({
    query_id: queryId,
    filters: [],
    filter_values: filterValues,
  }))
}
