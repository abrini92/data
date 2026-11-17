"""Brier score proof harness (deck slide 9).

Scores forecasts **from the forecast registry** (engine output), not
hand-written YAML probabilities. Baseline = class base rate before
forecast_at (status-quo alternative for "will X change" questions).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

import numpy as np

from data_ia.math.labels import MixedLabelError, normalize_label


@dataclass(frozen=True)
class ResolvedForecast:
    """One resolved short-horizon forecast paired with an engine probability."""

    question_id: str
    probability: float
    outcome: int  # 0 or 1
    label: str
    baseline_probability: float
    forecast_id: int | None = None
    question_class: str | None = None

    def __post_init__(self) -> None:
        if self.outcome not in (0, 1):
            raise ValueError("outcome must be 0 or 1")
        if not 0.0 <= self.probability <= 1.0:
            raise ValueError("probability must be in [0, 1]")
        if not 0.0 <= self.baseline_probability <= 1.0:
            raise ValueError("baseline_probability must be in [0, 1]")


@dataclass(frozen=True)
class CalibrationBin:
    lower: float
    upper: float
    n: int
    mean_probability: float | None
    mean_outcome: float | None


@dataclass(frozen=True)
class BrierReport:
    n: int
    model_brier: float | None
    baseline_brier: float | None
    brier_skill_score: float | None
    improvement: float | None
    bootstrap_diff_low: float | None
    bootstrap_diff_high: float | None
    calibration: tuple[CalibrationBin, ...]
    interpretable: bool
    verdict: str | None
    illustrative: bool
    disclaimer: str
    min_n: int = 30
    extra: dict = field(default_factory=dict)


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
        if not np.isfinite(p) or not 0.0 <= p <= 1.0:
            raise ValueError("probabilities must be finite and in [0, 1]")
        total += (p - o) ** 2
    return total / len(probabilities)


def naive_baseline_brier(
    outcomes: Sequence[int],
    baseline_probability: float = 0.5,
) -> float:
    """Brier of a constant baseline forecast."""
    return brier_score([baseline_probability] * len(outcomes), list(outcomes))


def class_base_rate(
    outcomes: Sequence[int],
    *,
    default: float = 0.5,
) -> float:
    """Base rate of the question class from prior resolved outcomes."""
    if not outcomes:
        return default
    return float(sum(outcomes) / len(outcomes))


def status_quo_baseline(*, change_question: bool = False) -> float:
    """Status-quo alternative for 'will X change' questions → P(no change)=0.5 default.

    Deck: status quo as an alternative for change questions. We use 0.0 for
    'no change' as the status-quo probability of the *change* event when the
    question is framed as 'will X change'. Callers pass change_question=True.
    """
    return 0.0 if change_question else 0.5


def paired_bootstrap_brier_diff(
    model_scores: Sequence[float],
    baseline_scores: Sequence[float],
    *,
    n_boot: int = 2000,
    seed: int = 42,
    alpha: float = 0.05,
) -> tuple[float, float]:
    """95% interval of (baseline - model) via paired bootstrap."""
    if len(model_scores) != len(baseline_scores):
        raise ValueError("paired scores must match length")
    n = len(model_scores)
    if n == 0:
        raise ValueError("need at least one pair")
    rng = np.random.default_rng(seed)
    model = np.asarray(model_scores, dtype=float)
    baseline = np.asarray(baseline_scores, dtype=float)
    diffs = np.empty(n_boot, dtype=float)
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        diffs[i] = float(np.mean(baseline[idx] - model[idx]))
    low = float(np.quantile(diffs, alpha / 2))
    high = float(np.quantile(diffs, 1.0 - alpha / 2))
    return low, high


def calibration_table(
    probabilities: Sequence[float],
    outcomes: Sequence[int],
    *,
    n_bins: int = 10,
) -> tuple[CalibrationBin, ...]:
    """Reliability table: mean predicted vs mean outcome per probability bin."""
    if len(probabilities) != len(outcomes):
        raise ValueError("probabilities and outcomes must match")
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    probs = np.asarray(probabilities, dtype=float)
    outs = np.asarray(outcomes, dtype=float)
    bins: list[CalibrationBin] = []
    for i in range(n_bins):
        lo, hi = float(edges[i]), float(edges[i + 1])
        if i == n_bins - 1:
            mask = (probs >= lo) & (probs <= hi)
        else:
            mask = (probs >= lo) & (probs < hi)
        count = int(mask.sum())
        if count == 0:
            bins.append(
                CalibrationBin(lo, hi, 0, None, None)
            )
        else:
            bins.append(
                CalibrationBin(
                    lo,
                    hi,
                    count,
                    float(np.mean(probs[mask])),
                    float(np.mean(outs[mask])),
                )
            )
    return tuple(bins)


def evaluate_proof(
    forecasts: Iterable[ResolvedForecast],
    *,
    min_n: int = 30,
    n_boot: int = 2000,
    seed: int = 42,
    n_bins: int = 10,
) -> BrierReport:
    """Compare model Brier to class-rate baseline; report BSS, bootstrap, bins."""
    items = list(forecasts)
    labels = [normalize_label(f.label) for f in items]
    try:
        from data_ia.math.labels import assert_homogeneous_labels

        batch_label = assert_homogeneous_labels(labels, context="brier") if items else "SYNTHETIC"
    except MixedLabelError:
        raise
    except ValueError:
        batch_label = "SYNTHETIC"

    illustrative = batch_label == "SYNTHETIC" or any(
        "ILLUSTRATIVE" in f.label.upper() or "SYNTHETIC" in f.label.upper() for f in items
    )
    disclaimer_synth = (
        "ILLUSTRATIVE/SYNTHETIC data involved — not real resolved outcomes. "
        "Do not present these numbers as production proof."
    )
    disclaimer_real = "Resolved set labelled REAL."

    if not items:
        return BrierReport(
            n=0,
            model_brier=None,
            baseline_brier=None,
            brier_skill_score=None,
            improvement=None,
            bootstrap_diff_low=None,
            bootstrap_diff_high=None,
            calibration=(),
            interpretable=False,
            verdict=None,
            illustrative=True,
            disclaimer="Empty forecast set — non interprétable.",
            min_n=min_n,
        )

    if any(not np.isfinite(f.probability) for f in items):
        raise ValueError("NaN/Inf probability rejected")

    probs = [f.probability for f in items]
    outcomes = [f.outcome for f in items]
    model_scores = [(p - o) ** 2 for p, o in zip(probs, outcomes, strict=True)]
    baseline_scores = [
        (f.baseline_probability - f.outcome) ** 2 for f in items
    ]
    model = float(np.mean(model_scores))
    baseline = float(np.mean(baseline_scores))
    if baseline == 0.0:
        bss = None if model == 0.0 else float("-inf")
    else:
        bss = 1.0 - (model / baseline)
    improvement = baseline - model
    boot_lo, boot_hi = paired_bootstrap_brier_diff(
        model_scores, baseline_scores, n_boot=n_boot, seed=seed
    )
    cal = calibration_table(probs, outcomes, n_bins=n_bins)

    interpretable = len(items) >= min_n
    verdict: str | None
    if not interpretable:
        verdict = None
        note = "non interprétable"
    else:
        note = "interpretable"
        verdict = "better_than_baseline" if improvement > 0 else "not_better_than_baseline"

    disclaimer = disclaimer_synth if illustrative else disclaimer_real
    if not interpretable:
        disclaimer = f"{disclaimer} Below minimum n={min_n}: non interprétable (n={len(items)})."

    return BrierReport(
        n=len(items),
        model_brier=model,
        baseline_brier=baseline,
        brier_skill_score=bss,
        improvement=improvement,
        bootstrap_diff_low=boot_lo,
        bootstrap_diff_high=boot_hi,
        calibration=cal,
        interpretable=interpretable,
        verdict=verdict if interpretable else None,
        illustrative=illustrative,
        disclaimer=disclaimer,
        min_n=min_n,
        extra={"status": note, "data_label": batch_label},
    )


def report_to_dict(report: BrierReport) -> dict:
    return {
        "n": report.n,
        "min_n": report.min_n,
        "interpretable": report.interpretable,
        "verdict": report.verdict if report.interpretable else "non interprétable",
        "model_brier": report.model_brier,
        "baseline_brier": report.baseline_brier,
        "brier_skill_score": report.brier_skill_score,
        "improvement": report.improvement,
        "bootstrap_diff_95": [report.bootstrap_diff_low, report.bootstrap_diff_high],
        "calibration_bins": [
            {
                "lower": b.lower,
                "upper": b.upper,
                "n": b.n,
                "mean_probability": b.mean_probability,
                "mean_outcome": b.mean_outcome,
            }
            for b in report.calibration
        ],
        "illustrative": report.illustrative,
        "disclaimer": report.disclaimer,
        **report.extra,
    }
