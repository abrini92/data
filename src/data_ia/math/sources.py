"""Source reliability model (deck slide 5 / BRIEF deliverable 4).

Observation model for source s:

    z_s = x + b_s + eps_s

where x is the latent truth, b_s is a persistent bias, and eps_s is zero-mean
noise with variance sigma_s^2.

From resolved questions with known truths x_i and source readings z_{s,i}:

    b_s     = mean(z_{s,i} - x_i)
    sigma_s^2 = mean((z_{s,i} - b_s - x_i)^2)
    tau_s   = 1 / sigma_s^2

Precision is shrunk toward a class prior with

    lambda_N = N / (N + N0)

Precision-weighted fusion of debiased observations for one sub-question:

    x_hat = sum_s (tau_s * (z_s - b_s)) / sum_s tau_s
    var   = 1 / sum_s tau_s
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

# Floor on variance so tau stays finite when a source is perfectly calibrated
# on a tiny sample (deck silent; chosen for numerical stability).
_MIN_VARIANCE = 1e-12


@dataclass(frozen=True)
class ErrorObservation:
    """One resolved (z, x) pair used to estimate source error stats."""

    z: float
    x: float


@dataclass(frozen=True)
class ClassPrior:
    """Prior for a source class (e.g. regulator site, wire news, social)."""

    bias: float = 0.0
    variance: float = 1.0
    n0: float = 5.0

    def __post_init__(self) -> None:
        if self.variance <= 0:
            raise ValueError("class prior variance must be positive")
        if self.n0 < 0:
            raise ValueError("class prior n0 must be non-negative")

    @property
    def precision(self) -> float:
        return 1.0 / self.variance


@dataclass(frozen=True)
class SourceReliability:
    """Estimated bias / precision for one source after optional shrinkage."""

    source_id: str
    bias: float
    variance: float
    precision: float
    n_obs: int
    lambda_n: float
    shrunk: bool

    def debias(self, z: float) -> float:
        return z - self.bias


@dataclass(frozen=True)
class SourceEstimate:
    """A debiased, precision-weighted contribution to a fusion."""

    source_id: str
    z_raw: float
    z_debiased: float
    precision: float
    weight: float


@dataclass(frozen=True)
class FusionResult:
    """Precision-weighted fusion of several source readings."""

    estimate: float
    variance: float
    precision: float
    contributions: tuple[SourceEstimate, ...]

    @property
    def std(self) -> float:
        return float(np.sqrt(self.variance))


def shrink_toward_prior(
    empirical: float,
    prior: float,
    n: int,
    n0: float,
) -> tuple[float, float]:
    """Shrink an empirical statistic toward a class prior.

    lambda_N = N / (N + N0). Returns (shrunk_value, lambda_N).
    When N=0, the prior is returned unchanged (lambda_N=0).
    """
    if n < 0:
        raise ValueError("n must be non-negative")
    if n0 < 0:
        raise ValueError("n0 must be non-negative")
    if n == 0 and n0 == 0:
        raise ValueError("n and n0 cannot both be zero")
    lambda_n = n / (n + n0)
    return lambda_n * empirical + (1.0 - lambda_n) * prior, lambda_n


def estimate_source_reliability(
    source_id: str,
    errors: list[ErrorObservation] | tuple[ErrorObservation, ...],
    prior: ClassPrior | None = None,
    *,
    shrink: bool = True,
) -> SourceReliability:
    """Estimate b_s, sigma_s^2, tau_s from resolved (z, x) pairs.

    If shrink=True (default), bias and variance are shrunk toward ``prior``
    (or a default zero-bias unit-variance prior) with lambda_N = N/(N+N0).
    """
    prior = prior or ClassPrior()
    n = len(errors)

    if n == 0:
        if not shrink:
            raise ValueError("cannot estimate without observations when shrink=False")
        return SourceReliability(
            source_id=source_id,
            bias=prior.bias,
            variance=prior.variance,
            precision=prior.precision,
            n_obs=0,
            lambda_n=0.0,
            shrunk=True,
        )

    zs = np.asarray([e.z for e in errors], dtype=float)
    xs = np.asarray([e.x for e in errors], dtype=float)
    residuals = zs - xs

    b_emp = float(np.mean(residuals))
    # Population-style mean of squared residual after removing estimated bias,
    # matching BRIEF: mean((z_s,i - b_s - x_i)^2).
    var_emp = float(np.mean((residuals - b_emp) ** 2))
    var_emp = max(var_emp, _MIN_VARIANCE)

    if not shrink:
        return SourceReliability(
            source_id=source_id,
            bias=b_emp,
            variance=var_emp,
            precision=1.0 / var_emp,
            n_obs=n,
            lambda_n=1.0,
            shrunk=False,
        )

    bias, lambda_n = shrink_toward_prior(b_emp, prior.bias, n, prior.n0)
    variance, _ = shrink_toward_prior(var_emp, prior.variance, n, prior.n0)
    variance = max(variance, _MIN_VARIANCE)

    return SourceReliability(
        source_id=source_id,
        bias=bias,
        variance=variance,
        precision=1.0 / variance,
        n_obs=n,
        lambda_n=lambda_n,
        shrunk=True,
    )


def precision_weight(precision: float, total_precision: float) -> float:
    """Normalised weight tau_s / sum_j tau_j."""
    if total_precision <= 0:
        raise ValueError("total precision must be positive")
    if precision < 0:
        raise ValueError("precision must be non-negative")
    return precision / total_precision


def n_eff(n: int, rho: float) -> float:
    """Effective independent-source count under pairwise correlation rho.

    n_eff = n / (1 + (n - 1) * rho)

    rho=0 → n_eff=n (independent); rho=1 → n_eff=1 (fully redundant).
    """
    if n < 1:
        raise ValueError("n must be at least 1")
    if not 0.0 <= rho <= 1.0:
        raise ValueError("rho must be in [0, 1]")
    return float(n) / (1.0 + (n - 1) * rho)


def fuse_observations(
    readings: dict[str, float],
    reliabilities: dict[str, SourceReliability],
    *,
    correlation_groups: Mapping[str, Sequence[str]] | None = None,
    group_rho: Mapping[str, float] | None = None,
) -> FusionResult:
    """Precision-weighted fusion of debiased source readings for one node.

    ``readings`` maps source_id -> raw observation z_s.
    Sources present in readings but missing from reliabilities raise KeyError.
    Sources with zero precision are ignored; at least one positive precision
    is required.

    Optional correlation: ``correlation_groups`` maps group_id -> source ids
    that relay the same wire (or otherwise share noise). ``group_rho`` maps
    group_id -> pairwise correlation in [0, 1]. Each member of a group of
    size n with correlation rho has its precision scaled by n_eff/n so the
    group's total precision matches tau * n_eff when members share equal tau.
    """
    if not readings:
        raise ValueError("readings must not be empty")

    scale_by_source = _correlation_precision_scales(
        list(readings.keys()),
        correlation_groups=correlation_groups,
        group_rho=group_rho,
    )

    total_tau = 0.0
    weighted_sum = 0.0
    parts: list[tuple[str, float, float, float]] = []

    for source_id, z in readings.items():
        rel = reliabilities[source_id]
        tau = rel.precision * scale_by_source.get(source_id, 1.0)
        if tau <= 0:
            continue
        z_hat = rel.debias(z)
        total_tau += tau
        weighted_sum += tau * z_hat
        parts.append((source_id, z, z_hat, tau))

    if total_tau <= 0:
        raise ValueError("at least one source must have positive precision")

    estimate = weighted_sum / total_tau
    contributions = tuple(
        SourceEstimate(
            source_id=sid,
            z_raw=z_raw,
            z_debiased=z_deb,
            precision=tau,
            weight=precision_weight(tau, total_tau),
        )
        for sid, z_raw, z_deb, tau in parts
    )

    return FusionResult(
        estimate=float(estimate),
        variance=float(1.0 / total_tau),
        precision=float(total_tau),
        contributions=contributions,
    )


def _correlation_precision_scales(
    source_ids: Sequence[str],
    *,
    correlation_groups: Mapping[str, Sequence[str]] | None,
    group_rho: Mapping[str, float] | None,
) -> dict[str, float]:
    """Return per-source precision multipliers (default 1.0)."""
    scales = {sid: 1.0 for sid in source_ids}
    if not correlation_groups:
        return scales

    rhos = group_rho or {}
    claimed: set[str] = set()
    for gid, members in correlation_groups.items():
        present = [sid for sid in members if sid in scales]
        if not present:
            continue
        overlap = claimed.intersection(present)
        if overlap:
            raise ValueError(
                f"source(s) {sorted(overlap)!r} appear in multiple correlation groups"
            )
        claimed.update(present)
        if len(present) < 2:
            continue
        rho = float(rhos.get(gid, 0.0))
        eff = n_eff(len(present), rho)
        factor = eff / float(len(present))
        for sid in present:
            scales[sid] = factor
    return scales
