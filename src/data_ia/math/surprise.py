"""Investigator surprise: surprise = -log P(x_t | past).

Deck silent on the exact predictive density; we use a Gaussian predictive
from the empirical mean/variance of the past series (with a variance floor).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats

_MIN_VAR = 1e-6


@dataclass(frozen=True)
class SurpriseResult:
    surprise: float
    log_prob: float
    mean: float
    variance: float
    x_t: float


def gaussian_surprise(x_t: float, past: list[float] | tuple[float, ...]) -> SurpriseResult:
    """Compute -log P(x_t | past) under N(mean(past), var(past))."""
    if not past:
        # Uninformative: unit Gaussian centred at 0.5 for probability-like series
        mean = 0.5
        var = 1.0
    else:
        arr = np.asarray(past, dtype=float)
        mean = float(np.mean(arr))
        var = float(np.var(arr)) if arr.size > 1 else 1.0
        var = max(var, _MIN_VAR)

    log_prob = float(stats.norm.logpdf(x_t, loc=mean, scale=np.sqrt(var)))
    return SurpriseResult(
        surprise=float(-log_prob),
        log_prob=log_prob,
        mean=mean,
        variance=var,
        x_t=float(x_t),
    )
