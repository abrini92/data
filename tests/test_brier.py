"""Brier proof tests — synthetic labels required."""

from __future__ import annotations

import pytest

from data_ia.math.brier import ResolvedForecast, brier_score, evaluate_proof


def test_brier_perfect_and_worst():
    assert brier_score([1.0, 0.0], [1, 0]) == pytest.approx(0.0)
    assert brier_score([0.0, 1.0], [1, 0]) == pytest.approx(1.0)


def test_evaluate_proof_beats_naive_on_calibrated_set():
    forecasts = [
        ResolvedForecast("a", 0.9, 1, "ILLUSTRATIVE/SYNTHETIC"),
        ResolvedForecast("b", 0.1, 0, "ILLUSTRATIVE/SYNTHETIC"),
        ResolvedForecast("c", 0.8, 1, "ILLUSTRATIVE/SYNTHETIC"),
        ResolvedForecast("d", 0.2, 0, "ILLUSTRATIVE/SYNTHETIC"),
    ]
    report = evaluate_proof(forecasts)
    assert report.illustrative is True
    assert "ILLUSTRATIVE" in report.disclaimer.upper() or "SYNTHETIC" in report.disclaimer.upper()
    assert report.model_brier < report.baseline_brier
    assert report.improvement == pytest.approx(report.baseline_brier - report.model_brier)
