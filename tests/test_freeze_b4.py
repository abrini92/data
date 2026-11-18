"""B4: freeze-by-question into a separate TEST registry."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from data_ia.db.session import reset_engine
from data_ia.freeze_calendar import clear_freeze_calendar_cache


@pytest.fixture()
def test_registry(tmp_path, monkeypatch):
    db = tmp_path / "test_registry.db"
    head = tmp_path / "chain_head.jsonl"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db.as_posix()}")
    monkeypatch.setenv("REGISTRY_CHAIN_HEAD_PATH", str(head))
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    monkeypatch.setenv("COLLECT_REAL_SOURCES", "false")
    monkeypatch.setenv("USE_SYNTHETIC", "false")
    from data_ia.config import get_settings

    get_settings.cache_clear()
    clear_freeze_calendar_cache()
    reset_engine()
    yield {"db": db, "head": head}
    get_settings.cache_clear()
    clear_freeze_calendar_cache()
    reset_engine()


def test_freeze_p1_in_separate_test_registry(test_registry):
    from data_ia.cli import main
    from data_ia.db.models import ForecastRegistry
    from data_ia.db.session import get_session, try_init_db
    from data_ia.forecast_registry import replay_forecast, verify_registry

    changes = "-1.7,-1.1,-1.1,-0.2,-7.3,2.7,1.3,0.5,-0.2,0.7,1.5,-1.3"
    code = main(
        [
            "freeze",
            "--question",
            "P1",
            "--probability",
            "0.42",
            "--data-cutoff",
            "2026-11-18T02:41:32+03:00",
            "--forecast-at",
            "2026-11-20T12:00:00+03:00",
            "--series",
            "riyad_bank_saudi_pmi_headline",
            "--series-changes",
            changes,
            "--label",
            "TEST",
            "--database-url",
            f"sqlite:///{test_registry['db'].as_posix()}",
            "--chain-head",
            str(test_registry["head"]),
        ]
    )
    assert code == 0

    try_init_db()
    session = get_session()
    try:
        rows = session.query(ForecastRegistry).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.question_id == "P1"
        assert row.data_label == "TEST"
        assert row.p_base == pytest.approx(0.3714, abs=1e-4)
        assert row.baseline_method and "persist_v3" in row.baseline_method
        assert row.data_cutoff != row.forecast_at
        assert row.series_id
        assert row.vintage_sha256
        assert row.git_commit != "unknown"
        assert row.prev_sha256 is None
        report = verify_registry(session, chain_head_path=test_registry["head"])
        assert report["ok"] is True
        replay = replay_forecast(session, row.id)
        assert replay["ok"] is True
        assert replay["mode"] == "frozen_baseline"
    finally:
        session.close()


def test_freeze_refused_after_deadline(test_registry):
    from data_ia.cli import main

    code = main(
        [
            "freeze",
            "--question",
            "P1",
            "--probability",
            "0.5",
            "--data-cutoff",
            "2026-11-18T00:00:00+03:00",
            "--forecast-at",
            "2026-12-01T00:00:00+03:00",  # after 30 Nov 23:59
            "--series",
            "riyad_bank_saudi_pmi_headline",
            "--series-changes",
            "1,1,1,1,1,1,1",
            "--label",
            "TEST",
            "--database-url",
            f"sqlite:///{test_registry['db'].as_posix()}",
            "--chain-head",
            str(test_registry["head"]),
        ]
    )
    assert code == 1
