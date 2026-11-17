"""CLI entrypoints: cycle, Brier proof, collect, verify-registry, replay."""

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
from data_ia.config import REPO_ROOT, get_settings
from data_ia.math.brier import (
    ResolvedForecast,
    class_base_rate,
    evaluate_proof,
    report_to_dict,
    status_quo_baseline,
)


def _settings_or_exit() -> int | None:
    """Return exit code if settings refuse to load (synthetic+real)."""
    try:
        get_settings.cache_clear()
        assert_synthetic_policy()
        get_settings()
        return None
    except (SyntheticBlockedError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
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
    from data_ia.db.models import ForecastRegistry, ResolvedQuestion
    from data_ia.db.session import get_session, try_init_db
    from data_ia.math.labels import MixedLabelError

    settings = get_settings()
    min_n = int(args.min_n if args.min_n is not None else settings.brier_min_n)

    try_init_db()
    session = get_session()
    try:
        # Pair registry rows with resolved outcomes by question_id when available.
        # For synthetic proof demos: load outcomes from YAML but probabilities from
        # registry rows that share question_id; if registry empty and --allow-seed-outcomes,
        # still refuse hand-written probabilities — baseline/outcomes only from seed.
        resolved_path = Path(
            args.path or (REPO_ROOT / "seeds" / "synthetic_resolved.yaml")
        )
        outcomes_by_id: dict[str, dict] = {}
        if resolved_path.exists():
            data = load_yaml(resolved_path)
            for item in data.get("resolved_questions") or []:
                outcomes_by_id[item["id"]] = item

        # Also load DB resolved rows
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
                },
            )

        registry_rows = session.query(ForecastRegistry).order_by(ForecastRegistry.id).all()

        # Build class base rates from resolved outcomes before each forecast_at.
        class_outcomes: dict[str, list[int]] = {}
        for item in outcomes_by_id.values():
            cls = item.get("question_class") or "default"
            class_outcomes.setdefault(cls, []).append(int(item["outcome"]))

        forecasts: list[ResolvedForecast] = []
        for row in registry_rows:
            outcome_item = outcomes_by_id.get(row.question_id)
            if outcome_item is None:
                continue
            cls = outcome_item.get("question_class") or "default"
            # Base rate from class outcomes (not 0.5). Status-quo alt for change Qs.
            text = str(outcome_item.get("text") or "")
            change_q = "change" in text.lower() or "will " in text.lower()
            prior_outcomes = class_outcomes.get(cls) or [
                int(outcome_item["outcome"])
            ]
            # Exclude this outcome itself for a proper prior when possible
            others = [o for o in prior_outcomes]
            base = class_base_rate(others, default=0.5)
            if change_q and base == 0.5 and len(set(others)) <= 1:
                base = status_quo_baseline(change_question=True)
                # For change questions status-quo P(change)=0; if that is too harsh
                # when class rate exists, prefer class rate:
                if others:
                    base = class_base_rate(others, default=0.5)

            forecasts.append(
                ResolvedForecast(
                    question_id=row.question_id,
                    probability=float(row.probability),
                    outcome=int(outcome_item["outcome"]),
                    label=row.data_label or outcome_item.get("label") or "SYNTHETIC",
                    baseline_probability=float(base),
                    forecast_id=row.id,
                    question_class=cls,
                )
            )

        if not forecasts:
            # No matched registry↔outcome pairs: report empty / non interprétable.
            report = evaluate_proof([], min_n=min_n)
            payload = report_to_dict(report)
            payload["source"] = "forecast_registry"
            payload["matched"] = 0
            payload["registry_n"] = len(registry_rows)
            payload["note"] = (
                "No registry forecasts matched resolved outcomes. "
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
        payload["registry_n"] = len(registry_rows)
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
                for k in ("n_parsed", "data_label", "fallback", "status", "timeout_seconds")
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

    p_replay = sub.add_parser("replay", help="Replay engine from stored observation ids")
    p_replay.add_argument("--forecast-id", type=int, required=True)
    p_replay.set_defaults(func=cmd_replay)

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

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
