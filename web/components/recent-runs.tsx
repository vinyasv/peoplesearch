"use client"

import * as React from "react"
import Link from "next/link"

import { Skeleton } from "@/components/ui/skeleton"
import { API_URL, listRuns } from "@/lib/api"
import type { RunSummary } from "@/lib/types"

const DATE = new Intl.DateTimeFormat("en", { month: "short", day: "numeric" })

export function RecentRuns() {
  const [runs, setRuns] = React.useState<RunSummary[] | null>(null)
  const [failed, setFailed] = React.useState(false)

  React.useEffect(() => {
    listRuns(6).then(setRuns, () => setFailed(true))
  }, [])

  if (failed) {
    return (
      <p className="text-sm text-muted-foreground">
        Couldn&apos;t reach the research server at {API_URL}. Start it with{" "}
        <code className="text-foreground">uv run people-research-web</code>, or
        set NEXT_PUBLIC_API_URL to where it runs.
      </p>
    )
  }

  if (!runs) {
    return (
      <div className="flex flex-col gap-5">
        {Array.from({ length: 3 }, (_, i) => (
          <div key={i} className="flex flex-col gap-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-3 w-28" />
          </div>
        ))}
      </div>
    )
  }

  if (!runs.length) {
    return <p className="text-sm text-muted-foreground">Your searches will show up here.</p>
  }

  return (
    <ul className="flex flex-col gap-5">
      {runs.map((r) => (
        <li key={r.id}>
          <Link
            href={`/runs/${encodeURIComponent(r.id)}`}
            className="group flex flex-col gap-1 outline-none"
          >
            <span className="line-clamp-2 font-serif text-[17px] leading-snug decoration-muted-foreground/50 underline-offset-4 group-hover:underline group-focus-visible:underline">
              {r.query}
            </span>
            <span className="text-sm text-muted-foreground">
              <span className={r.qualified ? "font-medium text-success" : undefined}>
                {r.qualified} of {r.people} qualified
              </span>
              <span className="ml-3">{DATE.format(new Date(r.created_at))}</span>
            </span>
          </Link>
        </li>
      ))}
    </ul>
  )
}
