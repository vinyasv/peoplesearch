"""Grade raw runs against the answer key (no API calls).

    uv run python eval/grade.py            # writes results.jsonl per variant, review.md, prints summary

Answer key = the Opus reference verdict for each case (reference/raw.jsonl, rep 0), overridden by any
human decisions in key_overrides.json: {"<case id>": {"status": "met|not_met|unclear", "note": "..."}}.
"""

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run_eval import check_citations  # noqa: E402

FLOW = Path(__file__).parent / "results"
HERE = Path(__file__).parent
VARIANTS = {"baseline": "Haiku 5.5", "v1": "Sonnet 5.5", "v2": "Haiku + rules", "v3": "Haiku + policy"}

# $/MTok (input, output). Cache writes 1.25x input, reads 0.1x input.
PRICES = {"claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.0, 10.0), "claude-opus-5-5": (4.0, 20.0)}
EXA_PER_SEARCH = 0.007 + 10 * 0.001  # auto search + highlights on ~10 results
EXA_PER_FETCH = 0.001


def llm_cost(model: str, u: dict) -> float:
    pin, pout = next((p for m, p in PRICES.items() if model.startswith(m)), (0, 0))
    return (u["input_tokens"] * pin + u["output_tokens"] * pout
            + u["cache_creation_input_tokens"] * pin * 1.25 + u["cache_read_input_tokens"] * pin * 0.1) / 1e6


def load(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []


KEY_CHANGES: list[str] = []  # filled by answer_key(); printed in the summary


def answer_key() -> dict[str, dict]:
    key = {r["prompt_id"]: {"status": r["verdict"]["status"], "source": "opus", "verdict": r["verdict"]}
           for r in load(FLOW / "reference" / "raw.jsonl") if r["rep"] == 0}
    # "Finding nothing" policy: Opus re-decided the cases the policy can change (reference_policy/).
    # Only accept the changes the policy explains; anything else means Opus disagreed with itself.
    public = {c["id"]: c["criterion"].get("public_record", False)
              for c in map(json.loads, (HERE / "cases.jsonl").read_text().splitlines())}
    for r in load(FLOW / "reference_policy" / "raw.jsonl"):
        cid, old, new = r["prompt_id"], key[r["prompt_id"]]["status"], r["verdict"]["status"]
        explained = (public[cid] and old == "unclear" and new == "not_met") or \
                    (not public[cid] and old == "not_met" and new == "unclear")
        if explained:
            key[cid] = {"status": new, "source": "opus (policy)", "verdict": r["verdict"]}
            KEY_CHANGES.append(f"{cid}: {old} -> {new}")
        elif new != old:
            KEY_CHANGES.append(f"{cid}: Opus now says {new}, kept {old} (not a policy change; flagged for review)")
            key[cid]["unstable"] = r["verdict"]
    overrides = HERE / "key_overrides.json"
    if overrides.exists():
        for cid, o in json.loads(overrides.read_text()).items():
            key.setdefault(cid, {})
            key[cid].update({"status": o["status"], "source": "human", "note": o.get("note", "")})
    return key


def grade_row(r: dict, key_status: str) -> dict:
    pred = r["verdict"]["status"]
    cites = r["citations"]
    if cites:
        cites_ok = sum(c["supported"] for c in cites) / len(cites)
    else:  # a met/not-met verdict must cite something; "unclear" with nothing found has nothing to get wrong
        cites_ok = 1.0 if pred == "unclear" else 0.0
    return {
        "correct": float(pred == key_status),
        "false_met": float(pred == "met" and key_status != "met"),
        "false_not_met": float(pred == "not_met" and key_status == "met"),
        "cites_ok": cites_ok,
        "no_lookup_not_met": float(pred == "not_met" and r["tool_calls"] == 0),
    }


def _consistency(rows: list[dict]) -> float:
    per = defaultdict(set)
    reps = defaultdict(int)
    for r in rows:
        per[r["prompt_id"]].add(r["verdict"]["status"])
        reps[r["prompt_id"]] += 1
    multi = [cid for cid in per if reps[cid] > 1]
    return sum(len(per[c]) == 1 for c in multi) / max(1, len(multi))


def wilson(k: float, n: int) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p, z = k / n, 1.96
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def main():
    key = answer_key()
    if not key:
        raise SystemExit("No reference run yet: run run_eval.py --variant reference first.")
    summary, by_case = {}, defaultdict(dict)
    for variant, label in VARIANTS.items():
        raw = load(FLOW / variant / "raw.jsonl")
        if not raw:
            continue
        rows = []
        for r in raw:
            if r["prompt_id"] not in key:
                continue
            k = key[r["prompt_id"]]["status"]
            seen_file = FLOW / variant / "seen" / f'{r["prompt_id"]}_rep{r["rep"]}.json'
            if seen_file.exists():  # re-check citations with the current checker
                r["citations"] = check_citations(r["verdict"]["evidence"], json.loads(seen_file.read_text()))
            r = {**r, "grade": grade_row(r, k), "expected": k}
            r["cost_usd"] = round(llm_cost(r["model"], r["usage"]) + r["web_searches"] * EXA_PER_SEARCH
                                  + r["page_fetches"] * EXA_PER_FETCH, 5)
            r["llm_cost_usd"] = round(llm_cost(r["model"], r["usage"]), 5)
            rows.append(r)
            by_case[r["prompt_id"]].setdefault(variant, []).append(r)
        with open(FLOW / variant / "results.jsonl", "w") as f:
            for r in rows:
                f.write(json.dumps({k: v for k, v in r.items() if k not in ("verdict", "citations")}
                                   | {"verdict_status": r["verdict"]["status"]}) + "\n")
        n = len(rows)
        correct = sum(r["grade"]["correct"] for r in rows)
        key_not_met = [r for r in rows if r["expected"] != "met"]
        key_met = [r for r in rows if r["expected"] == "met"]
        summary[label] = {
            "attempts": n,
            "accuracy": correct / n,
            "accuracy_ci": wilson(correct, n),
            "false_met_rate": sum(r["grade"]["false_met"] for r in key_not_met) / max(1, len(key_not_met)),
            "false_not_met_rate": sum(r["grade"]["false_not_met"] for r in key_met) / max(1, len(key_met)),
            "cites_ok": sum(r["grade"]["cites_ok"] for r in rows) / n,
            "no_lookup_not_met": int(sum(r["grade"]["no_lookup_not_met"] for r in rows)),
            "decisive_no_evidence": sum(1 for r in rows if r["verdict"]["status"] != "unclear" and not r["verdict"]["evidence"]),
            "quotes_supported": sum(c["supported"] for r in rows for c in r["citations"])
            / max(1, sum(len(r["citations"]) for r in rows)),
            "non_linkedin_source": sum(r["non_linkedin_source"] for r in rows) / n,
            "tool_calls": sum(r["tool_calls"] for r in rows) / n,
            "llm_cost": sum(r["llm_cost_usd"] for r in rows) / n,
            "total_cost": sum(r["cost_usd"] for r in rows) / n,
            "latency": sorted(r["latency_s"] for r in rows)[n // 2],
            "same_both_runs": _consistency(rows),
            "errors": len(load(FLOW / variant / "errors.jsonl")),
        }

    ref = load(FLOW / "reference" / "raw.jsonl")
    if ref:
        ref_cost = sum(llm_cost(r["model"], r["usage"]) + r["web_searches"] * EXA_PER_SEARCH
                       + r["page_fetches"] * EXA_PER_FETCH for r in ref)
        print(f"Reference (Opus 5.5): {len(ref)} cases, ${ref_cost:.2f} total, ${ref_cost / len(ref):.3f}/case")

    # Review file: every case where a model disagrees with the key
    cases = {c["id"]: c for c in map(json.loads, (HERE / "cases.jsonl").read_text().splitlines())}
    lines = ["# Answer key review", "",
             "Cases where Haiku or Sonnet disagree with the answer key. For each, decide the right verdict.", ""]
    n_dis = 0
    for cid, per in by_case.items():
        k = key[cid]
        if all(r["verdict"]["status"] == k["status"] for rs in per.values() for r in rs):
            continue
        n_dis += 1
        c = cases[cid]
        lines += [f"## {n_dis}. {c['candidate']['name']}: {c['criterion']['label']}", "",
                  f"`{cid}`", "", f"**Requirement:** {c['criterion']['requirement']}", "",
                  f"**Answer key ({k['source']}): {k['status'].replace('_', ' ')}**"]
        if k.get("verdict"):
            lines.append(f"> {k['verdict']['reasoning']}")
            lines += [f"> - {e['url']}" for e in k["verdict"]["evidence"][:3]]
        for variant, label in VARIANTS.items():
            for r in per.get(variant, []):
                v = r["verdict"]
                lines += ["", f"**{label}, run {r['rep'] + 1}: {v['status'].replace('_', ' ')}** "
                          f"({v['confidence']:.2f}, {r['tool_calls']} lookups)", f"> {v['reasoning']}"]
                lines += [f"> - {e['url']}" for e in v["evidence"][:3]]
        lines.append("")
    (HERE / "review.md").write_text("\n".join(lines))

    print(f"\n{'':<24}" + "".join(f"{lbl:>16}" for lbl in summary))
    fmt = {
        "attempts": "{:.0f}", "accuracy": "{:.0%}", "false_met_rate": "{:.0%}", "false_not_met_rate": "{:.0%}",
        "cites_ok": "{:.0%}", "quotes_supported": "{:.0%}", "decisive_no_evidence": "{:.0f}", "no_lookup_not_met": "{:.0f}", "non_linkedin_source": "{:.0%}",
        "same_both_runs": "{:.0%}", "tool_calls": "{:.1f}", "llm_cost": "${:.4f}", "total_cost": "${:.4f}", "latency": "{:.0f}s", "errors": "{:.0f}",
    }
    for k, f in fmt.items():
        print(f"{k:<24}" + "".join(f"{f.format(s[k]):>16}" for s in summary.values()))
    for lbl, s in summary.items():
        lo, hi = s["accuracy_ci"]
        print(f"{lbl} accuracy 95% CI: {lo:.0%}-{hi:.0%}")
    print(f"\n{n_dis} cases disagree with the key -> eval/review.md")
    if KEY_CHANGES:
        print("\nAnswer key changes from the policy re-check:")
        for c in KEY_CHANGES:
            print("  " + c)


if __name__ == "__main__":
    main()
