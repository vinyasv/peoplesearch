"use client"

import * as React from "react"

import { PageShell } from "@/components/page-shell"
import { ResultsView } from "@/components/results-view"
import { useResearchStream } from "@/hooks/use-research-stream"

export function LiveSearch({ query, n }: { query: string; n: number }) {
  const run = useResearchStream(query, n)

  // Once saved, point the URL at the saved run so a reload doesn't start (and pay for) a new search.
  React.useEffect(() => {
    if (run.runId) {
      window.history.replaceState(null, "", `/runs/${encodeURIComponent(run.runId)}`)
    }
  }, [run.runId])

  return (
    <PageShell>
      <ResultsView run={run} />
    </PageShell>
  )
}
