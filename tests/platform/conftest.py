"""Fixtures for platform tests — all DBs / users under tmp_path."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from data_ia.db.session import reset_engine

# Fixed test secret (≥ 32 chars). Never a production key.
TEST_UI_SECRET = "test-ui-secret-key-not-for-production-use!!"


@pytest.fixture()
def platform_sqlite(tmp_path, monkeypatch):
    """Isolated SQLite registry + chain head for platform tests."""
    db = tmp_path / "platform.db"
    head = tmp_path / "head.jsonl"
    users = tmp_path / "users.json"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db.as_posix()}")
    monkeypatch.setenv("REGISTRY_CHAIN_HEAD_PATH", str(head))
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    monkeypatch.setenv("COLLECT_REAL_SOURCES", "false")
    monkeypatch.setenv("USE_SYNTHETIC", "false")
    monkeypatch.setenv("DATAIA_ENV", "test")
    monkeypatch.setenv("DATAIA_UI_SECRET_KEY", TEST_UI_SECRET)
    monkeypatch.setenv("DATAIA_UI_USERS_PATH", str(users))
    from data_ia.config import get_settings

    get_settings.cache_clear()
    reset_engine()
    yield {"db": db, "head": head, "tmp": tmp_path, "users": users}
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


def seed_user(
    users_path: Path,
    *,
    username: str = "analyst1",
    password: str = "test-password-ok",
    role: str = "analyst",
) -> None:
    from data_ia.platform.auth import add_user

    add_user(users_path, username=username, password=password, role=role)  # type: ignore[arg-type]


def app_for(db: Path, head: Path, monkeypatch, users: Path | None = None, **settings_kw):
    monkeypatch.setenv("DATAIA_ENV", settings_kw.get("env", "test"))
    monkeypatch.setenv("REGISTRY_CHAIN_HEAD_PATH", str(head))
    monkeypatch.setenv("DATAIA_UI_SECRET_KEY", settings_kw.get("ui_secret_key", TEST_UI_SECRET))
    from data_ia.platform.app import create_app
    from data_ia.platform.settings import PlatformSettings

    users_path = users or (head.parent / "users.json")
    kw = {
        "env": "test",
        "prod_explicit": False,
        "registry_chain_head_path": str(head),
        "ui_secret_key": TEST_UI_SECRET,
        "ui_users_path": str(users_path),
    }
    kw.update(settings_kw)
    if "ui_secret_key" in settings_kw:
        monkeypatch.setenv("DATAIA_UI_SECRET_KEY", str(settings_kw["ui_secret_key"]))
    settings = PlatformSettings(**kw)
    return create_app(settings=settings, db_path=db)


def client_for(app, *, follow_redirects: bool = True):
    from fastapi.testclient import TestClient

    return TestClient(app, follow_redirects=follow_redirects)


def login(
    client,
    *,
    username: str = "analyst1",
    password: str = "test-password-ok",
):
    """Obtain session via CSRF-protected form login."""
    page = client.get("/auth/login")
    assert page.status_code == 200
    match = re.search(
        r'name="csrf_token"\s+value="([^"]+)"',
        page.text,
    )
    assert match, "CSRF token missing from login form"
    csrf = match.group(1)
    resp = client.post(
        "/auth/login",
        data={"username": username, "password": password, "csrf_token": csrf},
        headers={"Accept": "application/json"},
    )
    assert resp.status_code == 200, resp.text
    return resp
