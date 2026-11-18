"""Persistence v3 baseline — hand-checked against scripts/persist_v3.py."""

from __future__ import annotations

import pytest

from data_ia.math.persist_v3 import historical_frequency, p_haut


def test_p_haut_p1_last12_matches_reference():
    # From waves/vague1_bases_valeurs.yaml P1 method_detail (changes only; no PMI levels).
    changes = [-1.7, -1.1, -1.1, -0.2, -7.3, 2.7, 1.3, 0.5, -0.2, 0.7, 1.5, -1.3]
    p, detail = p_haut(changes)
    assert p == pytest.approx(0.3714, abs=1e-4)
    assert "markov" in detail


def test_p_haut_short_series_returns_half():
    p, detail = p_haut([1.0, -1.0])
    assert p == 0.5
    assert "justification" in detail


def test_historical_frequency_laplace():
    # k=3, n=4 → (3+1)/(4+2) = 4/6
    p, detail = historical_frequency([1, 0, 1, 1])
    assert p == pytest.approx(4 / 6)
    assert "frequency_laplace" in detail
