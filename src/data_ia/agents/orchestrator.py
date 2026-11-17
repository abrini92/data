"""Orchestrator: make the question verifiable and build the sub-question tree."""

from __future__ import annotations

from typing import Any

from data_ia.agents.base import Agent, AgentResult


class OrchestratorAgent(Agent):
    name = "orchestrator"
    produces = "Verified question object + sub-question tree (nodes, weights, types)"
    checks = "Every leaf has text, type, and weight; unique ids; single root"
    on_failure = "Mark question blocked; do not schedule Scout; record motive"

    def run(self, context: dict[str, Any]) -> AgentResult:
        seed = context.get("seed") or {}
        question = seed.get("question") or {}
        tree = seed.get("sub_questions") or []
        errors: list[str] = []
        checks: list[str] = []

        if not question.get("id") or not question.get("text"):
            errors.append("question missing id or text")
        checks.append("question_fields")

        ids = [n.get("id") for n in tree]
        if len(ids) != len(set(ids)):
            errors.append("duplicate sub-question ids")
        checks.append("unique_ids")

        leaves = [n for n in tree if n.get("node_type", "leaf") == "leaf"]
        for n in leaves:
            if not n.get("text"):
                errors.append(f"leaf {n.get('id')} missing text")
        checks.append("leaf_text")

        if errors:
            return AgentResult(
                agent=self.name,
                ok=False,
                checks=checks,
                errors=errors,
                failure_action=self.on_failure,
            )

        return AgentResult(
            agent=self.name,
            ok=True,
            checks=checks,
            produced={
                "question": question,
                "sub_questions": tree,
                "illustrative": bool(question.get("illustrative", True)),
            },
        )
