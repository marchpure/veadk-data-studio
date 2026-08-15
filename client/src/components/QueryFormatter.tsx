"use client"

import { Button } from "./ui/button"
import { Wand2 } from "lucide-react"

interface QueryFormatterProps {
  query: string
  onQueryChange: (query: string) => void
}

export function QueryFormatter({ query, onQueryChange }: QueryFormatterProps) {
  const formatQuery = () => {
    // Simple SQL formatter
    const formatted = query
      .replace(/\bSELECT\b/gi, "SELECT")
      .replace(/\bFROM\b/gi, "\nFROM")
      .replace(/\bWHERE\b/gi, "\nWHERE")
      .replace(/\bORDER BY\b/gi, "\nORDER BY")
      .replace(/\bGROUP BY\b/gi, "\nGROUP BY")
      .replace(/\bHAVING\b/gi, "\nHAVING")
      .replace(/\bJOIN\b/gi, "\nJOIN")
      .replace(/\bLEFT JOIN\b/gi, "\nLEFT JOIN")
      .replace(/\bRIGHT JOIN\b/gi, "\nRIGHT JOIN")
      .replace(/\bINNER JOIN\b/gi, "\nINNER JOIN")
      .replace(/\bAND\b/gi, "\n  AND")
      .replace(/\bOR\b/gi, "\n  OR")
      .trim()

    onQueryChange(formatted)
  }

  return (
    <Button onClick={formatQuery} variant="outline" size="sm" className="absolute top-2 right-2 z-10 bg-transparent">
      <Wand2 className="w-3 h-3 mr-1" />
      Format
    </Button>
  )
}