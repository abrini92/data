"""USE_SYNTHETIC default off; hard block with COLLECT_REAL_SOURCES."""

from __future__ import annotations

import pytest

from data_ia.db.session import reset_engine


def test_use_synthetic_defaults_false(monkeypatch):
    monkeypatch.delenv("USE_SYNTHETIC", raising=False)
    monkeypatch.delenv("COLLECT_REAL_SOURCES", raising=False)
    from data_ia.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    assert settings.use_synthetic is False
    assert settings.collect_real_sources is False
    get_settings.cache_clear()


def test_real_plus_synthetic_refused(monkeypatch):
    monkeypatch.setenv("COLLECT_REAL_SOURCES", "true")
    monkeypatch.setenv("USE_SYNTHETIC", "true")
    from data_ia.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(ValueError, match="forbidden|USE_SYNTHETIC|COLLECT_REAL"):
        get_settings()
    get_settings.cache_clear()
    monkeypatch.setenv("COLLECT_REAL_SOURCES", "false")
    monkeypatch.setenv("USE_SYNTHETIC", "false")
    get_settings.cache_clear()


def test_cli_cycle_refuses_real_plus_synthetic(monkeypatch, capsys):
    monkeypatch.setenv("COLLECT_REAL_SOURCES", "true")
    monkeypatch.setenv("USE_SYNTHETIC", "true")
    from data_ia.config import get_settings
    from data_ia.cli import main

    get_settings.cache_clear()
    code = main(["cycle"])
    get_settings.cache_clear()
    monkeypatch.setenv("COLLECT_REAL_SOURCES", "false")
    monkeypatch.setenv("USE_SYNTHETIC", "false")
    assert code == 2
