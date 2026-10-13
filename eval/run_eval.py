"""Run the verifier agent over the frozen eval cases and record raw outcomes.

    uv run python eval/run_eval.py --variant reference --model claude-opus-5-5 --effort high --max-turns 14
    uv run python eval/run_eval.py --variant baseline  --model claude-haiku-5-5 --reps 2
    uv run python eval/run_eval.py --variant v1        --model claude-sonnet-5-5 --reps 2

Writes eval/results/<variant>/{raw.jsonl, traces/, seen/, errors.jsonl}. Grading against
the answer key is a separate, free step (grade.py), so the key can change after review without re-running.
Rows are written as each case finishes; re-running skips (case, rep) pairs already in raw.jsonl.
"""

import argparse
import asyncio
import json
import random
import re
import sys
import time
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from people_research.config import Settings  # noqa: E402
from people_research.exa_client import Exa, normalize_url  # noqa: E402
from people_research.llm import LLM  # noqa: E402
from people_research.models import Candidate, Criterion  # noqa: E402
from people_research.verifier import AgentTrace, Verifier  # noqa: E402

CASES = Path(__file__).parent / "cases.jsonl"
OUT = Path(__file__).parent / "results"


# ---------- citation check ----------

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def _ngrams(words: list[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def quote_supported(quote: str, doc: str) -> bool:
    """Verbatim match, or a reformatted one: agents stitch profile lines together ("Title - Company (Current)").
    A fragment passes if >=85% of its words and >=40% of its word pairs appear in the doc.
    Each '...'-separated fragment must pass on its own."""
    doc_n = _norm(doc)
    doc_words = re.findall(r"\w+", doc_n)
    doc_uni, doc_bi = set(doc_words), _ngrams(doc_words, 2)
    frags = [f for f in re.split(r"\s*(?:\.\.\.|…)\s*", _norm(quote)) if len(f) > 8]
    if not frags:
        return False
    for f in frags:
        if f in doc_n:
            continue
        words = re.findall(r"\w+", f)
        bi = _ngrams(words, 2)
        if not words or not bi:
            return False
        if sum(w in doc_uni for w in words) / len(words) < 0.85 or len(bi & doc_bi) / len(bi) < 0.4:
            return False
    return True


def check_citations(evidence: list[dict], seen: dict[str, str]) -> list[dict]:
    """A citation holds if its URL was shown to the agent (as a page, a search result, or a link inside one)
    and the quote appears on that page. When the URL only appeared as a link (e.g. a post linked from a
    profile), the quote may come from the page that showed the link."""
    by_url = {}
    for u, text in seen.items():
        by_url.setdefault(normalize_url(u), []).append(text)
    out = []
    for e in evidence:
        key = normalize_url(e["url"])
        docs = by_url.get(key)
        if docs is None:
            docs = [t for t in seen.values() if key and key in normalize_url_text(t)]
        out.append({
            "url": e["url"],
            "url_seen": bool(docs),
            "supported": bool(docs) and any(quote_supported(e["quote"], d) for d in docs),
        })
    return out


def normalize_url_text(text: str) -> str:
    """Lower-cased text with URL schemes and 'www.' stripped, so normalize_url() keys can be searched in it."""
    return re.sub(r"https?://(www\.)?", "", (text or "").lower())


# ---------- runner ----------

def case_prompt(c: dict) -> str:
    cr = c["criterion"]
    return f"{c['candidate']['name']} | {cr['label']}: {cr['requirement']}"


async def run_one(verifier: Verifier, case: dict, rep: int, args, variant_dir: Path, lock: asyncio.Lock):
    cand = Candidate(**case["candidate"])
    crit = Criterion(**case["criterion"])
    trace = AgentTrace()
    t0 = time.monotonic()
    err_class = None
    verdict = None
    for attempt in range(3):
        try:
            verdict = await asyncio.wait_for(verifier.verify(cand, crit, trace), timeout=args.timeout_s)
            break
        except TimeoutError:
            err_class = "timeout"
            break
        except (anthropic.RateLimitError, anthropic.InternalServerError, anthropic.APIConnectionError) as e:
            err_class = f"api_error: {type(e).__name__}"
            await asyncio.sleep(2 ** attempt * 5 + random.random() * 5)
            trace = AgentTrace()
        except Exception as e:  # harness failure, not a model failure
            err_class = f"harness: {type(e).__name__}: {e}"
            break
    latency = round(time.monotonic() - t0, 1)

    served = sorted(set(trace.models))
    async with lock:
        if verdict is None:
            with open(variant_dir / "errors.jsonl", "a") as f:
                f.write(json.dumps({"prompt_id": case["id"], "rep": rep, "class": err_class,
                                    "model": served, "usage": trace.usage}) + "\n")
            print(f"  ERROR {case['id']} rep{rep}: {err_class or 'no verdict'}")
            return
        if any(not m.startswith(args.model) for m in served):
            with open(variant_dir / "errors.jsonl", "a") as f:
                f.write(json.dumps({"prompt_id": case["id"], "rep": rep, "class": "model_mismatch",
                                    "model": served, "usage": trace.usage}) + "\n")
            print(f"  MODEL MISMATCH {case['id']}: {served}")
            return

        ev = [e.model_dump() for e in verdict.evidence]
        cites = check_citations(ev, trace.seen)
        searches = sum(1 for t in trace.turns if t.get("role") == "tool_call" and t.get("name") == "web_search")
        fetches = sum(1 for t in trace.turns if t.get("role") == "tool_call" and t.get("name") == "fetch_page")
        row = {
            "prompt_id": case["id"], "rep": rep, "prompt": case_prompt(case), "tags": case["tags"],
            "model": served[0] if served else args.model, "effort": args.effort,
            "usage": trace.usage, "latency_s": latency, "tool_calls": verdict.tool_calls,
            "web_searches": searches, "page_fetches": fetches,
            "stop_reason": trace.stop_reason, "status": "truncated" if trace.stop_reason == "max_tokens" else "ok",
            "verdict": verdict.model_dump(), "citations": cites,
            "non_linkedin_source": any("linkedin.com" not in normalize_url(e["url"]) for e in ev),
        }
        traces = variant_dir / "traces"
        traces.mkdir(exist_ok=True)
        (traces / f"{case['id']}_rep{rep}.json").write_text(json.dumps(
            trace.turns + [{"role": "assistant", "content": json.dumps(verdict.model_dump(), indent=2)}], indent=1))
        seen_dir = variant_dir / "seen"
        seen_dir.mkdir(exist_ok=True)
        (seen_dir / f"{case['id']}_rep{rep}.json").write_text(json.dumps(trace.seen))
        with open(variant_dir / "raw.jsonl", "a") as f:
            f.write(json.dumps(row) + "\n")
        ok = sum(c["supported"] for c in cites)
        print(f"  {case['id']:<58} rep{rep} {verdict.status:<8} conf={verdict.confidence:.2f} "
              f"tools={verdict.tool_calls} cites={ok}/{len(cites)} {latency}s")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", required=True, help="reference | baseline | v1 ...")
    ap.add_argument("--model", required=True)
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--max-turns", type=int, default=8)
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--only", nargs="*", help="case ids to run (default: all)")
    ap.add_argument("--limit", type=int, help="first N cases only (for a pilot)")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--timeout-s", type=float, default=420)
    args = ap.parse_args()

    cases = [json.loads(line) for line in CASES.read_text().splitlines() if line.strip()]
    if args.only:
        cases = [c for c in cases if c["id"] in set(args.only)]
    if args.limit:
        cases = cases[: args.limit]

    variant_dir = OUT / args.variant
    variant_dir.mkdir(parents=True, exist_ok=True)
    raw = variant_dir / "raw.jsonl"
    done = set()
    if raw.exists():
        done = {(r["prompt_id"], r["rep"]) for r in map(json.loads, raw.read_text().splitlines()) if r}

    settings = Settings()
    settings.verifier_model = args.model
    settings.verifier_effort = args.effort
    settings.max_agent_turns = args.max_turns
    settings.llm_concurrency = args.concurrency
    verifier = Verifier(LLM(settings), Exa(settings), settings)

    todo = [(c, r) for c in cases for r in range(args.reps) if (c["id"], r) not in done]
    print(f"{args.variant}: {args.model} effort={args.effort} max_turns={args.max_turns}, "
          f"{len(todo)} attempts to run ({len(done)} already done)")
    lock = asyncio.Lock()
    sem = asyncio.Semaphore(args.concurrency)
    t0 = time.monotonic()

    async def bounded(c, r):
        async with sem:
            await run_one(verifier, c, r, args, variant_dir, lock)

    await asyncio.gather(*(bounded(c, r) for c, r in todo))
    print(f"done in {time.monotonic() - t0:.0f}s")


if __name__ == "__main__":
    asyncio.run(main())
