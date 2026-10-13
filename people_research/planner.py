from datetime import date

from .config import Settings
from .llm import LLM
from .models import SearchPlan

PLANNER_SYSTEM = """You turn a free-text people-search request into (1) a list of independently \
verifiable criteria and (2) a few queries for Exa's people search.

Criteria:
- Split the request into atomic conditions, one fact each. "SWE in NYC with 4+ years of three.js" \
is three criteria: profession, location, and years of three.js/professional experience (pick the \
reading the user most likely meant and state it precisely in `requirement`).
- Make every requirement concrete enough that a researcher can say met / not met from evidence. \
Resolve vague words: "NYC" means the New York City metro area; "at least 4 years of professional \
experience" means summed full-time industry roles, excluding internships and education.
- kind = "hard" for anything the user stated as a requirement; "soft" only for explicit \
preferences ("ideally", "bonus", "nice to have").
- research_hints: name the sources likely to settle it (LinkedIn-style profile work history, \
GitHub repos and languages, personal site, conference talks, company engineering blogs, \
npm packages) and what counts as evidence.
- label is a results-table column header: 1-3 words, distinct from the other labels.
- public_record: true when meeting the criterion would leave a findable public trace (a talk on a \
conference site, a paper in proceedings, an announced funding round or acquisition, a public repo), \
so researchers who search thoroughly and find nothing can call it not met. False when the fact may \
just be unpublished.
- Do not invent criteria the user did not ask for.

Exa queries:
- Exa people search matches profile pages semantically. Write 2-4 queries phrased as a \
description of the person, e.g. "software engineer in New York City who builds 3D web \
experiences with three.js". Vary the phrasing and emphasis across queries to widen recall \
(e.g. one using "WebGL", one using "creative developer").
- Fold in the most searchable criteria (role, location, core skill). Leave out things profile \
search can't filter well, like exact years of experience; the verifiers check those."""


async def plan_search(llm: LLM, settings: Settings, query: str) -> SearchPlan:
    resp = await llm.parse(
        model=settings.planner_model,
        effort=settings.planner_effort,
        output_format=SearchPlan,
        system=PLANNER_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": f"Today's date: {date.today().isoformat()}\n\nSearch request:\n{query}",
            }
        ],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"Planner declined the request: {resp.stop_details}")
    if resp.parsed_output is None:
        raise RuntimeError(f"Planner returned no plan (stop_reason={resp.stop_reason})")
    return resp.parsed_output
