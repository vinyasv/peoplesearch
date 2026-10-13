import type { RunReport, RunSummary } from "@/lib/types"

// The FastAPI backend (people_research/server.py). Browsers call it directly, so it needs
// this site's origin in PR_CORS_ORIGINS.
export const API_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000"
).replace(/\/$/, "")

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

export const listRuns = (limit = 20) =>
  getJSON<RunSummary[]>(`/api/runs?limit=${limit}`)

export const getRun = (id: string) =>
  getJSON<RunReport>(`/api/runs/${encodeURIComponent(id)}`)

export const searchURL = (query: string, n: number) =>
  `${API_URL}/api/search?${new URLSearchParams({ q: query, n: String(n) })}`
