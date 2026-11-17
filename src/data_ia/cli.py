"""CLI entrypoints: offline cycle, Brier proof, collect, agent catalog, dashboard hint."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from data_ia import __version__
from data_ia.agents import AGENT_CATALOG
from data_ia.agents.pipeline import load_yaml, run_offline_cycle
from data_ia.config import REPO_ROOT, get_settings
from data_ia.math.brier import ResolvedForecast, evaluate_proof


def cmd_cycle(_: argparse.Namespace) -> int:
    result = run_offline_cycle(persist=True)
    payload = {
        "db_mode": result.get("db_mode"),
        "final_probability": result.get("final_probability"),
        "interval": [
            result["context"].get("interval_low"),
            result["context"].get("interval_high"),
        ],
        "source_weights": result["context"].get("source_weights"),
        "disclaimer": result.get("disclaimer"),
        "agents": result.get("agent_results"),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if result.get("final_probability") is not None else 1


def cmd_brier(args: argparse.Namespace) -> int:
    path = Path(args.path or (REPO_ROOT / "seeds" / "synthetic_resolved.yaml"))
    data = load_yaml(path)
    forecasts = [
        ResolvedForecast(
            question_id=item["id"],
            probability=float(item["probability"]),
            outcome=int(item["outcome"]),
            label=item.get("label", "ILLUSTRATIVE/SYNTHETIC"),
            baseline_probability=float(item.get("baseline_probability", 0.5)),
        )
        for item in data.get("resolved_questions") or []
    ]
    report = evaluate_proof(forecasts)
    print(json.dumps(
        {
            "n": report.n,
            "model_brier": report.model_brier,
            "baseline_brier": report.baseline_brier,
            "improvement": report.improvement,
            "illustrative": report.illustrative,
            "disclaimer": report.disclaimer,
            "source_file": str(path),
        },
        indent=2,
    ))
    return 0


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
    from data_ia.connectors.registry import get_connector, list_sources, save_raw_cache

    settings = get_settings()
    real = bool(settings.collect_real_sources) or bool(args.real)

    if args.all:
        names = [s["name"] for s in list_sources(include_optional=bool(args.include_optional))]
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
            "controller_accepted": sum(
                1 for c in payload.controller_results if c.get("accepted")
            ),
            "skipped_reason": payload.skipped_reason,
            "errors": payload.errors,
            "cache_path": cache_path,
            "real": real,
        }
        summaries.append(summary)
        if args.source and not payload.ok:
            exit_code = 1
        elif args.all and not payload.ok and payload.provenance.fetch_mode != "skipped":
            exit_code = 1

    print(json.dumps({"real": real, "results": summaries}, indent=2, ensure_ascii=False))
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

    p_brier = sub.add_parser("brier", help="Brier proof vs naive baseline (synthetic set)")
    p_brier.add_argument("--path", help="YAML of resolved questions (ILLUSTRATIVE/SYNTHETIC)")
    p_brier.set_defaults(func=cmd_brier)

    p_agents = sub.add_parser("agents", help="Describe the six agents")
    p_agents.set_defaults(func=cmd_agents)

    p_dash = sub.add_parser("dashboard", help="Print Streamlit launch command")
    p_dash.set_defaults(func=cmd_dashboard)

    p_collect = sub.add_parser(
        "collect",
        help="Collect from a registered source (fixtures unless COLLECT_REAL_SOURCES)",
    )
    p_collect.add_argument("--source", help="Source name from config/sources.yaml")
    p_collect.add_argument("--all", action="store_true", help="Collect every non-optional source")
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
