"""Deterministic stub LLM so the pipeline runs offline in tests."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from data_ia.llm.base import LLMProvider, LLMResponse


class StubLLM(LLMProvider):
    """Hash-stable synthetic extractions — never real model calls."""

    def __init__(self, model: str = "stub-deterministic") -> None:
        self.model = model

    def complete(self, prompt: str, *, schema_hint: str | None = None) -> LLMResponse:
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        # Map digest bytes into a pseudo-probability in [0.15, 0.85]
        raw = int(digest[:8], 16) / 0xFFFFFFFF
        value = 0.15 + 0.70 * raw

        field = "probability"
        unit = "probability"
        if schema_hint:
            m = re.search(r"field\s*[:=]\s*(\w+)", schema_hint, re.I)
            if m:
                field = m.group(1)
            u = re.search(r"unit\s*[:=]\s*([^\s;]+)", schema_hint, re.I)
            if u:
                unit = u.group(1).strip()

        # Stable published_at derived from hash day offset (always in the past).
        day = int(digest[8:12], 16) % 28 + 1
        published_at = datetime(2024, 6, day, 12, 0, 0, tzinfo=timezone.utc).isoformat()

        # Passage: short excerpt from the prompt doc section.
        passage = prompt[-400:] if len(prompt) > 400 else prompt

        structured: dict[str, Any] = {
            "field_name": field,
            "value": round(value, 4),
            "unit": unit,
            "published_at": published_at,
            "source_passage": passage,
            "confidence": 0.5,
            "provider": "stub",
            "note": "ILLUSTRATIVE/SYNTHETIC stub extraction — not a real LLM judgement",
        }
        return LLMResponse(
            content=json.dumps(structured, ensure_ascii=False),
            structured=structured,
            model=self.model,
            provider="stub",
        )
