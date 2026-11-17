"""Shared agent contract: produce / check / on_failure (deck slide 8)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentResult:
    agent: str
    ok: bool
    produced: dict[str, Any] = field(default_factory=dict)
    checks: list[str] = field(default_factory=list)
    failure_action: str | None = None
    errors: list[str] = field(default_factory=list)


class Agent(ABC):
    name: str

    @abstractmethod
    def run(self, context: dict[str, Any]) -> AgentResult:
        """Execute one job step; mutate context via returned ``produced``."""

    def describe(self) -> dict[str, str]:
        return {
            "agent": self.name,
            "produces": self.produces,
            "checks": self.checks,
            "on_failure": self.on_failure,
        }

    produces: str = ""
    checks: str = ""
    on_failure: str = ""
