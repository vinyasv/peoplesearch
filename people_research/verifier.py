import asyncio
import json
from dataclasses import dataclass, field
from datetime import date

from .config import Settings
from .exa_client import Exa
from .llm import LLM
from .models import Candidate, Criterion, Evidence, Verdict

VERIFIER_SYSTEM = f"""You are a meticulous people researcher. You are given one candidate and one \
criterion. Decide whether the candidate meets that criterion, based only on evidence you find.

Today's date: {date.today().isoformat()}

How to work:
- Start from the candidate profile provided. If it already settles the criterion conclusively, \
call submit_verdict right away without searching.
- Otherwise use web_search and fetch_page to find corroborating sources: GitHub, personal sites, \
portfolios, conference talks, blog posts, company team pages, package registries. Run independent \
searches in parallel when that helps.
- Identity matters. Before using a source, check that it is about this same person (name plus \
employer, location, handle, or linked profile). Common names collide; discard sources you can't \
tie to the candidate.
- For durations ("4+ years"), compute from dated roles. Count overlapping roles once, exclude \
internships and education unless the criterion says otherwise, and treat an open-ended current \
role as running until today.
- When you can't find evidence, what that means depends on the criterion's public_record flag:
  - public_record="true" (talks, papers, funding rounds, acquisitions, repos): these leave a trace. \
If at least two targeted searches with different wording, aimed at the right person, find nothing, \
submit not_met and say what you searched for. Use unclear only when the evidence conflicts or you \
can't tell which person a source is about.
  - public_record="false": the fact may simply be unpublished. Finding nothing means unclear; use \
not_met only when evidence points against the criterion (e.g. based in another city, too few years).
- Evidence quotes must be short verbatim excerpts from pages you saw, with their URL. A not_met \
that rests on finding nothing may have no evidence; its reasoning names what you searched for.
- Be economical: a few targeted searches beat many broad ones.
- Finish by calling submit_verdict, alone, once. It is the only way your answer is recorded, and it \
ends your task: don't call other tools in the same turn, and do nothing after it.
- `reasoning` is shown to a recruiter scanning a results table, one line per criterion, so keep it \
to one or two sentences (about 40 words at most). State the deciding fact and its source, e.g. \
"Senior SWE at Stripe in NYC since 2019, per their LinkedIn." Leave out your working (month-by-month \
arithmetic, roles you ruled out). Express doubt through `confidence`, or in a short clause if it \
matters to the reader.

Confidence: 0.9+ when a primary source states it directly; 0.6-0.8 when it is inferred from \
strong indirect evidence; below 0.5 means you are mostly guessing."""

TOOLS = [
    {
        "name": "web_search",
        "description": "Search the live web with Exa. Returns titles, URLs, dates and relevant highlights.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural-language search query."},
                "objective": {
                    "type": "string",
                    "description": "Goal for this search turn; say which documents should rank first, which should "
                    "be excluded, and what specific facts or figures to pull from them.",
                },
            },
            "required": ["query", "objective"],
            "additionalProperties": False,
        },
    },
    {
        "name": "fetch_page",
        "description": "Fetch the main text of a web page (truncated to ~8k characters).",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
            "additionalProperties": False,
        },
    },
    {
        "name": "submit_verdict",
        "description": "Record your final verdict for this criterion. Call exactly once. This ends your task.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["met", "not_met", "unclear"]},
                "confidence": {"type": "number", "description": "0.0 to 1.0"},
                "reasoning": {
                    "type": "string",
                    "description": "One or two sentences (about 40 words at most) on why the criterion is met, not "
                    "met, or unclear: the deciding fact and its source, without your working.",
                },
                "evidence": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"url": {"type": "string"}, "quote": {"type": "string"}},
                        "required": ["url", "quote"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["status", "confidence", "reasoning", "evidence"],
            "additionalProperties": False,
        },
    },
]


def verdict_problem(v: dict, tool_calls: int) -> str | None:
    """Rules a verdict must meet before it's recorded. Returns what's wrong, or None."""
    if v["status"] == "met" and not v["evidence"]:
        return ("a met verdict must cite at least one source with a short quote. "
                "Add evidence, or submit unclear if you found none.")
    # not_met can rest on a thorough search that found nothing (public-record criteria), but not on nothing.
    if v["status"] == "not_met" and not v["evidence"] and tool_calls < 2:
        return ("a not_met verdict needs either a source that contradicts the criterion, or at least two "
                "targeted searches that found nothing. Search again, or submit unclear.")
    if v["status"] == "not_met" and tool_calls == 0:
        return ("you concluded not_met without any web lookup. The profile may simply leave this out. "
                "Run at least one web_search to check, then submit again.")
    return None


def _candidate_brief(c: Candidate) -> str:
    parts = [
        f"Name: {c.name}",
        f"Profile URL: {c.profile_url}",
        f"Headline: {c.headline or 'n/a'}",
        f"Location: {c.location or 'n/a'}",
    ]
    if c.work_history:
        parts.append("Structured work history:\n" + json.dumps(c.work_history, indent=1))
    if c.profile_text:
        parts.append("Profile page text:\n" + c.profile_text)
    return "\n".join(parts)


@dataclass
class AgentTrace:
    """Optional recorder for evals: the conversation, every page the agent saw, and token usage."""

    turns: list[dict] = field(default_factory=list)
    seen: dict[str, str] = field(default_factory=dict)  # url -> text shown to the agent
    usage: dict[str, int] = field(default_factory=lambda: {
        "input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0})
    models: list[str] = field(default_factory=list)
    stop_reason: str | None = None

    def add_usage(self, resp) -> None:
        self.models.append(resp.model)
        self.stop_reason = resp.stop_reason
        for k in self.usage:
            self.usage[k] += getattr(resp.usage, k, 0) or 0


class Verifier:
    def __init__(self, llm: LLM, exa: Exa, settings: Settings):
        self.llm = llm
        self.exa = exa
        self.settings = settings
        self.llm_sem = asyncio.Semaphore(settings.llm_concurrency)

    async def _run_tool(self, name: str, args: dict, trace: AgentTrace | None = None) -> str:
        if name == "web_search":
            results = await self.exa.web_search(args["query"], args["objective"])
            if trace is not None:
                for r in results:
                    trace.seen.setdefault(r["url"], "")
                    trace.seen[r["url"]] += "\n" + (r["title"] or "") + "\n" + "\n".join(r["highlights"])
            return json.dumps(results)
        if name == "fetch_page":
            text = await self.exa.fetch_page(args["url"])
            if trace is not None:
                trace.seen[args["url"]] = trace.seen.get(args["url"], "") + "\n" + text
            return text
        raise ValueError(f"unknown tool {name}")

    async def _tool_results(self, tool_uses: list, trace: AgentTrace | None) -> list[dict]:
        outputs = await asyncio.gather(*(self._run_tool(b.name, b.input, trace) for b in tool_uses), return_exceptions=True)
        results: list[dict] = []
        for block, out in zip(tool_uses, outputs):
            if trace is not None:
                trace.turns.append({"role": "tool_result", "content": f"Error: {out}" if isinstance(out, BaseException) else out[:4000]})
            if isinstance(out, BaseException):
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": f"Error: {out}", "is_error": True})
            else:
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": out})
        return results

    async def verify(self, candidate: Candidate, criterion: Criterion, trace: AgentTrace | None = None) -> Verdict:
        prompt = (
            f"<candidate>\n{_candidate_brief(candidate)}\n</candidate>\n\n"
            f"<criterion id=\"{criterion.id}\" kind=\"{criterion.kind}\" "
            f"public_record=\"{str(criterion.public_record).lower()}\">\n"
            f"{criterion.label}: {criterion.requirement}\n"
            f"Research hints: {criterion.research_hints}\n</criterion>\n\n"
            "Decide whether this candidate meets the criterion, then call submit_verdict."
        )
        messages: list[dict] = [{"role": "user", "content": prompt}]
        tool_calls = 0
        revisions = 0
        if trace is not None:
            trace.turns += [{"role": "system", "content": VERIFIER_SYSTEM}, {"role": "user", "content": prompt}]
            trace.seen[candidate.profile_url] = _candidate_brief(candidate)
        max_turns = self.settings.max_agent_turns

        for turn in range(max_turns):
            async with self.llm_sem:
                resp = await self.llm.create(
                    model=self.settings.verifier_model,
                    effort=self.settings.verifier_effort,
                    system=VERIFIER_SYSTEM,
                    tools=TOOLS,
                    messages=messages,
                )

            if trace is not None:
                trace.add_usage(resp)
                for b in resp.content:
                    if b.type == "text" and b.text.strip():
                        trace.turns.append({"role": "assistant", "content": b.text})
                    elif b.type == "tool_use":
                        trace.turns.append({"role": "tool_call", "name": b.name, "content": json.dumps(b.input, indent=2)})

            if resp.stop_reason == "refusal":
                return Verdict(criterion_id=criterion.id, status="error", reasoning=f"Model declined: {resp.stop_details}", tool_calls=tool_calls)

            messages.append({"role": "assistant", "content": resp.content})
            tool_uses = [b for b in resp.content if b.type == "tool_use"]

            # submit_verdict ends the agent: return without running any other tool calls from this turn
            # and without another model call, unless the verdict breaks a submission rule.
            submit = next((b for b in tool_uses if b.name == "submit_verdict"), None)
            if submit is not None:
                v = submit.input
                problem = verdict_problem(v, tool_calls)
                if problem is None or revisions >= 1 or turn == max_turns - 1:
                    status, reasoning = v["status"], v["reasoning"]
                    if problem:  # still unsupported after one send-back: don't record it as decisive
                        status, reasoning = "unclear", f"{reasoning} [Recorded as unclear: {problem.split('.')[0]}.]"
                    return Verdict(
                        criterion_id=criterion.id,
                        status=status,
                        confidence=max(0.0, min(1.0, float(v["confidence"]))),
                        reasoning=reasoning,
                        evidence=[Evidence(**e) for e in v["evidence"]],
                        tool_calls=tool_calls,
                        revisions=revisions,
                    )
                # Send it back: run any research calls from this turn, and answer the submit with the problem.
                revisions += 1
                others = [b for b in tool_uses if b is not submit]
                tool_calls += len(others)
                results = await self._tool_results(others, trace)
                results.append({"type": "tool_result", "tool_use_id": submit.id, "is_error": True,
                                "content": f"Verdict not recorded: {problem}"})
                if trace is not None:
                    trace.turns.append({"role": "tool_result", "content": f"Verdict not recorded: {problem}"})
                messages.append({"role": "user", "content": results})
                continue

            if not tool_uses:
                messages.append({"role": "user", "content": "Call submit_verdict now with your best judgment."})
                continue

            tool_calls += len(tool_uses)
            results = await self._tool_results(tool_uses, trace)
            if turn == max_turns - 2:
                results.append({"type": "text", "text": "Research budget is nearly used up. Call submit_verdict on your next turn."})
            messages.append({"role": "user", "content": results})

        return Verdict(
            criterion_id=criterion.id,
            status="unclear",
            reasoning=f"Agent did not submit a verdict within {max_turns} turns.",
            tool_calls=tool_calls,
        )
