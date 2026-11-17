"""LLM provider interface. No LLM output enters maths without validation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LLMResponse:
    content: str
    structured: dict[str, Any] | None = None
    model: str = ""
    provider: str = ""


class LLMProvider(ABC):
    @abstractmethod
    def complete(self, prompt: str, *, schema_hint: str | None = None) -> LLMResponse:
        """Return text and optional structured payload for Controller validation."""
