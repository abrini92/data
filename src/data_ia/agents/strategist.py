"""Strategist: fuse sources, aggregate taxonomy, emit final probability."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np
import yaml

from data_ia.agents.base import Agent, AgentResult
from data_ia.config import get_settings
from data_ia.math.aggregation import evaluate_taxonomy
from data_ia.math.sources import (
    ClassPrior,
    ErrorObservation,
    estimate_source_reliability,
    fuse_observations,
)


class StrategistAgent(Agent):
    name = "strategist"
    produces = "Final probability, interval, source weights, sensitivities, node probs"
    checks = "P in [0,1]; interval ordered; at least one leaf fused"
    on_failure = "Withhold dashboard publish; keep last good snapshot if any"

    def run(self, context: dict[str, Any]) -> AgentResult:
        settings = get_settings()
        accepted = context.get("accepted_observations") or []
        surprises = context.get("surprises") or {}
        error_history = context.get("source_error_history") or {}
        priors_cfg = context.get("source_priors") or self._load_yaml(settings.source_priors_path)
        taxonomy = context.get("taxonomy") or self._load_yaml(settings.taxonomy_path)

        if not accepted:
            return AgentResult(
                agent=self.name,
                ok=False,
                checks=["has_accepted"],
                errors=["no accepted observations to fuse"],
                failure_action=self.on_failure,
            )

        class_priors = {
            name: ClassPrior(
                bias=float(cfg.get("bias", 0.0)),
                variance=float(cfg.get("variance", 1.0)),
                n0=float(cfg.get("n0", 5.0)),
            )
            for name, cfg in (priors_cfg or {}).items()
        }
        default_prior = class_priors.get("open", ClassPrior())

        # Reliability per source from resolved error history (may be empty → prior)
        source_classes = {
            s["id"]: s.get("source_class", "open")
            for s in (context.get("sources") or [])
        }
        reliabilities = {}
        source_ids = {o["source_id"] for o in accepted}
        for sid in source_ids:
            cls = source_classes.get(sid, "open")
            prior = class_priors.get(cls, default_prior)
            pairs = error_history.get(sid) or []
            errors = [ErrorObservation(z=float(z), x=float(x)) for z, x in pairs]
            reliabilities[sid] = estimate_source_reliability(sid, errors, prior=prior)

        # Fuse per leaf
        by_leaf: dict[str, dict[str, float]] = defaultdict(dict)
        for obs in accepted:
            # Last write wins if duplicate source/leaf (deterministic seed order)
            by_leaf[obs["sub_question_id"]][obs["source_id"]] = float(
                obs["extracted_value"]
            )

        leaf_probs: dict[str, float] = {}
        leaf_vars: dict[str, float] = {}
        all_weights: dict[str, float] = defaultdict(float)
        leaf_meta: dict[str, Any] = {}

        for leaf_id, readings in by_leaf.items():
            fusion = fuse_observations(readings, reliabilities)
            # Clip fused estimate into probability domain for taxonomy leaves
            p = float(np.clip(fusion.estimate, 1e-6, 1 - 1e-6))
            leaf_probs[leaf_id] = p
            leaf_vars[leaf_id] = fusion.variance
            for c in fusion.contributions:
                all_weights[c.source_id] += c.weight
            leaf_meta[leaf_id] = {
                "estimate": p,
                "variance": fusion.variance,
                "surprise": (surprises.get(leaf_id) or {}).get("surprise"),
                "contributions": [
                    {
                        "source_id": c.source_id,
                        "z_raw": c.z_raw,
                        "z_debiased": c.z_debiased,
                        "weight": c.weight,
                        "precision": c.precision,
                    }
                    for c in fusion.contributions
                ],
            }

        # Normalise aggregate source weights for display
        total_w = sum(all_weights.values()) or 1.0
        source_weights = {k: v / total_w for k, v in all_weights.items()}

        agg = evaluate_taxonomy(taxonomy, leaf_probs)
        # Crude interval from leaf variances propagated via sensitivity abs-sum
        # (deck silent; documented choice in README).
        sens = agg.sensitivities
        var_p = 0.0
        for lid, var in leaf_vars.items():
            s = sens.get(lid, 0.0)
            var_p += (s**2) * var
        std = float(np.sqrt(max(var_p, 0.0)))
        lo = float(np.clip(agg.probability - 1.96 * std, 0.0, 1.0))
        hi = float(np.clip(agg.probability + 1.96 * std, 0.0, 1.0))

        checks = ["bounds", "interval", "fused_leaves"]
        errors: list[str] = []
        if not 0.0 <= agg.probability <= 1.0:
            errors.append("probability out of bounds")
        if lo > hi:
            errors.append("interval inverted")
        if not leaf_probs:
            errors.append("no leaf probabilities")

        ok = not errors
        disclaimer = (
            "ILLUSTRATIVE offline cycle — stub LLM extractions and seed tree; "
            "not a real forecast of CST/Starlink outcomes."
        )
        return AgentResult(
            agent=self.name,
            ok=ok,
            checks=checks,
            errors=errors,
            failure_action=None if ok else self.on_failure,
            produced={
                "final_probability": agg.probability,
                "interval_low": lo,
                "interval_high": hi,
                "source_weights": source_weights,
                "sensitivities": agg.sensitivities,
                "node_probabilities": agg.node_probabilities,
                "leaf_estimates": leaf_meta,
                "reliabilities": {
                    sid: {
                        "bias": r.bias,
                        "variance": r.variance,
                        "precision": r.precision,
                        "n_obs": r.n_obs,
                        "lambda_n": r.lambda_n,
                    }
                    for sid, r in reliabilities.items()
                },
                "disclaimer": disclaimer,
            },
        )

    @staticmethod
    def _load_yaml(path: str) -> dict[str, Any]:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            raise ValueError(f"expected mapping in {path}")
        return data
