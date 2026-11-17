"""CLI entrypoints: offline cycle, Brier proof, agent catalog, dashboard hint."""

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="data-ia", description=f"Data IA v{__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_cycle = sub.add_parser("cycle", help="Run full offline cycle (stub LLM)")
    p_cycle.set_defaults(func=cmd_cycle)

    p_brier = sub.add_parser("brier", help="Brier proof vs naive baseline (synthetic set)")
    p_brier.add_argument(
        "--path",
        help="YAML of resolved questions (ILLUSTRATIVE/SYNTHETIC)",
    )
    p_brier.set_defaults(func=cmd_brier)

    p_agents = sub.add_parser("agents", help="Describe the six agents")
    p_agents.set_defaults(func=cmd_agents)

    p_dash = sub.add_parser("dashboard", help="Print Streamlit launch command")
    p_dash.set_defaults(func=cmd_dashboard)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
