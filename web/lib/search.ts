export const EXAMPLES = [
  "Rust developers in San Francisco who maintain an open-source GitHub project with at least 1,000 stars",
  "Machine learning researchers in London who were first author on a NeurIPS, ICML or ICLR paper since 2023",
  "Software engineers in NYC with three.js experience and at least 4 years of professional experience",
]

export function searchHref(query: string, n: string | number) {
  return `/search?${new URLSearchParams({ q: query, n: String(n) })}`
}
