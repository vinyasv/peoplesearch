"""Email lookup for verified candidates, via one batched Exa Agent run.

The people search already gives us each LinkedIn URL for free. Emails aren't in search results,
so they cost an Agent run: metered compute plus ~$0.02 per email found, capped by a budget.
"""

import re

from exa_py import AsyncExa

from .config import Settings
from .models import CandidateReport, Contact

SYSTEM_PROMPT = """You find professional contact emails for specific, already-identified people.
- Each input row is one person, identified by name, LinkedIn URL and current employer. Only \
return an email you can attribute to that exact person.
- Prefer a work email; otherwise a professional email the person publishes themselves (personal \
site, GitHub profile, CV).
- Never construct an email from a naming pattern (first.last@company.com) unless it is confirmed.
- If no email can be found, return null for that person rather than a guess.
- Return every input person exactly once, keyed by their id."""

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _current_company(report: CandidateReport) -> str | None:
    for role in report.candidate.work_history:
        to = (role.get("dates") or {}).get("to_date")
        company = (role.get("company") or {}).get("name")
        if company and not to:
            return company
    return None


def _email_sources(grounding, index_by_path: dict[str, str]) -> dict[str, str]:
    """Map candidate id -> first citation URL for its email field, e.g. field 'structured.people[2].email'."""
    out: dict[str, str] = {}
    for entry in grounding or []:
        m = re.match(r"^(?:structured\.)?people\[(\d+)\]\.email$", entry.field or "")
        if m and entry.citations and m.group(1) in index_by_path:
            out[index_by_path[m.group(1)]] = entry.citations[0].url
    return out


async def enrich_emails(client: AsyncExa, settings: Settings, reports: list[CandidateReport]) -> float | None:
    """Fill report.contact for each report. Returns the email lookup cost in dollars, or None if none ran."""
    for r in reports:
        r.contact = Contact(linkedin_url=r.candidate.linkedin_url)

    if settings.enrich_emails == "off":
        return None
    targets = [r for r in reports if settings.enrich_emails == "all" or r.qualified]
    if not targets:
        return None

    rows = [
        {
            "id": r.candidate.id,
            "name": r.candidate.name,
            "linkedin_url": r.candidate.linkedin_url or r.candidate.profile_url,
            "current_company": _current_company(r),
            "location": r.candidate.location,
        }
        for r in targets
    ]
    schema = {
        "type": "object",
        "properties": {
            "people": {
                "type": "array",
                "maxItems": len(rows),
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "email": {"type": ["string", "null"], "format": "email"},
                    },
                    "required": ["id", "email"],
                },
            }
        },
        "required": ["people"],
    }

    try:
        run = await client.agent.runs.create(
            query="Find the professional email address for each person in the input.",
            system_prompt=SYSTEM_PROMPT,
            input={"data": rows},
            output_schema=schema,
            effort="auto",
            budget={"max_cost_dollars": settings.enrich_budget_dollars},
        )
        run = await client.agent.runs.poll_until_finished(run.id, poll_interval=3000, timeout_ms=15 * 60 * 1000)
    except Exception:
        for r in targets:
            r.contact.email_status = "error"
        raise

    cost = run.cost_dollars.total if run.cost_dollars else None
    if run.status != "completed" or not run.output or not isinstance(run.output.structured, dict):
        for r in targets:
            r.contact.email_status = "error"
        return cost

    people = run.output.structured.get("people") or []
    index_to_id = {str(i): p.get("id") for i, p in enumerate(people) if isinstance(p, dict)}
    sources = _email_sources(run.output.grounding, index_to_id)
    found = {
        p["id"]: p["email"].strip()
        for p in people
        if isinstance(p, dict) and isinstance(p.get("email"), str) and EMAIL_RE.match(p["email"].strip())
    }
    for r in targets:
        email = found.get(r.candidate.id)
        r.contact.email = email
        r.contact.email_source = sources.get(r.candidate.id) if email else None
        r.contact.email_status = "found" if email else "not_found"
    return cost
