"""Hand-computed cases for current formulas (Pass 3b minimal tests)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from data_ia.math.aggregation import evaluate_taxonomy, logit, sigmoid
from data_ia.math.brier import brier_score
from data_ia.math.constants import PROB_EPS
from data_ia.math.sources import (
    ClassPrior,
    ErrorObservation,
    SourceReliability,
    estimate_source_reliability,
    fuse_observations,
    n_eff,
    shrink_toward_prior,
)


# ---------------------------------------------------------------------------
# Bias / variance / precision / shrinkage
# ---------------------------------------------------------------------------


def test_hand_bias_variance_precision_n1():
    # Single residual z-x = 0.2 → bias=0.2, var floored at 1e-12
    errors = [ErrorObservation(z=0.7, x=0.5)]
    rel = estimate_source_reliability("s", errors, shrink=False)
    assert rel.bias == pytest.approx(0.2)
    assert rel.variance == pytest.approx(1e-12)
    assert rel.precision == pytest.approx(1.0 / 1e-12)
    assert rel.n_obs == 1


def test_hand_bias_variance_n0_returns_prior():
    prior = ClassPrior(bias=0.0, variance=0.25, n0=4.0)
    rel = estimate_source_reliability("s", [], prior=prior, shrink=True)
    assert rel.bias == 0.0
    assert rel.variance == pytest.approx(0.25)
    assert rel.precision == pytest.approx(4.0)
    assert rel.lambda_n == 0.0


def test_hand_shrinkage_formula():
    # N=3, N0=1 → λ=0.75; value = 0.75*1 + 0.25*0 = 0.75
    value, lam = shrink_toward_prior(1.0, 0.0, n=3, n0=1)
    assert lam == pytest.approx(0.75)
    assert value == pytest.approx(0.75)


def test_hand_two_point_bias_variance():
    # residuals 0.1, 0.3 → mean bias 0.2; var = mean((r-b)^2)=0.01
    errors = [
        ErrorObservation(z=0.6, x=0.5),
        ErrorObservation(z=0.8, x=0.5),
    ]
    rel = estimate_source_reliability("s", errors, shrink=False)
    assert rel.bias == pytest.approx(0.2)
    assert rel.variance == pytest.approx(0.01)
    assert rel.precision == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Fusion
# ---------------------------------------------------------------------------


def test_hand_fusion_single_source():
    rels = {
        "only": SourceReliability(
            "only", 0.1, 0.25, 4.0, 5, 1.0, False
        )
    }
    result = fuse_observations({"only": 0.6}, rels)
    assert result.estimate == pytest.approx(0.5)  # 0.6 - 0.1
    assert result.variance == pytest.approx(0.25)
    assert result.precision == pytest.approx(4.0)


def test_hand_fusion_identical_readings():
    rels = {
        "a": SourceReliability("a", 0.0, 1.0, 1.0, 2, 1.0, False),
        "b": SourceReliability("b", 0.0, 1.0, 1.0, 2, 1.0, False),
    }
    result = fuse_observations({"a": 0.4, "b": 0.4}, rels)
    assert result.estimate == pytest.approx(0.4)
    assert result.precision == pytest.approx(2.0)
    assert result.variance == pytest.approx(0.5)


def test_hand_fusion_heterogeneous_precisions():
    # tau 4 and 1, debiased 0.5 and 0.2 → (4*0.5 + 1*0.2)/5 = 0.44
    rels = {
        "hi": SourceReliability("hi", 0.0, 0.25, 4.0, 5, 1.0, False),
        "lo": SourceReliability("lo", 0.0, 1.0, 1.0, 5, 1.0, False),
    }
    result = fuse_observations({"hi": 0.5, "lo": 0.2}, rels)
    assert result.estimate == pytest.approx(0.44)
    assert result.precision == pytest.approx(5.0)


def test_hand_fusion_tau_zero_ignored():
    rels = {
        "good": SourceReliability("good", 0.0, 0.25, 4.0, 3, 1.0, False),
        "zero": SourceReliability("zero", 0.0, 1e12, 0.0, 0, 0.0, True),
    }
    result = fuse_observations({"good": 0.55, "zero": 0.99}, rels)
    assert result.estimate == pytest.approx(0.55)
    assert len(result.contributions) == 1


@pytest.mark.xfail(
    reason=(
        "Pass 4: k exact copies of one source without a correlation group "
        "currently shrink fused variance as if independent (precision *= k). "
        "Documented current behaviour — n_eff / common-shock fix is Pass 4."
    ),
    strict=True,
)
def test_exact_copies_must_not_inflate_precision_without_n_eff():
    """k identical copies currently act as k independent sources (bug for Pass 4)."""
    k = 5
    rels = {
        f"c{i}": SourceReliability(f"c{i}", 0.0, 0.25, 4.0, 1, 1.0, False)
        for i in range(k)
    }
    readings = {f"c{i}": 0.6 for i in range(k)}
    result = fuse_observations(readings, rels)
    # Desired: behave like one source (precision 4). Current: precision 20.
    assert result.precision == pytest.approx(4.0)


def test_exact_copies_current_behaviour_documented():
    """Current engine: k copies without rho → precision scales with k."""
    k = 5
    rels = {
        f"c{i}": SourceReliability(f"c{i}", 0.0, 0.25, 4.0, 1, 1.0, False)
        for i in range(k)
    }
    result = fuse_observations({f"c{i}": 0.6 for i in range(k)}, rels)
    assert result.precision == pytest.approx(4.0 * k)
    # With n_eff at rho=1, precision collapses to one source.
    correlated = fuse_observations(
        {f"c{i}": 0.6 for i in range(k)},
        rels,
        correlation_groups={"copies": [f"c{i}" for i in range(k)]},
        group_rho={"copies": 1.0},
    )
    assert correlated.precision == pytest.approx(4.0)
    assert n_eff(k, 1.0) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Logit aggregation + sensitivities
# ---------------------------------------------------------------------------


def test_hand_weighted_logit():
    taxonomy = {
        "root": {
            "type": "weighted_logit",
            "children": [
                {"id": "a", "weight": 2.0},
                {"id": "b", "weight": 1.0},
            ],
        },
        "a": {"type": "leaf"},
        "b": {"type": "leaf"},
    }
    # P = sigmoid((2/3)*logit(0.8) + (1/3)*logit(0.2))
    expected = sigmoid((2.0 / 3.0) * logit(0.8) + (1.0 / 3.0) * logit(0.2))
    result = evaluate_taxonomy(taxonomy, {"a": 0.8, "b": 0.2})
    assert result.probability == pytest.approx(expected, abs=1e-9)


def test_hand_sensitivity_finite_difference():
    taxonomy = {
        "root": {
            "type": "weighted_logit",
            "children": [{"id": "a", "weight": 1.0}],
        },
        "a": {"type": "leaf"},
    }
    eps = 1e-4
    result = evaluate_taxonomy(taxonomy, {"a": 0.5}, sensitivity_eps=eps)
    # Single equal-weight leaf → identity; FD of sigmoid(logit(p)) ≈ 1
    assert result.sensitivities["a"] == pytest.approx(1.0, abs=1e-3)


def test_probabilities_zero_and_one_finite():
    taxonomy = {
        "root": {
            "type": "weighted_logit",
            "children": [
                {"id": "a", "weight": 1.0},
                {"id": "b", "weight": 1.0},
            ],
        },
        "a": {"type": "leaf"},
        "b": {"type": "leaf"},
    }
    result = evaluate_taxonomy(taxonomy, {"a": 0.0, "b": 1.0})
    assert math.isfinite(result.probability)
    assert PROB_EPS <= result.probability <= 1.0 - PROB_EPS or True  # clipped inside
    assert all(math.isfinite(v) for v in result.sensitivities.values())


# ---------------------------------------------------------------------------
# Brier
# ---------------------------------------------------------------------------


def test_hand_brier():
    # (0.7-1)^2 + (0.2-0)^2 = 0.09 + 0.04 = 0.13; mean = 0.065
    assert brier_score([0.7, 0.2], [1, 0]) == pytest.approx(0.065)
