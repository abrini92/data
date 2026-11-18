"""Add-only migration of forecast_registry from Pass-3 schema to Pass-4 chain."""

from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from data_ia.config import REPO_ROOT, get_settings
from data_ia.db.models import (
    CHAIN_GENESIS_METHOD,
    CHAIN_GENESIS_QUESTION_ID,
    REGISTRY_PASS4_COLUMNS,
    ForecastAnnotation,
    ForecastRegistry,
    Question,
    install_forecast_registry_triggers,
)
from data_ia.forecast_registry import (
    config_hash,
    export_chain_head,
    git_commit_sha,
)
from data_ia.math.registry_hash import content_sha256, forecast_sha256


class MigrationError(ValueError):
    """Raised when migrate-registry cannot proceed safely."""


def _sqlite_path_from_url(url: str) -> Path | None:
    if not url.startswith("sqlite:"):
        return None
    raw = url.split("sqlite:///", 1)[-1]
    if raw.startswith("/") and len(raw) > 2 and raw[2] == ":":
        path = Path(unquote(raw[1:]))
    else:
        path = Path(unquote(raw))
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return path


def resolve_db_path(db: str | Path | None = None) -> Path:
    """Resolve the SQLite file path for migrate-registry."""
    if db is not None:
        return Path(db).resolve()
    settings = get_settings()
    path = _sqlite_path_from_url(settings.database_url)
    if path is None:
        raise MigrationError(
            "migrate-registry requires a SQLite DATABASE_URL or --db PATH"
        )
    return path


def backup_database(db_path: Path, *, backup_dir: Path | None = None) -> Path:
    """Copy the DB file to data/backups/dataia-YYYYMMDD-HHMMSS.db."""
    if not db_path.is_file():
        raise MigrationError(f"database file not found: {db_path}")
    dest_dir = backup_dir or (REPO_ROOT / "data" / "backups")
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = dest_dir / f"dataia-{stamp}.db"
    # Never overwrite the manual pre-4b backup.
    if dest.name == "dataia-pre-4b.db":
        dest = dest_dir / f"dataia-{stamp}-auto.db"
    shutil.copy2(db_path, dest)
    return dest


def existing_columns(engine: Engine, table: str = "forecast_registry") -> set[str]:
    insp = inspect(engine)
    if table not in insp.get_table_names():
        return set()
    return {col["name"] for col in insp.get_columns(table)}


def missing_pass4_columns(engine: Engine) -> list[tuple[str, str]]:
    present = existing_columns(engine)
    return [(name, sql_type) for name, sql_type in REGISTRY_PASS4_COLUMNS if name not in present]


def _table_has_column(engine: Engine, table: str, column: str) -> bool:
    return column in existing_columns(engine, table)


def find_genesis_id(engine: Engine, session: Session) -> int | None:
    """Return genesis row id without requiring Pass-4 columns via ORM."""
    if not _table_has_column(engine, "forecast_registry", "baseline_method"):
        return None
    row = session.execute(
        text(
            "SELECT id FROM forecast_registry "
            "WHERE baseline_method = :m ORDER BY id LIMIT 1"
        ),
        {"m": CHAIN_GENESIS_METHOD},
    ).first()
    return None if row is None else int(row[0])


def find_genesis_row(session: Session) -> ForecastRegistry | None:
    bind = session.get_bind()
    if bind is None or not _table_has_column(bind, "forecast_registry", "baseline_method"):  # type: ignore[arg-type]
        return None
    return (
        session.query(ForecastRegistry)
        .filter(ForecastRegistry.baseline_method == CHAIN_GENESIS_METHOD)
        .order_by(ForecastRegistry.id)
        .first()
    )


def _legacy_id_sha_pairs(engine: Engine, session: Session) -> list[dict[str, Any]]:
    """Read legacy (id, sha256) with raw SQL so pre-ALTER DBs work."""
    cols = existing_columns(engine)
    if "forecast_registry" not in inspect(engine).get_table_names():
        return []
    genesis_id = find_genesis_id(engine, session)
    if "baseline_method" not in cols:
        rows = session.execute(
            text("SELECT id, sha256 FROM forecast_registry ORDER BY id")
        ).fetchall()
        return [{"id": int(r[0]), "sha256": str(r[1])} for r in rows]
    if genesis_id is not None:
        rows = session.execute(
            text(
                "SELECT id, sha256 FROM forecast_registry "
                "WHERE id < :gid ORDER BY id"
            ),
            {"gid": genesis_id},
        ).fetchall()
        return [{"id": int(r[0]), "sha256": str(r[1])} for r in rows]
    # Schema has Pass-4 columns but no genesis: legacy only if chain fields unset.
    rows = session.execute(
        text(
            """
            SELECT id, sha256 FROM forecast_registry
            WHERE prev_sha256 IS NULL
              AND p_base IS NULL
              AND baseline_method IS NULL
              AND series_id IS NULL
              AND vintage_sha256 IS NULL
              AND observations_content_hash IS NULL
              AND seed_hash IS NULL
              AND wave_id IS NULL
            ORDER BY id
            """
        )
    ).fetchall()
    # If any row has chain fields set, this is a fresh chained DB — no legacy.
    any_chained = session.execute(
        text(
            """
            SELECT 1 FROM forecast_registry
            WHERE prev_sha256 IS NOT NULL
               OR p_base IS NOT NULL
               OR baseline_method IS NOT NULL
               OR series_id IS NOT NULL
               OR vintage_sha256 IS NOT NULL
               OR observations_content_hash IS NOT NULL
               OR seed_hash IS NOT NULL
               OR wave_id IS NOT NULL
            LIMIT 1
            """
        )
    ).first()
    if any_chained is not None:
        return []
    return [{"id": int(r[0]), "sha256": str(r[1])} for r in rows]


def legacy_rows(session: Session) -> list[ForecastRegistry]:
    bind = session.get_bind()
    if bind is None:
        return []
    pairs = _legacy_id_sha_pairs(bind, session)  # type: ignore[arg-type]
    if not pairs:
        return []
    ids = [p["id"] for p in pairs]
    rows = (
        session.query(ForecastRegistry)
        .filter(ForecastRegistry.id.in_(ids))
        .order_by(ForecastRegistry.id)
        .all()
    )
    return rows


def legacy_set_hash(rows: list[ForecastRegistry] | list[dict[str, Any]]) -> str:
    payload = []
    for r in rows:
        if isinstance(r, dict):
            payload.append({"id": r["id"], "sha256": r["sha256"]})
        else:
            payload.append({"id": r.id, "sha256": r.sha256})
    return content_sha256(payload)


def _ensure_annotations_table(engine: Engine) -> None:
    ForecastAnnotation.__table__.create(bind=engine, checkfirst=True)


def _ensure_genesis_question(session: Session) -> None:
    existing = session.get(Question, CHAIN_GENESIS_QUESTION_ID)
    if existing is not None:
        return
    session.add(
        Question(
            id=CHAIN_GENESIS_QUESTION_ID,
            text="Registry chain genesis (migration marker; not a forecast)",
            status="system",
            illustrative=True,
        )
    )
    session.flush()


def plan_migration(engine: Engine, session: Session) -> dict[str, Any]:
    """Describe what migrate-registry would do (no writes)."""
    missing = missing_pass4_columns(engine)
    legacy_pairs = _legacy_id_sha_pairs(engine, session)
    genesis_id = find_genesis_id(engine, session)
    genesis_sha = None
    if genesis_id is not None:
        genesis_sha = session.execute(
            text("SELECT sha256 FROM forecast_registry WHERE id = :id"),
            {"id": genesis_id},
        ).scalar()
    already = genesis_id is not None and not missing
    planned_legacy_hash = legacy_set_hash(legacy_pairs) if legacy_pairs else None
    return {
        "ok": True,
        "dry_run": True,
        "already_migrated": already,
        "columns_to_add": [name for name, _ in missing],
        "legacy_n": len(legacy_pairs),
        "legacy_ids": [p["id"] for p in legacy_pairs],
        "genesis_exists": genesis_id is not None,
        "genesis_id": genesis_id,
        "genesis_sha256": genesis_sha,
        "planned_legacy_set_hash": planned_legacy_hash,
        "planned_genesis": None
        if already or not legacy_pairs
        else {
            "question_id": CHAIN_GENESIS_QUESTION_ID,
            "baseline_method": CHAIN_GENESIS_METHOD,
            "prev_sha256": None,
            "legacy_set_hash": planned_legacy_hash,
            "note": "chain head export starts at this genesis row",
        },
        "annotations_table": "forecast_annotations" in inspect(engine).get_table_names(),
    }


def apply_column_adds(engine: Engine, missing: list[tuple[str, str]]) -> list[str]:
    added: list[str] = []
    if not missing:
        return added
    with engine.begin() as conn:
        for name, sql_type in missing:
            conn.execute(
                text(f"ALTER TABLE forecast_registry ADD COLUMN {name} {sql_type}")
            )
            added.append(name)
    return added


def insert_genesis(
    session: Session,
    legacy: list[ForecastRegistry],
    *,
    chain_head_path: Path | None = None,
    export_head: bool = True,
) -> ForecastRegistry:
    """Append the chain genesis row after legacy rows (never rewrite them)."""
    if not legacy:
        raise MigrationError("refusing genesis with zero legacy rows")
    if find_genesis_row(session) is not None:
        raise MigrationError("chain genesis already present")

    _ensure_genesis_question(session)
    settings = get_settings()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    set_hash = legacy_set_hash(legacy)
    commit = git_commit_sha(allow_unknown=False)
    fields = {
        "question_id": CHAIN_GENESIS_QUESTION_ID,
        "forecast_at": now.isoformat().replace("+00:00", "Z"),
        "data_cutoff": now.isoformat().replace("+00:00", "Z"),
        "git_commit": commit,
        "config_hash": config_hash(),
        "extractor_version": settings.extractor_version,
        "observation_ids": [],
        "probability": 0.0,
        "interval_low": None,
        "interval_high": None,
        "data_label": "SYNTHETIC",
        "prev_sha256": None,
        "p_base": None,
        "baseline_method": CHAIN_GENESIS_METHOD,
        "series_id": "registry_migration_4b",
        "vintage_sha256": set_hash,
        "observations_content_hash": set_hash,
        "seed_hash": set_hash,
        "wave_id": None,
    }
    digest = forecast_sha256(fields)
    row = ForecastRegistry(
        question_id=fields["question_id"],
        forecast_at=now,
        data_cutoff=now,
        git_commit=fields["git_commit"],
        config_hash=fields["config_hash"],
        extractor_version=fields["extractor_version"],
        observation_ids=fields["observation_ids"],
        probability=fields["probability"],
        interval_low=None,
        interval_high=None,
        data_label=fields["data_label"],
        prev_sha256=None,
        p_base=None,
        baseline_method=CHAIN_GENESIS_METHOD,
        series_id=fields["series_id"],
        vintage_sha256=set_hash,
        observations_content_hash=set_hash,
        seed_hash=set_hash,
        wave_id=None,
        sha256=digest,
    )
    session.add(row)
    session.flush()
    if export_head:
        export_chain_head(
            sha256=digest,
            forecast_id=row.id,
            question_id=CHAIN_GENESIS_QUESTION_ID,
            path=chain_head_path,
        )
    return row


def migrate_registry(
    *,
    db_path: Path,
    dry_run: bool = False,
    chain_head_path: Path | None = None,
    backup_dir: Path | None = None,
    create_backup: bool = True,
) -> dict[str, Any]:
    """Migrate a SQLite registry DB: ADD COLUMN + genesis. Idempotent."""
    db_path = Path(db_path).resolve()
    if not db_path.is_file():
        raise MigrationError(f"database file not found: {db_path}")

    # Deferred imports to allow --db to override engine binding in CLI.
    from data_ia.db.session import get_engine, get_session, reset_engine
    from data_ia.config import get_settings as _gs

    url = f"sqlite:///{db_path.as_posix()}"
    import os

    os.environ["DATABASE_URL"] = url
    _gs.cache_clear()
    reset_engine()
    engine = get_engine()
    # Ensure ORM metadata tables that may be missing (annotations) exist on write.
    session = get_session()
    try:
        plan = plan_migration(engine, session)
        plan["db_path"] = str(db_path)
        plan["dry_run"] = dry_run

        if dry_run:
            plan["backup_path"] = None
            plan["written"] = False
            return plan

        backup_path = None
        if create_backup:
            backup_path = backup_database(db_path, backup_dir=backup_dir)
        plan["backup_path"] = None if backup_path is None else str(backup_path)

        if plan["already_migrated"]:
            _ensure_annotations_table(engine)
            install_forecast_registry_triggers(engine)
            session.commit()
            plan["written"] = False
            plan["ok"] = True
            plan["note"] = "already migrated; no changes"
            return plan

        # Capture legacy pairs before ALTER (ORM cannot SELECT missing cols).
        legacy_pairs_before = _legacy_id_sha_pairs(engine, session)
        added = apply_column_adds(engine, missing_pass4_columns(engine))
        # Refresh session after ALTER (new columns).
        session.close()
        reset_engine()
        engine = get_engine()
        session = get_session()

        _ensure_annotations_table(engine)
        install_forecast_registry_triggers(engine)

        genesis = find_genesis_row(session)
        # After ADD COLUMN, legacy pairs are still those without genesis.
        if genesis is None:
            legacy = (
                session.query(ForecastRegistry)
                .filter(ForecastRegistry.id.in_([p["id"] for p in legacy_pairs_before]))
                .order_by(ForecastRegistry.id)
                .all()
                if legacy_pairs_before
                else []
            )
        else:
            legacy = legacy_rows(session)
        genesis_row = None
        if genesis is None and legacy:
            genesis_row = insert_genesis(
                session,
                legacy,
                chain_head_path=chain_head_path,
                export_head=True,
            )
            session.commit()
        else:
            session.commit()

        plan["columns_added"] = added
        plan["written"] = True
        plan["legacy_n"] = len(legacy_pairs_before)
        plan["legacy_ids"] = [p["id"] for p in legacy_pairs_before]
        if genesis_row is not None:
            plan["genesis_id"] = genesis_row.id
            plan["genesis_sha256"] = genesis_row.sha256
            plan["genesis_exists"] = True
            plan["planned_legacy_set_hash"] = legacy_set_hash(legacy_pairs_before)
        plan["already_migrated"] = (
            find_genesis_id(engine, session) is not None
            and not missing_pass4_columns(engine)
        )
        plan["ok"] = True
        return plan
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def annotate_forecast(
    session: Session,
    *,
    forecast_id: int,
    label: str,
    reason: str,
) -> ForecastAnnotation:
    """Append-only annotation (does not rewrite the registry row)."""
    row = session.get(ForecastRegistry, forecast_id)
    if row is None:
        raise MigrationError(f"forecast_id {forecast_id} not found")
    label_norm = str(label).strip().upper()
    if not label_norm:
        raise MigrationError("label must be non-empty")
    if not str(reason).strip():
        raise MigrationError("reason must be non-empty")
    # Ensure table exists when called on a freshly migrated engine.
    bind = session.get_bind()
    if bind is not None:
        _ensure_annotations_table(bind)  # type: ignore[arg-type]
        install_forecast_registry_triggers(bind)  # type: ignore[arg-type]
    ann = ForecastAnnotation(
        forecast_id=forecast_id,
        label=label_norm,
        reason=str(reason).strip(),
        created_at=datetime.now(timezone.utc).replace(microsecond=0),
    )
    session.add(ann)
    session.flush()
    return ann


def list_annotations(session: Session) -> list[dict[str, Any]]:
    bind = session.get_bind()
    if bind is not None:
        names = inspect(bind).get_table_names()
        if "forecast_annotations" not in names:
            return []
    rows = (
        session.query(ForecastAnnotation)
        .order_by(ForecastAnnotation.id)
        .all()
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        created = r.created_at
        if created is not None and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        out.append(
            {
                "id": r.id,
                "forecast_id": r.forecast_id,
                "label": r.label,
                "reason": r.reason,
                "created_at": None
                if created is None
                else created.astimezone(timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z"),
            }
        )
    return out


def test_excluded_forecast_ids(session: Session) -> set[int]:
    """Forecast ids with an append-only TEST annotation (excluded from brier)."""
    bind = session.get_bind()
    if bind is not None and "forecast_annotations" not in inspect(bind).get_table_names():
        return set()
    rows = (
        session.query(ForecastAnnotation.forecast_id)
        .filter(ForecastAnnotation.label == "TEST")
        .all()
    )
    return {int(r[0]) for r in rows}


def open_legacy_sqlite_schema(path: Path) -> sqlite3.Connection:
    """Helper for tests: create an empty Pass-3 forecast_registry schema."""
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.executescript(
        """
        CREATE TABLE questions (
            id VARCHAR(64) PRIMARY KEY,
            text TEXT NOT NULL,
            horizon TEXT,
            region VARCHAR(64),
            zone VARCHAR(64),
            target_variable TEXT,
            threshold FLOAT,
            unit VARCHAR(64),
            resolution_source TEXT,
            resolution_rule TEXT,
            status VARCHAR(32),
            illustrative BOOLEAN,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE forecast_registry (
            id INTEGER NOT NULL PRIMARY KEY,
            question_id VARCHAR(64) NOT NULL,
            forecast_at DATETIME NOT NULL,
            data_cutoff DATETIME NOT NULL,
            git_commit VARCHAR(64) NOT NULL,
            config_hash VARCHAR(64) NOT NULL,
            extractor_version VARCHAR(32) NOT NULL,
            observation_ids JSON NOT NULL,
            probability FLOAT NOT NULL,
            interval_low FLOAT,
            interval_high FLOAT,
            data_label VARCHAR(32) NOT NULL,
            sha256 VARCHAR(64) NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
            FOREIGN KEY(question_id) REFERENCES questions (id)
        );
        CREATE TRIGGER forecast_registry_no_update
        BEFORE UPDATE ON forecast_registry
        BEGIN
          SELECT RAISE(ABORT, 'forecast_registry is append-only: UPDATE rejected');
        END;
        CREATE TRIGGER forecast_registry_no_delete
        BEFORE DELETE ON forecast_registry
        BEGIN
          SELECT RAISE(ABORT, 'forecast_registry is append-only: DELETE rejected');
        END;
        """
    )
    con.commit()
    return con
