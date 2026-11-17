"""Engine / session factory with PostgreSQL or SQLite fallback.

If ``DATABASE_URL`` points at Postgres but the server is unreachable, callers
may fall back explicitly via ``get_engine(fallback_sqlite=True)``.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from data_ia.config import REPO_ROOT, get_settings
from data_ia.db.models import Base

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def sqlite_url(path: Path | None = None) -> str:
    db_path = path or (REPO_ROOT / "data" / "dataia.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path.as_posix()}"


def is_sqlite_url(url: str) -> bool:
    return url.startswith("sqlite:")


def _ensure_sqlite_parent(url: str) -> None:
    """Create parent directory for sqlite:///... paths (relative or absolute)."""
    if not is_sqlite_url(url):
        return
    # sqlite:///./data/x.db  or  sqlite:////C:/abs/x.db
    raw = url.split("sqlite:///", 1)[-1]
    if raw.startswith("/") and len(raw) > 2 and raw[2] == ":":
        # /C:/... → C:/...
        path = Path(raw[1:])
    else:
        path = Path(raw)
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)


def get_engine(*, fallback_sqlite: bool = False, echo: bool = False) -> Engine:
    global _engine, _SessionLocal
    settings = get_settings()
    url = settings.database_url

    if fallback_sqlite and not is_sqlite_url(url):
        url = sqlite_url()

    if _engine is not None and str(_engine.url) == url:
        return _engine

    connect_args: dict = {}
    if is_sqlite_url(url):
        _ensure_sqlite_parent(url)
        connect_args["check_same_thread"] = False

    engine = create_engine(url, echo=echo, future=True, connect_args=connect_args)

    if is_sqlite_url(url):

        @event.listens_for(engine, "connect")
        def _fk_pragma(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    else:
        # Best-effort pgvector extension (ignored if missing / no perms).
        try:
            with engine.begin() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        except Exception:
            pass

    _engine = engine
    _SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return engine


def reset_engine() -> None:
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def init_db(*, fallback_sqlite: bool = False) -> Engine:
    """Create all tables. Use SQLite when Docker/Postgres is unavailable."""
    engine = get_engine(fallback_sqlite=fallback_sqlite)
    Base.metadata.create_all(bind=engine)
    return engine


def get_session(*, fallback_sqlite: bool = False) -> Session:
    get_engine(fallback_sqlite=fallback_sqlite)
    assert _SessionLocal is not None
    return _SessionLocal()


def try_init_db() -> tuple[Engine, str]:
    """Prefer configured DB; on connection failure, fall back to SQLite.

    Returns (engine, mode) where mode is 'postgres' | 'sqlite' | 'sqlite-fallback'.
    """
    settings = get_settings()
    url = settings.database_url
    if is_sqlite_url(url):
        engine = init_db(fallback_sqlite=False)
        return engine, "sqlite"

    try:
        engine = get_engine(fallback_sqlite=False)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        Base.metadata.create_all(bind=engine)
        return engine, "postgres"
    except Exception:
        reset_engine()
        engine = init_db(fallback_sqlite=True)
        return engine, "sqlite-fallback"
