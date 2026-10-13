"use client"

import * as React from "react"
import { CircleAlertIcon } from "lucide-react"

import { PersonSheet } from "@/components/person-sheet"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Skeleton } from "@/components/ui/skeleton"
import { Spinner } from "@/components/ui/spinner"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { VERDICT_LABEL, VerdictCell } from "@/components/verdict-mark"
import { linkedinHandle, linkedinUrl, subtitle } from "@/lib/format"
import { STAGE_LABEL, type Person, type RunState } from "@/lib/run-state"
import { cn } from "@/lib/utils"

function StatusLine({ run, total }: { run: RunState; total: number }) {
  if (run.status === "running") {
    const label =
      run.stage === "researching" && total
        ? `Checking requirements, ${run.finished} of ${total} done`
        : run.stage
          ? STAGE_LABEL[run.stage]
          : "Starting"
    return (
      <p className="flex items-center gap-2 text-muted-foreground" aria-live="polite">
        <Spinner />
        {label}
      </p>
    )
  }
  const people = Object.values(run.people)
  if (!people.length) return null
  const qualified = people.filter((p) => p.qualified).length
  return (
    <p className="flex flex-wrap gap-x-6 gap-y-1" aria-live="polite">
      <span>
        <span className="font-semibold">
          {qualified} of {people.length}
        </span>{" "}
        meet every requirement
      </span>
      {run.emailCost != null && (
        <span className="text-muted-foreground">
          Email lookup cost ${run.emailCost.toFixed(2)}
        </span>
      )}
    </p>
  )
}

function Requirements({ run }: { run: RunState }) {
  if (!run.criteria.length) {
    return run.status === "running" ? (
      <div className="flex max-w-2xl flex-col gap-2.5">
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-4 w-2/3" />
        <Skeleton className="h-4 w-1/2" />
      </div>
    ) : null
  }
  return (
    <dl className="grid max-w-3xl gap-x-8 gap-y-2.5 text-sm sm:grid-cols-[minmax(9rem,auto)_1fr]">
      {run.criteria.map((c) => (
        <React.Fragment key={c.id}>
          <dt className="font-medium">
            {c.label}
            {c.kind === "soft" && (
              <span className="font-normal text-muted-foreground"> (nice to have)</span>
            )}
          </dt>
          <dd className="text-muted-foreground max-sm:mb-2">{c.requirement}</dd>
        </React.Fragment>
      ))}
    </dl>
  )
}

function EmailCell({ person, run }: { person: Person; run: RunState }) {
  const c = person.contact
  if (c?.email_status === "found" && c.email) {
    return (
      <a
        href={`mailto:${c.email}`}
        onClick={(e) => e.stopPropagation()}
        className="underline-offset-4 hover:underline"
      >
        {c.email}
      </a>
    )
  }
  if (!c && person.qualified && run.stage === "contacts") {
    return (
      <span className="flex items-center gap-1.5 text-muted-foreground">
        <Spinner />
        Looking up
      </span>
    )
  }
  if (c && c.email_status !== "not_requested") {
    return (
      <span className="text-muted-foreground">
        {c.email_status === "error" ? "Lookup failed" : "None found"}
      </span>
    )
  }
  return null
}

function SkeletonRows({ rows, cols }: { rows: number; cols: number }) {
  return Array.from({ length: rows }, (_, r) => (
    <TableRow key={r} className="hover:bg-transparent">
      <TableCell className="py-3 pl-0">
        <div className="flex flex-col gap-1.5">
          <Skeleton className="h-3.5" style={{ width: 110 + ((r * 37) % 80) }} />
          <Skeleton className="h-3 w-44" />
        </div>
      </TableCell>
      {Array.from({ length: cols }, (_, c) => (
        <TableCell key={c} className="text-center">
          <VerdictCell status={null} />
        </TableCell>
      ))}
      <TableCell colSpan={3} />
    </TableRow>
  ))
}

export function ResultsView({ run }: { run: RunState }) {
  const [openId, setOpenId] = React.useState<string | null>(null)
  const [filter, setFilter] = React.useState<"all" | "qualified">("all")

  const people = run.order.map((id) => run.people[id]).filter(Boolean)
  const total = people.length * run.criteria.length
  const qualifiedCount = people.filter((p) => p.qualified).length
  const shown = filter === "qualified" ? people.filter((p) => p.qualified) : people
  const running = run.status === "running"

  return (
    <div className="flex flex-col gap-10">
      <div className="flex flex-col gap-4">
        <h1 className="max-w-4xl font-serif text-[28px] leading-[1.2] text-pretty sm:text-[34px]">
          {run.query}
        </h1>
        <StatusLine run={run} total={total} />
      </div>

      <Requirements run={run} />

      {run.status === "error" && (
        <Alert variant="destructive" className="max-w-2xl">
          <CircleAlertIcon />
          <AlertTitle>The search stopped</AlertTitle>
          <AlertDescription>{run.error}</AlertDescription>
        </Alert>
      )}
      {run.warning && (
        <Alert className="max-w-2xl">
          <CircleAlertIcon />
          <AlertDescription>{run.warning}</AlertDescription>
        </Alert>
      )}

      {!(run.status === "error" && people.length === 0) && (
        <section className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <ToggleGroup
              value={[filter]}
              onValueChange={(v) => v[0] && setFilter(v[0] as typeof filter)}
              size="sm"
              aria-label="Which people to show"
            >
              <ToggleGroupItem value="all">Everyone {people.length || ""}</ToggleGroupItem>
              <ToggleGroupItem value="qualified">Qualified {qualifiedCount}</ToggleGroupItem>
            </ToggleGroup>
            {people.length > 0 && (
              <p className="text-sm text-muted-foreground">
                Select a person to see the evidence
              </p>
            )}
          </div>

          <Table>
            <TableHeader>
              <TableRow className="border-foreground hover:bg-transparent">
                <TableHead className="pl-0 align-bottom">Person</TableHead>
                {run.criteria.map((c) => (
                  <TableHead
                    key={c.id}
                    className={cn(
                      "w-24 py-2 text-center align-bottom text-xs leading-tight whitespace-normal",
                      c.kind === "soft" && "font-normal text-muted-foreground"
                    )}
                  >
                    {c.label}
                  </TableHead>
                ))}
                <TableHead className="w-16 text-right align-bottom">Score</TableHead>
                <TableHead className="pl-6 align-bottom">Email</TableHead>
                <TableHead className="pr-0 align-bottom">LinkedIn</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {people.length === 0 ? (
                <SkeletonRows rows={5} cols={run.criteria.length || 3} />
              ) : (
                shown.map((p) => {
                  const li = linkedinUrl(p.info)
                  const out = p.done && !p.qualified
                  return (
                    <TableRow
                      key={p.info.id}
                      onClick={() => setOpenId(p.info.id)}
                      className="cursor-pointer hover:bg-accent/60"
                    >
                      <TableCell className="py-3 pl-0">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation()
                            setOpenId(p.info.id)
                          }}
                          className="flex max-w-72 flex-col text-left outline-none focus-visible:underline"
                        >
                          <span className={cn("font-medium", out && "text-muted-foreground")}>
                            {p.info.name}
                          </span>
                          <span className="truncate text-[13px] text-muted-foreground">
                            {subtitle(p.info)}
                          </span>
                        </button>
                      </TableCell>
                      {run.criteria.map((c) => (
                        <TableCell key={c.id} className="text-center">
                          <VerdictCell status={p.verdicts[c.id]?.status ?? null} />
                        </TableCell>
                      ))}
                      <TableCell
                        className={cn(
                          "text-right tabular-nums",
                          out ? "text-muted-foreground" : "font-medium"
                        )}
                      >
                        {p.score != null ? Math.round(p.score * 100) : ""}
                      </TableCell>
                      <TableCell className="max-w-60 truncate pl-6">
                        <EmailCell person={p} run={run} />
                      </TableCell>
                      <TableCell className="max-w-44 truncate pr-0">
                        {li && (
                          <a
                            href={li}
                            target="_blank"
                            rel="noopener noreferrer"
                            onClick={(e) => e.stopPropagation()}
                            className="text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
                          >
                            {linkedinHandle(li)}
                          </a>
                        )}
                      </TableCell>
                    </TableRow>
                  )
                })
              )}
            </TableBody>
          </Table>

          {people.length > 0 && shown.length === 0 && (
            <p className="py-6 text-sm text-muted-foreground">
              {running
                ? "No one has passed every required check yet. People appear here as soon as they do."
                : "No one passed every required check. Switch to Everyone to see who came closest."}
            </p>
          )}

          {people.length > 0 && (
            <div className="flex flex-wrap gap-x-6 gap-y-2 pt-2 text-[13px] text-muted-foreground">
              {(["met", "not_met", "unclear", "skipped"] as const).map((s) => (
                <span key={s} className="flex items-center gap-2">
                  <VerdictCell status={s} className="size-4 animate-none [&_svg]:size-2.5" />
                  {s === "skipped" ? "Not checked after a required one failed" : VERDICT_LABEL[s]}
                </span>
              ))}
            </div>
          )}
        </section>
      )}

      <PersonSheet run={run} personId={openId} onClose={() => setOpenId(null)} />
    </div>
  )
}
