import { CheckIcon, XIcon } from "lucide-react"

import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import type { VerdictStatus } from "@/lib/types"

export const VERDICT_LABEL: Record<VerdictStatus, string> = {
  met: "Met",
  not_met: "Not met",
  unclear: "Unclear",
  error: "Check failed",
  skipped: "Not checked",
}

// One square in the people × requirements grid. Met is the only filled state, so a
// qualified row reads as a solid bar of green at a glance.
const CELL: Record<VerdictStatus, string> = {
  met: "bg-success text-success-foreground",
  not_met: "border border-input text-muted-foreground",
  unclear: "border border-dashed border-input text-muted-foreground",
  error: "border border-destructive/60 text-destructive",
  skipped: "text-muted-foreground/40",
}

export function VerdictCell({
  status,
  className,
}: {
  status: VerdictStatus | null
  className?: string
}) {
  if (status === null) {
    return (
      <Skeleton
        aria-label="Checking"
        className={cn("inline-block size-6 rounded-[4px] align-middle", className)}
      />
    )
  }
  return (
    <span
      role="img"
      aria-label={VERDICT_LABEL[status]}
      className={cn(
        "inline-flex size-6 items-center justify-center rounded-[4px] align-middle text-xs font-semibold duration-200 animate-in fade-in-0 zoom-in-75 motion-reduce:animate-none",
        CELL[status],
        className
      )}
    >
      {status === "met" && <CheckIcon className="size-3.5" strokeWidth={3} />}
      {status === "not_met" && <XIcon className="size-3.5" strokeWidth={2.25} />}
      {status === "unclear" && "?"}
      {status === "error" && "!"}
      {status === "skipped" && "–"}
    </span>
  )
}
