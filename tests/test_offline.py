"""Offline checks with fake Anthropic and Exa clients: no network, no API keys.

Run: uv run python -m unittest tests/test_offline.py -v
"""

import asyncio
import os
import unittest
from types import SimpleNamespace as NS

os.environ.setdefault("EXA_API_KEY", "test")

from people_research import exa_client as exa_mod
from people_research.config import Settings
from people_research.exa_client import Exa
from people_research.llm import LLM
from people_research.models import Candidate, Criterion, SearchPlan
from people_research.pipeline import run
from people_research.verifier import TOOLS, Verifier

CRITERIA = [
    Criterion(id="profession", label="Profession", requirement="Software engineer", kind="hard", research_hints=""),
    Criterion(id="location", label="Location", requirement="NYC metro", kind="hard", research_hints=""),
]


def tool_use(id_, name, input_):
    return NS(type="tool_use", id=id_, name=name, input=input_)


def submit(id_, status="met", reasoning="Senior SWE at Acme in NYC since 2019 per their LinkedIn."):
    return tool_use(id_, "submit_verdict", {
        "status": status, "confidence": 0.9, "reasoning": reasoning,
        "evidence": [{"url": "https://example.com/p", "quote": "Software Engineer, New York"}],
    })


class FakeMessages:
    """Replays scripted turns per criterion and records every request."""

    def __init__(self, script):
        self.script = script  # criterion id -> list of content lists
        self.calls = []

    async def create(self, **kw):
        self.calls.append(kw)
        crit_id = kw["messages"][0]["content"].split('criterion id="')[1].split('"')[0]
        turn = sum(1 for c in self.calls if f'criterion id="{crit_id}"' in c["messages"][0]["content"]) - 1
        turns = self.script[crit_id]
        content = turns[min(turn, len(turns) - 1)]
        stop = "tool_use" if any(b.type == "tool_use" for b in content) else "end_turn"
        return NS(content=content, stop_reason=stop, stop_details=None)

    async def parse(self, **kw):
        self.calls.append(kw)
        plan = SearchPlan(criteria=CRITERIA, exa_queries=["software engineer in New York City using three.js"])
        return NS(parsed_output=plan, stop_reason="end_turn", stop_details=None)


class FakeAgentRuns:
    """Returns an email for every input row except the last, plus one malformed entry."""

    def __init__(self):
        self.created = []

    async def create(self, **kw):
        self.created.append(kw)
        return NS(id="agent_run_1")

    async def poll_until_finished(self, run_id, **kw):
        rows = self.created[-1]["input"]["data"]
        people = [{"id": r["id"], "email": f"{r['id']}@example.com"} for r in rows[:-1]]
        people.append({"id": rows[-1]["id"], "email": "not-an-email"})
        grounding = [NS(field="structured.people[0].email", citations=[NS(url="https://example.com/cv.pdf")])]
        return NS(status="completed", output=NS(structured={"people": people}, grounding=grounding),
                  cost_dollars=NS(total=0.12))


class FakeExaClient:
    def __init__(self, n_people=25, fail_urls=()):
        self.search_calls, self.contents_calls = [], []
        self.n_people, self.fail_urls = n_people, set(fail_urls)
        self.agent = NS(runs=FakeAgentRuns())

    async def search(self, query, **kw):
        self.search_calls.append({"query": query, **kw})
        if kw.get("category") == "people":
            n = min(kw.get("num_results") or 10, self.n_people)
            return NS(results=[NS(url=f"https://linkedin.com/in/p{i}", title=f"Person {i} - SWE", text="SWE, NYC",
                                  entities=None) for i in range(n)])
        return NS(results=[NS(title="Repo", url="https://github.com/p0", published_date=None, highlights=["three.js"])])

    async def get_contents(self, urls, **kw):
        self.contents_calls.append({"urls": urls, **kw})
        if urls[0] in self.fail_urls:
            return NS(results=[], statuses=[NS(id=urls[0], status="error", source="CRAWL_NOT_FOUND")])
        return NS(results=[NS(text="page text")], statuses=[NS(id=urls[0], status="success", source=None)])


def make(script, exa_client=None):
    settings = Settings()
    llm = LLM(settings)
    fake = FakeMessages(script)
    llm.client = NS(beta=NS(messages=fake))
    exa = Exa(settings)
    exa.client = exa_client or FakeExaClient()
    return settings, llm, fake, exa


class Requirements(unittest.TestCase):
    def test_defaults(self):
        s = Settings()
        self.assertEqual(s.verifier_model, "claude-haiku-5-5")
        self.assertEqual(s.candidates, 10)
        self.assertEqual(s.results_per_query, 10)

    def test_agent_stops_after_submit_and_writes_reasoning(self):
        script = {"profession": [
            [tool_use("t1", "web_search", {"query": "x", "objective": "y"}),
             tool_use("t2", "fetch_page", {"url": "https://example.com/a"})],
            # submit alongside a stray search: the stray call must not run, and no further model call happens
            [submit("t3"), tool_use("t4", "web_search", {"query": "stray", "objective": "stray"})],
            [submit("t5", reasoning="should never be reached")],
        ]}
        settings, llm, fake, exa = make(script)
        v = asyncio.run(Verifier(llm, exa, settings).verify(Candidate(id="1", name="A", profile_url="u"), CRITERIA[0]))

        self.assertEqual(len(fake.calls), 2, "agent made a model call after submit_verdict")
        self.assertEqual([c["query"] for c in exa.client.search_calls], ["x"], "stray tool call ran after submit")
        self.assertEqual(v.status, "met")
        self.assertIn("Acme", v.reasoning)
        self.assertEqual(v.tool_calls, 2)

    def test_not_met_without_lookup_is_sent_back(self):
        script = {"profession": [
            [submit("t1", status="not_met")],                                    # no lookup yet -> sent back
            [tool_use("t2", "web_search", {"query": "x", "objective": "y"})],
            [submit("t3", status="not_met")],                                    # now it has looked -> recorded
        ]}
        settings, llm, fake, exa = make(script)
        v = asyncio.run(Verifier(llm, exa, settings).verify(Candidate(id="1", name="A", profile_url="u"), CRITERIA[0]))
        self.assertEqual(v.status, "not_met")
        self.assertEqual(v.revisions, 1)
        self.assertEqual(v.tool_calls, 1)
        sent_back = fake.calls[1]["messages"][2]["content"][-1]  # user turn after the first submit
        self.assertTrue(sent_back["is_error"])
        self.assertEqual(sent_back["tool_use_id"], "t1")

    def test_insisting_without_support_becomes_unclear(self):
        no_evidence = tool_use("t1", "submit_verdict", {"status": "met", "confidence": 0.9, "reasoning": "r", "evidence": []})
        settings, llm, fake, exa = make({"profession": [[no_evidence], [no_evidence]]})
        v = asyncio.run(Verifier(llm, exa, settings).verify(Candidate(id="1", name="A", profile_url="u"), CRITERIA[0]))
        self.assertEqual(v.status, "unclear")
        self.assertEqual(v.revisions, 1)
        self.assertEqual(len(fake.calls), 2)

    def test_not_met_from_empty_search_needs_two_lookups(self):
        empty = lambda i: tool_use(i, "submit_verdict", {"status": "not_met", "confidence": 0.7,
                                                          "reasoning": "Searched talks; none found.", "evidence": []})
        search = lambda i: tool_use(i, "web_search", {"query": "x", "objective": "y"})
        script = {"profession": [[search("s1")], [empty("t1")], [search("s2")], [empty("t2")]]}
        settings, llm, fake, exa = make(script)
        crit = CRITERIA[0].model_copy(update={"public_record": True})
        v = asyncio.run(Verifier(llm, exa, settings).verify(Candidate(id="1", name="A", profile_url="u"), crit))
        self.assertEqual(v.status, "not_met")      # accepted after the second search
        self.assertEqual(v.revisions, 1)            # first attempt (1 lookup) was sent back
        self.assertIn('public_record="true"', fake.calls[0]["messages"][0]["content"])

    def test_verifier_request_shape(self):
        settings, llm, fake, exa = make({"profession": [[submit("t1")]]})
        asyncio.run(Verifier(llm, exa, settings).verify(Candidate(id="1", name="A", profile_url="u"), CRITERIA[0]))
        req = fake.calls[0]
        self.assertEqual(req["model"], "claude-haiku-5-5")
        self.assertNotIn("fallbacks", req, "Haiku 5.5 has no server-side fallback")
        self.assertEqual(req["output_config"], {"effort": "medium"})
        self.assertNotIn("tool_choice", req)
        reasoning_desc = next(t for t in TOOLS if t["name"] == "submit_verdict")["input_schema"]["properties"]["reasoning"]
        self.assertIn("One or two sentences", reasoning_desc["description"])

    def test_exa_calls_follow_skill(self):
        script = {"profession": [[tool_use("t1", "web_search", {"query": "jane github", "objective": "find repos"})],
                                 [submit("t2")]]}
        settings, llm, fake, exa = make(script)
        asyncio.run(Verifier(llm, exa, settings).verify(Candidate(id="1", name="A", profile_url="u"), CRITERIA[0]))
        call = exa.client.search_calls[0]
        self.assertEqual(call["contents"], {"highlights": True})
        self.assertEqual(call["objective"], "find repos")
        for gated in ("num_results", "category", "include_domains", "exclude_domains", "start_published_date"):
            self.assertNotIn(gated, call)

    def test_fetch_page_failed_status_becomes_tool_error(self):
        script = {"profession": [[tool_use("t1", "fetch_page", {"url": "https://bad.example"})], [submit("t2")]]}
        settings, llm, fake, exa = make(script, FakeExaClient(fail_urls={"https://bad.example"}))
        asyncio.run(Verifier(llm, exa, settings).verify(Candidate(id="1", name="A", profile_url="u"), CRITERIA[0]))
        result = fake.calls[1]["messages"][2]["content"][0]
        self.assertTrue(result["is_error"])
        self.assertIn("CRAWL_NOT_FOUND", result["content"])

    def test_pipeline_end_to_end(self):
        script = {"profession": [[submit("a")]], "location": [[submit("b")]]}
        settings, llm, fake, exa = make(script)
        orig_llm, orig_exa = run.__globals__["LLM"], run.__globals__["Exa"]
        run.__globals__["LLM"], run.__globals__["Exa"] = (lambda s: llm), (lambda s: exa)
        try:
            report = asyncio.run(run("SWE in NYC", settings))
        finally:
            run.__globals__["LLM"], run.__globals__["Exa"] = orig_llm, orig_exa

        people = [c for c in exa.client.search_calls if c.get("category") == "people"]
        self.assertTrue(all(c["num_results"] == 10 for c in people))
        self.assertEqual(len(report.results), 10)
        self.assertTrue(all(r.qualified for r in report.results))
        self.assertTrue(all(v.reasoning for r in report.results for v in r.verdicts))
        planner = fake.calls[0]
        self.assertEqual(planner["model"], "claude-opus-5-5")
        self.assertEqual(planner["fallbacks"], "default")
        self.assertTrue(all(r.contact.linkedin_url == r.candidate.profile_url for r in report.results))
        self.assertEqual(report.email_lookup_cost, 0.12)

    def test_email_lookup_only_for_qualified(self):
        # profession passes for everyone; location fails for p1 and p3
        script = {"profession": [[submit("a")]], "location": [[submit("b")]]}
        settings, llm, fake, exa = make(script)
        settings.candidates = 4
        orig = FakeMessages.create

        async def create(self_, **kw):
            resp = await orig(self_, **kw)
            prompt = kw["messages"][0]["content"]
            if 'criterion id="location"' in prompt and ("in/p1\n" in prompt or "in/p3\n" in prompt):
                resp.content = [submit("x", status="not_met")]
            return resp

        FakeMessages.create = create
        orig_llm, orig_exa = run.__globals__["LLM"], run.__globals__["Exa"]
        run.__globals__["LLM"], run.__globals__["Exa"] = (lambda s: llm), (lambda s: exa)
        try:
            report = asyncio.run(run("SWE in NYC", settings))
        finally:
            FakeMessages.create = orig
            run.__globals__["LLM"], run.__globals__["Exa"] = orig_llm, orig_exa

        rows = exa.client.agent.runs.created[0]["input"]["data"]
        qualified = {r.candidate.id for r in report.results if r.qualified}
        self.assertEqual({r["id"] for r in rows}, qualified)
        self.assertEqual(len(qualified), 2)
        req = exa.client.agent.runs.created[0]
        self.assertEqual(req["effort"], "auto")
        self.assertEqual(req["budget"], {"max_cost_dollars": settings.enrich_budget_dollars})
        by_id = {r.candidate.id: r.contact for r in report.results}
        first, last = rows[0]["id"], rows[-1]["id"]
        self.assertEqual(by_id[first].email_status, "found")
        self.assertEqual(by_id[first].email_source, "https://example.com/cv.pdf")
        self.assertEqual(by_id[last].email_status, "not_found", "malformed email should be rejected")
        unqualified = [r for r in report.results if not r.qualified]
        self.assertTrue(all(r.contact.email_status == "not_requested" for r in unqualified))


if __name__ == "__main__":
    unittest.main()
