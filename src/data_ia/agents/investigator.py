"""Investigator: explain surprise = -log P(x_t | past)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from data_ia.agents.base import Agent, AgentResult
from data_ia.math.surprise import gaussian_surprise


class InvestigatorAgent(Agent):
    name = "investigator"
    produces = "Per-leaf surprise scores and short why-notes for large jumps"
    checks = "Surprise finite; past series optional; flag when surprise > threshold"
    on_failure = "Attach 'insufficient history' note; do not block Strategist"

    SURPRISE_THRESHOLD = 5.0

    def run(self, context: dict[str, Any]) -> AgentResult:
        accepted = context.get("accepted_observations") or []
        history = context.get("leaf_history") or {}  # leaf_id -> list[float]
        by_leaf: dict[str, list[float]] = defaultdict(list)
        for obs in accepted:
            by_leaf[obs["sub_question_id"]].append(float(obs["extracted_value"]))

        surprises: dict[str, dict[str, Any]] = {}
        alerts: list[str] = []
        for leaf_id, values in by_leaf.items():
            x_t = sum(values) / len(values)
            past = list(history.get(leaf_id) or [])
            result = gaussian_surprise(x_t, past)
            note = "within_expectation"
            if result.surprise > self.SURPRISE_THRESHOLD:
                note = "high_surprise_review_sources"
                alerts.append(leaf_id)
            if not past:
                note = "insufficient_history"
            surprises[leaf_id] = {
                "surprise": result.surprise,
                "log_prob": result.log_prob,
                "x_t": result.x_t,
                "mean": result.mean,
                "variance": result.variance,
                "note": note,
            }

        return AgentResult(
            agent=self.name,
            ok=True,
            checks=["finite_surprise", "threshold"],
            produced={"surprises": surprises, "surprise_alerts": alerts},
            failure_action=None,
        )
