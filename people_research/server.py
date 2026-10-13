"""API for the web/ frontend: streams pipeline progress over Server-Sent Events and serves saved runs."""

import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .config import Settings
from .models import RunReport
from .pipeline import run

RUNS = Path("runs")
app = FastAPI()
# The Next.js frontend (web/) runs on another origin, locally on :3000 and on Vercel in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("PR_CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()],
    allow_origin_regex=os.getenv("PR_CORS_ORIGIN_REGEX") or None,
    allow_methods=["GET"],
)


def _event(type_: str, data: dict) -> dict:
    """Turn a pipeline progress callback into a JSON-safe event for the page."""
    if type_ == "plan":
        return {"type": "plan", "plan": data["plan"].model_dump()}
    if type_ == "sourced":
        return {"type": "sourced", "candidates": [
            c.model_dump(include={"id", "name", "profile_url", "linkedin_url", "headline", "location"})
            for c in data["candidates"]
        ]}
    if type_ == "verdict":
        return {"type": "verdict", "candidate_id": data["candidate"].id, "verdict": data["verdict"].model_dump()}
    if type_ == "candidate_done":
        r = data["report"]
        return {"type": "candidate_done", "candidate_id": r.candidate.id, "qualified": r.qualified,
                "score": r.score, "verdicts": [v.model_dump() for v in r.verdicts]}
    if type_ == "contacts":
        return {"type": "contacts", "cost": data["cost"],
                "contacts": {r.candidate.id: r.contact.model_dump() for r in data["reports"]}}
    return {"type": type_, **data}


@app.get("/api/search")
async def search(request: Request, q: str = Query(min_length=3, max_length=500), n: int = Query(10, ge=1, le=25)):
    settings = Settings()
    settings.candidates = n
    queue: asyncio.Queue[dict | None] = asyncio.Queue()

    async def work():
        try:
            report = await run(q, settings, lambda t, d: queue.put_nowait(_event(t, d)))
            slug = re.sub(r"[^a-z0-9]+", "-", q.lower()).strip("-")[:50]
            out = RUNS / f"{datetime.now():%Y%m%d-%H%M%S}-{slug}.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(report.model_dump_json(indent=2))
            queue.put_nowait({"type": "done", "order": [r.candidate.id for r in report.results],
                              "run_id": out.stem, "report_path": str(out),
                              "email_lookup_cost": report.email_lookup_cost})
        except Exception as e:
            queue.put_nowait({"type": "error", "message": f"{type(e).__name__}: {e}"})
        finally:
            queue.put_nowait(None)

    task = asyncio.create_task(work())

    async def stream():
        try:
            while True:
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    if await request.is_disconnected():
                        break
                    yield ": keep-alive\n\n"
                    continue
                if ev is None:
                    break
                yield f"data: {json.dumps(ev)}\n\n"
        finally:
            # Closing the tab stops the agents instead of letting them run on.
            task.cancel()

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


def _load_run(path: Path) -> RunReport | None:
    try:
        return RunReport.model_validate_json(path.read_text())
    except (OSError, ValueError):  # plan files and partial writes live in runs/ too
        return None


@app.get("/api/runs")
async def list_runs(limit: int = Query(20, ge=1, le=100)):
    out = []
    for path in sorted(RUNS.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        report = _load_run(path)
        if report is None:
            continue
        out.append({
            "id": path.stem,
            "query": report.query,
            "created_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
            "people": len(report.results),
            "qualified": sum(r.qualified for r in report.results),
            "criteria": len(report.plan.criteria),
        })
        if len(out) >= limit:
            break
    return out


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
        raise HTTPException(404)
    report = _load_run(RUNS / f"{run_id}.json")
    if report is None:
        raise HTTPException(404)
    return report.model_dump(exclude={"results": {"__all__": {"candidate": {"profile_text", "work_history"}}}})


def main() -> None:
    import uvicorn

    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    print(f"People research API on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")
