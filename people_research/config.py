import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    # Models. Planner decomposes the query; verifier runs one agent per (person, criterion).
    planner_model: str = os.getenv("PR_PLANNER_MODEL", "claude-opus-5-5")
    verifier_model: str = os.getenv("PR_VERIFIER_MODEL", "claude-haiku-5-5")
    planner_effort: str = os.getenv("PR_PLANNER_EFFORT", "high")
    verifier_effort: str = os.getenv("PR_VERIFIER_EFFORT", "medium")

    # Server-side refusal fallback (routes a declined request to another model in the same call).
    # Only sent for models that support it; Haiku 5.5 has no server-side fallback.
    use_fallbacks: bool = os.getenv("PR_FALLBACKS", "1") != "0"

    # Sourcing
    candidates: int = int(os.getenv("PR_CANDIDATES", "10"))
    results_per_query: int = int(os.getenv("PR_RESULTS_PER_QUERY", "10"))

    # Agent limits
    max_agent_turns: int = int(os.getenv("PR_MAX_AGENT_TURNS", "8"))
    llm_concurrency: int = int(os.getenv("PR_LLM_CONCURRENCY", "8"))
    exa_concurrency: int = int(os.getenv("PR_EXA_CONCURRENCY", "5"))

    # Email lookup (Exa Agent API, ~$0.02 per email found plus run compute).
    # "qualified" = only people who meet every hard criterion, "all", or "off".
    enrich_emails: str = os.getenv("PR_ENRICH_EMAILS", "qualified")
    enrich_budget_dollars: float = float(os.getenv("PR_ENRICH_BUDGET", "2"))

    # Stop researching a candidate once a hard criterion is confidently not met.
    early_stop: bool = True
    early_stop_confidence: float = 0.75

    exa_api_key: str | None = field(default_factory=lambda: os.getenv("EXA_API_KEY"))
