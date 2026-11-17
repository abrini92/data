"""End-to-end offline cycle without Docker (SQLite)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from data_ia.config import REPO_ROOT
from data_ia.db.session import reset_engine


@pytest.fixture()
def sqlite_env(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db.as_posix()}")
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    monkeypatch.setenv("COLLECT_REAL_SOURCES", "false")
    monkeypatch.setenv("USE_SYNTHETIC", "false")
    from data_ia.config import get_settings

    get_settings.cache_clear()
    reset_engine()
    yield db
    get_settings.cache_clear()
    reset_engine()


def test_offline_cycle_produces_probability(sqlite_env, monkeypatch):
    from data_ia.agents.pipeline import run_offline_cycle
    from data_ia.config import get_settings

    seed = REPO_ROOT / "seeds" / "ksa_macro_2026.yaml"
    assert seed.exists()
    monkeypatch.setenv("TAXONOMY_PATH", str(REPO_ROOT / "config" / "taxonomy.yaml"))
    get_settings.cache_clear()
    result = run_offline_cycle(seed_path=seed, persist=True)
    assert result["db_mode"] in {"sqlite", "sqlite-fallback"}
    assert result["final_probability"] is not None
    assert 0.0 <= result["final_probability"] <= 1.0
    assert result["disclaimer"]
    assert "ILLUSTRATIVE" in result["disclaimer"].upper() or "SYNTHETIC" in result["disclaimer"].upper() or "stub" in result["disclaimer"].lower()
    assert result.get("forecast_registry_id") is not None
    agents_ok = {r["agent"]: r["ok"] for r in result["agent_results"]}
    assert agents_ok.get("orchestrator") is True
    assert agents_ok.get("strategist") is True


def test_cycle_default_seed_with_clean_environment(tmp_path, monkeypatch):
    """Default seed path must work with no SEED_PATH / no .env file."""
    from pathlib import Path

    from data_ia.agents.pipeline import run_offline_cycle
    from data_ia.config import Settings, get_settings
    from data_ia.db.session import reset_engine

    # Leave the repo .env behind so Settings does not pick it up.
    monkeypatch.chdir(tmp_path)
    for var in (
        "SEED_PATH",
        "TAXONOMY_PATH",
        "SOURCE_PRIORS_PATH",
        "PRIOR_MAPPING_PATH",
        "SOURCES_REGISTRY_PATH",
        "LLM_PROVIDER",
        "COLLECT_REAL_SOURCES",
        "USE_SYNTHETIC",
        "LLM_API_KEY",
        "EIA_API_KEY",
        "GASTAT_API_KEY",
        "SAMA_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)

    db = tmp_path / "clean.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db.as_posix()}")
    get_settings.cache_clear()
    reset_engine()

    settings = Settings(_env_file=None)
    assert Path(settings.seed_path).is_file(), f"default seed missing: {settings.seed_path}"
    get_settings.cache_clear()
    try:
        result = run_offline_cycle(persist=True)
    finally:
        get_settings.cache_clear()
        reset_engine()

    assert result["final_probability"] is not None
    assert 0.0 <= result["final_probability"] <= 1.0
    agents_ok = {r["agent"]: r["ok"] for r in result["agent_results"]}
    assert agents_ok.get("strategist") is True


def test_optional_starlink_seed_still_runs(sqlite_env, monkeypatch):
    from data_ia.agents.pipeline import run_offline_cycle
    from data_ia.config import get_settings

    seed = REPO_ROOT / "seeds" / "starlink_ksa.yaml"
    monkeypatch.setenv(
        "TAXONOMY_PATH", str(REPO_ROOT / "config" / "taxonomy_starlink.yaml")
    )
    get_settings.cache_clear()
    result = run_offline_cycle(seed_path=seed, persist=True)
    assert result["final_probability"] is not None
    assert 0.0 <= result["final_probability"] <= 1.0


def test_nonoil_seed_not_ready(sqlite_env, monkeypatch):
    from data_ia.agents.pipeline import run_offline_cycle
    from data_ia.config import get_settings

    seed = REPO_ROOT / "seeds" / "ksa_nonoil_growth_2027.yaml"
    get_settings.cache_clear()
    result = run_offline_cycle(seed_path=seed, persist=True)
    assert result.get("not_ready") is True
    assert result.get("final_probability") is None


@pytest.mark.postgres
def test_postgres_optional():
    """Skipped unless DATABASE_URL is postgres and server is up."""
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("DATABASE_URL is not postgres")
    from sqlalchemy import create_engine, text

    try:
        eng = create_engine(url)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"postgres unavailable: {exc}")
