import React, { useMemo, useState } from "react"
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Loader2,
  ShieldCheck,
} from "lucide-react"

import type { BatchFilterPreflightResponse } from "../services/api"
import { cn } from "../lib/utils"
import { Badge } from "./ui/badge"

interface FilterPreflightPanelProps {
  loading: boolean
  response: BatchFilterPreflightResponse | null
  error: string | null
  activeFilterCount: number
  className?: string
}

export function FilterPreflightPanel({
  loading,
  response,
  error,
  activeFilterCount,
  className,
}: FilterPreflightPanelProps) {
  const [expanded, setExpanded] = useState(false)

  const hasData = Boolean(response && Array.isArray(response.data) && response.data.length > 0)
  const successfulCount = response?.successful_queries ?? 0
  const totalCount = response?.total_queries ?? 0
  const failedCount = response?.failed_queries ?? 0

  const summaryLabel = useMemo(() => {
    if (loading) return "Validating filters"
    if (error) return "Preflight failed"
    if (!hasData) {
      if (activeFilterCount > 0) return "Waiting for diagnostics"
      return "No active filters"
    }
    return `${successfulCount}/${totalCount} valid`
  }, [activeFilterCount, error, hasData, loading, successfulCount, totalCount])

  const showPanel = loading || Boolean(error) || hasData || activeFilterCount > 0
  if (!showPanel) {
    return null
  }

  const showWarningTone = Boolean(error) || failedCount > 0

  return (
    <div
      className={cn(
        "relative border-b border-[#2b2f35] bg-[#0d1014]",
        className,
      )}
    >
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(251,146,60,0.12),transparent_60%)]" />
      <div className="relative px-4 py-2.5">
        <div className="flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={() => setExpanded((prev) => !prev)}
            className="inline-flex items-center gap-2 rounded-md px-1.5 py-1 text-xs text-gray-200 transition-colors hover:bg-[#171d24] hover:text-white"
          >
            {expanded ? (
              <ChevronDown className="h-3.5 w-3.5" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5" />
            )}
            {loading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin text-brand-orange" />
            ) : showWarningTone ? (
              <AlertTriangle className="h-3.5 w-3.5 text-amber-300" />
            ) : (
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-300" />
            )}
            <span className="font-medium tracking-wide">Filter Preflight</span>
          </button>

          <div className="flex flex-wrap items-center gap-2">
            <Badge
              className={cn(
                "border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em]",
                showWarningTone
                  ? "border-amber-400/40 bg-amber-500/15 text-amber-200"
                  : "border-[#3c444f] bg-[#161c24] text-gray-300",
              )}
            >
              {summaryLabel}
            </Badge>
            <Badge className="border border-[#39414c] bg-[#181c22] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-gray-400">
              {activeFilterCount} active
            </Badge>
          </div>
        </div>

        {expanded && (
          <div className="mt-2.5 space-y-2">
            {error && (
              <div className="rounded-lg border border-amber-400/35 bg-amber-500/10 px-2.5 py-2 text-[11px] text-amber-200">
                {error}
              </div>
            )}

            {!error && !hasData && activeFilterCount > 0 && !loading && (
              <div className="rounded-lg border border-[#303742] bg-[#131920] px-2.5 py-2 text-[11px] text-gray-400">
                Apply changes and wait a moment to inspect per-query diagnostics.
              </div>
            )}

            {hasData &&
              response?.data.map((entry) => (
                <div
                  key={entry.query_id}
                  className={cn(
                    "rounded-lg border px-2.5 py-2",
                    entry.success
                      ? "border-emerald-400/25 bg-emerald-500/10"
                      : "border-amber-400/35 bg-amber-500/10",
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs font-medium text-gray-100">
                      {entry.query_name || entry.query_id}
                    </p>
                    <Badge
                      className={cn(
                        "border px-1.5 py-0 text-[10px] font-semibold uppercase tracking-[0.08em]",
                        entry.success
                          ? "border-emerald-400/30 bg-emerald-500/15 text-emerald-200"
                          : "border-amber-400/35 bg-amber-500/15 text-amber-200",
                      )}
                    >
                      {entry.success ? "valid" : "invalid"}
                    </Badge>
                  </div>

                  <p className="mt-1 text-[10px] text-gray-400">
                    query_id: <span className="font-mono text-gray-300">{entry.query_id}</span>
                  </p>

                  {entry.error && (
                    <p className="mt-1 text-[11px] text-amber-200">{entry.error}</p>
                  )}

                  {Array.isArray(entry.warnings) && entry.warnings.length > 0 && (
                    <p className="mt-1 text-[11px] text-amber-100/90">
                      warnings: {entry.warnings.join(", ")}
                    </p>
                  )}

                  {Array.isArray(entry.compiled_filters) &&
                    entry.compiled_filters.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {entry.compiled_filters.map((compiled, index) => (
                          <span
                            key={`${entry.query_id}-${compiled.field}-${index}`}
                            className="rounded-md border border-[#404751] bg-[#141a21] px-1.5 py-0.5 font-mono text-[10px] text-gray-300"
                          >
                            {compiled.field} {compiled.operator}
                          </span>
                        ))}
                      </div>
                    )}
                </div>
              ))}
          </div>
        )}
      </div>
    </div>
  )
}
