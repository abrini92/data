"""Brier score proof harness (deck slide 9 / BRIEF deliverable 5).

All synthetic resolved questions MUST be labelled ILLUSTRATIVE/SYNTHETIC
and must never be presented as real outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class ResolvedForecast:
    """One resolved short-horizon forecast.

    ``label`` must include ILLUSTRATIVE or SYNTHETIC for seeded demos.
    """

    question_id: str
    probability: float
    outcome: int  # 0 or 1
    label: str
    baseline_probability: float = 0.5

    def __post_init__(self) -> None:
        if self.outcome not in (0, 1):
            raise ValueError("outcome must be 0 or 1")
        if not 0.0 <= self.probability <= 1.0:
            raise ValueError("probability must be in [0, 1]")
        if not 0.0 <= self.baseline_probability <= 1.0:
            raise ValueError("baseline_probability must be in [0, 1]")


@dataclass(frozen=True)
class BrierReport:
    n: int
    model_brier: float
    baseline_brier: float
    improvement: float
    illustrative: bool
    disclaimer: str


def brier_score(probabilities: Sequence[float], outcomes: Sequence[int]) -> float:
    """Mean squared error of probabilistic forecasts: mean((p - o)^2)."""
    if len(probabilities) != len(outcomes):
        raise ValueError("probabilities and outcomes must have the same length")
    if not probabilities:
        raise ValueError("need at least one forecast")
    total = 0.0
    for p, o in zip(probabilities, outcomes, strict=True):
        if o not in (0, 1):
            raise ValueError("outcomes must be 0 or 1")
        if not 0.0 <= p <= 1.0:
            raise ValueError("probabilities must be in [0, 1]")
        total += (p - o) ** 2
    return total / len(probabilities)


def naive_baseline_brier(
    outcomes: Sequence[int],
    baseline_probability: float = 0.5,
) -> float:
    """Brier of a constant baseline forecast (default 0.5 = uninformed)."""
    return brier_score([baseline_probability] * len(outcomes), list(outcomes))


def evaluate_proof(forecasts: Iterable[ResolvedForecast]) -> BrierReport:
    """Compare model Brier to the naive baseline on a resolved set."""
    items = list(forecasts)
    if not items:
        raise ValueError("forecasts must not be empty")

    illustrative = all(
        "ILLUSTRATIVE" in f.label.upper() or "SYNTHETIC" in f.label.upper()
        for f in items
    )
    probs = [f.probability for f in items]
    outcomes = [f.outcome for f in items]
    # Per-item baseline then mean; allows mixed baselines if needed
    baseline_scores = [
        (f.baseline_probability - f.outcome) ** 2 for f in items
    ]
    model = brier_score(probs, outcomes)
    baseline = sum(baseline_scores) / len(baseline_scores)
    disclaimer = (
        "ILLUSTRATIVE/SYNTHETIC data only — not real resolved outcomes. "
        "Do not present these numbers as production proof."
        if illustrative
        else "Resolved set contains items not labelled ILLUSTRATIVE/SYNTHETIC."
    )
    return BrierReport(
        n=len(items),
        model_brier=model,
        baseline_brier=baseline,
        improvement=baseline - model,
        illustrative=illustrative,
        disclaimer=disclaimer,
    )
