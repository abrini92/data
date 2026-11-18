"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from data_ia.math.sources import ClassPrior, ErrorObservation


@pytest.fixture
def unit_prior() -> ClassPrior:
    return ClassPrior(bias=0.0, variance=1.0, n0=5.0)


@pytest.fixture
def biased_errors() -> list[ErrorObservation]:
    """Source consistently high by ~0.2 with small noise (ILLUSTRATIVE)."""
    # (z, x): bias ≈ 0.2, residual noise non-zero so variance is estimable
    pairs = [
        (0.72, 0.50),
        (0.63, 0.45),
        (0.78, 0.60),
        (0.57, 0.35),
        (0.88, 0.70),
    ]
    return [ErrorObservation(z=z, x=x) for z, x in pairs]


@pytest.fixture(autouse=True)
def _isolate_chain_head(tmp_path_factory, monkeypatch):
    """Keep registry chain-head writes out of the repo during tests."""
    root = tmp_path_factory.mktemp("chain_heads")
    path = root / "registry_chain_head.jsonl"
    monkeypatch.setenv("REGISTRY_CHAIN_HEAD_PATH", str(path))
    from data_ia.config import get_settings

    get_settings.cache_clear()
    yield path
    get_settings.cache_clear()
