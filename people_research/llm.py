from typing import Any

import anthropic

from .config import Settings

FALLBACK_BETA = "server-side-fallback-2026-07-01"
# Models that accept `fallbacks: "default"`. Haiku 5.5 has no server-side refusal fallback.
FALLBACK_MODELS = {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}


class LLM:
    """Thin wrapper so every call gets the same fallback/effort/caching defaults."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = anthropic.AsyncAnthropic(max_retries=4)

    def _common(self, model: str, effort: str) -> dict[str, Any]:
        kw: dict[str, Any] = {
            "output_config": {"effort": effort},
            "cache_control": {"type": "ephemeral"},
        }
        if self.settings.use_fallbacks and model in FALLBACK_MODELS:
            kw["betas"] = [FALLBACK_BETA]
            kw["fallbacks"] = "default"
        return kw

    async def parse(self, *, model: str, effort: str, output_format, **kwargs):
        common = self._common(model, effort)
        return await self.client.beta.messages.parse(
            model=model, max_tokens=16000, output_format=output_format, **common, **kwargs
        )

    async def create(self, *, model: str, effort: str, **kwargs):
        common = self._common(model, effort)
        return await self.client.beta.messages.create(
            model=model, max_tokens=16000, **common, **kwargs
        )
