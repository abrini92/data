"""Controller rejection / quarantine paths."""

from __future__ import annotations

import math

import pytest

from data_ia.agents.controller import ControllerAgent
from data_ia.math.controller_rules import (
    ExtractedObservation,
    ExtractionSchema,
    chi_squared_consistency,
    validate_schema_and_range,
)


def test_reject_out_of_range():
    schema = ExtractionSchema("probability", 0.0, 1.0, "probability")
    obs = ExtractedObservation("s", "probability", 1.5)
    result = validate_schema_and_range(obs, schema)
    assert result.accepted is False
    assert result.action == "reject"


def test_reject_wrong_type():
    schema = ExtractionSchema("probability", 0.0, 1.0, "probability")
    obs = ExtractedObservation("s", "probability", "not-a-number")
    result = validate_schema_and_range(obs, schema)
    assert result.action == "reject"


def test_accept_in_range():
    schema = ExtractionSchema("probability", 0.0, 1.0, "probability")
    obs = ExtractedObservation("s", "probability", 0.42)
    result = validate_schema_and_range(obs, schema)
    assert result.accepted is True
    assert result.cleaned_value == pytest.approx(0.42)


def test_non_finite_quarantine():
    schema = ExtractionSchema("probability", 0.0, 1.0, "probability")
    for bad in (math.nan, math.inf, -math.inf):
        obs = ExtractedObservation("s", "probability", bad)
        result = validate_schema_and_range(obs, schema)
        assert result.accepted is False
        assert result.action == "quarantine"
        assert any(i.code == "non_finite" for i in result.issues)


def test_chi2_quarantines_outliers():
    # Clear outlier under tight source variances → quarantine
    wild = chi_squared_consistency(
        [0.40, 0.41, 0.39, 0.95],
        variances=[0.0001, 0.0001, 0.0001, 0.0001],
        alpha=0.01,
    )
    assert wild.action == "quarantine"
    assert any(i.code == "chi2_inconsistent" for i in wild.issues)

    # Consistent set under the same variance model → accept
    consistent = chi_squared_consistency(
        [0.40, 0.41, 0.39, 0.405],
        variances=[0.01, 0.01, 0.01, 0.01],
        alpha=0.01,
    )
    assert consistent.accepted is True
    assert consistent.action == "accept"


def test_chi2_single_source_accepted():
    result = chi_squared_consistency([0.5])
    assert result.accepted is True
    assert "single_source" in result.flags


def test_controller_agent_rejects_bad_values():
    agent = ControllerAgent()
    context = {
        "require_extraction_fields": True,
        "forecast_at": "2026-11-18T00:00:00+00:00",
        "data_cutoff": "2026-11-18T00:00:00+00:00",
        "question": {"unit": "probability"},
        "source_priors": {"open": {"bias": 0.0, "variance": 0.1, "n0": 5}},
        "sources": [
            {"id": "a", "source_class": "open"},
            {"id": "b", "source_class": "open"},
            {"id": "c", "source_class": "open"},
        ],
        "observations": [
            {
                "source_id": "a",
                "sub_question_id": "leaf1",
                "extracted_field": "probability",
                "extracted_value": 0.4,
                "unit": "probability",
                "published_at": "2026-01-01T00:00:00+00:00",
                "source_passage": "a says 0.4",
                "data_label": "SYNTHETIC",
            },
            {
                "source_id": "b",
                "sub_question_id": "leaf1",
                "extracted_field": "probability",
                "extracted_value": 0.45,
                "unit": "probability",
                "published_at": "2026-01-01T00:00:00+00:00",
                "source_passage": "b says 0.45",
                "data_label": "SYNTHETIC",
            },
            {
                "source_id": "c",
                "sub_question_id": "leaf1",
                "extracted_field": "probability",
                "extracted_value": 2.5,
                "unit": "probability",
                "published_at": "2026-01-01T00:00:00+00:00",
                "source_passage": "c says 2.5",
                "data_label": "SYNTHETIC",
            },
        ],
    }
    result = agent.run(context)
    assert result.ok is True
    assert len(result.produced["rejected_observations"]) == 1
    assert all(o["status"] == "accepted" for o in result.produced["accepted_observations"])
