import argparse
import asyncio
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

from rich.console import Console
from rich.table import Table

from .config import Settings
from .llm import LLM
from .models import RunReport, SearchPlan
from .pipeline import run
from .planner import plan_search

console = Console()

ICON = {"met": "[green]✓[/]", "not_met": "[red]✗[/]", "unclear": "[yellow]?[/]", "skipped": "[dim]–[/]", "error": "[magenta]![/]"}


def print_plan(plan: SearchPlan) -> None:
    t = Table(title="Criteria", show_lines=False)
    for col in ("id", "kind", "requirement"):
        t.add_column(col)
    for c in plan.criteria:
        t.add_row(c.id, c.kind, c.requirement)
    console.print(t)
    console.print("[bold]Exa queries[/]")
    for q in plan.exa_queries:
        console.print(f"  • {q}")


def progress(event: str, data: dict) -> None:
    if event == "sourced":
        console.print(f"\n[bold]Sourced {len(data['candidates'])} candidates[/], researching…\n")
    elif event == "verdict":
        v, c = data["verdict"], data["candidate"]
        if v.status != "skipped":
            console.print(f"  {ICON[v.status]} {c.name:<28} {data['criterion'].id:<24} conf={v.confidence:.2f} tools={v.tool_calls}")
            console.print(f"      [dim]{v.reasoning}[/]")
    elif event == "stage" and data["stage"] == "contacts":
        console.print("\n[bold]Finding emails for qualified people…[/]")
    elif event == "warning":
        console.print(f"[yellow]{data['message']}[/]")
    elif event == "candidate_done":
        r = data["report"]
        tag = "[green]QUALIFIED[/]" if r.qualified else "[dim]not qualified[/]"
        console.print(f"[bold]→ {r.candidate.name}[/] {tag} score={r.score}")


def _domains(urls: list[str]) -> str:
    seen: list[str] = []
    for u in urls:
        d = urlsplit(u).netloc.lower().removeprefix("www.")
        if d and d not in seen:
            seen.append(d)
    return "\n".join(seen) or "[dim]—[/]"


def print_results(report: RunReport) -> None:
    hard = [c for c in report.plan.criteria if c.kind == "hard"]
    summary = Table(title=f"Results: {report.query}", title_justify="left")
    summary.add_column("#", justify="right")
    summary.add_column("Name")
    summary.add_column("Qualified", justify="center")
    # Short column codes keep the table narrow; the legend below maps them to the criteria.
    for i, c in enumerate(report.plan.criteria, 1):
        summary.add_column(f"C{i}", justify="center")
    summary.add_column("Score", justify="right")
    summary.add_column("Email", overflow="fold")
    summary.add_column("LinkedIn", overflow="fold")
    for i, r in enumerate(report.results, 1):
        name = f"[bold green]{r.candidate.name}[/]" if r.qualified else r.candidate.name
        met = sum(v.status == "met" for v, c in zip(r.verdicts, report.plan.criteria) if c.kind == "hard")
        q = "[green]yes[/]" if r.qualified else f"[dim]{met}/{len(hard)}[/]"
        profile = unquote((r.contact.linkedin_url or r.candidate.profile_url).split("://", 1)[-1].removeprefix("www."))
        email = {"found": r.contact.email, "not_found": "[dim]not found[/]", "error": "[dim]lookup failed[/]"}.get(
            r.contact.email_status, "[dim]–[/]")
        summary.add_row(str(i), name, q, *[ICON[v.status] for v in r.verdicts], f"{r.score:.2f}", email, profile)
    console.print(summary)
    for i, c in enumerate(report.plan.criteria, 1):
        console.print(f"  [bold]C{i}[/] {c.label}{'' if c.kind == 'hard' else ' (soft)'}: [dim]{c.requirement}[/]")
    console.print("  [dim]✓ met  ✗ not met  ? unclear  – skipped (an earlier hard criterion failed)  ! error[/]")
    if report.email_lookup_cost is not None:
        console.print(f"  [dim]Emails looked up for qualified people only. Lookup cost: ${report.email_lookup_cost:.2f}[/]")
    console.print()

    labels = {c.id: c.label for c in report.plan.criteria}
    detail = Table(title="Why: one row per candidate × criterion", title_justify="left", show_lines=False, expand=True)
    detail.add_column("Candidate", no_wrap=True)
    detail.add_column("Criterion", no_wrap=True)
    detail.add_column("Verdict", no_wrap=True)
    detail.add_column("Conf", justify="right")
    detail.add_column("Why", ratio=1, min_width=40)
    detail.add_column("Sources", no_wrap=True)
    detail.add_column("Tool calls", justify="right")
    for i, r in enumerate(report.results, 1):
        for j, v in enumerate(r.verdicts):
            if v.status == "skipped":
                continue
            who = f"{i}. {r.candidate.name}" if j == 0 else ""
            detail.add_row(
                who,
                labels[v.criterion_id],
                f"{ICON[v.status]} {v.status.replace('_', ' ')}",
                f"{v.confidence:.2f}",
                v.reasoning,
                _domains([e.url for e in v.evidence]),
                str(v.tool_calls),
            )
        detail.add_section()
    console.print(detail)


def main() -> None:
    p = argparse.ArgumentParser(description="Exa people search with per-criterion agentic verification.")
    p.add_argument("query", nargs="?", help="Free-text search, e.g. 'SWEs in NYC with 4+ years of three.js'")
    p.add_argument("-n", "--candidates", type=int, help="How many candidates to research (default 10)")
    p.add_argument("--plan-only", action="store_true", help="Decompose the query and stop (no Exa/agent cost)")
    p.add_argument("--plan", type=Path, help="Use a saved/edited plan JSON instead of calling the planner")
    p.add_argument("--save-plan", type=Path, help="Write the plan JSON here (use with --plan-only to edit it)")
    p.add_argument("--no-early-stop", action="store_true", help="Research every criterion even after a hard fail")
    p.add_argument("--verifier-model", help="Model for the research agents")
    p.add_argument("--verifier-effort", choices=["low", "medium", "high", "xhigh", "max"])
    p.add_argument("-o", "--out", type=Path, help="Report path (default runs/<timestamp>-<slug>.json)")
    p.add_argument("--show", type=Path, help="Print the tables for a saved report JSON and exit")
    args = p.parse_args()

    if args.show:
        print_results(RunReport.model_validate_json(args.show.read_text()))
        return

    settings = Settings()
    if args.candidates:
        settings.candidates = args.candidates
    if args.no_early_stop:
        settings.early_stop = False
    if args.verifier_model:
        settings.verifier_model = args.verifier_model
    if args.verifier_effort:
        settings.verifier_effort = args.verifier_effort

    plan = SearchPlan.model_validate_json(args.plan.read_text()) if args.plan else None
    query = args.query or (args.plan.stem if args.plan else None)
    if not query:
        p.error("a query or --plan is required")

    if plan is None:
        with console.status("Breaking the query into criteria…"):
            plan = asyncio.run(plan_search(LLM(settings), settings, query))
    print_plan(plan)
    if args.save_plan:
        args.save_plan.write_text(plan.model_dump_json(indent=2))
        console.print(f"Plan saved to {args.save_plan}")
    if args.plan_only:
        return

    report = asyncio.run(run(query, settings, progress, plan=plan))
    console.print()
    print_results(report)

    out = args.out
    if out is None:
        slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")[:50]
        out = Path("runs") / f"{datetime.now():%Y%m%d-%H%M%S}-{slug}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report.model_dump_json(indent=2))
    console.print(f"\nFull report with evidence: {out}")


if __name__ == "__main__":
    sys.exit(main())
