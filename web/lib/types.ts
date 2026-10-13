// Mirrors people_research/models.py and the SSE events in people_research/server.py.

export type CriterionKind = "hard" | "soft"

export type Criterion = {
  id: string
  label: string
  requirement: string
  kind: CriterionKind
  research_hints: string
  public_record?: boolean
}

export type SearchPlan = {
  criteria: Criterion[]
  exa_queries: string[]
}

export type Candidate = {
  id: string
  name: string
  profile_url: string
  linkedin_url: string | null
  headline: string | null
  location: string | null
}

export type Evidence = { url: string; quote: string }

export type VerdictStatus = "met" | "not_met" | "unclear" | "skipped" | "error"

export type Verdict = {
  criterion_id: string
  status: VerdictStatus
  confidence: number
  reasoning: string
  evidence: Evidence[]
  tool_calls: number
  revisions: number
}

export type Contact = {
  linkedin_url: string | null
  email: string | null
  email_source: string | null
  email_status: "found" | "not_found" | "not_requested" | "error"
}

export type CandidateReport = {
  candidate: Candidate
  verdicts: Verdict[]
  qualified: boolean
  score: number
  contact: Contact
}

export type RunReport = {
  query: string
  plan: SearchPlan
  results: CandidateReport[]
  email_lookup_cost: number | null
}

export type RunSummary = {
  id: string
  query: string
  created_at: string
  people: number
  qualified: number
  criteria: number
}

export type Stage = "planning" | "sourcing" | "researching" | "contacts"

export type StreamEvent =
  | { type: "stage"; stage: Stage }
  | { type: "plan"; plan: SearchPlan }
  | { type: "sourced"; candidates: Candidate[] }
  | { type: "verdict"; candidate_id: string; verdict: Verdict }
  | {
      type: "candidate_done"
      candidate_id: string
      qualified: boolean
      score: number
      verdicts: Verdict[]
    }
  | { type: "contacts"; cost: number | null; contacts: Record<string, Contact> }
  | { type: "warning"; message: string }
  | {
      type: "done"
      order: string[]
      run_id: string
      email_lookup_cost: number | null
    }
  | { type: "error"; message: string }
