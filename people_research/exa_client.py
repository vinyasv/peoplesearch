import asyncio
import dataclasses
import hashlib
from urllib.parse import urlsplit

from exa_py import AsyncExa

from .config import Settings
from .models import Candidate

PROFILE_TEXT_CHARS = 6000
PAGE_TEXT_CHARS = 8000


def normalize_url(url: str) -> str:
    parts = urlsplit(url)
    host = parts.netloc.lower().removeprefix("www.")
    return f"{host}{parts.path.rstrip('/')}".lower()


class Exa:
    """AsyncExa with a concurrency cap and a page cache shared by all agents in a run."""

    def __init__(self, settings: Settings):
        if not settings.exa_api_key:
            raise RuntimeError("EXA_API_KEY is not set")
        self.client = AsyncExa(api_key=settings.exa_api_key)
        self.sem = asyncio.Semaphore(settings.exa_concurrency)
        self._pages: dict[str, str] = {}

    # ---------- sourcing ----------

    async def people_search(self, query: str, num_results: int) -> list[Candidate]:
        # category="people" retrieves raw profile documents; our own agents do the verification.
        # Profile text (capped) rather than highlights so verifiers see the full work history.
        async with self.sem:
            resp = await self.client.search(
                query,
                category="people",
                num_results=num_results,
                contents={"text": {"max_characters": PROFILE_TEXT_CHARS}},
            )
        out = []
        for r in resp.results:
            person = next((e for e in (r.entities or []) if e.type == "person"), None)
            props = person.properties if person else None
            name = (props.name if props and props.name else None) or (r.title or r.url).split(" - ")[0].split(" | ")[0]
            self._pages[normalize_url(r.url)] = r.text or ""
            out.append(
                Candidate(
                    id=hashlib.sha1(normalize_url(r.url).encode()).hexdigest()[:10],
                    name=name.strip(),
                    profile_url=r.url,
                    linkedin_url=r.url if "linkedin.com/in/" in r.url else None,
                    headline=r.title,
                    location=props.location if props else None,
                    work_history=[dataclasses.asdict(w) for w in (props.work_history or [])] if props else [],
                    profile_text=r.text or "",
                    matched_queries=[query],
                )
            )
        return out

    # ---------- agent tools ----------

    async def web_search(self, query: str, objective: str) -> list[dict]:
        # Exa's recommended agent-tool shape: query + objective, bare highlights, server defaults otherwise.
        async with self.sem:
            resp = await self.client.search(
                query,
                type="auto",
                objective=objective,
                contents={"highlights": True},
            )
        return [
            {
                "title": r.title,
                "url": r.url,
                "published_date": r.published_date,
                "highlights": r.highlights or [],
            }
            for r in resp.results
        ]

    async def fetch_page(self, url: str) -> str:
        key = normalize_url(url)
        if key in self._pages and self._pages[key]:
            return self._pages[key][:PAGE_TEXT_CHARS]
        # Full text, capped: the verifier needs whole-page context (dated roles, bios), and the cap
        # keeps each tool result small for the subagent.
        async with self.sem:
            resp = await self.client.get_contents([url], text={"max_characters": PAGE_TEXT_CHARS})
        # /contents can return 200 with per-URL failures; check statuses before trusting results.
        failed = [s for s in (resp.statuses or []) if s.status != "success"]
        if failed or not resp.results:
            reason = failed[0].source if failed and failed[0].source else "unknown error"
            raise RuntimeError(f"could not fetch {url} ({reason})")
        text = resp.results[0].text or ""
        self._pages[key] = text
        return text or "(no text could be extracted from this page)"


async def source_candidates(exa: Exa, queries: list[str], per_query: int, limit: int) -> list[Candidate]:
    """Run every planner query, then merge by profile URL. Profiles matched by more queries rank first."""
    batches = await asyncio.gather(*(exa.people_search(q, per_query) for q in queries))
    merged: dict[str, Candidate] = {}
    first_seen: dict[str, int] = {}
    for batch in batches:
        for rank, c in enumerate(batch):
            key = normalize_url(c.profile_url)
            if key in merged:
                merged[key].matched_queries += c.matched_queries
                first_seen[key] = min(first_seen[key], rank)
            else:
                merged[key] = c
                first_seen[key] = rank
    ordered = sorted(merged, key=lambda k: (-len(merged[k].matched_queries), first_seen[k]))
    return [merged[k] for k in ordered[:limit]]
