import asyncio
from collections.abc import Callable

from .config import Settings
from .enrich import enrich_emails
from .exa_client import Exa, source_candidates
from .llm import LLM
from .models import Candidate, CandidateReport, Criterion, RunReport, SearchPlan, Verdict
from .planner import plan_search
from .verifier import Verifier

WEIGHT = {"hard": 2.0, "soft": 1.0}

# (event, payload) -> None; lets the CLI show progress without the pipeline knowing about rich.
Progress = Callable[[str, dict], None]


def score_candidate(criteria: list[Criterion], verdicts: list[Verdict]) -> tuple[bool, float]:
    by_id = {v.criterion_id: v for v in verdicts}
    qualified = all(by_id[c.id].status == "met" for c in criteria if c.kind == "hard")
    total = sum(WEIGHT[c.kind] for c in criteria)
    got = 0.0
    for c in criteria:
        v = by_id[c.id]
        if v.status == "met":
            got += WEIGHT[c.kind] * v.confidence
        elif v.status in ("unclear", "error"):
            got += WEIGHT[c.kind] * 0.3
    return qualified, round(got / total, 3) if total else 0.0


async def research_candidate(
    verifier: Verifier, settings: Settings, candidate: Candidate, criteria: list[Criterion], progress: Progress
) -> CandidateReport:
    """One independent agent per criterion, run concurrently. If a hard criterion comes back
    confidently not met, the remaining agents for this candidate are cancelled."""
    tasks = {asyncio.create_task(verifier.verify(candidate, c)): c for c in criteria}
    verdicts: dict[str, Verdict] = {}
    pending = set(tasks)
    while pending:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        for t in done:
            crit = tasks[t]
            try:
                v = t.result()
            except Exception as e:  # keep one failing agent from sinking the candidate
                v = Verdict(criterion_id=crit.id, status="error", reasoning=repr(e))
            verdicts[crit.id] = v
            progress("verdict", {"candidate": candidate, "criterion": crit, "verdict": v})
            if (
                settings.early_stop
                and crit.kind == "hard"
                and v.status == "not_met"
                and v.confidence >= settings.early_stop_confidence
                and pending
            ):
                for p in pending:
                    p.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                for p in pending:
                    verdicts[tasks[p].id] = Verdict(
                        criterion_id=tasks[p].id, status="skipped", reasoning=f"Skipped: '{crit.label}' not met."
                    )
                pending = set()

    ordered = [verdicts[c.id] for c in criteria]
    qualified, score = score_candidate(criteria, ordered)
    report = CandidateReport(candidate=candidate, verdicts=ordered, qualified=qualified, score=score)
    progress("candidate_done", {"report": report})
    return report


async def run(query: str, settings: Settings, progress: Progress = lambda *_: None, plan: SearchPlan | None = None) -> RunReport:
    llm = LLM(settings)
    exa = Exa(settings)

    if plan is None:
        progress("stage", {"stage": "planning"})
        plan = await plan_search(llm, settings, query)
    progress("plan", {"plan": plan})

    progress("stage", {"stage": "sourcing"})
    candidates = await source_candidates(exa, plan.exa_queries, settings.results_per_query, settings.candidates)
    progress("sourced", {"candidates": candidates})
    progress("stage", {"stage": "researching"})

    verifier = Verifier(llm, exa, settings)
    reports = await asyncio.gather(
        *(research_candidate(verifier, settings, c, plan.criteria, progress) for c in candidates)
    )
    reports.sort(key=lambda r: (r.qualified, r.score), reverse=True)

    if settings.enrich_emails != "off" and any(settings.enrich_emails == "all" or r.qualified for r in reports):
        progress("stage", {"stage": "contacts"})
    try:
        cost = await enrich_emails(exa.client, settings, reports)
    except Exception as e:  # a failed lookup shouldn't throw away the research
        cost = None
        progress("warning", {"message": f"Email lookup failed: {e}"})
    progress("contacts", {"reports": reports, "cost": cost})
    return RunReport(query=query, plan=plan, results=reports, email_lookup_cost=cost)
