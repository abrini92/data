"""BRIEF-5 Lot 2 acceptance: A2.1–A2.7."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="platform tests need the [ui] extra")

from data_ia.config import REPO_ROOT
from data_ia.platform.auth import (
    SESSION_COOKIE,
    add_user,
    hash_password,
    verify_password,
)
from data_ia.platform.logging import CORRELATION_HEADER, clear_redactions, register_redaction
from data_ia.platform.settings import PlatformConfigError, load_platform_settings
from tests.platform.conftest import (
    TEST_UI_SECRET,
    app_for,
    client_for,
    login,
    seed_user,
)


def test_a2_1_unauthenticated_api_401_except_health(healthy_chain, monkeypatch):
    users = healthy_chain["users"]
    seed_user(users)
    app = app_for(healthy_chain["db"], healthy_chain["head"], monkeypatch, users=users)
    client = client_for(app)
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json().get("mode") == "minimal"
    for path in (
        "/api/v1/registry/rows",
        "/api/v1/registry/verify",
        "/api/v1/waves",
        "/api/v1/registry/verify/export",
    ):
        resp = client.get(path, headers={"Accept": "application/json"})
        assert resp.status_code == 401, path
    # HTML pages redirect to login (do not follow redirects).
    bare = client_for(app, follow_redirects=False)
    page = bare.get("/", headers={"Accept": "text/html"})
    assert page.status_code in {302, 307}
    assert "/auth/login" in page.headers.get("location", "")


def test_a2_2_scrypt_unique_salts_and_users_gitignored(tmp_path):
    salt1, h1 = hash_password("same-password-value")
    salt2, h2 = hash_password("same-password-value")
    assert salt1 != salt2
    assert h1 != h2
    assert verify_password("same-password-value", salt1, h1)
    assert not verify_password("wrong", salt1, h1)

    users_path = tmp_path / "ui" / "users.json"
    add_user(users_path, username="a", password="password-aa", role="viewer")
    add_user(users_path, username="b", password="password-aa", role="analyst")
    data = json.loads(users_path.read_text(encoding="utf-8"))
    hashes = [u["password_hash"] for u in data["users"]]
    salts = [u["salt"] for u in data["users"]]
    assert hashes[0] != hashes[1]
    assert salts[0] != salts[1]
    # Default users path under data/ui/ is gitignored.
    import subprocess

    proc = subprocess.run(
        ["git", "check-ignore", "-v", "data/ui/users.json"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "data/ui" in proc.stdout or "users" in proc.stdout or proc.stdout.strip()


def test_a2_3_session_cookie_flags_and_csrf(healthy_chain, monkeypatch):
    users = healthy_chain["users"]
    seed_user(users)
    app = app_for(healthy_chain["db"], healthy_chain["head"], monkeypatch, users=users)
    client = client_for(app)
    resp = login(client)
    # Cookie flags from Set-Cookie on login response.
    set_cookie = resp.headers.get("set-cookie", "")
    # Starlette may split cookies; inspect client cookies jar + raw header.
    assert SESSION_COOKIE in client.cookies
    # HttpOnly / SameSite=Strict on session cookie.
    assert "HttpOnly" in set_cookie or "httponly" in set_cookie.lower()
    assert "samesite=strict" in set_cookie.lower()

    # Tampered cookie refused.
    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE, "definitely-not-a-valid-signature")
    denied = client.get("/api/v1/registry/rows", headers={"Accept": "application/json"})
    assert denied.status_code == 401

    # Fresh client: POST login without CSRF refused.
    client2 = client_for(app)
    bad = client2.post(
        "/auth/login",
        data={"username": "analyst1", "password": "test-password-ok", "csrf_token": "nope"},
        headers={"Accept": "application/json"},
    )
    assert bad.status_code == 403


def test_a2_4_canary_env_never_leaks(healthy_chain, monkeypatch, caplog):
    canary_secret = "CANARY_SECRET_VALUE_XYZ_9911_LONG"
    canary_other = "CANARY_OTHER_ENV_VALUE_7711_LONG"
    monkeypatch.setenv("DATAIA_UI_SECRET_KEY", canary_secret)
    monkeypatch.setenv("DATAIA_CANARY_PROBE", canary_other)
    register_redaction(canary_secret, canary_other)
    clear_redactions()
    register_redaction(canary_secret, canary_other)

    # Config error must not echo the key.
    with pytest.raises(PlatformConfigError) as excinfo:
        load_platform_settings(ui_secret_key="short")
    assert canary_secret not in str(excinfo.value)
    assert "short" not in str(excinfo.value).lower() or "missing" in str(excinfo.value).lower()

    users = healthy_chain["users"]
    seed_user(users)
    # App with canary secret; force a 500 via a route that raises.
    app = app_for(
        healthy_chain["db"],
        healthy_chain["head"],
        monkeypatch,
        users=users,
        ui_secret_key=canary_secret,
    )

    @app.get("/api/v1/_boom")
    def _boom():  # noqa: ANN202
        raise RuntimeError(f"boom {canary_secret} {canary_other}")

    client = client_for(app)
    login(client)
    with caplog.at_level(logging.ERROR, logger="data_ia.platform"):
        resp = client.get("/api/v1/_boom", headers={"Accept": "application/json"})
    assert resp.status_code == 500
    body = resp.text
    assert canary_secret not in body
    assert canary_other not in body
    # Captured log records redacted.
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert canary_secret not in joined
    assert canary_other not in joined


def test_a2_5_json_logs_and_correlation_header(healthy_chain, monkeypatch, tmp_path):
    users = healthy_chain["users"]
    seed_user(users)
    log_dir = tmp_path / "logs"
    app = app_for(
        healthy_chain["db"],
        healthy_chain["head"],
        monkeypatch,
        users=users,
        ui_log_dir=str(log_dir),
    )
    client = client_for(app)
    login(client)
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    cid = resp.headers.get(CORRELATION_HEADER)
    assert cid
    log_path = log_dir / "platform.log"
    assert log_path.is_file()
    lines = [ln for ln in log_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines
    for ln in lines:
        obj = json.loads(ln)
        assert isinstance(obj, dict)
        assert "ts" in obj
        assert "level" in obj


def test_a2_6_audit_export_role_gate(healthy_chain, monkeypatch):
    users = healthy_chain["users"]
    seed_user(users, username="viewer1", password="test-password-ok", role="viewer")
    seed_user(users, username="analyst1", password="test-password-ok", role="analyst")
    seed_user(users, username="eval1", password="test-password-ok", role="evaluator")
    app = app_for(healthy_chain["db"], healthy_chain["head"], monkeypatch, users=users)

    for name, expect in (("viewer1", 403), ("analyst1", 403), ("eval1", 200)):
        client = client_for(app)
        login(client, username=name, password="test-password-ok")
        resp = client.get("/api/v1/registry/verify/export")
        assert resp.status_code == expect, name
        if expect == 200:
            body = resp.json()
            assert "verdict" in body
            assert "git_commit" in body


def test_a2_7_refuses_missing_or_short_secret(monkeypatch, tmp_path):
    monkeypatch.delenv("DATAIA_UI_SECRET_KEY", raising=False)
    with pytest.raises(PlatformConfigError) as missing:
        load_platform_settings(
            ui_secret_key="",
            registry_chain_head_path=str(tmp_path / "h.jsonl"),
        )
    msg = str(missing.value)
    assert "SECRET" in msg.upper() or "missing" in msg.lower() or "short" in msg.lower()
    # Must not echo an attempted short key value.
    with pytest.raises(PlatformConfigError) as short:
        load_platform_settings(
            ui_secret_key="tiny",
            registry_chain_head_path=str(tmp_path / "h.jsonl"),
        )
    assert "tiny" not in str(short.value)
