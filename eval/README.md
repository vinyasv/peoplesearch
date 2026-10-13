# Verifier eval: Haiku 5.5 vs Sonnet 5.5

Run on 2026-10-13. It measures how well the research subagent decides one hard requirement for one person.

- **Cases:** 50 frozen tasks from two hard searches, listed in `cases.md`. 40 come from the acquisition / early-employee / infra-talk query and 10 from the London ML-researcher query.
- **Answer key:** an Opus 5.5 agent at high effort with up to 14 turns. It is not yet human-reviewed; the 8 cases where the models disagree are in `review.md`.
- **Runs:** 2 per case per model.

## Result

| | Haiku 5.5 | Sonnet 5.5 |
|---|---|---|
| Matches answer key | 92% (85–96%) | 92% (85–96%) |
| Wrongly passes someone | 4% | 2% |
| Wrongly drops someone | 6% | 2% |
| Quotes found on a page the agent saw | 99% | 99% |
| "Met"/"not met" with no evidence | 0 | 5 |
| "Not met" with no web lookup | 2 | 3 |
| Cites a non-LinkedIn source | 90% | 55% |
| Web lookups per check | 1.8 | 0.9 |
| Cost per check (Claude + Exa) | $0.032 | $0.046 |
| Typical time per check | 10s | 7s |

### v2: Haiku + verdict rules (same day)

The code now sends a verdict back once if it says "not met" without any web lookup, or "met"/"not met" without evidence (`verdict_problem()` in `people_research/verifier.py`).

| | Haiku (baseline) | Haiku + rules |
|---|---|---|
| Matches answer key | 92% (85–96%) | 87% (79–92%) |
| "Not met" with no web lookup | 2 | **0** |
| "Met"/"not met" with no evidence | 0 | 0 |
| Verdicts sent back | – | 1 of 100 |
| Cost per check | $0.032 | $0.035 |

The rule removed the failure it targets, but it only fired once. The accuracy drop is run-to-run variation, not the rule: none of the 7 cases that went from right to wrong were sent back (7 went right to wrong, 2 wrong to right; a sign test gives p ≈ 0.18). Four of those 7 are the same judgment call: the agent searched for a talk, found none, and said "not met" where the key says "unclear". Defining that boundary is the next lever.

### v3: "finding nothing" policy (same day)

The planner now flags each criterion `public_record` when meeting it would leave a findable trace (talks, papers, funding rounds, acquisitions, repos). The agent prompt says what finding nothing means:
- **Public-record criteria:** two or more targeted searches that find nothing mean **not met**.
- **Everything else:** finding nothing means **unclear**.

"Not met" may now rest on a documented empty search (2+ lookups) instead of a quote.

The answer key was updated to match. Opus re-decided the 11 cases the policy can change, and 5 changes were accepted, all "unclear" to "not met" on talks or funding. One other change was rejected: Opus flipped Kanapin's tenure case to "met", which is not a policy effect, so the old verdict was kept and the case flagged. All variants below are scored against this key, which is why the older numbers differ from the tables above.

| | Haiku | Sonnet | Haiku + rules | **Haiku + policy** |
|---|---|---|---|---|
| Matches answer key | 86% | 86% | 87% | **92%** (85–96%) |
| Same verdict on both runs | 92% | 94% | 84% | **96%** |
| "Not met" with no web lookup | 2 | 3 | 0 | 0 |
| Web lookups per check | 1.8 | 0.9 | 1.9 | 2.1 |
| Cost per check | $0.032 | $0.046 | $0.035 | $0.037 |

Against "Haiku + rules", v3 fixed 8 checks and broke 3 (p ≈ 0.23), so the gain is likely but not proven at 50 cases. The 8 remaining wrong checks involve 3 people. In 2 of them (Kanapin's tenure) Haiku agrees with Opus's own re-run, so the key is probably wrong there; see `review.md`.

The re-check and v3 run cost about $5.

**Decision:** keep Haiku 5.5 as the verifier, with the verdict rules and the "finding nothing" policy. Accuracy is tied; Haiku is cheaper, does more research and always cites evidence. "Not met" without any web lookup should be fixed in code, not by changing model.

The full run cost about $14.

## Re-run

```bash
# answer key, then the models (each skips cases already done)
uv run python eval/run_eval.py --variant reference --model claude-opus-5-5 --effort high --max-turns 14
uv run python eval/run_eval.py --variant baseline  --model claude-haiku-5-5 --reps 2
uv run python eval/run_eval.py --variant v1        --model claude-sonnet-5-5 --reps 2

# score (free; re-run after editing key_overrides.json), then rebuild the report
uv run python eval/grade.py
node eval/build-report-lite.mjs eval/results/
```

To test a prompt or code change, run it as a new variant (`--variant v2`) and add it to `VARIANTS` in `grade.py`. Human corrections to the answer key go in `eval/key_overrides.json` as `{"<case id>": {"status": "met|not_met|unclear", "note": "..."}}`.

## Files

The case data and results contain names and contact details of real people, so they stay local and are not in git (`cases.jsonl`, `cases.md`, `review.md`, `results/`).

- `cases.jsonl`, `cases.md`: the 50 cases.
- `run_eval.py`: runs the real verifier agent and records the transcript, the pages it saw and its token usage.
- `grade.py`: scores against the key, checks citations, and writes `review.md`.
- `results/<variant>/`: `raw.jsonl`, `results.jsonl`, `traces/` and `seen/` for each variant (`reference` = Opus, `baseline` = Haiku, `v1` = Sonnet).
- `results/report.html`: the case-by-case report.
