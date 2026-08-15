import React, { useEffect, useMemo, useState } from "react"
import { Filter, PanelLeft, PanelLeftClose, X } from "lucide-react"

import type { DashboardFilterDefinition } from "../services/api"
import { cn } from "../lib/utils"
import { isEmptyFilterValue } from "../utils/dashboardFilters"
import { DashboardFilterBar } from "./DashboardFilterBar"
import { Badge } from "./ui/badge"
import { Button } from "./ui/button"

interface DashboardFilterSidebarProps {
  filters: DashboardFilterDefinition[]
  values: Record<string, unknown>
  onChange: (nextValues: Record<string, unknown>) => void
  storageKey?: string
  className?: string
  actions?: React.ReactNode
  diagnosticsPanel?: React.ReactNode
  defaultCollapsed?: boolean
}

const getAppliedFilterCount = (
  filters: DashboardFilterDefinition[],
  values: Record<string, unknown>,
): number => {
  const uniqueIds = new Set<string>()
  for (const filter of filters) {
    uniqueIds.add(filter.id)
  }

  let count = 0
  for (const id of uniqueIds) {
    const keys = [id, `${id}_start`, `${id}_end`, `${id}_min`, `${id}_max`]
    if (keys.some((key) => !isEmptyFilterValue(values[key]))) {
      count += 1
    }
  }
  return count
}

export function DashboardFilterSidebar({
  filters,
  values,
  onChange,
  storageKey,
  className,
  actions,
  diagnosticsPanel,
  defaultCollapsed = true,
}: DashboardFilterSidebarProps) {
  const collapseStorageKey = storageKey ? `${storageKey}:sidebar-collapsed` : null
  const [isCollapsed, setIsCollapsed] = useState<boolean>(() => {
    if (!collapseStorageKey || typeof window === "undefined") {
      return defaultCollapsed
    }
    const persisted = window.localStorage.getItem(collapseStorageKey)
    if (persisted === null) {
      return defaultCollapsed
    }
    return persisted === "1"
  })
  const [isMobileDrawerOpen, setIsMobileDrawerOpen] = useState(false)

  useEffect(() => {
    if (!collapseStorageKey || typeof window === "undefined") {
      setIsCollapsed(defaultCollapsed)
      return
    }
    const persisted = window.localStorage.getItem(collapseStorageKey)
    if (persisted === null) {
      setIsCollapsed(defaultCollapsed)
      return
    }
    setIsCollapsed(persisted === "1")
  }, [collapseStorageKey, defaultCollapsed])

  useEffect(() => {
    if (!collapseStorageKey || typeof window === "undefined") {
      return
    }
    window.localStorage.setItem(collapseStorageKey, isCollapsed ? "1" : "0")
  }, [collapseStorageKey, isCollapsed])

  useEffect(() => {
    if (typeof document === "undefined") {
      return
    }
    if (!isMobileDrawerOpen) {
      return
    }

    const { body } = document
    const originalOverflow = body.style.overflow
    body.style.overflow = "hidden"

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsMobileDrawerOpen(false)
      }
    }

    window.addEventListener("keydown", handleEscape)
    return () => {
      body.style.overflow = originalOverflow
      window.removeEventListener("keydown", handleEscape)
    }
  }, [isMobileDrawerOpen])

  const appliedCount = useMemo(
    () => getAppliedFilterCount(filters, values),
    [filters, values],
  )
  const hasActiveFilters = appliedCount > 0

  const clearAll = () => {
    onChange({})
  }

  const filterContent = (
    <>
      <DashboardFilterBar
        filters={filters}
        values={values}
        onChange={onChange}
        variant="sidebar"
        showHeader={false}
        collapsible={false}
      />
      <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
        {actions}
        <Button
          type="button"
          onClick={clearAll}
          disabled={appliedCount === 0}
          className="h-8 border border-red-400/70 bg-red-500/80 px-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-white hover:bg-red-500 disabled:cursor-not-allowed disabled:border-red-400/20 disabled:bg-red-500/20 disabled:text-red-100/60"
        >
          Clear All Filters
        </Button>
      </div>
      {diagnosticsPanel && <div className="mt-2.5">{diagnosticsPanel}</div>}
    </>
  )

  if (!filters.length) {
    return null
  }

  return (
    <div className={cn("relative h-full min-h-0", className)}>
      <div className="pointer-events-none absolute inset-0 hidden lg:block" />

      <div className="absolute left-3 top-3 z-40 lg:hidden">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setIsMobileDrawerOpen(true)}
          className={cn(
            "h-8 px-3 text-xs shadow-lg backdrop-blur",
            hasActiveFilters
              ? "border-brand-orange/70 bg-brand-orange/20 text-brand-orange"
              : "border-[#39414c] bg-[#10141a]/95 text-gray-200",
          )}
        >
          <Filter className="mr-1.5 h-3.5 w-3.5 text-brand-orange" />
          Filters
          <Badge
            className={cn(
              "ml-1.5 px-1.5 py-0 text-[9px] font-semibold uppercase tracking-[0.08em]",
              hasActiveFilters
                ? "border border-brand-orange/60 bg-brand-orange/30 text-brand-orange"
                : "border border-[#3b414a] bg-[#1a1f26] text-gray-300",
            )}
          >
            {appliedCount}
          </Badge>
        </Button>
      </div>

      <aside
        className={cn(
          "hidden h-full min-h-0 border-r border-[#2a3240] bg-[#0d1117] lg:flex lg:flex-col",
          "transition-[width] duration-200 ease-out",
          isCollapsed ? "w-[56px]" : "w-[340px] xl:w-[360px]",
        )}
      >
        <div className="border-b border-[#29313d] px-2 py-2.5">
          <div className={cn("flex items-center", isCollapsed ? "justify-center" : "justify-between gap-2")}>
            {!isCollapsed && (
              <div className="inline-flex items-center gap-2 text-xs text-gray-200">
                <Filter className="h-3.5 w-3.5 text-brand-orange" />
                <span className="font-medium tracking-wide">Filters</span>
              </div>
            )}
            <button
              type="button"
              onClick={() => setIsCollapsed((prev) => !prev)}
              className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-[#3b414b] bg-[#13171c] text-gray-300 transition-colors hover:border-brand-orange/50 hover:text-brand-orange"
              aria-label={isCollapsed ? "Expand filters" : "Collapse filters"}
            >
              {isCollapsed ? (
                <PanelLeft className="h-3.5 w-3.5" />
              ) : (
                <PanelLeftClose className="h-3.5 w-3.5" />
              )}
            </button>
          </div>

          {!isCollapsed && (
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <Badge
                className={cn(
                  "px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em]",
                  hasActiveFilters
                    ? "border border-brand-orange/60 bg-brand-orange/25 text-brand-orange"
                    : "border border-[#39414c] bg-[#181c22] text-gray-300",
                )}
              >
                {appliedCount} active
              </Badge>
              <Badge className="border border-brand-orange/30 bg-brand-orange/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-brand-orange">
                Auto apply
              </Badge>
            </div>
          )}
        </div>

        {isCollapsed ? (
          <div className="flex flex-1 justify-center px-1.5 py-3">
            <button
              type="button"
              onClick={() => setIsCollapsed(false)}
              className={cn(
                "group inline-flex h-[180px] w-10 flex-col items-center justify-between rounded-xl border px-1.5 py-2 shadow-[0_8px_16px_rgba(0,0,0,0.35)] transition-colors",
                hasActiveFilters
                  ? "border-brand-orange/80 bg-brand-orange/25 text-brand-orange hover:bg-brand-orange/35"
                  : "border-[#3a424d] bg-[#141a22] text-gray-300 hover:border-brand-orange/45 hover:text-brand-orange",
              )}
              aria-label="Open filters sidebar"
            >
              <Filter className="h-4 w-4" />
              <span className="[writing-mode:vertical-rl] rotate-180 text-[10px] font-semibold uppercase tracking-[0.16em]">
                Filters
              </span>
              <span
                className={cn(
                  "inline-flex min-w-[20px] items-center justify-center rounded-full border px-1 py-0 text-[9px] font-semibold",
                  hasActiveFilters
                    ? "border-brand-orange/70 bg-brand-orange text-[#1a1207]"
                    : "border-[#4a5360] bg-[#1d2530] text-gray-200",
                )}
              >
                {appliedCount}
              </span>
            </button>
          </div>
        ) : (
          <div className="custom-scrollbar flex-1 min-h-0 overflow-y-auto px-2.5 py-2.5">
            {filterContent}
          </div>
        )}
      </aside>

      {isMobileDrawerOpen && (
        <div className="fixed inset-0 z-[80] lg:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-black/60 backdrop-blur-[1px]"
            onClick={() => setIsMobileDrawerOpen(false)}
            aria-label="Close filters"
          />
          <aside className="absolute left-0 top-0 h-full w-[min(90vw,360px)] border-r border-[#2a3240] bg-[#0d1117] shadow-2xl">
            <div className="flex items-center justify-between border-b border-[#29313d] px-3 py-2.5">
              <div className="inline-flex items-center gap-2 text-xs text-gray-200">
                <Filter className="h-3.5 w-3.5 text-brand-orange" />
                <span className="font-medium tracking-wide">Filters</span>
              </div>
              <button
                type="button"
                onClick={() => setIsMobileDrawerOpen(false)}
                className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-[#3b414b] bg-[#13171c] text-gray-300 transition-colors hover:border-brand-orange/50 hover:text-brand-orange"
                aria-label="Close filters"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
            <div className="custom-scrollbar h-[calc(100%-48px)] overflow-y-auto px-2.5 py-2.5">
              {filterContent}
            </div>
          </aside>
        </div>
      )}
    </div>
  )
}
