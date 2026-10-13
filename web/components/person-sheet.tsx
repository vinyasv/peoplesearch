"use client"

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Spinner } from "@/components/ui/spinner"
import { VERDICT_LABEL, VerdictCell } from "@/components/verdict-mark"
import { domain, linkedinHandle, linkedinUrl, subtitle } from "@/lib/format"
import type { Person, RunState } from "@/lib/run-state"
import type { Criterion, Verdict } from "@/lib/types"
import { cn } from "@/lib/utils"

function ExternalLink({
  href,
  className,
  children,
}: {
  href: string
  className?: string
  children: React.ReactNode
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={cn(
        "underline decoration-muted-foreground/40 underline-offset-4 hover:decoration-foreground",
        className
      )}
    >
      {children}
    </a>
  )
}

function emailNote(person: Person, running: boolean) {
  const c = person.contact
  if (!c) {
    return person.qualified && running
      ? "Looked up once every check finishes"
      : "Not looked up"
  }
  if (c.email_status === "not_requested") {
    return "Only looked up for people who meet every requirement"
  }
  return c.email_status === "error" ? "Lookup failed" : "None found"
}

function Contacts({ person, running }: { person: Person; running: boolean }) {
  const { info, contact } = person
  const linkedin = linkedinUrl(info)
  return (
    <dl className="grid grid-cols-[5rem_1fr] gap-x-4 gap-y-2 text-sm">
      <dt className="text-muted-foreground">Email</dt>
      <dd className="min-w-0 break-words">
        {contact?.email_status === "found" && contact.email ? (
          <>
            <a href={`mailto:${contact.email}`} className="font-medium hover:underline">
              {contact.email}
            </a>
            {contact.email_source && (
              <span className="text-muted-foreground">
                {" "}
                from{" "}
                <ExternalLink href={contact.email_source}>
                  {domain(contact.email_source)}
                </ExternalLink>
              </span>
            )}
          </>
        ) : (
          <span className="text-muted-foreground">{emailNote(person, running)}</span>
        )}
      </dd>
      <dt className="text-muted-foreground">LinkedIn</dt>
      <dd className="min-w-0 break-words">
        {linkedin ? (
          <ExternalLink href={linkedin}>{linkedinHandle(linkedin)}</ExternalLink>
        ) : (
          <span className="text-muted-foreground">None found</span>
        )}
      </dd>
      {!linkedin && (
        <>
          <dt className="text-muted-foreground">Profile</dt>
          <dd className="min-w-0 break-words">
            <ExternalLink href={info.profile_url}>
              {info.profile_url.replace(/^https?:\/\/(www\.)?/, "")}
            </ExternalLink>
          </dd>
        </>
      )}
    </dl>
  )
}

function CriterionResult({
  criterion,
  verdict,
}: {
  criterion: Criterion
  verdict: Verdict | undefined
}) {
  // One quote per source site.
  const seen = new Set<string>()
  const evidence = (verdict?.evidence ?? []).filter((e) => {
    const d = domain(e.url)
    if (seen.has(d)) return false
    seen.add(d)
    return true
  })

  return (
    <section className="grid grid-cols-[1.5rem_1fr] gap-x-3 py-6">
      <VerdictCell status={verdict?.status ?? null} className="mt-px" />
      <div className="flex min-w-0 flex-col gap-2">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4">
          <h3 className="font-semibold">
            {criterion.label}
            {criterion.kind === "soft" && (
              <span className="font-normal text-muted-foreground"> (nice to have)</span>
            )}
          </h3>
          <span className="text-sm text-muted-foreground">
            {verdict ? (
              verdict.status === "skipped" ? (
                VERDICT_LABEL.skipped
              ) : (
                `${VERDICT_LABEL[verdict.status]}, ${Math.round(verdict.confidence * 100)}% sure`
              )
            ) : (
              <span className="flex items-center gap-1.5">
                <Spinner />
                Checking
              </span>
            )}
          </span>
        </div>
        <p className="text-sm text-muted-foreground">{criterion.requirement}</p>
        {verdict && verdict.status !== "skipped" && (
          <p className="text-[15px] leading-relaxed">{verdict.reasoning}</p>
        )}
        {verdict?.status === "skipped" && (
          <p className="text-sm text-muted-foreground">
            Skipped because a required check had already failed.
          </p>
        )}
        {evidence.length > 0 && (
          <ul className="mt-2 flex flex-col gap-4">
            {evidence.map((e) => (
              <li key={e.url} className="flex flex-col gap-1">
                {e.quote && (
                  <p className="font-serif text-[16px] leading-relaxed">
                    <mark className="bg-highlight box-decoration-clone px-0.5 text-foreground">
                      {e.quote}
                    </mark>
                  </p>
                )}
                <ExternalLink href={e.url} className="w-fit text-[13px] text-muted-foreground">
                  {domain(e.url)}
                </ExternalLink>
              </li>
            ))}
          </ul>
        )}
        {verdict && verdict.status !== "skipped" && (
          <p className="text-[13px] text-muted-foreground">
            {verdict.tool_calls
              ? `Based on ${verdict.tool_calls} web ${verdict.tool_calls > 1 ? "lookups" : "lookup"}`
              : "Based on the profile alone"}
          </p>
        )}
      </div>
    </section>
  )
}

export function PersonSheet({
  run,
  personId,
  onClose,
}: {
  run: RunState
  personId: string | null
  onClose: () => void
}) {
  const person = personId ? run.people[personId] : undefined
  const running = run.status === "running"
  const missed = person
    ? run.criteria.filter(
        (c) => c.kind === "hard" && person.done && person.verdicts[c.id]?.status !== "met"
      ).length
    : 0

  return (
    <Sheet open={!!person} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-full gap-0 sm:max-w-xl">
        {person && (
          <div className="flex-1 overflow-y-auto">
            <SheetHeader className="gap-1 px-6 pt-8 pr-14 pb-6 sm:px-8">
              <SheetTitle className="text-xl font-semibold tracking-tight">
                {person.info.name}
              </SheetTitle>
              <SheetDescription>{subtitle(person.info)}</SheetDescription>
              <p className="pt-2 text-sm">
                {!person.done ? (
                  <span className="text-muted-foreground">Still checking</span>
                ) : person.qualified ? (
                  <span className="font-medium text-success">Meets every requirement</span>
                ) : (
                  <span className="text-muted-foreground">
                    Missed {missed} required {missed === 1 ? "check" : "checks"}
                  </span>
                )}
                {person.score != null && (
                  <span className="ml-4 text-muted-foreground tabular-nums">
                    Score {Math.round(person.score * 100)}
                  </span>
                )}
              </p>
            </SheetHeader>
            <div className="border-y px-6 py-5 sm:px-8">
              <Contacts person={person} running={running} />
            </div>
            <div className="flex flex-col divide-y px-6 pb-10 sm:px-8">
              {run.criteria.map((c) => (
                <CriterionResult key={c.id} criterion={c} verdict={person.verdicts[c.id]} />
              ))}
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  )
}
