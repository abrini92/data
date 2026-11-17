"""Brier proof tests — registry scoring, BSS, bootstrap, edge cases."""

from __future__ import annotations

import math

import pytest

from data_ia.math.brier import (
    ResolvedForecast,
    brier_score,
    evaluate_proof,
    report_to_dict,
)
from data_ia.math.labels import MixedLabelError


def test_brier_perfect_and_worst():
    assert brier_score([1.0, 0.0], [1, 0]) == pytest.approx(0.0)
    assert brier_score([0.0, 1.0], [1, 0]) == pytest.approx(1.0)


def test_evaluate_proof_beats_naive_on_calibrated_set():
    forecasts = [
        ResolvedForecast("a", 0.9, 1, "ILLUSTRATIVE/SYNTHETIC", 0.5),
        ResolvedForecast("b", 0.1, 0, "ILLUSTRATIVE/SYNTHETIC", 0.5),
        ResolvedForecast("c", 0.8, 1, "ILLUSTRATIVE/SYNTHETIC", 0.5),
        ResolvedForecast("d", 0.2, 0, "ILLUSTRATIVE/SYNTHETIC", 0.5),
    ]
    report = evaluate_proof(forecasts, min_n=4)
    assert report.illustrative is True
    assert "ILLUSTRATIVE" in report.disclaimer.upper() or "SYNTHETIC" in report.disclaimer.upper()
    assert report.model_brier is not None and report.baseline_brier is not None
    assert report.model_brier < report.baseline_brier
    assert report.brier_skill_score == pytest.approx(
        1.0 - report.model_brier / report.baseline_brier
    )
    assert report.bootstrap_diff_low is not None
    assert report.calibration
    assert report.interpretable is True


def test_below_min_n_non_interpretable():
    forecasts = [
        ResolvedForecast("a", 0.9, 1, "SYNTHETIC", 0.5),
        ResolvedForecast("b", 0.1, 0, "SYNTHETIC", 0.5),
    ]
    report = evaluate_proof(forecasts, min_n=30)
    assert report.interpretable is False
    assert report.verdict is None
    assert "non interprétable" in report.disclaimer.lower() or "non interprétable" in report_to_dict(report)["verdict"]


def test_empty_batch():
    report = evaluate_proof([], min_n=30)
    assert report.n == 0
    assert report.interpretable is False


def test_all_same_outcomes():
    forecasts = [
        ResolvedForecast(f"q{i}", 0.8, 1, "SYNTHETIC", 1.0) for i in range(5)
    ]
    report = evaluate_proof(forecasts, min_n=5)
    assert report.n == 5
    assert report.model_brier is not None


def test_probability_zero_and_one():
    forecasts = [
        ResolvedForecast("a", 0.0, 0, "SYNTHETIC", 0.5),
        ResolvedForecast("b", 1.0, 1, "SYNTHETIC", 0.5),
    ]
    report = evaluate_proof(forecasts, min_n=2)
    assert report.model_brier == pytest.approx(0.0)


def test_nan_probability_rejected():
    with pytest.raises(ValueError):
        ResolvedForecast("a", math.nan, 1, "SYNTHETIC", 0.5)


def test_mixed_labels_refused():
    forecasts = [
        ResolvedForecast("a", 0.9, 1, "REAL", 0.5),
        ResolvedForecast("b", 0.1, 0, "SYNTHETIC", 0.5),
    ]
    with pytest.raises(MixedLabelError):
        evaluate_proof(forecasts, min_n=2)
