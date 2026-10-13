import type { Candidate } from "@/lib/types"

export function domain(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "")
  } catch {
    return url
  }
}

// Exa's page title often repeats the name ("Jane Doe - Engineer at X | LinkedIn").
export function subtitle(c: Candidate) {
  let h = (c.headline ?? "").replace(/\s*\|\s*LinkedIn\s*$/i, "")
  if (h.toLowerCase().startsWith(c.name.toLowerCase())) {
    h = h.slice(c.name.length).replace(/^[\s\-–—|,:]+/, "")
  }
  return h || c.location || ""
}

export function linkedinHandle(url: string) {
  const tail = url.replace(/\/$/, "").split("/in/").pop() || url
  try {
    return decodeURIComponent(tail)
  } catch {
    return tail
  }
}

// Older saved runs only have the profile URL, which is usually the LinkedIn page itself.
export function linkedinUrl(c: Candidate) {
  if (c.linkedin_url) return c.linkedin_url
  return /linkedin\.com\/in\//.test(c.profile_url) ? c.profile_url : null
}
