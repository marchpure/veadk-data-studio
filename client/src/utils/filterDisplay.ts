import type { DashboardFilterDefinition } from "../services/api"
import { isEmptyFilterValue } from "./dashboardFilters"

export interface ActiveFilterChip {
  id: string
  filterId: string
  label: string
  displayValue: string
  keysToClear: string[]
}

const FILTER_TYPE_PRIORITY: Record<string, number> = {
  select: 50,
  multiselect: 45,
  date_range: 40,
  number_range: 35,
  text: 30,
}

const toDisplayDate = (value: string): string => {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return value
  }
  const date = new Date(`${value}T00:00:00`)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  })
}

const normalizeScalar = (value: unknown): string => {
  if (value === null || value === undefined) {
    return ""
  }
  if (typeof value === "string") {
    return value.trim()
  }
  return String(value)
}

const getRenderableFilters = (
  filters: DashboardFilterDefinition[],
): DashboardFilterDefinition[] => {
  const byId = new Map<string, DashboardFilterDefinition[]>()
  for (const filter of filters) {
    const group = byId.get(filter.id) ?? []
    group.push(filter)
    byId.set(filter.id, group)
  }

  return Array.from(byId.values()).map((group) => {
    const representative = [...group].sort((a, b) => {
      const priorityA = FILTER_TYPE_PRIORITY[a.filter_type] ?? 0
      const priorityB = FILTER_TYPE_PRIORITY[b.filter_type] ?? 0
      if (priorityA !== priorityB) {
        return priorityB - priorityA
      }

      const optionsA = Array.isArray(a.options) ? a.options.length : 0
      const optionsB = Array.isArray(b.options) ? b.options.length : 0
      return optionsB - optionsA
    })[0]

    const explicitLabel = group.find((candidate) => {
      const label = (candidate.display_label || "").trim()
      return label.length > 0 && label !== candidate.field_name
    })?.display_label

    return {
      ...representative,
      display_label: explicitLabel || representative.display_label || representative.field_name,
    }
  })
}

const buildDateRangeDisplay = (startRaw: unknown, endRaw: unknown): string | null => {
  const start = normalizeScalar(startRaw)
  const end = normalizeScalar(endRaw)
  if (!start && !end) {
    return null
  }
  if (start && end) {
    return `${toDisplayDate(start)} - ${toDisplayDate(end)}`
  }
  if (start) {
    return `From ${toDisplayDate(start)}`
  }
  return `Until ${toDisplayDate(end)}`
}

const buildNumberRangeDisplay = (minRaw: unknown, maxRaw: unknown): string | null => {
  const min = normalizeScalar(minRaw)
  const max = normalizeScalar(maxRaw)
  if (!min && !max) {
    return null
  }
  if (min && max) {
    return `${min} - ${max}`
  }
  if (min) {
    return `Min ${min}`
  }
  return `Max ${max}`
}

const buildMultiSelectDisplay = (rawValue: unknown): string | null => {
  if (!Array.isArray(rawValue)) {
    return null
  }

  const normalizedValues = rawValue
    .map((value) => normalizeScalar(value))
    .filter((value) => value.length > 0)
  if (normalizedValues.length === 0) {
    return null
  }
  if (normalizedValues.length === 1) {
    return normalizedValues[0]
  }
  if (normalizedValues.length <= 3) {
    return normalizedValues.join(", ")
  }
  return `${normalizedValues.length} selected`
}

export const buildActiveFilterChips = (
  filters: DashboardFilterDefinition[],
  values: Record<string, unknown>,
): ActiveFilterChip[] => {
  const renderableFilters = getRenderableFilters(filters)
  const chips: ActiveFilterChip[] = []

  for (const filter of renderableFilters) {
    const label = filter.display_label || filter.field_name || filter.id

    if (filter.filter_type === "date_range") {
      const startKey = `${filter.id}_start`
      const endKey = `${filter.id}_end`
      const displayValue = buildDateRangeDisplay(values[startKey], values[endKey])
      if (!displayValue) {
        continue
      }
      const keysToClear = [startKey, endKey].filter(
        (key) => !isEmptyFilterValue(values[key]),
      )
      chips.push({
        id: `${filter.id}:date`,
        filterId: filter.id,
        label,
        displayValue,
        keysToClear,
      })
      continue
    }

    if (filter.filter_type === "number_range") {
      const minKey = `${filter.id}_min`
      const maxKey = `${filter.id}_max`
      const displayValue = buildNumberRangeDisplay(values[minKey], values[maxKey])
      if (!displayValue) {
        continue
      }
      const keysToClear = [minKey, maxKey].filter(
        (key) => !isEmptyFilterValue(values[key]),
      )
      chips.push({
        id: `${filter.id}:number`,
        filterId: filter.id,
        label,
        displayValue,
        keysToClear,
      })
      continue
    }

    if (filter.filter_type === "multiselect") {
      const displayValue = buildMultiSelectDisplay(values[filter.id])
      if (!displayValue) {
        continue
      }
      chips.push({
        id: `${filter.id}:multi`,
        filterId: filter.id,
        label,
        displayValue,
        keysToClear: [filter.id],
      })
      continue
    }

    const scalarValue = normalizeScalar(values[filter.id])
    if (!scalarValue) {
      continue
    }
    chips.push({
      id: `${filter.id}:value`,
      filterId: filter.id,
      label,
      displayValue: scalarValue,
      keysToClear: [filter.id],
    })
  }

  return chips
}

export const removeActiveFilterChip = (
  values: Record<string, unknown>,
  chip: ActiveFilterChip,
): Record<string, unknown> => {
  const nextValues = { ...values }
  for (const key of chip.keysToClear) {
    delete nextValues[key]
  }
  return nextValues
}
