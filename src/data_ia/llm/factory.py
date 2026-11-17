"""Select LLM provider from settings."""

from __future__ import annotations

from data_ia.config import get_settings
from data_ia.llm.base import LLMProvider
from data_ia.llm.stub import StubLLM


def get_llm() -> LLMProvider:
    settings = get_settings()
    provider = (settings.llm_provider or "stub").lower()
    if provider == "stub":
        return StubLLM(model=settings.llm_model)
    # Real providers intentionally not wired in v1 offline path.
    # Callers that set LLM_PROVIDER=openai without a key still get the stub
    # so tests never make external calls by accident.
    if not settings.llm_api_key:
        return StubLLM(model=settings.llm_model)
    raise NotImplementedError(
        f"LLM provider {provider!r} is not implemented in v1; use stub "
        "or set LLM_PROVIDER=stub for offline runs."
    )
