"""Append-only forecast registry: hash verify, tamper, replay, dual cycle."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from data_ia.config import REPO_ROOT
from data_ia.db.session import reset_engine


@pytest.fixture()
def sqlite_env(tmp_path, monkeypatch):
    db = tmp_path / "reg.db"
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


def test_two_cycles_append_two_registry_rows(sqlite_env, monkeypatch):
    from data_ia.agents.pipeline import run_offline_cycle
    from data_ia.config import get_settings
    from data_ia.db.models import ForecastRegistry
    from data_ia.db.session import get_session, try_init_db
    from data_ia.forecast_registry import verify_registry

    seed = REPO_ROOT / "seeds" / "ksa_macro_2026.yaml"
    monkeypatch.setenv("TAXONOMY_PATH", str(REPO_ROOT / "config" / "taxonomy.yaml"))
    get_settings.cache_clear()

    t0 = datetime(2026, 11, 18, 10, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 11, 18, 11, 0, 0, tzinfo=timezone.utc)
    r1 = run_offline_cycle(seed_path=seed, persist=True, forecast_at=t0)
    r2 = run_offline_cycle(seed_path=seed, persist=True, forecast_at=t1)
    assert r1["forecast_registry_id"] is not None
    assert r2["forecast_registry_id"] is not None
    assert r1["forecast_registry_id"] != r2["forecast_registry_id"]

    try_init_db()
    session = get_session()
    try:
        n = session.query(ForecastRegistry).count()
        assert n >= 2
        report = verify_registry(session)
        assert report["ok"] is True
        assert report["n"] >= 2
    finally:
        session.close()


def test_tampered_hash_fails_verify(sqlite_env, monkeypatch):
    from data_ia.agents.pipeline import run_offline_cycle
    from data_ia.config import get_settings
    from data_ia.db.session import get_session, try_init_db
    from data_ia.forecast_registry import verify_registry

    seed = REPO_ROOT / "seeds" / "ksa_macro_2026.yaml"
    monkeypatch.setenv("TAXONOMY_PATH", str(REPO_ROOT / "config" / "taxonomy.yaml"))
    get_settings.cache_clear()
    run_offline_cycle(seed_path=seed, persist=True)

    try_init_db()
    session = get_session()
    try:
        # Bypass ORM trigger by using a raw connection after disabling triggers? 
        # SQLite triggers block UPDATE — so we recreate table content via delete+insert
        # is also blocked. Use PRAGMA / drop trigger for the tamper simulation only.
        session.execute(text("DROP TRIGGER IF EXISTS forecast_registry_no_update"))
        session.execute(
            text("UPDATE forecast_registry SET sha256 = 'deadbeef' WHERE id = 1")
        )
        session.commit()
        report = verify_registry(session)
        assert report["ok"] is False
        assert report["mismatches"]
    finally:
        session.close()


def test_replay_reproduces_probability(sqlite_env, monkeypatch):
    from data_ia.agents.pipeline import load_yaml, run_offline_cycle
    from data_ia.config import get_settings
    from data_ia.db.session import get_session, try_init_db
    from data_ia.forecast_registry import replay_forecast

    seed_path = REPO_ROOT / "seeds" / "ksa_macro_2026.yaml"
    monkeypatch.setenv("TAXONOMY_PATH", str(REPO_ROOT / "config" / "taxonomy.yaml"))
    get_settings.cache_clear()
    result = run_offline_cycle(seed_path=seed_path, persist=True)
    fid = result["forecast_registry_id"]
    assert fid is not None

    try_init_db()
    session = get_session()
    try:
        settings = get_settings()
        seed = load_yaml(seed_path)
        taxonomy = load_yaml(settings.taxonomy_path)
        priors = load_yaml(settings.source_priors_path)
        report = replay_forecast(
            session, int(fid), seed=seed, taxonomy=taxonomy, source_priors=priors
        )
        assert report["ok"] is True
        assert report["replayed_probability"] == pytest.approx(
            report["stored_probability"], abs=1e-9
        )
    finally:
        session.close()


def test_append_only_trigger_rejects_update(sqlite_env, monkeypatch):
    from data_ia.agents.pipeline import run_offline_cycle
    from data_ia.config import get_settings
    from data_ia.db.session import get_session, try_init_db
    from sqlalchemy.exc import OperationalError

    seed = REPO_ROOT / "seeds" / "ksa_macro_2026.yaml"
    monkeypatch.setenv("TAXONOMY_PATH", str(REPO_ROOT / "config" / "taxonomy.yaml"))
    get_settings.cache_clear()
    run_offline_cycle(seed_path=seed, persist=True)

    try_init_db()
    session = get_session()
    try:
        with pytest.raises((OperationalError, Exception)):
            session.execute(
                text("UPDATE forecast_registry SET probability = 0.99 WHERE id = 1")
            )
            session.commit()
    finally:
        session.rollback()
        session.close()
