"""B3: chained hashes, exported head, detect coherent rewrite and deletion."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from data_ia.db.session import reset_engine


@pytest.fixture()
def sqlite_env(tmp_path, monkeypatch):
    db = tmp_path / "chain.db"
    head = tmp_path / "head.jsonl"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db.as_posix()}")
    monkeypatch.setenv("REGISTRY_CHAIN_HEAD_PATH", str(head))
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    monkeypatch.setenv("COLLECT_REAL_SOURCES", "false")
    monkeypatch.setenv("USE_SYNTHETIC", "false")
    from data_ia.config import get_settings

    get_settings.cache_clear()
    reset_engine()
    yield {"db": db, "head": head}
    get_settings.cache_clear()
    reset_engine()


def _freeze_two(head: Path):
    from data_ia.db.session import get_session, try_init_db
    from data_ia.freeze import freeze_question

    try_init_db()
    session = get_session()
    try:
        r1 = freeze_question(
            session,
            question_id="P1",
            probability=0.4,
            data_cutoff="2026-11-18T02:00:00+03:00",
            forecast_at="2026-11-19T12:00:00+03:00",
            series_id="series_a",
            vintage_sha256="a" * 64,
            data_label="TEST",
            changes=[1, 1, -1, 1, 1, 1, -1, 1],
            allow_dirty=True,
            chain_head_path=head,
        )
        r2 = freeze_question(
            session,
            question_id="P3",
            probability=0.55,
            data_cutoff="2026-11-18T02:00:00+03:00",
            forecast_at="2026-11-19T13:00:00+03:00",
            series_id="series_b",
            vintage_sha256="b" * 64,
            data_label="TEST",
            changes=[1, -1, 1, -1, 1, -1, 1],
            allow_dirty=True,
            chain_head_path=head,
        )
        session.commit()
        return r1, r2
    finally:
        session.close()


def test_chain_links_and_head_ok(sqlite_env):
    from data_ia.db.models import ForecastRegistry
    from data_ia.db.session import get_session, try_init_db
    from data_ia.forecast_registry import verify_registry

    _freeze_two(sqlite_env["head"])
    try_init_db()
    session = get_session()
    try:
        rows = session.query(ForecastRegistry).order_by(ForecastRegistry.id).all()
        assert len(rows) == 2
        assert rows[0].prev_sha256 is None
        assert rows[1].prev_sha256 == rows[0].sha256
        assert rows[0].git_commit != "unknown"
        report = verify_registry(session, chain_head_path=sqlite_env["head"])
        assert report["ok"] is True
    finally:
        session.close()


def test_coherent_rewrite_detected(sqlite_env):
    from data_ia.db.session import get_session, try_init_db
    from data_ia.forecast_registry import row_fields, verify_registry
    from data_ia.math.registry_hash import forecast_sha256

    _freeze_two(sqlite_env["head"])
    try_init_db()
    session = get_session()
    try:
        session.execute(text("DROP TRIGGER IF EXISTS forecast_registry_no_update"))
        # Coherent rewrite of probability + sha on row 1 (breaks chain to row 2 / head)
        row = session.execute(
            text("SELECT id, sha256 FROM forecast_registry ORDER BY id")
        ).first()
        # Update probability; recompute sha without fixing chain / head
        session.execute(
            text("UPDATE forecast_registry SET probability = 0.99 WHERE id = :id"),
            {"id": row.id},
        )
        session.commit()
        # Re-load and set a matching sha for the tampered fields only
        from data_ia.db.models import ForecastRegistry

        tampered = session.get(ForecastRegistry, row.id)
        fields = row_fields(tampered)
        fields["probability"] = 0.99
        new_sha = forecast_sha256(fields)
        session.execute(text("DROP TRIGGER IF EXISTS forecast_registry_no_update"))
        session.execute(
            text("UPDATE forecast_registry SET sha256 = :sha WHERE id = :id"),
            {"sha": new_sha, "id": row.id},
        )
        session.commit()
        report = verify_registry(session, chain_head_path=sqlite_env["head"])
        assert report["ok"] is False
        assert report["chain_breaks"] or report["head_mismatch"] or report["mismatches"]
    finally:
        session.close()


def test_deletion_detected(sqlite_env):
    from data_ia.db.session import get_session, try_init_db
    from data_ia.forecast_registry import verify_registry

    _freeze_two(sqlite_env["head"])
    try_init_db()
    session = get_session()
    try:
        session.execute(text("DROP TRIGGER IF EXISTS forecast_registry_no_delete"))
        session.execute(text("DELETE FROM forecast_registry WHERE id = 1"))
        session.commit()
        report = verify_registry(session, chain_head_path=sqlite_env["head"])
        assert report["ok"] is False
        assert report["id_gaps"] or report["chain_breaks"] or report["head_mismatch"]
    finally:
        session.close()


def test_git_commit_unknown_refused(sqlite_env, monkeypatch):
    from data_ia.db.session import get_session, try_init_db
    from data_ia.forecast_registry import RegistryIntegrityError, append_forecast
    from data_ia.db.models import Question

    try_init_db()
    session = get_session()
    try:
        session.add(Question(id="Qx", text="x", status="active"))
        session.flush()
        with pytest.raises(RegistryIntegrityError, match="unknown"):
            append_forecast(
                session,
                question_id="Qx",
                forecast_at=datetime(2026, 11, 18, tzinfo=timezone.utc),
                data_cutoff=datetime(2026, 11, 17, tzinfo=timezone.utc),
                observation_ids=[],
                probability=0.5,
                interval_low=None,
                interval_high=None,
                data_label="TEST",
                git_commit="unknown",
                export_head=False,
            )
    finally:
        session.close()
