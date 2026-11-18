"""BRIEF-4b: migrate-registry, legacy verify, TEST annotation exclusion."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from data_ia.config import REPO_ROOT
from data_ia.db.session import reset_engine
from data_ia.math.registry_hash import legacy_forecast_sha256


def _canon_dt(value: str) -> str:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _legacy_fields(**overrides):
    base = {
        "question_id": "q_legacy",
        "forecast_at": "2026-11-17T23:00:00Z",
        "data_cutoff": "2026-11-17T22:00:00Z",
        "git_commit": "a" * 40,
        "config_hash": "b" * 64,
        "extractor_version": "0.1.0",
        "observation_ids": [1, 2],
        "probability": 0.42,
        "interval_low": 0.1,
        "interval_high": 0.9,
        "data_label": "SYNTHETIC",
    }
    base.update(overrides)
    return base


@pytest.fixture()
def legacy_db(tmp_path, monkeypatch):
    """Pass-3 schema SQLite DB with two hashed legacy rows."""
    from data_ia.migrate_registry import open_legacy_sqlite_schema

    db = tmp_path / "legacy.db"
    head = tmp_path / "head.jsonl"
    backups = tmp_path / "backups"
    backups.mkdir()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db.as_posix()}")
    monkeypatch.setenv("REGISTRY_CHAIN_HEAD_PATH", str(head))
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    monkeypatch.setenv("COLLECT_REAL_SOURCES", "false")
    monkeypatch.setenv("USE_SYNTHETIC", "false")
    from data_ia.config import get_settings

    get_settings.cache_clear()
    reset_engine()

    con = open_legacy_sqlite_schema(db)
    con.execute(
        "INSERT INTO questions (id, text, status, illustrative) VALUES (?, ?, ?, ?)",
        ("q_legacy", "legacy question", "active", 0),
    )
    rows = []
    for i, (fat, cut, obs) in enumerate(
        [
            ("2026-11-17T23:00:00", "2026-11-17T22:00:00", [1, 2]),
            ("2026-11-17T23:10:00", "2026-11-17T22:10:00", [3, 4]),
        ],
        start=1,
    ):
        fields = _legacy_fields(
            forecast_at=_canon_dt(fat),
            data_cutoff=_canon_dt(cut),
            observation_ids=obs,
            probability=0.4 + 0.01 * i,
        )
        digest = legacy_forecast_sha256(fields)
        con.execute(
            """
            INSERT INTO forecast_registry (
              id, question_id, forecast_at, data_cutoff, git_commit, config_hash,
              extractor_version, observation_ids, probability, interval_low,
              interval_high, data_label, sha256, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                i,
                fields["question_id"],
                fat,
                cut,
                fields["git_commit"],
                fields["config_hash"],
                fields["extractor_version"],
                json.dumps(obs),
                fields["probability"],
                fields["interval_low"],
                fields["interval_high"],
                fields["data_label"],
                digest,
                fat,
            ),
        )
        rows.append({"id": i, "sha256": digest, "probability": fields["probability"]})
    con.commit()
    con.close()

    yield {"db": db, "head": head, "backups": backups, "rows": rows}
    get_settings.cache_clear()
    reset_engine()


def test_migrate_adds_columns_preserves_values_idempotent_dry_run(legacy_db, monkeypatch):
    import sqlite3

    from data_ia.migrate_registry import migrate_registry

    db = legacy_db["db"]
    head = legacy_db["head"]
    backups = legacy_db["backups"]
    original = {r["id"]: r for r in legacy_db["rows"]}

    dry = migrate_registry(
        db_path=db,
        dry_run=True,
        chain_head_path=head,
        backup_dir=backups,
    )
    assert dry["ok"] is True
    assert dry["written"] is False
    assert dry["legacy_n"] == 2
    assert "prev_sha256" in dry["columns_to_add"]
    assert list(backups.iterdir()) == []  # dry-run: no backup

    # Fingerprint file mtime/size unchanged by dry-run
    before_stat = db.stat()
    dry2 = migrate_registry(
        db_path=db, dry_run=True, chain_head_path=head, backup_dir=backups
    )
    assert dry2["legacy_n"] == 2
    assert db.stat().st_size == before_stat.st_size

    report = migrate_registry(
        db_path=db,
        dry_run=False,
        chain_head_path=head,
        backup_dir=backups,
    )
    assert report["ok"] is True
    assert report["written"] is True
    assert report["backup_path"]
    assert Path(report["backup_path"]).is_file()
    assert Path(report["backup_path"]).name != "dataia-pre-4b.db"
    assert report["genesis_id"] == 3
    assert head.is_file() and head.read_text(encoding="utf-8").strip()

    con = sqlite3.connect(db)
    cols = {r[1] for r in con.execute("PRAGMA table_info(forecast_registry)")}
    for name in (
        "prev_sha256",
        "p_base",
        "baseline_method",
        "series_id",
        "vintage_sha256",
        "observations_content_hash",
        "seed_hash",
        "wave_id",
    ):
        assert name in cols
    for rid, meta in original.items():
        row = con.execute(
            "SELECT probability, sha256, prev_sha256 FROM forecast_registry WHERE id = ?",
            (rid,),
        ).fetchone()
        assert row[0] == meta["probability"]
        assert row[1] == meta["sha256"]
        assert row[2] is None
    gen = con.execute(
        "SELECT baseline_method, prev_sha256 FROM forecast_registry WHERE id = 3"
    ).fetchone()
    assert gen[0] == "chain_genesis"
    assert gen[1] is None
    con.close()

    again = migrate_registry(
        db_path=db,
        dry_run=False,
        chain_head_path=head,
        backup_dir=backups,
        create_backup=True,
    )
    assert again["ok"] is True
    assert again["already_migrated"] is True
    # Idempotent: still exactly one genesis, legacy sha unchanged
    con = sqlite3.connect(db)
    n_gen = con.execute(
        "SELECT COUNT(*) FROM forecast_registry WHERE baseline_method = 'chain_genesis'"
    ).fetchone()[0]
    assert n_gen == 1
    for rid, meta in original.items():
        sha = con.execute(
            "SELECT sha256 FROM forecast_registry WHERE id = ?", (rid,)
        ).fetchone()[0]
        assert sha == meta["sha256"]
    con.close()

    from data_ia.config import get_settings
    from data_ia.db.session import get_session
    from data_ia.forecast_registry import verify_registry

    get_settings.cache_clear()
    reset_engine()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db.as_posix()}")
    monkeypatch.setenv("REGISTRY_CHAIN_HEAD_PATH", str(head))
    get_settings.cache_clear()
    reset_engine()
    session = get_session()
    try:
        report = verify_registry(session, chain_head_path=head)
        assert report["ok"] is True
        assert report["legacy_n"] == 2
        assert report["genesis_id"] == 3
    finally:
        session.close()


def test_migrate_real_production_copy_verify(tmp_path, monkeypatch):
    prod = REPO_ROOT / "data" / "dataia.db"
    if not prod.is_file():
        pytest.skip("production data/dataia.db absent")

    db = tmp_path / "prod_copy.db"
    head = tmp_path / "head.jsonl"
    backups = tmp_path / "backups"
    backups.mkdir()
    shutil.copy2(prod, db)

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db.as_posix()}")
    monkeypatch.setenv("REGISTRY_CHAIN_HEAD_PATH", str(head))
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    monkeypatch.setenv("COLLECT_REAL_SOURCES", "false")
    monkeypatch.setenv("USE_SYNTHETIC", "false")
    from data_ia.config import get_settings
    from data_ia.db.session import get_session
    from data_ia.forecast_registry import verify_registry
    from data_ia.migrate_registry import migrate_registry

    get_settings.cache_clear()
    reset_engine()

    report = migrate_registry(
        db_path=db, dry_run=False, chain_head_path=head, backup_dir=backups
    )
    assert report["ok"] is True
    assert report["legacy_n"] >= 1

    # Production may already be migrated: idempotent migrate does not re-export
    # the head into this temp path — seed it from the report / DB genesis.
    if report.get("genesis_sha256") and report.get("genesis_id"):
        from data_ia.db.models import CHAIN_GENESIS_QUESTION_ID
        from data_ia.forecast_registry import export_chain_head, read_chain_head

        if read_chain_head(head) != report["genesis_sha256"]:
            export_chain_head(
                sha256=str(report["genesis_sha256"]),
                forecast_id=int(report["genesis_id"]),
                question_id=CHAIN_GENESIS_QUESTION_ID,
                path=head,
            )

    get_settings.cache_clear()
    reset_engine()
    session = get_session()
    try:
        v = verify_registry(session, chain_head_path=head)
        assert v["ok"] is True, v
        assert v["legacy_n"] == report["legacy_n"]
    finally:
        session.close()


def test_brier_excludes_annotated_test(tmp_path, monkeypatch):
    from data_ia.cli import main
    from data_ia.db.models import Question, ResolvedQuestion
    from data_ia.db.session import get_session, try_init_db
    from data_ia.forecast_registry import append_forecast
    from data_ia.migrate_registry import annotate_forecast
    from data_ia.math.brier_match import match_registry_to_resolved
    import yaml

    db = tmp_path / "brier_ann.db"
    head = tmp_path / "head.jsonl"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db.as_posix()}")
    monkeypatch.setenv("REGISTRY_CHAIN_HEAD_PATH", str(head))
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    monkeypatch.setenv("COLLECT_REAL_SOURCES", "false")
    monkeypatch.setenv("USE_SYNTHETIC", "false")
    from data_ia.config import get_settings

    get_settings.cache_clear()
    reset_engine()
    try_init_db()
    session = get_session()
    try:
        session.add(Question(id="ann_q", text="q", status="resolved"))
        session.add(
            ResolvedQuestion(
                id="ann_q",
                text="q",
                outcome=1,
                resolved_on=None,
                label="SYNTHETIC",
                data_label="SYNTHETIC",
                question_class="ann",
            )
        )
        session.flush()
        row = append_forecast(
            session,
            question_id="ann_q",
            forecast_at=datetime(2026, 11, 18, 12, tzinfo=timezone.utc),
            data_cutoff=datetime(2026, 11, 18, 11, tzinfo=timezone.utc),
            observation_ids=[],
            probability=0.7,
            interval_low=None,
            interval_high=None,
            data_label="SYNTHETIC",
            git_commit="c" * 40,
            p_base=0.5,
            baseline_method="frequency",
            export_head=True,
            chain_head_path=head,
        )
        annotate_forecast(
            session,
            forecast_id=row.id,
            label="TEST",
            reason="verification cycle exclusion",
        )
        session.commit()
        fid = row.id
    finally:
        session.close()

    from data_ia.db.models import ForecastRegistry
    from data_ia.migrate_registry import test_excluded_forecast_ids

    session = get_session()
    try:
        excluded = test_excluded_forecast_ids(session)
        assert fid in excluded
        rows = session.query(ForecastRegistry).all()
        scored = [r for r in rows if r.id not in excluded]
        forecasts, meta = match_registry_to_resolved(
            scored,
            {
                "ann_q": {
                    "id": "ann_q",
                    "outcome": 1,
                    "data_label": "SYNTHETIC",
                    "question_class": "ann",
                    "resolved_on": None,
                }
            },
        )
        assert forecasts == []
    finally:
        session.close()

    outcomes = tmp_path / "outcomes.yaml"
    outcomes.write_text(
        yaml.safe_dump(
            {
                "resolved_questions": [
                    {
                        "id": "ann_q",
                        "outcome": 1,
                        "data_label": "SYNTHETIC",
                        "question_class": "ann",
                        "text": "q",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main(["brier", "--path", str(outcomes), "--min-n", "1"])
    assert code == 0
    payload = json.loads(buf.getvalue())
    assert payload["matched"] == 0
    assert any(r.get("reason") == "annotated_TEST" for r in (payload.get("rejected") or []))


def test_verify_detects_rewrite_and_deletion_after_migration(legacy_db, monkeypatch):
    from data_ia.config import get_settings
    from data_ia.db.session import get_session
    from data_ia.forecast_registry import verify_registry
    from data_ia.migrate_registry import migrate_registry

    db = legacy_db["db"]
    head = legacy_db["head"]
    backups = legacy_db["backups"]
    migrate_registry(
        db_path=db, dry_run=False, chain_head_path=head, backup_dir=backups
    )

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db.as_posix()}")
    monkeypatch.setenv("REGISTRY_CHAIN_HEAD_PATH", str(head))
    get_settings.cache_clear()
    reset_engine()
    session = get_session()
    try:
        assert verify_registry(session, chain_head_path=head)["ok"] is True

        session.execute(text("DROP TRIGGER IF EXISTS forecast_registry_no_update"))
        session.execute(
            text("UPDATE forecast_registry SET probability = 0.99 WHERE id = 1")
        )
        session.commit()
        report = verify_registry(session, chain_head_path=head)
        assert report["ok"] is False
        assert report["mismatches"]

        # Restore probability for deletion test on a fresh copy path
    finally:
        session.close()

    # Separate deletion on a fresh migrated copy
    db2 = legacy_db["db"].parent / "legacy_del.db"
    shutil.copy2(legacy_db["db"], db2)
    # Re-build clean migrated DB from original backup made during first migrate
    # Use the pre-migration backup instead
    backup = next(Path(backups).glob("dataia-*.db"))
    shutil.copy2(backup, db2)
    head2 = legacy_db["db"].parent / "head_del.jsonl"
    migrate_registry(
        db_path=db2,
        dry_run=False,
        chain_head_path=head2,
        backup_dir=backups,
        create_backup=False,
    )
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db2.as_posix()}")
    monkeypatch.setenv("REGISTRY_CHAIN_HEAD_PATH", str(head2))
    get_settings.cache_clear()
    reset_engine()
    session = get_session()
    try:
        session.execute(text("DROP TRIGGER IF EXISTS forecast_registry_no_delete"))
        session.execute(text("DELETE FROM forecast_registry WHERE id = 1"))
        session.commit()
        report = verify_registry(session, chain_head_path=head2)
        assert report["ok"] is False
        assert report["id_gaps"] or report["chain_breaks"] or report["head_mismatch"]
    finally:
        session.close()
