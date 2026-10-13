# Usage

## Setup

```bash
uv sync
cp .env.example .env   # set EXA_API_KEY; Anthropic creds via ANTHROPIC_API_KEY or `ant auth login`
```

`.env.example` also lists the optional overrides (models, concurrency, email lookup budget).

## CLI

```bash
# Check the criteria breakdown first (only calls the planner)
uv run people-research "Software engineers in NYC with three.js experience and 4+ years of professional experience" --plan-only --save-plan plan.json

# Edit plan.json if needed, then run it
uv run people-research "SWE NYC three.js" --plan plan.json -n 10
```

Finished runs are saved to `runs/` as JSON.

## Web UI

The frontend is a Next.js (App Router) + shadcn/ui app in `web/`. It talks to the FastAPI server in `people_research/server.py`.

```bash
uv run people-research-web            # API on http://127.0.0.1:8000
cd web && npm install && npm run dev  # UI on http://localhost:3000
```

```
/              search box, examples, recent searches
/search?q=&n=  live run: streams Server-Sent Events from GET /api/search
/runs/[id]     a saved run from GET /api/runs/{id}; live runs switch to this URL when they finish
```

The page streams progress as each agent finishes. Click a person to see why each requirement was or wasn't met, with links to the sources. Closing the tab stops the run.

`NEXT_PUBLIC_API_URL` defaults to `http://127.0.0.1:8000`. The API allows `http://localhost:3000` by default. The browser talks to the API directly (EventSource for the stream), so the API must allow the site's origin.

Add shadcn components with `npx shadcn@latest add <component>` from `web/`.

## Contact details and cost

For qualified people, the pipeline looks up emails in one batched Exa Agent run. It costs metered compute plus about $0.02 per email found, capped by `PR_ENRICH_BUDGET` (default $2 per run). Set `PR_ENRICH_EMAILS` to `qualified`, `all` or `off`.

## Deploy

**Frontend on Vercel.** Import the repo, set **Root Directory** to `web`, and add:

| Env var | Value |
| --- | --- |
| `NEXT_PUBLIC_API_URL` | Public URL of the API, e.g. `https://people-research-api.fly.dev` |

**API somewhere that allows long requests.** A search streams for several minutes, which is longer than Vercel functions allow, so run the FastAPI server on a host such as Fly.io, Railway or Render with:

| Env var | Value |
| --- | --- |
| `HOST` | `0.0.0.0` |
| `PORT` | whatever the host provides |
| `PR_CORS_ORIGINS` | `https://your-app.vercel.app` (comma-separated) |
| `PR_CORS_ORIGIN_REGEX` | optional, e.g. `https://your-app-.*\.vercel\.app` for preview deploys |
| `EXA_API_KEY`, `ANTHROPIC_API_KEY` | as in `.env.example` |

Saved runs are JSON files in `runs/`, so give the API a persistent volume if you want history to survive restarts.

The API has no auth, and every search spends Exa and Anthropic credit. Add auth or rate limiting before sharing the URL publicly.
