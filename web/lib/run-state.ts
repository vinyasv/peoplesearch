import type {
  Candidate,
  Contact,
  Criterion,
  RunReport,
  Stage,
  StreamEvent,
  Verdict,
} from "@/lib/types"

export type Person = {
  info: Candidate
  verdicts: Record<string, Verdict>
  done: boolean
  qualified: boolean
  score: number | null
  contact: Contact | null
}

export type RunState = {
  query: string
  status: "running" | "done" | "error"
  stage: Stage | null
  criteria: Criterion[]
  order: string[]
  people: Record<string, Person>
  finished: number
  emailCost: number | null
  warning: string | null
  error: string | null
  runId: string | null
}

export function initialRun(query: string): RunState {
  return {
    query,
    status: "running",
    stage: null,
    criteria: [],
    order: [],
    people: {},
    finished: 0,
    emailCost: null,
    warning: null,
    error: null,
    runId: null,
  }
}

function withVerdict(state: RunState, id: string, v: Verdict): RunState {
  const p = state.people[id]
  if (!p || p.verdicts[v.criterion_id]) return state
  return {
    ...state,
    finished: state.finished + 1,
    people: {
      ...state.people,
      [id]: { ...p, verdicts: { ...p.verdicts, [v.criterion_id]: v } },
    },
  }
}

export type RunAction = StreamEvent | { type: "disconnected" }

export function runReducer(state: RunState, ev: RunAction): RunState {
  switch (ev.type) {
    case "stage":
      return { ...state, stage: ev.stage }
    case "plan":
      return { ...state, criteria: ev.plan.criteria }
    case "sourced": {
      if (!ev.candidates.length) {
        return {
          ...state,
          status: "error",
          error: "No matching profiles found. Try broader wording.",
        }
      }
      const people: Record<string, Person> = {}
      for (const c of ev.candidates) {
        people[c.id] = {
          info: c,
          verdicts: {},
          done: false,
          qualified: false,
          score: null,
          contact: null,
        }
      }
      return { ...state, people, order: ev.candidates.map((c) => c.id) }
    }
    case "verdict":
      return withVerdict(state, ev.candidate_id, ev.verdict)
    case "candidate_done": {
      let next = state
      for (const v of ev.verdicts) next = withVerdict(next, ev.candidate_id, v)
      const p = next.people[ev.candidate_id]
      if (!p) return next
      return {
        ...next,
        people: {
          ...next.people,
          [ev.candidate_id]: {
            ...p,
            done: true,
            qualified: ev.qualified,
            score: ev.score,
          },
        },
      }
    }
    case "contacts": {
      const people = { ...state.people }
      for (const [id, contact] of Object.entries(ev.contacts)) {
        if (people[id]) people[id] = { ...people[id], contact }
      }
      return { ...state, people, emailCost: ev.cost }
    }
    case "warning":
      return { ...state, warning: ev.message }
    case "done":
      return {
        ...state,
        status: "done",
        stage: null,
        runId: ev.run_id,
        emailCost: ev.email_lookup_cost ?? state.emailCost,
        order: [
          ...ev.order.filter((id) => state.people[id]),
          ...state.order.filter((id) => !ev.order.includes(id)),
        ],
      }
    case "error":
      return { ...state, status: "error", error: ev.message }
    case "disconnected":
      if (state.status !== "running") return state
      return {
        ...state,
        status: "error",
        error:
          "Lost the connection to the research server. Check that it's still running, then search again.",
      }
  }
}

export function runFromReport(id: string, report: RunReport): RunState {
  const people: Record<string, Person> = {}
  let finished = 0
  for (const r of report.results) {
    const verdicts: Record<string, Verdict> = {}
    for (const v of r.verdicts) verdicts[v.criterion_id] = v
    finished += r.verdicts.length
    people[r.candidate.id] = {
      info: r.candidate,
      verdicts,
      done: true,
      qualified: r.qualified,
      score: r.score,
      contact: r.contact,
    }
  }
  return {
    ...initialRun(report.query),
    status: "done",
    criteria: report.plan.criteria,
    order: report.results.map((r) => r.candidate.id),
    people,
    finished,
    emailCost: report.email_lookup_cost,
    runId: id,
  }
}

export const STAGE_LABEL: Record<Stage, string> = {
  planning: "Breaking your search into requirements",
  sourcing: "Finding people",
  researching: "Checking each requirement",
  contacts: "Finding emails for qualified people",
}
