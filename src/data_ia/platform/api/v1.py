"""GET-only /api/v1 routes (Lots 1–2)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from data_ia import __version__
from data_ia.platform.auth import AuthUser
from data_ia.platform.envelope import envelope
from data_ia.platform.logging import get_platform_logger
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


def _user(request: Request) -> AuthUser | None:
    return getattr(request.state, "user", None)


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
    """Read HEAD without spawning a subprocess (A3.9)."""
    try:
        from data_ia.config import REPO_ROOT

        head = REPO_ROOT / ".git" / "HEAD"
        if not head.is_file():
            return "unknown"
        content = head.read_text(encoding="utf-8").strip()
        if content.startswith("ref:"):
            ref = content.split(":", 1)[1].strip()
            ref_path = REPO_ROOT / ".git" / ref
            if ref_path.is_file():
                return ref_path.read_text(encoding="utf-8").strip()[:40]
            return "unknown"
        return content[:40]
    except Exception:  # noqa: BLE001
        return "unknown"


@router.get("/health")
def health(request: Request) -> dict[str, Any]:
    settings = _settings(request)
    st = _status(request)
    user = _user(request)
    # Minimal health without session (A2.1).
    if user is None:
        return envelope(
            {
                "version": __version__,
                "database": {
                    "present": st.present,
                    "migrated": st.migrated,
                    "message": st.message,
                    "read_only": True,
                },
                "read_only_confirmed": True,
                "mode": "minimal",
            },
            env=settings.env,
            data_label="n/a",
        )
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
            "mode": "full",
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


@router.get("/registry/verify/export")
def registry_verify_export(request: Request) -> JSONResponse:
    """Audit export JSON — evaluator only (A2.6). Generated on the fly, never stored."""
    user = _user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="authentication required")
    if user.role != "evaluator":
        raise HTTPException(status_code=403, detail="evaluator role required")
    settings = _settings(request)
    st = _status(request)
    correlation_id = getattr(request.state, "correlation_id", "")
    get_platform_logger().info(
        "audit export",
        extra={
            "event": "audit_export",
            "user": user.username,
            "role": user.role,
            "correlation_id": correlation_id,
            "route": "/api/v1/registry/verify/export",
            "method": "GET",
        },
    )
    if not st.present or not st.migrated:
        body = envelope(
            {"ok": False, "verdict": "ÉCHEC", "message": st.message, "git_commit": _git_commit()},
            env=settings.env,
            data_label="n/a",
        )
        return JSONResponse(body)
    db = _db(request)
    assert db is not None
    head = Path(settings.registry_chain_head_path)
    session = db.session()
    try:
        report = verify_svc.verify_registry_report(session, chain_head_path=head)
        label = report.pop("data_label", "REAL")
        report["git_commit"] = _git_commit()
        report["exported_by"] = user.username
        return JSONResponse(envelope(report, env=settings.env, data_label=str(label)))
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
