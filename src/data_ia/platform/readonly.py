"""Read-only SQLite adapter for the platform UI (never init_db / migrate)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import quote

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from data_ia.db.models import REGISTRY_PASS4_COLUMNS

# Column that marks a Pass-4b migrated schema (BRIEF-5 §4.3).
MIGRATION_MARKER_COLUMN = "prev_sha256"


class ReadOnlyError(RuntimeError):
    """Raised when a write is attempted or the RO connection rejects mutation."""


@dataclass(frozen=True)
class DatabaseStatus:
    """Health-facing DB status (no writes)."""

    present: bool
    migrated: bool
    path: str | None
    message: str
    read_only: bool = True


def _sqlite_ro_url(path: Path) -> str:
    """Build a SQLAlchemy SQLite URL that enables URI query args (mode=ro)."""
    # sqlachemy requires `uri=true` in the URL for mode=ro to be honoured.
    # Absolute POSIX path works on Windows as C:/Users/...
    posix = path.resolve().as_posix()
    quoted = quote(posix, safe="/:")
    return f"sqlite:///file:{quoted}?mode=ro&uri=true"


class ReadOnlyDatabase:
    """Open an existing SQLite file with mode=ro and PRAGMA query_only=ON."""

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self._engine: Engine | None = None
        self._SessionLocal: sessionmaker[Session] | None = None

    def exists(self) -> bool:
        return self.path.is_file()

    def status(self) -> DatabaseStatus:
        if not self.exists():
            return DatabaseStatus(
                present=False,
                migrated=False,
                path=str(self.path),
                message="base absente",
                read_only=True,
            )
        engine = self.engine()
        cols = _table_columns(engine, "forecast_registry")
        if MIGRATION_MARKER_COLUMN not in cols:
            return DatabaseStatus(
                present=True,
                migrated=False,
                path=str(self.path),
                message=(
                    "schéma non migré : lancer `data-ia migrate-registry` "
                    "(Dev, avec accord)"
                ),
                read_only=True,
            )
        # Soft check: all Pass-4 columns expected (informational).
        missing = [name for name, _ in REGISTRY_PASS4_COLUMNS if name not in cols]
        if missing:
            return DatabaseStatus(
                present=True,
                migrated=False,
                path=str(self.path),
                message=(
                    "schéma non migré : lancer `data-ia migrate-registry` "
                    "(Dev, avec accord)"
                ),
                read_only=True,
            )
        return DatabaseStatus(
            present=True,
            migrated=True,
            path=str(self.path),
            message="ok",
            read_only=True,
        )

    def engine(self) -> Engine:
        if self._engine is not None:
            return self._engine
        if not self.exists():
            raise FileNotFoundError(f"database missing: {self.path}")
        url = _sqlite_ro_url(self.path)
        engine = create_engine(
            url,
            future=True,
            connect_args={"uri": True, "check_same_thread": False},
        )

        @event.listens_for(engine, "connect")
        def _query_only(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA query_only = ON")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        self._engine = engine
        self._SessionLocal = sessionmaker(
            bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
        )
        return engine

    def session(self) -> Session:
        self.engine()
        assert self._SessionLocal is not None
        return self._SessionLocal()

    def execute_read(self, sql: str, params: dict[str, Any] | None = None) -> Any:
        """Run a read statement; reject obvious write verbs before hitting the DB."""
        _reject_write_sql(sql)
        with self.engine().connect() as conn:
            return conn.execute(text(sql), params or {})

    def attempt_write(self, sql: str, params: dict[str, Any] | None = None) -> None:
        """Attempt a mutation; always raises ReadOnlyError on success path of reject."""
        _reject_write_sql(sql)
        try:
            with self.engine().connect() as conn:
                conn.execute(text(sql), params or {})
                conn.commit()
        except (OperationalError, DBAPIError) as exc:
            raise ReadOnlyError(f"write rejected by read-only database: {exc}") from exc
        raise ReadOnlyError("write unexpectedly succeeded on read-only adapter")

    def close(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
        self._engine = None
        self._SessionLocal = None


def _reject_write_sql(sql: str) -> None:
    head = sql.lstrip().split(None, 1)[0].upper() if sql.strip() else ""
    if head in {
        "INSERT",
        "UPDATE",
        "DELETE",
        "CREATE",
        "DROP",
        "ALTER",
        "REPLACE",
        "ATTACH",
        "DETACH",
        "VACUUM",
        "REINDEX",
    }:
        raise ReadOnlyError(f"write statement refused by adapter: {head}")


def _table_columns(engine: Engine, table: str) -> set[str]:
    try:
        insp = inspect(engine)
        if table not in insp.get_table_names():
            return set()
        return {c["name"] for c in insp.get_columns(table)}
    except Exception:  # noqa: BLE001
        return set()


def open_readonly(path: Path) -> ReadOnlyDatabase:
    return ReadOnlyDatabase(path)
