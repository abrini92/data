"""Orchestrator: make the question verifiable and build the sub-question tree."""

from __future__ import annotations

from typing import Any

from data_ia.agents.base import Agent, AgentResult

# Slide-2 / BRIEF-3 §6 required fields for a computable question.
REQUIRED_QUESTION_FIELDS = (
    "target_variable",
    "threshold",
    "horizon",
    "zone",
    "unit",
    "resolution_source",
    "resolution_rule",
)


class OrchestratorAgent(Agent):
    name = "orchestrator"
    produces = "Verified question object + sub-question tree (nodes, weights, types)"
    checks = "Slide-2 fields present; every leaf has text/type/weight; unique ids; tree non-empty"
    on_failure = "Mark question blocked / not ready; do not schedule Scout; record motive"

    def run(self, context: dict[str, Any]) -> AgentResult:
        seed = context.get("seed") or {}
        question = dict(seed.get("question") or {})
        tree = list(seed.get("sub_questions") or [])
        errors: list[str] = []
        checks: list[str] = []

        if not question.get("id") or not question.get("text"):
            errors.append("question missing id or text")
        checks.append("question_fields")

        missing = [f for f in REQUIRED_QUESTION_FIELDS if question.get(f) in (None, "")]
        if missing:
            errors.append(f"question missing required slide-2 fields: {', '.join(missing)}")
        checks.append("slide2_fields")

        # Empty tree → not ready (no forecast). Do not invent a tree.
        if not tree:
            errors.append("not ready: sub-question tree is empty")
            checks.append("tree_nonempty")
            return AgentResult(
                agent=self.name,
                ok=False,
                checks=checks,
                errors=errors,
                failure_action=self.on_failure,
                produced={
                    "question": question,
                    "sub_questions": [],
                    "not_ready": True,
                    "illustrative": bool(question.get("illustrative", True)),
                },
            )
        checks.append("tree_nonempty")

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
                produced={
                    "question": question,
                    "sub_questions": tree,
                    "not_ready": "not ready" in "; ".join(errors).lower(),
                    "illustrative": bool(question.get("illustrative", True)),
                },
            )

        return AgentResult(
            agent=self.name,
            ok=True,
            checks=checks,
            produced={
                "question": question,
                "sub_questions": tree,
                "not_ready": False,
                "illustrative": bool(question.get("illustrative", True)),
            },
        )
