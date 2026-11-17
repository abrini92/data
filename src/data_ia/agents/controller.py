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
from data_ia.math.labels import MixedLabelError, assert_homogeneous_labels, normalize_label
from data_ia.math.lookahead import LookAheadError, assert_cutoff_ordering
from data_ia.math.sources import (
    ClassPrior,
    ErrorObservation,
    SourceReliability,
    estimate_source_reliability,
)


class ControllerAgent(Agent):
    name = "controller"
    produces = "Accepted / rejected / quarantined observations; reliability inputs"
    checks = "Schema field+type; range; unit; published_at; chi-squared; no look-ahead; label homo"
    on_failure = "Reject schema/range failures; quarantine chi2 failures; exclude from maths"

    DEFAULT_SCHEMA = ExtractionSchema(
        field_name="probability",
        value_min=0.0,
        value_max=1.0,
        value_type="probability",
    )

    def run(self, context: dict[str, Any]) -> AgentResult:
        observations = list(context.get("observations") or [])
        question = context.get("question") or (context.get("seed") or {}).get("question") or {}
        expected_unit = question.get("unit")
        schema = ExtractionSchema(
            field_name="probability",
            value_min=0.0,
            value_max=1.0,
            value_type="probability",
            expected_unit=str(expected_unit) if expected_unit else None,
        )
        # Pipeline stubs extract probabilities; unit check against question when present.
        require_fields = bool(context.get("require_extraction_fields", True))

        forecast_at = context.get("forecast_at")
        data_cutoff = context.get("data_cutoff") or forecast_at

        accepted: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        quarantined: list[dict[str, Any]] = []
        checks = ["schema", "range", "unit", "published_at", "chi2", "lookahead", "labels"]
        errors: list[str] = []

        try:
            if observations:
                assert_homogeneous_labels(
                    [normalize_label(o.get("data_label")) for o in observations],
                    context="controller_observations",
                )
        except MixedLabelError as exc:
            return AgentResult(
                agent=self.name,
                ok=False,
                checks=checks,
                errors=[str(exc)],
                failure_action=self.on_failure,
            )

        # Build reliabilities for chi2 from error history (resolved before forecast_at).
        reliabilities = self._reliabilities(context)

        by_leaf: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for obs in observations:
            extracted = ExtractedObservation(
                source_id=obs["source_id"],
                field_name=obs.get("extracted_field") or "probability",
                value=obs.get("extracted_value"),
                unit=obs.get("unit"),
                published_at=obs.get("published_at") or obs.get("collected_at"),
                source_passage=obs.get("source_passage") or obs.get("raw_doc"),
            )
            result = validate_schema_and_range(
                extracted,
                schema,
                require_extraction_fields=require_fields,
            )
            updated = dict(obs)
            updated["published_at"] = extracted.published_at
            updated["unit"] = extracted.unit
            updated["source_passage"] = extracted.source_passage
            updated["data_label"] = normalize_label(obs.get("data_label"))

            if not result.accepted:
                updated["status"] = result.action
                updated["rejection_reason"] = "; ".join(i.message for i in result.issues)
                if result.action == "quarantine":
                    quarantined.append(updated)
                else:
                    rejected.append(updated)
                continue

            # No look-ahead: published_at <= data_cutoff <= forecast_at
            if forecast_at and data_cutoff:
                try:
                    assert_cutoff_ordering(
                        published_at=updated.get("published_at"),
                        data_cutoff=data_cutoff,
                        forecast_at=forecast_at,
                    )
                except LookAheadError as exc:
                    updated["status"] = "rejected"
                    updated["rejection_reason"] = f"look_ahead:{exc}"
                    rejected.append(updated)
                    continue

            updated["extracted_value"] = result.cleaned_value
            updated["status"] = "pending_chi2"
            by_leaf[updated["sub_question_id"]].append(updated)

        for _leaf_id, group in by_leaf.items():
            values = [float(o["extracted_value"]) for o in group]
            rels: list[SourceReliability] = []
            for o in group:
                sid = o["source_id"]
                if sid in reliabilities:
                    rels.append(reliabilities[sid])
            if len(rels) == len(values) and rels:
                chi = chi_squared_consistency(values, reliabilities=rels)
            else:
                chi = chi_squared_consistency(values)

            if not chi.accepted:
                for o in group:
                    o["status"] = "quarantined"
                    o["rejection_reason"] = "; ".join(i.message for i in chi.issues)
                    quarantined.append(o)
            else:
                for o in group:
                    o["status"] = "accepted"
                    if "single_source" in chi.flags:
                        o.setdefault("meta", {})
                        if isinstance(o["meta"], dict):
                            o["meta"] = {**o["meta"], "single_source": True}
                        else:
                            o["meta"] = {"single_source": True}
                    accepted.append(o)

        ok = bool(accepted)
        if not ok and not errors:
            errors = ["no observations accepted"]
        return AgentResult(
            agent=self.name,
            ok=ok,
            checks=checks,
            errors=errors,
            failure_action=None if ok else self.on_failure,
            produced={
                "accepted_observations": accepted,
                "rejected_observations": rejected,
                "quarantined_observations": quarantined,
                "reliabilities_for_chi2": {
                    sid: {
                        "bias": r.bias,
                        "variance": r.variance,
                        "precision": r.precision,
                    }
                    for sid, r in reliabilities.items()
                },
            },
        )

    def _reliabilities(self, context: dict[str, Any]) -> dict[str, SourceReliability]:
        error_history = context.get("source_error_history") or {}
        priors_cfg = context.get("source_priors") or {}
        source_classes = {
            s["id"]: s.get("source_class", "open")
            for s in (context.get("sources") or [])
        }
        class_priors = {
            name: ClassPrior(
                bias=float(cfg.get("bias", 0.0)),
                variance=float(cfg.get("variance", 1.0)),
                n0=float(cfg.get("n0", 5.0)),
            )
            for name, cfg in priors_cfg.items()
            if isinstance(cfg, dict)
        }
        default_prior = class_priors.get("open", ClassPrior())
        out: dict[str, SourceReliability] = {}
        source_ids = {o["source_id"] for o in (context.get("observations") or [])}
        for sid in source_ids:
            cls = source_classes.get(sid, "open")
            prior = class_priors.get(cls, default_prior)
            pairs = error_history.get(sid) or []
            errors = [ErrorObservation(z=float(z), x=float(x)) for z, x in pairs]
            out[sid] = estimate_source_reliability(sid, errors, prior=prior)
        return out
