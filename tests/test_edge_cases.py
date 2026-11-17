"""Edge-case hygiene: empty, labels, duplicates, hash, NaN."""

from __future__ import annotations

import math

import pytest

from data_ia.math.brier import evaluate_proof
from data_ia.math.controller_rules import (
    ExtractedObservation,
    ExtractionSchema,
    validate_schema_and_range,
)
from data_ia.math.labels import MixedLabelError, assert_homogeneous_labels
from data_ia.math.registry_hash import forecast_sha256


def test_mixed_labels_assert():
    with pytest.raises(MixedLabelError):
        assert_homogeneous_labels(["REAL", "SYNTHETIC"], context="edge")


def test_duplicated_observation_ids_in_hash_payload():
    fields = {
        "question_id": "q",
        "forecast_at": "2026-01-01T00:00:00+00:00",
        "data_cutoff": "2026-01-01T00:00:00+00:00",
        "git_commit": "abc",
        "config_hash": "def",
        "extractor_version": "0.1.0",
        "observation_ids": [1, 1, 2],
        "probability": 0.5,
        "interval_low": 0.1,
        "interval_high": 0.9,
        "data_label": "SYNTHETIC",
    }
    h1 = forecast_sha256(fields)
    fields2 = dict(fields)
    fields2["observation_ids"] = [1, 2]
    h2 = forecast_sha256(fields2)
    assert h1 != h2


def test_hash_tampering_changes_digest():
    fields = {
        "question_id": "q",
        "forecast_at": "2026-01-01T00:00:00+00:00",
        "data_cutoff": "2026-01-01T00:00:00+00:00",
        "git_commit": "abc",
        "config_hash": "def",
        "extractor_version": "0.1.0",
        "observation_ids": [1],
        "probability": 0.5,
        "interval_low": 0.1,
        "interval_high": 0.9,
        "data_label": "SYNTHETIC",
    }
    h1 = forecast_sha256(fields)
    fields["probability"] = 0.51
    assert forecast_sha256(fields) != h1


def test_inf_rejected_by_schema():
    schema = ExtractionSchema("probability", 0.0, 1.0, "probability")
    result = validate_schema_and_range(
        ExtractedObservation("s", "probability", math.inf), schema
    )
    assert result.action == "quarantine"


def test_empty_brier_batch():
    report = evaluate_proof([])
    assert report.n == 0
    assert report.interpretable is False
