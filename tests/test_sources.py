"""Tests for source bias / variance / shrinkage / precision-weighted fusion.

All numeric fixtures are ILLUSTRATIVE / SYNTHETIC — not real CST outcomes.
"""

from __future__ import annotations

import math

import pytest

from data_ia.math.sources import (
    ClassPrior,
    ErrorObservation,
    SourceReliability,
    estimate_source_reliability,
    fuse_observations,
    precision_weight,
    shrink_toward_prior,
)


# ---------------------------------------------------------------------------
# Shrinkage
# ---------------------------------------------------------------------------


def test_lambda_n_formula():
    _, lam = shrink_toward_prior(empirical=1.0, prior=0.0, n=5, n0=5)
    assert lam == pytest.approx(0.5)


def test_shrink_halfway_between_empirical_and_prior():
    value, lam = shrink_toward_prior(empirical=1.0, prior=0.0, n=5, n0=5)
    assert lam == pytest.approx(0.5)
    assert value == pytest.approx(0.5)


def test_shrink_full_weight_when_n0_zero():
    value, lam = shrink_toward_prior(empirical=0.8, prior=0.0, n=3, n0=0)
    assert lam == pytest.approx(1.0)
    assert value == pytest.approx(0.8)


def test_shrink_prior_only_when_n_zero():
    value, lam = shrink_toward_prior(empirical=0.8, prior=0.1, n=0, n0=5)
    assert lam == pytest.approx(0.0)
    assert value == pytest.approx(0.1)


def test_shrink_rejects_both_zero():
    with pytest.raises(ValueError, match="both be zero"):
        shrink_toward_prior(1.0, 0.0, n=0, n0=0)


def test_shrink_rejects_negative_n():
    with pytest.raises(ValueError):
        shrink_toward_prior(1.0, 0.0, n=-1, n0=1)


# ---------------------------------------------------------------------------
# Bias / variance from resolved errors
# ---------------------------------------------------------------------------


def test_empirical_bias_is_mean_of_z_minus_x(biased_errors):
    rel = estimate_source_reliability("news_a", biased_errors, shrink=False)
    expected_bias = sum(e.z - e.x for e in biased_errors) / len(biased_errors)
    assert rel.bias == pytest.approx(expected_bias)
    assert expected_bias == pytest.approx(0.196)


def test_empirical_variance_formula(biased_errors):
    rel = estimate_source_reliability("news_a", biased_errors, shrink=False)
    residuals = [e.z - e.x for e in biased_errors]
    b = sum(residuals) / len(residuals)
    expected_var = sum((r - b) ** 2 for r in residuals) / len(residuals)
    assert rel.variance == pytest.approx(expected_var)
    assert rel.precision == pytest.approx(1.0 / expected_var)
    assert rel.variance > 1e-12  # noisy fixture, not floored


def test_tau_is_inverse_variance():
    errors = [
        ErrorObservation(z=0.6, x=0.5),
        ErrorObservation(z=0.7, x=0.5),
        ErrorObservation(z=0.4, x=0.5),
        ErrorObservation(z=0.5, x=0.5),
    ]
    rel = estimate_source_reliability("s1", errors, shrink=False)
    assert rel.precision == pytest.approx(1.0 / rel.variance)


def test_perfect_calibration_gets_variance_floor():
    errors = [ErrorObservation(z=0.5, x=0.5)] * 4
    rel = estimate_source_reliability("perfect", errors, shrink=False)
    assert rel.variance == pytest.approx(1e-12)
    assert math.isfinite(rel.precision)


def test_empty_errors_without_shrink_raises():
    with pytest.raises(ValueError, match="without observations"):
        estimate_source_reliability("s", [], shrink=False)


def test_empty_errors_with_shrink_returns_prior(unit_prior):
    rel = estimate_source_reliability("s", [], prior=unit_prior, shrink=True)
    assert rel.bias == unit_prior.bias
    assert rel.variance == unit_prior.variance
    assert rel.precision == unit_prior.precision
    assert rel.lambda_n == 0.0
    assert rel.shrunk is True


def test_shrinkage_pulls_bias_toward_prior(biased_errors):
    prior = ClassPrior(bias=0.0, variance=1.0, n0=5.0)
    emp = estimate_source_reliability("news_a", biased_errors, shrink=False)
    shr = estimate_source_reliability(
        "news_a", biased_errors, prior=prior, shrink=True
    )
    # N=5, N0=5 → halfway to prior bias 0
    assert shr.bias == pytest.approx(0.5 * emp.bias)
    assert shr.lambda_n == pytest.approx(0.5)
    assert shr.shrunk is True
    assert abs(shr.bias) < abs(emp.bias)


def test_debias_subtracts_bias():
    rel = SourceReliability(
        source_id="s",
        bias=0.2,
        variance=0.04,
        precision=25.0,
        n_obs=10,
        lambda_n=1.0,
        shrunk=False,
    )
    assert rel.debias(0.7) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Precision weights & fusion
# ---------------------------------------------------------------------------


def test_precision_weight_normalises():
    assert precision_weight(3.0, 10.0) == pytest.approx(0.3)


def test_precision_weight_rejects_non_positive_total():
    with pytest.raises(ValueError):
        precision_weight(1.0, 0.0)


def test_fusion_precision_weighted_mean():
    """Two sources, known taus → weighted average of debiased z."""
    rels = {
        "a": SourceReliability(
            "a", bias=0.0, variance=0.25, precision=4.0, n_obs=10, lambda_n=1.0, shrunk=False
        ),
        "b": SourceReliability(
            "b", bias=0.0, variance=1.0, precision=1.0, n_obs=10, lambda_n=1.0, shrunk=False
        ),
    }
    result = fuse_observations({"a": 0.6, "b": 0.4}, rels)
    # x_hat = (4*0.6 + 1*0.4) / 5 = 0.56
    assert result.estimate == pytest.approx(0.56)
    assert result.precision == pytest.approx(5.0)
    assert result.variance == pytest.approx(0.2)
    weights = {c.source_id: c.weight for c in result.contributions}
    assert weights["a"] == pytest.approx(0.8)
    assert weights["b"] == pytest.approx(0.2)


def test_fusion_debias_before_averaging():
    rels = {
        "high": SourceReliability(
            "high", bias=0.2, variance=0.25, precision=4.0, n_obs=8, lambda_n=1.0, shrunk=False
        ),
        "low": SourceReliability(
            "low", bias=-0.1, variance=1.0, precision=1.0, n_obs=8, lambda_n=1.0, shrunk=False
        ),
    }
    # Raw: 0.7 and 0.3 → debiased 0.5 and 0.4 → (4*0.5 + 1*0.4)/5 = 0.48
    result = fuse_observations({"high": 0.7, "low": 0.3}, rels)
    assert result.estimate == pytest.approx(0.48)
    by_id = {c.source_id: c for c in result.contributions}
    assert by_id["high"].z_debiased == pytest.approx(0.5)
    assert by_id["low"].z_debiased == pytest.approx(0.4)


def test_fusion_ignores_zero_precision_source():
    rels = {
        "good": SourceReliability(
            "good", bias=0.0, variance=0.25, precision=4.0, n_obs=5, lambda_n=1.0, shrunk=False
        ),
        "dead": SourceReliability(
            "dead", bias=0.0, variance=1e12, precision=0.0, n_obs=0, lambda_n=0.0, shrunk=True
        ),
    }
    result = fuse_observations({"good": 0.55, "dead": 0.99}, rels)
    assert result.estimate == pytest.approx(0.55)
    assert len(result.contributions) == 1


def test_fusion_requires_positive_precision():
    rels = {
        "dead": SourceReliability(
            "dead", bias=0.0, variance=1.0, precision=0.0, n_obs=0, lambda_n=0.0, shrunk=True
        ),
    }
    with pytest.raises(ValueError, match="positive precision"):
        fuse_observations({"dead": 0.5}, rels)


def test_fusion_empty_readings_raises():
    with pytest.raises(ValueError, match="empty"):
        fuse_observations({}, {})


def test_fusion_missing_reliability_raises():
    with pytest.raises(KeyError):
        fuse_observations(
            {"unknown": 0.5},
            {"other": SourceReliability("other", 0.0, 1.0, 1.0, 1, 1.0, False)},
        )


def test_end_to_end_estimate_then_fuse(biased_errors, unit_prior):
    """Estimate reliability from history, then fuse a new reading (synthetic)."""
    rel = estimate_source_reliability(
        "news_a", biased_errors, prior=unit_prior, shrink=True
    )
    other = SourceReliability(
        "regulator",
        bias=0.0,
        variance=0.05,
        precision=20.0,
        n_obs=20,
        lambda_n=1.0,
        shrunk=False,
    )
    result = fuse_observations(
        {"news_a": 0.65, "regulator": 0.50},
        {"news_a": rel, "regulator": other},
    )
    assert 0.0 < result.estimate < 1.0
    assert result.variance > 0
    assert abs(sum(c.weight for c in result.contributions) - 1.0) < 1e-9
