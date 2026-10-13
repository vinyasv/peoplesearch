import { redirect } from "next/navigation"

import { LiveSearch } from "./live-search"

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; n?: string }>
}) {
  const { q, n } = await searchParams
  const query = q?.trim() ?? ""
  if (query.length < 3) redirect("/")
  const size = Math.min(25, Math.max(1, Number(n) || 10))
  // Keyed so a new query remounts and starts a fresh stream.
  return <LiveSearch key={`${size}:${query}`} query={query} n={size} />
}
