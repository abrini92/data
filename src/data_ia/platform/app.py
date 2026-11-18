"""FastAPI application factory (Lots 1–2: API + local auth)."""

from __future__ import annotations

import secrets
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from data_ia.platform.api.v1 import router as v1_router
from data_ia.platform.auth import (
    CSRF_COOKIE,
    CSRF_FORM_FIELD,
    SESSION_COOKIE,
    AuthError,
    AuthUser,
    authenticate,
    check_login_rate,
    clear_login_rate,
    dump_session,
    load_session,
    new_csrf_token,
    sign_csrf,
    verify_csrf,
)
from data_ia.platform.logging import (
    CORRELATION_HEADER,
    get_platform_logger,
    register_redaction,
    setup_platform_logging,
)
from data_ia.platform.readonly import ReadOnlyDatabase, open_readonly
from data_ia.platform.settings import (
    PlatformConfigError,
    PlatformSettings,
    load_platform_settings,
)

_PUBLIC_PATHS = frozenset(
    {
        "/auth/login",
        "/auth/logout",
        "/api/v1/health",
    }
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

    register_redaction(settings.ui_secret_key)
    setup_platform_logging(log_dir=settings.log_directory())
    log = get_platform_logger()

    app = FastAPI(
        title="Data IA Platform",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,  # OpenAPI only for authenticated users (Lot 2+).
    )
    app.state.settings = settings
    app.state.logger = log

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
    app.state.db = db
    app.state.db_path = resolved

    app.include_router(v1_router)

    @app.middleware("http")
    async def correlation_and_auth(request: Request, call_next: Callable):  # type: ignore[type-arg]
        started = time.perf_counter()
        correlation_id = request.headers.get(CORRELATION_HEADER) or str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        request.state.user = None

        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            path = request.url.path.rstrip("/") or "/"
            if path not in {"/auth/login", "/auth/logout"}:
                return _json_405(correlation_id)

        path = request.url.path
        public = _is_public(path, request.method)

        user = _user_from_cookie(request, settings)
        request.state.user = user

        if not public and user is None:
            resp = _unauthorized(request)
            resp.headers[CORRELATION_HEADER] = correlation_id
            return resp

        # OpenAPI only when authenticated.
        if path == "/api/v1/openapi.json" and user is None:
            resp = _unauthorized(request)
            resp.headers[CORRELATION_HEADER] = correlation_id
            return resp

        try:
            response = await call_next(request)
        except Exception:
            log.exception(
                "unhandled error",
                extra={
                    "correlation_id": correlation_id,
                    "route": path,
                    "method": request.method,
                    "event": "error",
                },
            )
            response = JSONResponse(
                {
                    "detail": "internal error",
                    "correlation_id": correlation_id,
                },
                status_code=500,
            )

        response.headers[CORRELATION_HEADER] = correlation_id
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        log.info(
            "request",
            extra={
                "correlation_id": correlation_id,
                "route": path,
                "method": request.method,
                "status": getattr(response, "status_code", 0),
                "duration_ms": duration_ms,
                "user": user.username if user else None,
                "role": user.role if user else None,
                "event": "access",
            },
        )
        return response

    @app.get("/api/v1/openapi.json")
    def openapi_authenticated(request: Request) -> JSONResponse:
        return JSONResponse(app.openapi())

    @app.get("/auth/login", response_class=HTMLResponse)
    def login_form(request: Request) -> HTMLResponse:
        token = new_csrf_token()
        signed = sign_csrf(settings.ui_secret_key, token)
        html = (
            "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<title>Data IA — login</title></head><body>"
            "<main><h1>Data IA</h1>"
            "<form method=\"post\" action=\"/auth/login\">"
            f"<input type=\"hidden\" name=\"{CSRF_FORM_FIELD}\" value=\"{token}\">"
            "<label for=\"username\">Username</label>"
            "<input id=\"username\" name=\"username\" autocomplete=\"username\" required>"
            "<label for=\"password\">Password</label>"
            "<input id=\"password\" name=\"password\" type=\"password\" "
            "autocomplete=\"current-password\" required>"
            "<button type=\"submit\">Sign in</button>"
            "</form></main></body></html>"
        )
        resp = HTMLResponse(html)
        resp.set_cookie(
            CSRF_COOKIE,
            signed,
            httponly=True,
            samesite="strict",
            max_age=3600,
            path="/",
        )
        return resp

    @app.api_route(
        "/auth/login",
        methods=["PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    )
    def auth_login_method_block() -> JSONResponse:
        return JSONResponse({"detail": "Method Not Allowed"}, status_code=405)

    @app.post("/auth/login")
    async def auth_login(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
        csrf_token: str = Form(...),
    ) -> Response:
        correlation_id = getattr(request.state, "correlation_id", "")
        signed = request.cookies.get(CSRF_COOKIE, "")
        if not signed or not verify_csrf(settings.ui_secret_key, signed, csrf_token):
            return JSONResponse(
                {"detail": "CSRF validation failed", "correlation_id": correlation_id},
                status_code=403,
            )
        rate_key = f"{request.client.host if request.client else 'local'}:{username}"
        try:
            check_login_rate(rate_key)
            user = authenticate(settings.users_file(), username, password)
        except AuthError as exc:
            register_redaction(password)
            return JSONResponse(
                {"detail": str(exc), "correlation_id": correlation_id},
                status_code=401,
            )
        clear_login_rate(rate_key)
        register_redaction(password)
        token = dump_session(settings.ui_secret_key, user)
        accept = request.headers.get("accept", "")
        if "application/json" in accept and "text/html" not in accept:
            resp: Response = JSONResponse(
                {"ok": True, "username": user.username, "role": user.role}
            )
        else:
            resp = RedirectResponse(url="/", status_code=303)
        _set_session_cookie(resp, token, settings)
        # Rotate CSRF
        new_tok = new_csrf_token()
        resp.set_cookie(
            CSRF_COOKIE,
            sign_csrf(settings.ui_secret_key, new_tok),
            httponly=True,
            samesite="strict",
            max_age=3600,
            path="/",
        )
        return resp

    @app.api_route(
        "/auth/logout",
        methods=["GET", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    )
    def auth_logout_method_block() -> JSONResponse:
        return JSONResponse({"detail": "Method Not Allowed"}, status_code=405)

    @app.post("/auth/logout")
    async def auth_logout(
        request: Request,
        csrf_token: str = Form(default=""),
    ) -> Response:
        signed = request.cookies.get(CSRF_COOKIE, "")
        if not signed or not verify_csrf(settings.ui_secret_key, signed, csrf_token):
            # Also accept CSRF from JSON body for API clients.
            if request.headers.get("content-type", "").startswith("application/json"):
                try:
                    body = await request.json()
                except Exception:
                    body = {}
                csrf_token = str(body.get("csrf_token") or "")
            if not signed or not verify_csrf(settings.ui_secret_key, signed, csrf_token):
                return JSONResponse({"detail": "CSRF validation failed"}, status_code=403)
        resp = RedirectResponse(url="/auth/login", status_code=303)
        resp.delete_cookie(SESSION_COOKIE, path="/")
        resp.delete_cookie(CSRF_COOKIE, path="/")
        return resp

    @app.get("/")
    def root(request: Request) -> Response:
        user = getattr(request.state, "user", None)
        if user is None:
            return RedirectResponse(url="/auth/login", status_code=302)
        # Lot 3 replaces this with the dashboard; keep a minimal landing for Lot 2.
        return HTMLResponse(
            "<!DOCTYPE html><html lang=\"en\"><body><main>"
            f"<h1>Data IA</h1><p>Signed in as {user.username} ({user.role}).</p>"
            "</main></body></html>"
        )

    @app.exception_handler(Exception)
    async def generic_error(request: Request, exc: Exception) -> JSONResponse:
        correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
        log = get_platform_logger()
        log.exception(
            "error",
            extra={"correlation_id": correlation_id, "event": "error", "route": str(request.url.path)},
        )
        return JSONResponse(
            {"detail": "internal error", "correlation_id": correlation_id},
            status_code=500,
        )

    return app


def _is_public(path: str, method: str) -> bool:
    normalized = path.rstrip("/") or "/"
    if normalized in _PUBLIC_PATHS:
        return True
    if normalized.startswith("/auth/login") or normalized.startswith("/auth/logout"):
        return True
    return False


def _user_from_cookie(request: Request, settings: PlatformSettings) -> AuthUser | None:
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        return None
    return load_session(
        settings.ui_secret_key,
        raw,
        max_age_seconds=settings.session_max_age_seconds(),
    )


def _set_session_cookie(resp: Response, token: str, settings: PlatformSettings) -> None:
    resp.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="strict",
        max_age=settings.session_max_age_seconds(),
        path="/",
    )


def _unauthorized(request: Request) -> Response:
    accept = request.headers.get("accept", "")
    wants_html = "text/html" in accept and "application/json" not in accept
    path = request.url.path
    if wants_html or not path.startswith("/api/"):
        return RedirectResponse(url="/auth/login", status_code=302)
    return JSONResponse({"detail": "authentication required"}, status_code=401)


def _json_405(correlation_id: str) -> JSONResponse:
    resp = JSONResponse({"detail": "Method Not Allowed"}, status_code=405)
    resp.headers[CORRELATION_HEADER] = correlation_id
    return resp


def require_user(request: Request) -> AuthUser:
    user = getattr(request.state, "user", None)
    if user is None:
        raise AuthError("authentication required")
    return user
