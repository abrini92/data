"""No look-ahead: future observations and post-forecast resolutions refused."""

from __future__ import annotations

import pytest

from data_ia.agents.controller import ControllerAgent
from data_ia.math.lookahead import (
    LookAheadError,
    assert_cutoff_ordering,
    assert_resolution_before_forecast,
)


def test_future_observation_rejected_by_cutoff():
    with pytest.raises(LookAheadError):
        assert_cutoff_ordering(
            published_at="2026-12-01T00:00:00+00:00",
            data_cutoff="2026-11-01T00:00:00+00:00",
            forecast_at="2026-11-01T00:00:00+00:00",
        )


def test_resolution_after_forecast_rejected():
    with pytest.raises(LookAheadError):
        assert_resolution_before_forecast("2026-12-01", "2026-11-01T00:00:00+00:00")


def test_controller_rejects_future_dated_observation():
    agent = ControllerAgent()
    context = {
        "require_extraction_fields": True,
        "forecast_at": "2026-06-01T00:00:00+00:00",
        "data_cutoff": "2026-06-01T00:00:00+00:00",
        "question": {"unit": "probability"},
        "source_priors": {"open": {"bias": 0.0, "variance": 0.1, "n0": 5}},
        "sources": [{"id": "a", "source_class": "open"}],
        "observations": [
            {
                "source_id": "a",
                "sub_question_id": "leaf1",
                "extracted_field": "probability",
                "extracted_value": 0.4,
                "unit": "probability",
                "published_at": "2026-12-01T00:00:00+00:00",
                "source_passage": "future leak",
                "data_label": "SYNTHETIC",
            }
        ],
    }
    result = agent.run(context)
    assert result.ok is False
    assert result.produced["rejected_observations"]
    assert "look_ahead" in (result.produced["rejected_observations"][0].get("rejection_reason") or "")
