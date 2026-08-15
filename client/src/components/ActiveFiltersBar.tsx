import React, { useEffect, useMemo, useRef, useState } from "react"
import { Filter, X } from "lucide-react"

import { cn } from "../lib/utils"
import type { ActiveFilterChip } from "../utils/filterDisplay"
import { Badge } from "./ui/badge"
import { Button } from "./ui/button"

interface ActiveFiltersBarProps {
  chips: ActiveFilterChip[]
  onRemoveChip: (chip: ActiveFilterChip) => void
  onClearAll: () => void
  maxVisible?: number
  className?: string
}

export function ActiveFiltersBar({
  chips,
  onRemoveChip,
  onClearAll,
  maxVisible = 4,
  className,
}: ActiveFiltersBarProps) {
  const [showOverflowMenu, setShowOverflowMenu] = useState(false)
  const overflowRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!showOverflowMenu) {
      return
    }

    const onDocumentMouseDown = (event: MouseEvent) => {
      if (!overflowRef.current?.contains(event.target as Node)) {
        setShowOverflowMenu(false)
      }
    }

    const onEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setShowOverflowMenu(false)
      }
    }

    document.addEventListener("mousedown", onDocumentMouseDown)
    document.addEventListener("keydown", onEscape)
    return () => {
      document.removeEventListener("mousedown", onDocumentMouseDown)
      document.removeEventListener("keydown", onEscape)
    }
  }, [showOverflowMenu])

  const visibleChips = useMemo(() => chips.slice(0, maxVisible), [chips, maxVisible])
  const overflowChips = useMemo(() => chips.slice(maxVisible), [chips, maxVisible])

  if (chips.length === 0) {
    return null
  }

  return (
    <div
      className={cn(
        "border-b border-[#28303c] bg-[#0e131a]/95 px-3 py-2",
        className,
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <Badge className="h-7 border border-[#3b424d] bg-[#171d25] px-2.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-gray-200">
            <Filter className="mr-1 h-3.5 w-3.5 text-brand-orange" />
            {chips.length} filters applied
          </Badge>

          <div className="flex min-w-0 items-center gap-1 overflow-hidden">
            {visibleChips.map((chip) => (
              <div
                key={chip.id}
                className="inline-flex h-7 min-w-0 max-w-[220px] shrink-0 items-center gap-1 rounded-full border border-brand-orange/40 bg-brand-orange/15 pl-2.5 pr-1 text-[11px] text-brand-orange"
                title={`${chip.label}: ${chip.displayValue}`}
              >
                <span className="truncate">
                  <span className="font-semibold">{chip.label}:</span> {chip.displayValue}
                </span>
                <button
                  type="button"
                  onClick={() => onRemoveChip(chip)}
                  className="inline-flex h-5 w-5 items-center justify-center rounded-full text-brand-orange transition-colors hover:bg-brand-orange/20 hover:text-white"
                  aria-label={`Remove ${chip.label} filter`}
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}

            {overflowChips.length > 0 && (
              <div className="relative shrink-0" ref={overflowRef}>
                <button
                  type="button"
                  onClick={() => setShowOverflowMenu((prev) => !prev)}
                  className="inline-flex h-7 items-center rounded-full border border-[#3b424d] bg-[#171d25] px-2.5 text-[11px] font-semibold text-gray-200 transition-colors hover:border-brand-orange/50 hover:text-brand-orange"
                >
                  +{overflowChips.length} more
                </button>
                {showOverflowMenu && (
                  <div className="absolute left-0 top-full z-50 mt-1.5 w-[280px] rounded-lg border border-[#3a424d] bg-[#131920] p-1.5 shadow-[0_14px_24px_rgba(0,0,0,0.45)]">
                    {overflowChips.map((chip) => (
                      <div
                        key={chip.id}
                        className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-[11px] text-gray-200 hover:bg-[#1d2530]"
                      >
                        <span className="min-w-0 truncate">
                          <span className="font-semibold">{chip.label}:</span> {chip.displayValue}
                        </span>
                        <button
                          type="button"
                          onClick={() => onRemoveChip(chip)}
                          className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-gray-400 transition-colors hover:bg-[#2a333f] hover:text-white"
                          aria-label={`Remove ${chip.label} filter`}
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        <Button
          type="button"
          onClick={onClearAll}
          className="h-8 shrink-0 border border-red-400/70 bg-red-500/80 px-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-white hover:bg-red-500 disabled:cursor-not-allowed disabled:border-red-400/25 disabled:bg-red-500/20 disabled:text-red-100/60"
        >
          Clear All Filters
        </Button>
      </div>
    </div>
  )
}
