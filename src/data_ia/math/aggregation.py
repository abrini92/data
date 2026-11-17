"""Logit aggregation of sub-question probabilities into a final answer.

Taxonomy nodes (YAML/JSON, deck slide 7 / BRIEF deliverable 4):

- ``leaf``: terminal node whose probability comes from fusion.
- ``weighted_logit``: P = sigmoid(sum_k w_k * logit(p_k)).
- ``and``: independent conjunction P = product(p_k).
- ``or``: independent disjunction P = 1 - product(1 - p_k).

Sensitivities dP/dx_k are computed by finite differences on leaf inputs
(deck silent on analytic form; FD chosen for taxonomy generality).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

_EPS = 1e-12


def logit(p: float) -> float:
    p = float(np.clip(p, _EPS, 1.0 - _EPS))
    return float(np.log(p / (1.0 - p)))


def sigmoid(x: float) -> float:
    # Numerically stable logistic
    if x >= 0:
        z = np.exp(-x)
        return float(1.0 / (1.0 + z))
    z = np.exp(x)
    return float(z / (1.0 + z))


@dataclass(frozen=True)
class AggregationResult:
    probability: float
    node_probabilities: dict[str, float]
    leaf_inputs: dict[str, float]
    sensitivities: dict[str, float]


def _require_prob(name: str, p: float) -> float:
    if not 0.0 <= p <= 1.0:
        raise ValueError(f"probability for {name!r} must be in [0, 1], got {p}")
    return float(p)


def evaluate_taxonomy(
    taxonomy: Mapping[str, Any],
    leaf_probs: Mapping[str, float],
    *,
    root: str | None = None,
    sensitivity_eps: float = 1e-4,
) -> AggregationResult:
    """Evaluate a taxonomy tree and return final P plus dP/dx_k.

    ``taxonomy`` maps node_id -> node spec with keys:
    ``type``, optional ``children`` (list of {id, weight}), optional ``weight`` sum
    need not be 1 (weights are used as written for weighted_logit).
    """
    if not taxonomy:
        raise ValueError("taxonomy must not be empty")

    root_id = root or _infer_root(taxonomy)
    clipped = {k: _require_prob(k, v) for k, v in leaf_probs.items()}

    cache: dict[str, float] = {}

    def eval_node(node_id: str) -> float:
        if node_id in cache:
            return cache[node_id]
        if node_id not in taxonomy:
            # Bare leaf referenced only via leaf_probs
            if node_id in clipped:
                cache[node_id] = clipped[node_id]
                return cache[node_id]
            raise KeyError(f"unknown taxonomy node {node_id!r}")

        node = taxonomy[node_id]
        ntype = node.get("type", "leaf")

        if ntype == "leaf":
            if node_id not in clipped:
                raise KeyError(f"missing leaf probability for {node_id!r}")
            val = clipped[node_id]
        elif ntype == "weighted_logit":
            children = node.get("children") or []
            if not children:
                raise ValueError(f"weighted_logit node {node_id!r} has no children")
            weights = [float(child.get("weight", 1.0)) for child in children]
            wsum = sum(weights)
            if wsum <= 0:
                raise ValueError(f"weighted_logit node {node_id!r} has non-positive weights")
            total = 0.0
            for child, w in zip(children, weights, strict=True):
                total += (w / wsum) * logit(eval_node(child["id"]))
            val = sigmoid(total)
        elif ntype == "and":
            children = node.get("children") or []
            prod = 1.0
            for child in children:
                prod *= eval_node(child["id"])
            val = float(prod)
        elif ntype == "or":
            children = node.get("children") or []
            prod = 1.0
            for child in children:
                prod *= 1.0 - eval_node(child["id"])
            val = float(1.0 - prod)
        else:
            raise ValueError(f"unsupported taxonomy type {ntype!r} on {node_id!r}")

        cache[node_id] = val
        return val

    p_final = eval_node(root_id)
    node_probs = dict(cache)

    # Finite-difference sensitivities on every leaf that contributed
    leaf_ids = sorted(k for k in clipped if k in node_probs or k in leaf_probs)
    sensitivities: dict[str, float] = {}
    for lid in leaf_ids:
        base = clipped[lid]
        hi = dict(clipped)
        lo = dict(clipped)
        hi[lid] = float(np.clip(base + sensitivity_eps, _EPS, 1.0 - _EPS))
        lo[lid] = float(np.clip(base - sensitivity_eps, _EPS, 1.0 - _EPS))
        p_hi_val = _eval_only(taxonomy, hi, root_id)
        p_lo_val = _eval_only(taxonomy, lo, root_id)
        denom = hi[lid] - lo[lid]
        sensitivities[lid] = float((p_hi_val - p_lo_val) / denom) if denom else 0.0

    return AggregationResult(
        probability=float(p_final),
        node_probabilities=node_probs,
        leaf_inputs=dict(clipped),
        sensitivities=sensitivities,
    )


def _eval_only(
    taxonomy: Mapping[str, Any],
    leaf_probs: Mapping[str, float],
    root_id: str,
) -> float:
    cache: dict[str, float] = {}

    def eval_node(node_id: str) -> float:
        if node_id in cache:
            return cache[node_id]
        if node_id not in taxonomy:
            cache[node_id] = float(leaf_probs[node_id])
            return cache[node_id]
        node = taxonomy[node_id]
        ntype = node.get("type", "leaf")
        if ntype == "leaf":
            val = float(leaf_probs[node_id])
        elif ntype == "weighted_logit":
            children = node.get("children") or []
            weights = [float(child.get("weight", 1.0)) for child in children]
            wsum = sum(weights) or 1.0
            total = 0.0
            for child, w in zip(children, weights, strict=True):
                total += (w / wsum) * logit(eval_node(child["id"]))
            val = sigmoid(total)
        elif ntype == "and":
            prod = 1.0
            for child in node.get("children") or []:
                prod *= eval_node(child["id"])
            val = float(prod)
        elif ntype == "or":
            prod = 1.0
            for child in node.get("children") or []:
                prod *= 1.0 - eval_node(child["id"])
            val = float(1.0 - prod)
        else:
            raise ValueError(f"unsupported taxonomy type {ntype!r}")
        cache[node_id] = val
        return val

    return eval_node(root_id)


def _infer_root(taxonomy: Mapping[str, Any]) -> str:
    referenced: set[str] = set()
    for node in taxonomy.values():
        for child in node.get("children") or []:
            referenced.add(child["id"])
    roots = [nid for nid in taxonomy if nid not in referenced]
    if len(roots) != 1:
        raise ValueError(
            f"cannot infer unique root (found {roots!r}); pass root= explicitly"
        )
    return roots[0]
