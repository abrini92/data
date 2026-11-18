"""CLI entrypoints: cycle, Brier proof, collect, verify-registry, replay, freeze, import-waves."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from data_ia import __version__
from data_ia.agents import AGENT_CATALOG
from data_ia.agents.pipeline import (
    SyntheticBlockedError,
    assert_synthetic_policy,
    load_yaml,
    run_offline_cycle,
)
from data_ia.config import REPO_ROOT, get_settings, settings_error_public_message
from data_ia.math.brier import evaluate_proof, report_to_dict


def _settings_or_exit() -> int | None:
    """Return exit code if settings refuse to load (synthetic+real)."""
    try:
        get_settings.cache_clear()
        assert_synthetic_policy()
        get_settings()
        return None
    except (SyntheticBlockedError, ValueError) as exc:
        print(
            json.dumps(
                {"ok": False, "error": settings_error_public_message(exc)},
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2


def cmd_cycle(_: argparse.Namespace) -> int:
    err = _settings_or_exit()
    if err is not None:
        return err
    result = run_offline_cycle(persist=True)
    payload = {
        "db_mode": result.get("db_mode"),
        "final_probability": result.get("final_probability"),
        "forecast_registry_id": result.get("forecast_registry_id"),
        "not_ready": result.get("not_ready"),
        "interval": [
            result["context"].get("interval_low"),
            result["context"].get("interval_high"),
        ],
        "source_weights": result["context"].get("source_weights"),
        "disclaimer": result.get("disclaimer"),
        "agents": result.get("agent_results"),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    if result.get("not_ready"):
        return 1
    return 0 if result.get("final_probability") is not None else 1


def cmd_brier(args: argparse.Namespace) -> int:
    """Score forecasts from the registry (engine output), not YAML probabilities."""
    err = _settings_or_exit()
    if err is not None:
        return err
    from data_ia.db.models import CHAIN_GENESIS_QUESTION_ID, ForecastRegistry, ResolvedQuestion
    from data_ia.db.session import get_session, try_init_db
    from data_ia.math.brier_match import match_registry_to_resolved
    from data_ia.math.labels import MixedLabelError
    from data_ia.migrate_registry import test_excluded_forecast_ids

    settings = get_settings()
    min_n = int(args.min_n if args.min_n is not None else settings.brier_min_n)

    try_init_db()
    session = get_session()
    try:
        resolved_path = Path(
            args.path or (REPO_ROOT / "seeds" / "synthetic_resolved.yaml")
        )
        outcomes_by_id: dict[str, dict] = {}
        if resolved_path.exists():
            data = load_yaml(resolved_path)
            for item in data.get("resolved_questions") or []:
                outcomes_by_id[item["id"]] = item

        for row in session.query(ResolvedQuestion).all():
            outcomes_by_id.setdefault(
                row.id,
                {
                    "id": row.id,
                    "outcome": row.outcome,
                    "label": row.label,
                    "data_label": row.data_label,
                    "question_class": row.question_class,
                    "resolved_on": row.resolved_on.isoformat() if row.resolved_on else None,
                    "wave_id": (row.meta or {}).get("wave_id") if row.meta else None,
                },
            )

        registry_rows = session.query(ForecastRegistry).order_by(ForecastRegistry.id).all()
        excluded = test_excluded_forecast_ids(session)
        scored_rows = []
        annotation_rejections: list[dict] = []
        for row in registry_rows:
            if row.question_id == CHAIN_GENESIS_QUESTION_ID:
                continue
            if row.id in excluded:
                annotation_rejections.append(
                    {
                        "forecast_id": row.id,
                        "question_id": row.question_id,
                        "reason": "annotated_TEST",
                    }
                )
                continue
            scored_rows.append(row)
        forecasts, meta = match_registry_to_resolved(scored_rows, outcomes_by_id)
        if annotation_rejections:
            meta.setdefault("rejected", [])
            meta["rejected"] = list(annotation_rejections) + list(meta.get("rejected") or [])
            meta["excluded_test_ids"] = sorted(excluded)

        if not forecasts:
            report = evaluate_proof([], min_n=min_n)
            payload = report_to_dict(report)
            payload["source"] = "forecast_registry"
            payload["matched"] = 0
            payload["registry_n"] = len(registry_rows)
            payload["rejected"] = meta.get("rejected")
            payload["note"] = (
                "No eligible registry forecasts matched resolved outcomes "
                "(late / post-resolution / post-deadline rows rejected). "
                "Engine probabilities are never read from YAML."
            )
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return 0

        try:
            report = evaluate_proof(forecasts, min_n=min_n)
        except MixedLabelError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
            return 1

        payload = report_to_dict(report)
        payload["source"] = "forecast_registry"
        payload["matched"] = len(forecasts)
        payload["n_questions"] = meta.get("n_questions")
        payload["registry_n"] = len(registry_rows)
        payload["rejected"] = meta.get("rejected")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    finally:
        session.close()


def cmd_verify_registry(_: argparse.Namespace) -> int:
    err = _settings_or_exit()
    if err is not None:
        return err
    from data_ia.db.session import get_session, try_init_db
    from data_ia.forecast_registry import verify_registry

    try_init_db()
    session = get_session()
    try:
        report = verify_registry(session)
        print(json.dumps(report, indent=2))
        return 0 if report["ok"] else 1
    finally:
        session.close()


def cmd_migrate_registry(args: argparse.Namespace) -> int:
    """ADD COLUMN + chain genesis for Pass-3 → Pass-4 registry schema."""
    err = _settings_or_exit()
    if err is not None:
        return err
    from data_ia.migrate_registry import MigrationError, migrate_registry, resolve_db_path

    try:
        db_path = resolve_db_path(args.db)
        report = migrate_registry(db_path=db_path, dry_run=bool(args.dry_run))
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("ok") else 1
    except MigrationError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1


def cmd_annotate_forecast(args: argparse.Namespace) -> int:
    """Append-only annotation on a registry row (no rewrite/delete)."""
    err = _settings_or_exit()
    if err is not None:
        return err
    from data_ia.db.session import get_session, try_init_db
    from data_ia.migrate_registry import MigrationError, annotate_forecast

    try_init_db()
    session = get_session()
    try:
        ann = annotate_forecast(
            session,
            forecast_id=int(args.id),
            label=str(args.label),
            reason=str(args.reason),
        )
        session.commit()
        print(
            json.dumps(
                {
                    "ok": True,
                    "annotation_id": ann.id,
                    "forecast_id": ann.forecast_id,
                    "label": ann.label,
                    "reason": ann.reason,
                    "created_at": ann.created_at.isoformat().replace("+00:00", "Z")
                    if ann.created_at.tzinfo
                    else ann.created_at.isoformat() + "Z",
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    except MigrationError as exc:
        session.rollback()
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    finally:
        session.close()


def cmd_replay(args: argparse.Namespace) -> int:
    err = _settings_or_exit()
    if err is not None:
        return err
    from data_ia.agents.pipeline import load_yaml
    from data_ia.db.session import get_session, try_init_db
    from data_ia.forecast_registry import replay_forecast

    settings = get_settings()
    try_init_db()
    session = get_session()
    try:
        seed = load_yaml(settings.seed_path)
        taxonomy = load_yaml(settings.taxonomy_path)
        priors = load_yaml(settings.source_priors_path)
        report = replay_forecast(
            session,
            int(args.forecast_id),
            seed=seed,
            taxonomy=taxonomy,
            source_priors=priors,
        )
        print(json.dumps(report, indent=2))
        return 0 if report.get("ok") else 1
    finally:
        session.close()


def cmd_import_waves(args: argparse.Namespace) -> int:
    """Import vague1 / vague1b with SHA-256 verification (Priority 0 A)."""
    err = _settings_or_exit()
    if err is not None:
        return err
    from data_ia.db.session import get_session, try_init_db
    from data_ia.wave_import import WaveHashError, import_waves, load_wave

    names = list(args.wave) if args.wave else ["vague1", "vague1b"]
    if args.verify_only:
        reports = []
        try:
            for name in names:
                bundle = load_wave(name, require_hash=True)
                reports.append(
                    {
                        "wave": bundle.wave_id,
                        "file": bundle.path.name,
                        "sha256": bundle.sha256,
                        "ok": True,
                        "n_questions": len(bundle.questions),
                        "bases_sha256": bundle.bases_sha256,
                        "errata": None
                        if bundle.errata_path is None
                        else bundle.errata_path.name,
                    }
                )
        except WaveHashError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
            return 1
        print(json.dumps({"ok": True, "waves": reports}, indent=2, ensure_ascii=False))
        return 0

    try_init_db()
    session = get_session()
    try:
        report = import_waves(session, names=names)
        session.commit()
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    except WaveHashError as exc:
        session.rollback()
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    finally:
        session.close()


def cmd_freeze(args: argparse.Namespace) -> int:
    """Freeze one proof question into the registry (B4)."""
    err = _settings_or_exit()
    if err is not None:
        return err
    from data_ia.db.session import get_session, reset_engine, try_init_db
    from data_ia.forecast_registry import RegistryIntegrityError
    from data_ia.freeze import FreezeError, freeze_question, vintage_sha_from_changes
    from data_ia.freeze_calendar import FreezeDeadlineError

    if args.database_url:
        import os

        os.environ["DATABASE_URL"] = args.database_url
        get_settings.cache_clear()
        reset_engine()

    if args.chain_head:
        import os

        os.environ["REGISTRY_CHAIN_HEAD_PATH"] = args.chain_head
        get_settings.cache_clear()

    changes = None
    if args.series_changes:
        changes = [float(x) for x in args.series_changes.split(",")]
    event_history = None
    if args.event_history:
        event_history = [int(x) for x in args.event_history.split(",")]

    vintage = args.vintage_sha
    if not vintage and changes is not None:
        vintage = vintage_sha_from_changes(changes, series_id=args.series)

    forecast_at = args.forecast_at
    data_cutoff = args.data_cutoff
    if data_cutoff is None:
        print(
            json.dumps({"ok": False, "error": "--data-cutoff is required"}, indent=2),
            file=sys.stderr,
        )
        return 2

    try_init_db()
    session = get_session()
    try:
        result = freeze_question(
            session,
            question_id=args.question,
            probability=float(args.probability),
            data_cutoff=data_cutoff,
            forecast_at=forecast_at,
            series_id=args.series,
            vintage_sha256=str(vintage),
            data_label=args.label,
            wave_id=args.wave,
            changes=changes,
            event_history=event_history,
            baseline_method=args.baseline_method,
            p_base_override=args.p_base,
            baseline_justification=args.baseline_justification,
            allow_dirty=bool(args.allow_dirty) or str(args.label).upper() == "TEST",
            export_head=True,
        )
        session.commit()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (FreezeError, FreezeDeadlineError, RegistryIntegrityError, ValueError) as exc:
        session.rollback()
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    finally:
        session.close()


def cmd_agents(_: argparse.Namespace) -> int:
    print(json.dumps([a.describe() for a in AGENT_CATALOG], indent=2))
    return 0


def cmd_dashboard(_: argparse.Namespace) -> int:
    settings = get_settings()
    app = REPO_ROOT / "src" / "data_ia" / "dashboard" / "app.py"
    print(
        f"Run: streamlit run {app} --server.port {settings.dashboard_port}\n"
        "Ensure an offline cycle has been run first so the SQLite/Postgres DB has a snapshot."
    )
    return 0


def cmd_collect(args: argparse.Namespace) -> int:
    """Fetch one or all registered sources (fixtures unless COLLECT_REAL_SOURCES)."""
    err = _settings_or_exit()
    if err is not None:
        return err
    from data_ia.connectors.registry import get_connector, list_sources, save_raw_cache

    settings = get_settings()
    real = bool(settings.collect_real_sources) or bool(args.real)

    if args.all:
        names = [
            s["name"]
            for s in list_sources(include_optional=bool(args.include_optional))
            if s.get("connector")
        ]
    elif args.source:
        names = [args.source]
    else:
        print("Specify --source <name> or --all", file=sys.stderr)
        return 2

    summaries: list[dict] = []
    exit_code = 0
    for name in names:
        try:
            connector = get_connector(name)
        except KeyError as exc:
            print(str(exc), file=sys.stderr)
            exit_code = 1
            continue

        payload = connector.collect(real=real)
        cache_path = None
        if payload.ok or payload.raw is not None or payload.raw_text:
            cache_path = str(save_raw_cache(name, payload))

        summary = {
            "source": name,
            "ok": payload.ok,
            "fetch_mode": payload.provenance.fetch_mode,
            "url": payload.provenance.url,
            "content_hash": payload.provenance.content_hash,
            "connector_version": payload.provenance.connector_version,
            "n_records": len(payload.records),
            "n_parsed": len(payload.records),
            "controller_accepted": sum(
                1 for c in payload.controller_results if c.get("accepted")
            ),
            "skipped_reason": payload.skipped_reason,
            "errors": payload.errors,
            "status": (payload.meta or {}).get("status"),
            "cache_path": cache_path,
            "real": real,
            "meta": {
                k: payload.meta.get(k)
                for k in (
                    "n_parsed",
                    "data_label",
                    "fallback",
                    "status",
                    "timeout_seconds",
                    "real_disabled",
                )
                if k in (payload.meta or {})
            },
        }
        summaries.append(summary)
        if args.source and not payload.ok:
            exit_code = 1
        elif args.all and not payload.ok and payload.provenance.fetch_mode != "skipped":
            exit_code = 1

    print(
        json.dumps(
            {"real": real, "results": summaries, "n_sources": len(summaries)},
            indent=2,
            ensure_ascii=False,
        )
    )
    return exit_code


def cmd_sources(_: argparse.Namespace) -> int:
    from data_ia.connectors.registry import list_sources

    print(json.dumps(list_sources(include_optional=True), indent=2, ensure_ascii=False))
    return 0


def cmd_ui(args: argparse.Namespace) -> int:
    """Launch the read-only platform UI (requires [ui] extra)."""
    try:
        import uvicorn
    except ImportError:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "install the [ui] extra: pip install -e \".[ui]\"",
                }
            ),
            file=sys.stderr,
        )
        return 2
    from data_ia.platform.settings import (
        PlatformConfigError,
        load_platform_settings,
    )

    env = args.env
    overrides: dict = {"env": env}
    if env == "prod":
        overrides["prod_explicit"] = True
    if args.host:
        overrides["ui_host"] = args.host
    if args.port is not None:
        overrides["ui_port"] = args.port
    try:
        settings = load_platform_settings(**overrides)
    except PlatformConfigError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    if settings.ui_host not in {"127.0.0.1", "localhost", "::1"}:
        print(
            json.dumps(
                {
                    "ok": True,
                    "warning": "non-loopback bind requested; local use only",
                    "host": settings.ui_host,
                }
            ),
            file=sys.stderr,
        )
    # Import create_app only after settings validate (secret key etc.).
    from data_ia.platform.app import create_app

    app = create_app(settings=settings)
    uvicorn.run(app, host=settings.ui_host, port=settings.ui_port, log_level="info")
    return 0


def cmd_ui_user(args: argparse.Namespace) -> int:
    """Manage local UI accounts (writes users file only, never the registry)."""
    import getpass

    from data_ia.platform.auth import (
        AuthError,
        ROLES,
        add_user,
        default_users_path,
        load_users,
        set_user_disabled,
    )

    path = Path(args.users_path) if args.users_path else default_users_path()
    action = args.ui_user_action
    try:
        if action == "add":
            # Password never accepted as a CLI argument (BRIEF-5 §4.5).
            password = getpass.getpass("Password: ")
            confirm = getpass.getpass("Confirm password: ")
            if password != confirm:
                print(json.dumps({"ok": False, "error": "passwords do not match"}), file=sys.stderr)
                return 2
            role = args.role
            if role not in ROLES:
                print(json.dumps({"ok": False, "error": "invalid role"}), file=sys.stderr)
                return 2
            add_user(path, username=args.username, password=password, role=role)
            print(json.dumps({"ok": True, "username": args.username, "role": role, "path": str(path)}))
            return 0
        if action == "list":
            users = load_users(path)
            safe = [
                {
                    "username": u.get("username"),
                    "role": u.get("role"),
                    "disabled": bool(u.get("disabled")),
                }
                for u in users
            ]
            print(json.dumps({"ok": True, "users": safe, "path": str(path)}, indent=2))
            return 0
        if action == "disable":
            set_user_disabled(path, args.username, True)
            print(json.dumps({"ok": True, "username": args.username, "disabled": True}))
            return 0
    except AuthError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps({"ok": False, "error": "unknown action"}), file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="data-ia", description=f"Data IA v{__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_cycle = sub.add_parser("cycle", help="Run full offline cycle (stub LLM)")
    p_cycle.set_defaults(func=cmd_cycle)

    p_brier = sub.add_parser(
        "brier",
        help="Brier proof from forecast_registry vs class-rate baseline",
    )
    p_brier.add_argument(
        "--path",
        help="YAML of resolved outcomes (probabilities ignored; engine registry used)",
    )
    p_brier.add_argument("--min-n", type=int, default=None, help="Minimum n for interpretable verdict")
    p_brier.set_defaults(func=cmd_brier)

    p_verify = sub.add_parser("verify-registry", help="Recompute forecast_registry hashes")
    p_verify.set_defaults(func=cmd_verify_registry)

    p_migrate = sub.add_parser(
        "migrate-registry",
        help="ADD COLUMN + chain genesis (Pass-3 → Pass-4); never rewrites rows",
    )
    p_migrate.add_argument(
        "--db",
        default=None,
        help="SQLite DB path (default: DATABASE_URL / data/dataia.db)",
    )
    p_migrate.add_argument(
        "--dry-run",
        action="store_true",
        help="Show columns/legacy/genesis plan; write nothing",
    )
    p_migrate.set_defaults(func=cmd_migrate_registry)

    p_annotate = sub.add_parser(
        "annotate-forecast",
        help="Append-only annotation (e.g. TEST) without rewriting the registry row",
    )
    p_annotate.add_argument("--id", type=int, required=True, help="forecast_registry id")
    p_annotate.add_argument("--label", required=True, help="Annotation label (e.g. TEST)")
    p_annotate.add_argument("--reason", required=True, help="Why this annotation exists")
    p_annotate.set_defaults(func=cmd_annotate_forecast)

    p_replay = sub.add_parser("replay", help="Replay engine from stored observation ids")
    p_replay.add_argument("--forecast-id", type=int, required=True)
    p_replay.set_defaults(func=cmd_replay)

    p_import = sub.add_parser(
        "import-waves",
        help="Import vague1/vague1b after SHA-256 verification",
    )
    p_import.add_argument(
        "--wave",
        action="append",
        help="Wave name (default: vague1 and vague1b). Repeatable.",
    )
    p_import.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify SHA-256 sidecars; do not write the DB",
    )
    p_import.set_defaults(func=cmd_import_waves)

    p_freeze = sub.add_parser(
        "freeze",
        help="Freeze one proof question (p_model + persist_v3 p_base) into the registry",
    )
    p_freeze.add_argument("--question", required=True, help="Question id, e.g. P1")
    p_freeze.add_argument("--probability", type=float, required=True)
    p_freeze.add_argument("--data-cutoff", required=True, help="ISO timestamp (≠ forecast_at)")
    p_freeze.add_argument("--forecast-at", default=None, help="ISO timestamp (default: now)")
    p_freeze.add_argument("--series", required=True, help="Frozen series id / label")
    p_freeze.add_argument("--vintage-sha", default=None, help="Millésime content SHA-256")
    p_freeze.add_argument(
        "--series-changes",
        default=None,
        help="Comma-separated signed changes for persist_v3 (no PMI levels printed)",
    )
    p_freeze.add_argument(
        "--event-history",
        default=None,
        help="Comma-separated 0/1 events for frequency baseline",
    )
    p_freeze.add_argument("--baseline-method", default=None, choices=["persist_v3", "frequency", "0.5"])
    p_freeze.add_argument("--p-base", type=float, default=None, help="Override stored p_base")
    p_freeze.add_argument("--baseline-justification", default=None)
    p_freeze.add_argument("--label", default="TEST", help="data_label (TEST for test registry)")
    p_freeze.add_argument("--wave", default=None)
    p_freeze.add_argument("--database-url", default=None, help="Override DATABASE_URL (test registry)")
    p_freeze.add_argument("--chain-head", default=None, help="Override chain-head jsonl path")
    p_freeze.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Allow dirty git tree (implied for --label TEST)",
    )
    p_freeze.set_defaults(func=cmd_freeze)

    p_agents = sub.add_parser("agents", help="Describe the six agents")
    p_agents.set_defaults(func=cmd_agents)

    p_dash = sub.add_parser("dashboard", help="Print Streamlit launch command")
    p_dash.set_defaults(func=cmd_dashboard)

    p_collect = sub.add_parser(
        "collect",
        help="Collect from a registered source (fixtures unless COLLECT_REAL_SOURCES)",
    )
    p_collect.add_argument("--source", help="Source name from config/sources.yaml")
    p_collect.add_argument("--all", action="store_true", help="Collect every connector source")
    p_collect.add_argument(
        "--include-optional",
        action="store_true",
        help="With --all, also include optional sources (e.g. sama)",
    )
    p_collect.add_argument(
        "--real",
        action="store_true",
        help="Force live HTTP even if COLLECT_REAL_SOURCES is false",
    )
    p_collect.set_defaults(func=cmd_collect)

    p_sources = sub.add_parser("sources", help="List sources.yaml registry")
    p_sources.set_defaults(func=cmd_sources)

    p_ui = sub.add_parser("ui", help="Run read-only platform UI (requires [ui] extra)")
    p_ui.add_argument("--host", default=None, help="Bind host (default 127.0.0.1)")
    p_ui.add_argument("--port", type=int, default=None, help="Bind port (default 8520)")
    p_ui.add_argument(
        "--env",
        choices=["test", "prod"],
        default="test",
        help="DATAIA_ENV (prod must be explicit)",
    )
    p_ui.set_defaults(func=cmd_ui)

    p_ui_user = sub.add_parser(
        "ui-user",
        help="Manage local UI accounts (users file only; password via getpass)",
    )
    ui_user_sub = p_ui_user.add_subparsers(dest="ui_user_action", required=True)
    p_add = ui_user_sub.add_parser("add", help="Add a user (password prompted, never as argv)")
    p_add.add_argument("--username", required=True)
    p_add.add_argument("--role", required=True, choices=sorted(["viewer", "analyst", "evaluator"]))
    p_add.add_argument("--users-path", default=None, help="Override users JSON path")
    p_add.set_defaults(func=cmd_ui_user)
    p_list = ui_user_sub.add_parser("list", help="List local UI users")
    p_list.add_argument("--users-path", default=None)
    p_list.set_defaults(func=cmd_ui_user)
    p_disable = ui_user_sub.add_parser("disable", help="Disable a local UI user")
    p_disable.add_argument("--username", required=True)
    p_disable.add_argument("--users-path", default=None)
    p_disable.set_defaults(func=cmd_ui_user)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
