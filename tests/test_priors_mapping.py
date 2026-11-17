"""Prior mapping: monotonic score→variance; loader rejects non-monotonic tables."""

from __future__ import annotations

import pytest

from data_ia.priors import (
    PriorMappingError,
    class_prior_from_score,
    load_prior_mapping,
    prior_variance_for_score,
    validate_prior_mapping,
)


def test_default_mapping_is_monotonic():
    data = load_prior_mapping()
    validate_prior_mapping(data)
    scores = [float(r["score"]) for r in data["score_to_variance"]]
    variances = [float(r["variance"]) for r in data["score_to_variance"]]
    assert scores == sorted(scores)
    assert all(variances[i] > variances[i + 1] for i in range(len(variances) - 1))
    assert "PROVISIONAL" in str(data.get("status", "")).upper()


def test_higher_score_lower_variance():
    data = load_prior_mapping()
    v_low = prior_variance_for_score(0.5, data)
    v_high = prior_variance_for_score(0.95, data)
    assert v_high < v_low
    prior = class_prior_from_score(0.9, data)
    assert prior.bias == 0.0
    assert prior.variance == pytest.approx(prior_variance_for_score(0.9, data))


def test_rejects_non_monotonic_table():
    bad = {
        "prior_bias": 0.0,
        "n0": 5.0,
        "score_to_variance": [
            {"score": 0.0, "variance": 0.1},
            {"score": 0.5, "variance": 0.2},  # variance increases — invalid
            {"score": 1.0, "variance": 0.05},
        ],
    }
    with pytest.raises(PriorMappingError):
        validate_prior_mapping(bad)
