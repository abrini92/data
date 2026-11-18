"""GET-only /api/v1 routes (Lot 1)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from data_ia import __version__
from data_ia.platform.envelope import envelope
from data_ia.platform.readonly import DatabaseStatus, ReadOnlyDatabase
from data_ia.platform.services import registry as registry_svc
from data_ia.platform.services import verify as verify_svc
from data_ia.platform.services import waves as waves_svc
from data_ia.platform.settings import PlatformSettings

router = APIRouter(prefix="/api/v1")


def _settings(request: Request) -> PlatformSettings:
    return request.app.state.settings


def _db(request: Request) -> ReadOnlyDatabase | None:
    return getattr(request.app.state, "db", None)


def _status(request: Request) -> DatabaseStatus:
    db = _db(request)
    if db is None:
        return DatabaseStatus(
            present=False,
            migrated=False,
            path=None,
            message="base absente",
            read_only=True,
        )
    return db.status()


def _git_commit() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(Path(__file__).resolve().parents[4]),
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()[:40]
    except Exception:  # noqa: BLE001
        return "unknown"


@router.get("/health")
def health(request: Request) -> dict[str, Any]:
    settings = _settings(request)
    st = _status(request)
    return envelope(
        {
            "version": __version__,
            "git_commit": _git_commit(),
            "database": {
                "present": st.present,
                "migrated": st.migrated,
                "path": st.path,
                "message": st.message,
                "read_only": st.read_only,
            },
            "read_only_confirmed": True,
        },
        env=settings.env,
        data_label="n/a",
    )


@router.get("/registry/rows")
def registry_rows(
    request: Request, offset: int = 0, limit: int = 100
) -> dict[str, Any]:
    settings = _settings(request)
    st = _status(request)
    if not st.present:
        return envelope(
            {"rows": [], "total": 0, "offset": offset, "limit": limit, "message": st.message},
            env=settings.env,
            data_label="n/a",
        )
    if not st.migrated:
        return envelope(
            {"rows": [], "total": 0, "offset": offset, "limit": limit, "message": st.message},
            env=settings.env,
            data_label="n/a",
        )
    db = _db(request)
    assert db is not None
    session = db.session()
    try:
        payload = registry_svc.list_registry_rows(session, offset=offset, limit=limit)
        label = payload.pop("data_label")
        return envelope(payload, env=settings.env, data_label=label)
    finally:
        session.close()


@router.get("/registry/rows/{row_id}")
def registry_row(request: Request, row_id: int) -> dict[str, Any]:
    settings = _settings(request)
    st = _status(request)
    if not st.present or not st.migrated:
        raise HTTPException(status_code=404, detail=st.message)
    db = _db(request)
    assert db is not None
    session = db.session()
    try:
        row = registry_svc.get_registry_row(session, row_id)
        if row is None:
            raise HTTPException(status_code=404, detail="row not found")
        label = row.get("data_label") or "n/a"
        return envelope({"row": row}, env=settings.env, data_label=str(label))
    finally:
        session.close()


@router.get("/registry/verify")
def registry_verify(request: Request) -> dict[str, Any]:
    settings = _settings(request)
    st = _status(request)
    if not st.present:
        return envelope(
            {"ok": False, "verdict": "ÉCHEC", "message": st.message},
            env=settings.env,
            data_label="n/a",
        )
    if not st.migrated:
        return envelope(
            {"ok": False, "verdict": "ÉCHEC", "message": st.message},
            env=settings.env,
            data_label="n/a",
        )
    db = _db(request)
    assert db is not None
    head = Path(settings.registry_chain_head_path)
    session = db.session()
    try:
        report = verify_svc.verify_registry_report(session, chain_head_path=head)
        label = report.pop("data_label", "REAL")
        return envelope(report, env=settings.env, data_label=str(label))
    finally:
        session.close()


@router.get("/waves")
def waves_list(request: Request) -> dict[str, Any]:
    settings = _settings(request)
    payload = waves_svc.list_waves(Path(settings.waves_dir))
    label = payload.pop("data_label", "REAL")
    return envelope(payload, env=settings.env, data_label=str(label))


@router.get("/waves/{wave_id}")
def waves_one(request: Request, wave_id: str) -> dict[str, Any]:
    settings = _settings(request)
    try:
        item = waves_svc.get_wave(wave_id, waves_dir=Path(settings.waves_dir))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="wave not found") from None
    label = item.get("data_label") or "REAL"
    return envelope({"wave": item}, env=settings.env, data_label=str(label))


def method_not_allowed_response() -> JSONResponse:
    return JSONResponse({"detail": "Method Not Allowed"}, status_code=405)
