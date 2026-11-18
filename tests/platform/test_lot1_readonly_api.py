"""BRIEF-5 Lot 1 acceptance: A1.1–A1.8 (updated for Lot 2 auth)."""

from __future__ import annotations

import hashlib
import socket
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="platform tests need the [ui] extra")
from sqlalchemy import text

from data_ia.config import REPO_ROOT
from data_ia.platform.settings import PROD_DB_PATH, PlatformConfigError
from tests.platform.conftest import TEST_UI_SECRET, app_for, client_for, login, seed_user


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _authed(healthy_chain, monkeypatch, role: str = "analyst"):
    users = healthy_chain["users"]
    seed_user(users, username="u1", password="test-password-ok", role=role)
    app = app_for(healthy_chain["db"], healthy_chain["head"], monkeypatch, users=users)
    client = client_for(app)
    login(client, username="u1", password="test-password-ok")
    return client


# --- A1.1 -----------------------------------------------------------------


def test_a1_1_adapter_rejects_writes(tmp_path):
    import sqlite3

    from data_ia.platform.readonly import ReadOnlyError, open_readonly

    db_path = tmp_path / "ro.db"
    con = sqlite3.connect(db_path)
    con.execute("CREATE TABLE t (x INTEGER)")
    con.execute("INSERT INTO t VALUES (1)")
    con.commit()
    con.close()

    db = open_readonly(db_path)
    for sql in (
        "INSERT INTO t VALUES (2)",
        "UPDATE t SET x = 3",
        "DELETE FROM t",
        "CREATE TABLE u (y INTEGER)",
    ):
        with pytest.raises(ReadOnlyError):
            db.attempt_write(sql)
    with pytest.raises(Exception):
        with db.engine().connect() as conn:
            conn.execute(text("INSERT INTO t VALUES (9)"))
            conn.commit()


# --- A1.2 -----------------------------------------------------------------


def _all_route_paths(app) -> set[str]:
    paths: set[str] = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        if path:
            paths.add(path)
    return paths


def test_a1_2_mutation_methods_405_except_auth(healthy_chain, monkeypatch):
    users = healthy_chain["users"]
    seed_user(users)
    app = app_for(healthy_chain["db"], healthy_chain["head"], monkeypatch, users=users)
    client = client_for(app)
    login(client)

    api_paths = _all_route_paths(app)
    assert "/api/v1/health" in api_paths
    mutations = ["POST", "PUT", "PATCH", "DELETE"]
    probe_paths = {
        p.replace("{row_id}", "1").replace("{wave_id}", "vague1")
        for p in api_paths
    }
    for path in sorted(probe_paths):
        if path.startswith("/auth/"):
            continue
        for method in mutations:
            resp = client.request(method, path)
            assert resp.status_code == 405, f"{method} {path} -> {resp.status_code}"

    # Auth POST is allowed; other verbs 405.
    page = client.get("/auth/login")
    assert page.status_code == 200
    assert client.put("/auth/login").status_code == 405
    assert client.post("/auth/logout", data={"csrf_token": "bad"}).status_code in {
        403,
        303,
        200,
    }


# --- A1.3 -----------------------------------------------------------------


def test_a1_3_db_sha256_unchanged_after_api_session(healthy_chain, monkeypatch):
    db = healthy_chain["db"]
    before = file_sha256(db)
    client = _authed(healthy_chain, monkeypatch)
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/registry/rows").status_code == 200
    assert client.get("/api/v1/registry/verify").status_code == 200
    assert client.get("/api/v1/waves").status_code == 200
    rows = client.get("/api/v1/registry/rows").json()["rows"]
    if rows:
        assert client.get(f"/api/v1/registry/rows/{rows[0]['id']}").status_code == 200
    after = file_sha256(db)
    assert after == before


# --- A1.4 -----------------------------------------------------------------


def test_a1_4_verify_matches_engine_ok(healthy_chain, monkeypatch):
    from data_ia.db.session import get_session, try_init_db
    from data_ia.forecast_registry import verify_registry

    try_init_db()
    session = get_session()
    try:
        engine_report = verify_registry(
            session, chain_head_path=healthy_chain["head"]
        )
    finally:
        session.close()

    client = _authed(healthy_chain, monkeypatch)
    api = client.get("/api/v1/registry/verify").json()
    assert engine_report["ok"] is True
    assert api["ok"] is True
    assert api["verdict"] == "OK"
    assert (0 if engine_report["ok"] else 1) == (0 if api["ok"] else 1)


def test_a1_4_verify_detects_rewrite(healthy_chain, monkeypatch):
    from data_ia.db.models import ForecastRegistry
    from data_ia.db.session import get_session, try_init_db
    from data_ia.forecast_registry import row_fields, verify_registry
    from data_ia.math.registry_hash import forecast_sha256

    try_init_db()
    session = get_session()
    try:
        session.execute(text("DROP TRIGGER IF EXISTS forecast_registry_no_update"))
        row = session.execute(
            text("SELECT id FROM forecast_registry ORDER BY id")
        ).first()
        session.execute(
            text("UPDATE forecast_registry SET probability = 0.99 WHERE id = :id"),
            {"id": row.id},
        )
        session.commit()
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
        engine_report = verify_registry(
            session, chain_head_path=healthy_chain["head"]
        )
    finally:
        session.close()

    assert engine_report["ok"] is False
    client = _authed(healthy_chain, monkeypatch)
    api = client.get("/api/v1/registry/verify").json()
    assert api["ok"] is False
    assert api["verdict"] == "ÉCHEC"
    assert (0 if api["ok"] else 1) == 1


def test_a1_4_verify_detects_deletion(healthy_chain, monkeypatch):
    from data_ia.db.session import get_session, try_init_db
    from data_ia.forecast_registry import verify_registry

    try_init_db()
    session = get_session()
    try:
        session.execute(text("DROP TRIGGER IF EXISTS forecast_registry_no_delete"))
        session.execute(text("DELETE FROM forecast_registry WHERE id = 1"))
        session.commit()
        engine_report = verify_registry(
            session, chain_head_path=healthy_chain["head"]
        )
    finally:
        session.close()

    assert engine_report["ok"] is False
    client = _authed(healthy_chain, monkeypatch)
    api = client.get("/api/v1/registry/verify").json()
    assert api["ok"] is False
    assert api["verdict"] == "ÉCHEC"


# --- A1.5 -----------------------------------------------------------------


def test_a1_5_test_env_refuses_prod_db(monkeypatch, tmp_path):
    from data_ia.platform.settings import PlatformSettings

    monkeypatch.setenv("DATAIA_ENV", "test")
    monkeypatch.setenv("DATAIA_UI_SECRET_KEY", TEST_UI_SECRET)
    settings = PlatformSettings(
        env="test",
        ui_secret_key=TEST_UI_SECRET,
        ui_test_db_path=str(PROD_DB_PATH),
        registry_chain_head_path=str(tmp_path / "head.jsonl"),
    )
    with pytest.raises(PlatformConfigError, match="refuses production database"):
        settings.resolved_sqlite_path()


def test_a1_5_prod_without_explicit_refused(monkeypatch, tmp_path):
    from data_ia.platform.settings import PlatformSettings

    monkeypatch.delenv("DATAIA_ENV", raising=False)
    monkeypatch.setenv("DATAIA_UI_SECRET_KEY", TEST_UI_SECRET)
    with pytest.raises(Exception, match="explicit"):
        PlatformSettings(
            env="prod",
            prod_explicit=False,
            ui_secret_key=TEST_UI_SECRET,
            registry_chain_head_path=str(tmp_path / "head.jsonl"),
        )


# --- A1.6 -----------------------------------------------------------------


def test_a1_6_missing_db_health_no_create(tmp_path, monkeypatch):
    missing = tmp_path / "does_not_exist.db"
    head = tmp_path / "head.jsonl"
    users = tmp_path / "users.json"
    head.write_text("", encoding="utf-8")
    assert not missing.exists()
    seed_user(users)
    app = app_for(missing, head, monkeypatch, users=users)
    client = client_for(app)
    # Health is public (minimal).
    body = client.get("/api/v1/health").json()
    assert body["database"]["present"] is False
    assert "base absente" in body["database"]["message"]
    assert not missing.exists()


def test_a1_6_unmigrated_schema_message(tmp_path, monkeypatch):
    from data_ia.migrate_registry import open_legacy_sqlite_schema

    db = tmp_path / "legacy.db"
    head = tmp_path / "head.jsonl"
    users = tmp_path / "users.json"
    head.write_text("", encoding="utf-8")
    con = open_legacy_sqlite_schema(db)
    con.close()
    before = file_sha256(db)
    seed_user(users)
    app = app_for(db, head, monkeypatch, users=users)
    client = client_for(app)
    health = client.get("/api/v1/health").json()
    assert health["database"]["present"] is True
    assert health["database"]["migrated"] is False
    assert "schéma non migré" in health["database"]["message"]
    login(client)
    rows = client.get("/api/v1/registry/rows").json()
    assert rows["rows"] == []
    assert "schéma non migré" in rows.get("message", "")
    assert file_sha256(db) == before


# --- A1.7 -----------------------------------------------------------------


def test_a1_7_envelope_fields(healthy_chain, monkeypatch):
    client = _authed(healthy_chain, monkeypatch)
    for path in (
        "/api/v1/health",
        "/api/v1/registry/rows",
        "/api/v1/registry/verify",
        "/api/v1/waves",
    ):
        body = client.get(path).json()
        assert "data_label" in body
        assert body["env"] == "test"
        assert "generated_at" in body
        assert body["generated_at"].endswith("+03:00")


# --- A1.8 -----------------------------------------------------------------


def test_a1_8_no_network_connect(healthy_chain, monkeypatch):
    real_connect = socket.socket.connect

    def _boom(self, address):  # noqa: ANN001
        host = address[0] if isinstance(address, tuple) else str(address)
        if host in {"127.0.0.1", "::1", "localhost"}:
            return real_connect(self, address)
        raise AssertionError(f"network connect forbidden: {address!r}")

    monkeypatch.setattr(socket.socket, "connect", _boom)
    client = _authed(healthy_chain, monkeypatch)
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/registry/rows").status_code == 200
    rows = client.get("/api/v1/registry/rows").json().get("rows") or []
    if rows:
        assert client.get(f"/api/v1/registry/rows/{rows[0]['id']}").status_code == 200
    assert client.get("/api/v1/registry/verify").status_code == 200
    assert client.get("/api/v1/waves").status_code == 200
    waves = client.get("/api/v1/waves").json().get("waves") or []
    if waves:
        wid = waves[0]["id"]
        assert client.get(f"/api/v1/waves/{wid}").status_code == 200


def test_a0_guards_paths_exist():
    """Sanity: inventory from Lot 0 and production path constant."""
    assert (REPO_ROOT / "docs" / "PLATFORM-INVENTORY.md").is_file()
    assert PROD_DB_PATH.name == "dataia.db"
