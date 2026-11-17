"""Prior mapping: NIG provisional config; loader rejects bad k / nu0."""

from __future__ import annotations

import pytest

from data_ia.priors import (
    PriorMappingError,
    class_prior_from_score,
    load_prior_mapping,
    nig_prior_for_class,
    prior_variance_for_score,
    validate_prior_mapping,
)


def _valid_nig(**overrides):
    base = {
        "status": "CONVENTION – PROVISIONAL, not calibrated",
        "nig": {
            "b0": 0.0,
            "kappa0": 2.0,
            "nu0": 4.0,
            "sigma2_ref": 0.10,
        },
        "k_by_class": {"A": 0.5, "B": 1.0, "C": 1.25, "D": 2.0},
        "prior_bias": 0.0,
        "score_to_variance": [
            {"score": 0.0, "variance": 0.40},
            {"score": 0.5, "variance": 0.20},
            {"score": 1.0, "variance": 0.05},
        ],
    }
    base.update(overrides)
    return base


def test_default_mapping_is_nig_provisional():
    data = load_prior_mapping()
    validate_prior_mapping(data)
    assert "PROVISIONAL" in str(data.get("status", "")).upper()
    nig = data["nig"]
    assert nig["b0"] == 0.0
    assert nig["kappa0"] == pytest.approx(2.0)
    assert nig["nu0"] == pytest.approx(4.0)
    assert nig["nu0"] > 2
    assert data["k_by_class"] == {"A": 0.5, "B": 1.0, "C": 1.25, "D": 2.0}


def test_nig_s0_sq_by_class():
    data = load_prior_mapping()
    a = nig_prior_for_class("A", data)
    d = nig_prior_for_class("D", data)
    assert a["b0"] == 0.0
    assert a["s0_sq"] == pytest.approx(0.5 * float(data["nig"]["sigma2_ref"]))
    assert d["s0_sq"] == pytest.approx(2.0 * float(data["nig"]["sigma2_ref"]))
    assert a["s0_sq"] < d["s0_sq"]


def test_higher_score_lower_variance():
    data = load_prior_mapping()
    v_low = prior_variance_for_score(0.5, data)
    v_high = prior_variance_for_score(0.95, data)
    assert v_high < v_low
    prior = class_prior_from_score(0.9, data)
    assert prior.bias == 0.0
    assert prior.variance == pytest.approx(prior_variance_for_score(0.9, data))


def test_rejects_non_monotonic_k_table():
    bad = _valid_nig(k_by_class={"A": 0.5, "B": 1.0, "C": 0.8, "D": 2.0})
    with pytest.raises(PriorMappingError, match="monotone"):
        validate_prior_mapping(bad)


def test_rejects_nu0_le_2():
    bad = _valid_nig()
    bad["nig"] = {**bad["nig"], "nu0": 2.0}
    with pytest.raises(PriorMappingError, match="nu0"):
        validate_prior_mapping(bad)


def test_rejects_non_monotonic_score_table():
    bad = _valid_nig(
        score_to_variance=[
            {"score": 0.0, "variance": 0.1},
            {"score": 0.5, "variance": 0.2},
            {"score": 1.0, "variance": 0.05},
        ]
    )
    with pytest.raises(PriorMappingError):
        validate_prior_mapping(bad)


def test_source_priors_bias_aligned_on_b0():
    import yaml
    from data_ia.config import REPO_ROOT

    path = REPO_ROOT / "config" / "source_priors.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    for name, cfg in data.items():
        assert float(cfg["bias"]) == 0.0, name
