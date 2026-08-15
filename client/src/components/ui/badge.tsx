import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "../../lib/utils"

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium transition-colors",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-primary text-primary-foreground shadow hover:bg-primary/80",
        secondary:
          "border-transparent bg-secondary text-secondary-foreground hover:bg-secondary/80",
        destructive:
          "border-transparent bg-destructive text-destructive-foreground shadow hover:bg-destructive/80",
        outline: "text-foreground",
        // Brand variants
        "brand-orange":
          "bg-brand-orange/10 text-brand-orange border-brand-orange/30",
        "brand-orange-solid":
          "bg-brand-orange text-white border-brand-orange",
        "brand-muted":
          "bg-brand-orange-muted/10 text-brand-orange-muted border-brand-orange-muted/30",
        // Type badges for databases/connections
        postgres:
          "bg-blue-500/10 text-blue-400 border-blue-500/30",
        mongodb:
          "bg-green-500/10 text-green-400 border-green-500/30",
        mysql:
          "bg-orange-500/10 text-orange-400 border-orange-500/30",
        sqlite:
          "bg-cyan-500/10 text-cyan-400 border-cyan-500/30",
        csv:
          "bg-purple-500/10 text-purple-400 border-purple-500/30",
        // AI Model types
        openai:
          "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
        azure:
          "bg-sky-500/10 text-sky-400 border-sky-500/30",
        groq:
          "bg-violet-500/10 text-violet-400 border-violet-500/30",
        openrouter:
          "bg-rose-500/10 text-rose-400 border-rose-500/30",
        claude_code:
          "bg-brand-orange/10 text-brand-orange border-brand-orange/30",
        // Generic notebook badge with better color (indigo instead of pink)
        notebook:
          "bg-indigo-500/10 text-indigo-400 border-indigo-500/30",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  )
}

export { Badge, badgeVariants }