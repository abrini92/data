"""Fixtures for platform Lot 1 — all DBs under tmp_path."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from data_ia.db.session import reset_engine


@pytest.fixture()
def platform_sqlite(tmp_path, monkeypatch):
    """Isolated SQLite registry + chain head for platform tests."""
    db = tmp_path / "platform.db"
    head = tmp_path / "head.jsonl"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db.as_posix()}")
    monkeypatch.setenv("REGISTRY_CHAIN_HEAD_PATH", str(head))
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    monkeypatch.setenv("COLLECT_REAL_SOURCES", "false")
    monkeypatch.setenv("USE_SYNTHETIC", "false")
    monkeypatch.setenv("DATAIA_ENV", "test")
    from data_ia.config import get_settings

    get_settings.cache_clear()
    reset_engine()
    yield {"db": db, "head": head, "tmp": tmp_path}
    get_settings.cache_clear()
    reset_engine()


def _freeze_two(head: Path):
    from data_ia.db.session import get_session, try_init_db
    from data_ia.freeze import freeze_question

    try_init_db()
    session = get_session()
    try:
        freeze_question(
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
        freeze_question(
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
    finally:
        session.close()


@pytest.fixture()
def healthy_chain(platform_sqlite):
    _freeze_two(platform_sqlite["head"])
    return platform_sqlite


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
