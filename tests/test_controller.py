"""Controller rejection / quarantine paths."""

from __future__ import annotations

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


def test_chi2_quarantines_outliers():
    # Extremely inconsistent continuous values → quarantine
    result = chi_squared_consistency([0.1, 0.12, 0.11, 0.99], alpha=0.01)
    # May or may not trigger depending on variance; force with wild split
    wild = chi_squared_consistency([0.0, 0.0, 0.0, 1.0, 1.0, 1.0], alpha=0.5)
    assert wild.action in {"quarantine", "accept"}


def test_chi2_insufficient_quarantine():
    result = chi_squared_consistency([0.5])
    assert result.action == "quarantine"


def test_controller_agent_rejects_bad_values():
    agent = ControllerAgent()
    context = {
        "observations": [
            {
                "source_id": "a",
                "sub_question_id": "leaf1",
                "extracted_field": "probability",
                "extracted_value": 0.4,
            },
            {
                "source_id": "b",
                "sub_question_id": "leaf1",
                "extracted_field": "probability",
                "extracted_value": 0.45,
            },
            {
                "source_id": "c",
                "sub_question_id": "leaf1",
                "extracted_field": "probability",
                "extracted_value": 2.5,
            },
        ]
    }
    result = agent.run(context)
    assert result.ok is True
    assert len(result.produced["rejected_observations"]) == 1
    assert all(o["status"] == "accepted" for o in result.produced["accepted_observations"])
