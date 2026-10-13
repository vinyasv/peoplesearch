"use client"

import * as React from "react"
import Link from "next/link"
import { FileQuestionIcon } from "lucide-react"

import { PageShell } from "@/components/page-shell"
import { ResultsView } from "@/components/results-view"
import { Button } from "@/components/ui/button"
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import { Skeleton } from "@/components/ui/skeleton"
import { getRun } from "@/lib/api"
import { runFromReport, type RunState } from "@/lib/run-state"

export function SavedRun({ id }: { id: string }) {
  const [run, setRun] = React.useState<RunState | null>(null)
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    getRun(id).then(
      (report) => setRun(runFromReport(id, report)),
      (e: Error) => setError(e.message)
    )
  }, [id])

  return (
    <PageShell>
      {error ? (
        <Empty className="border">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <FileQuestionIcon />
            </EmptyMedia>
            <EmptyTitle>Couldn&apos;t load this search</EmptyTitle>
            <EmptyDescription>
              {error.startsWith("404")
                ? "It may have been deleted from the server."
                : `The research server didn't respond (${error}).`}
            </EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <Button render={<Link href="/" />} nativeButton={false}>
              Start a new search
            </Button>
          </EmptyContent>
        </Empty>
      ) : run ? (
        <ResultsView run={run} />
      ) : (
        <div className="flex flex-col gap-4">
          <Skeleton className="h-8 w-2/3" />
          <Skeleton className="h-4 w-64" />
          <Skeleton className="mt-4 h-96 rounded-xl" />
        </div>
      )}
    </PageShell>
  )
}
