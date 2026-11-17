"""Scout: find sources in the catalogue / seed list."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from data_ia.agents.base import Agent, AgentResult


class ScoutAgent(Agent):
    name = "scout"
    produces = "Candidate source catalogue entries (url, class, publisher, rights)"
    checks = "URL parseable; source_class in allow-list; no duplicate ids"
    on_failure = "Drop invalid candidates; continue with remaining; flag coverage gap"

    ALLOWED_CLASSES = {"open", "agreement", "internal", "press", "social", "regulator"}

    def run(self, context: dict[str, Any]) -> AgentResult:
        seed = context.get("seed") or {}
        sources = list(seed.get("sources") or [])
        checks: list[str] = []
        errors: list[str] = []
        accepted: list[dict[str, Any]] = []

        seen: set[str] = set()
        for src in sources:
            sid = src.get("id")
            if not sid or sid in seen:
                errors.append(f"bad or duplicate source id: {sid!r}")
                continue
            seen.add(sid)
            url = src.get("url") or ""
            if url:
                parsed = urlparse(url)
                if parsed.scheme not in {"http", "https"}:
                    errors.append(f"source {sid}: invalid URL scheme")
                    continue
            cls = (src.get("source_class") or "open").lower()
            if cls not in self.ALLOWED_CLASSES:
                errors.append(f"source {sid}: class {cls!r} not allowed")
                continue
            accepted.append(src)

        checks.extend(["url_scheme", "source_class", "unique_ids"])

        if not accepted:
            return AgentResult(
                agent=self.name,
                ok=False,
                checks=checks,
                errors=errors or ["no sources accepted"],
                failure_action=self.on_failure,
            )

        return AgentResult(
            agent=self.name,
            ok=True,
            checks=checks,
            errors=errors,
            produced={"sources": accepted, "coverage_gap": bool(errors)},
        )
