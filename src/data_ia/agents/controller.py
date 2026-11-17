"""Controller: schema + range + chi-squared; reject / quarantine."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from data_ia.agents.base import Agent, AgentResult
from data_ia.math.controller_rules import (
    ExtractedObservation,
    ExtractionSchema,
    chi_squared_consistency,
    validate_schema_and_range,
)


class ControllerAgent(Agent):
    name = "controller"
    produces = "Accepted / rejected / quarantined observations; reliability inputs"
    checks = "Schema field+type; range bounds; chi-squared cross-source consistency"
    on_failure = "Reject schema/range failures; quarantine chi2 failures; exclude from maths"

    DEFAULT_SCHEMA = ExtractionSchema(
        field_name="probability",
        value_min=0.0,
        value_max=1.0,
        value_type="probability",
    )

    def run(self, context: dict[str, Any]) -> AgentResult:
        observations = list(context.get("observations") or [])
        schema = self.DEFAULT_SCHEMA
        accepted: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        quarantined: list[dict[str, Any]] = []
        checks = ["schema", "range", "chi2"]

        by_leaf: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for obs in observations:
            extracted = ExtractedObservation(
                source_id=obs["source_id"],
                field_name=obs.get("extracted_field") or "probability",
                value=obs.get("extracted_value"),
            )
            result = validate_schema_and_range(extracted, schema)
            updated = dict(obs)
            if not result.accepted:
                updated["status"] = result.action
                updated["rejection_reason"] = "; ".join(i.message for i in result.issues)
                if result.action == "quarantine":
                    quarantined.append(updated)
                else:
                    rejected.append(updated)
                continue
            updated["extracted_value"] = result.cleaned_value
            updated["status"] = "pending_chi2"
            by_leaf[updated["sub_question_id"]].append(updated)

        for leaf_id, group in by_leaf.items():
            values = [float(o["extracted_value"]) for o in group]
            chi = chi_squared_consistency(values)
            if not chi.accepted:
                for o in group:
                    o["status"] = "quarantined"
                    o["rejection_reason"] = "; ".join(i.message for i in chi.issues)
                    quarantined.append(o)
            else:
                for o in group:
                    o["status"] = "accepted"
                    accepted.append(o)

        ok = bool(accepted)
        return AgentResult(
            agent=self.name,
            ok=ok,
            checks=checks,
            errors=[] if ok else ["no observations accepted"],
            failure_action=None if ok else self.on_failure,
            produced={
                "accepted_observations": accepted,
                "rejected_observations": rejected,
                "quarantined_observations": quarantined,
            },
        )
