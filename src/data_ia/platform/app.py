"""FastAPI application factory (Lot 1: API only, no auth)."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from data_ia.platform.api.v1 import router as v1_router
from data_ia.platform.readonly import ReadOnlyDatabase, open_readonly
from data_ia.platform.settings import (
    PlatformConfigError,
    PlatformSettings,
    load_platform_settings,
)


def create_app(
    settings: PlatformSettings | None = None,
    *,
    db_path: Path | None = None,
) -> FastAPI:
    """Create the platform app. Does not create or migrate any database file."""
    if settings is None:
        settings = load_platform_settings()

    if settings.env == "prod" and not settings.prod_explicit:
        raise PlatformConfigError(
            "prod requires an explicit request (--env prod or DATAIA_ENV=prod)"
        )

    app = FastAPI(
        title="Data IA Platform",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
    )
    app.state.settings = settings

    resolved: Path | None
    if db_path is not None:
        resolved = db_path.resolve()
        settings._refuse_prod_db_in_test(resolved)
    else:
        try:
            resolved = settings.resolved_sqlite_path()
        except PlatformConfigError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise PlatformConfigError(str(exc)) from exc

    db: ReadOnlyDatabase | None = None
    if resolved is not None:
        db = open_readonly(resolved)
        # Do not create the file if missing — status reports "base absente".
    app.state.db = db
    app.state.db_path = resolved

    app.include_router(v1_router)

    @app.api_route(
        "/auth/login",
        methods=["GET", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    )
    def auth_login_not_built() -> JSONResponse:
        # Lot 2 will add POST /auth/login. Other methods stay 405.
        return JSONResponse({"detail": "Method Not Allowed"}, status_code=405)

    @app.api_route(
        "/auth/logout",
        methods=["GET", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    )
    def auth_logout_not_built() -> JSONResponse:
        return JSONResponse({"detail": "Method Not Allowed"}, status_code=405)

    @app.post("/auth/login")
    def auth_login_stub() -> JSONResponse:
        # Placeholder so A1.2 can treat login as the sole allowed POST (Lot 2).
        return JSONResponse({"detail": "auth not implemented"}, status_code=501)

    @app.post("/auth/logout")
    def auth_logout_stub() -> JSONResponse:
        return JSONResponse({"detail": "auth not implemented"}, status_code=501)

    @app.middleware("http")
    async def block_mutations_except_auth(request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            path = request.url.path.rstrip("/") or "/"
            if path not in {"/auth/login", "/auth/logout"}:
                return JSONResponse({"detail": "Method Not Allowed"}, status_code=405)
        return await call_next(request)

    return app
