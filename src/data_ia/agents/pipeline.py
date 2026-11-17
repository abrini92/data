"""Run the six agents end-to-end and persist a daily snapshot."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.orm import Session

from data_ia.agents.base import AgentResult
from data_ia.agents.collector import CollectorAgent
from data_ia.agents.controller import ControllerAgent
from data_ia.agents.investigator import InvestigatorAgent
from data_ia.agents.orchestrator import OrchestratorAgent
from data_ia.agents.scout import ScoutAgent
from data_ia.agents.strategist import StrategistAgent
from data_ia.config import get_settings
from data_ia.db.models import (
    DailySnapshot,
    Observation,
    Question,
    ResolvedQuestion,
    Source,
    SourceError,
    SubQuestion,
    SubQuestionEstimate,
)
from data_ia.db.session import get_session, try_init_db


def load_yaml(path: str | Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"expected mapping in {path}")
    return data


def run_agents(seed: dict[str, Any], *, taxonomy: dict[str, Any] | None = None,
               source_priors: dict[str, Any] | None = None,
               source_error_history: dict[str, list[tuple[float, float]]] | None = None,
               leaf_history: dict[str, list[float]] | None = None) -> dict[str, Any]:
    """Execute Orchestrator → Scout → Collector → Controller → Investigator → Strategist."""
    context: dict[str, Any] = {
        "seed": seed,
        "taxonomy": taxonomy,
        "source_priors": source_priors,
        "source_error_history": source_error_history or {},
        "leaf_history": leaf_history or {},
    }
    agents = [
        OrchestratorAgent(),
        ScoutAgent(),
        CollectorAgent(),
        ControllerAgent(),
        InvestigatorAgent(),
        StrategistAgent(),
    ]
    results: list[AgentResult] = []

    for agent in agents:
        # Feed prior produced keys into context
        result = agent.run(context)
        results.append(result)
        context.update(result.produced)
        if not result.ok and agent.name in {"orchestrator", "scout", "collector", "controller", "strategist"}:
            break

    return {
        "context": context,
        "agent_results": [
            {
                "agent": r.agent,
                "ok": r.ok,
                "checks": r.checks,
                "errors": r.errors,
                "failure_action": r.failure_action,
                "produced_keys": sorted(r.produced.keys()),
            }
            for r in results
        ],
        "final_probability": context.get("final_probability"),
        "disclaimer": context.get("disclaimer"),
    }


def persist_cycle(session: Session, seed: dict[str, Any], cycle: dict[str, Any],
                  as_of: date | None = None) -> None:
    """Write question tree, sources, observations, estimates, snapshot."""
    as_of = as_of or date.today()
    ctx = cycle["context"]
    q = seed["question"]

    existing = session.get(Question, q["id"])
    if existing is None:
        session.add(
            Question(
                id=q["id"],
                text=q["text"],
                horizon=date.fromisoformat(q["horizon"]) if q.get("horizon") else None,
                region=q.get("region"),
                status="active",
                illustrative=bool(q.get("illustrative", True)),
            )
        )
    session.flush()

    for src in ctx.get("sources") or seed.get("sources") or []:
        if session.get(Source, src["id"]) is None:
            session.add(
                Source(
                    id=src["id"],
                    name=src["name"],
                    url=src.get("url"),
                    source_class=src.get("source_class", "open"),
                    publisher=src.get("publisher"),
                    freshness_days=src.get("freshness_days"),
                    usage_rights=src.get("usage_rights"),
                    active=True,
                    meta={"illustrative": True},
                )
            )
    session.flush()

    # Insert tree parents before children so SQLite FK checks pass.
    pending = {
        n["id"]: n for n in (seed.get("sub_questions") or []) if session.get(SubQuestion, n["id"]) is None
    }
    inserted: set[str] = set()
    while pending:
        progress = False
        for nid, node in list(pending.items()):
            parent = node.get("parent_id")
            if parent is not None and session.get(SubQuestion, parent) is None and parent not in inserted:
                continue
            session.add(
                SubQuestion(
                    id=node["id"],
                    question_id=q["id"],
                    parent_id=parent,
                    text=node["text"],
                    node_type=node.get("node_type", "leaf"),
                    weight=float(node.get("weight", 1.0)),
                    illustrative=bool(node.get("illustrative", True)),
                    sort_order=int(node.get("sort_order", 0)),
                )
            )
            inserted.add(nid)
            del pending[nid]
            progress = True
        if progress:
            session.flush()
        else:
            # Cycle or missing parent — insert remaining without ordering.
            for node in pending.values():
                session.add(
                    SubQuestion(
                        id=node["id"],
                        question_id=q["id"],
                        parent_id=None,
                        text=node["text"],
                        node_type=node.get("node_type", "leaf"),
                        weight=float(node.get("weight", 1.0)),
                        illustrative=bool(node.get("illustrative", True)),
                        sort_order=int(node.get("sort_order", 0)),
                    )
                )
            session.flush()
            break

    for obs in (
        list(ctx.get("accepted_observations") or [])
        + list(ctx.get("rejected_observations") or [])
        + list(ctx.get("quarantined_observations") or [])
    ):
        collected = obs.get("collected_at")
        if isinstance(collected, str):
            collected_dt = datetime.fromisoformat(collected)
        else:
            collected_dt = datetime.now(timezone.utc)
        session.add(
            Observation(
                source_id=obs["source_id"],
                sub_question_id=obs.get("sub_question_id"),
                raw_doc=obs.get("raw_doc"),
                extracted_value=obs.get("extracted_value"),
                extracted_field=obs.get("extracted_field"),
                url=obs.get("url"),
                collected_at=collected_dt,
                content_hash=obs.get("content_hash"),
                extractor_version=obs.get("extractor_version"),
                status=obs.get("status", "raw"),
                rejection_reason=obs.get("rejection_reason"),
                meta=obs.get("meta"),
            )
        )

    for leaf_id, meta in (ctx.get("leaf_estimates") or {}).items():
        existing_est = (
            session.query(SubQuestionEstimate)
            .filter_by(sub_question_id=leaf_id, as_of=as_of)
            .one_or_none()
        )
        if existing_est is None:
            session.add(
                SubQuestionEstimate(
                    sub_question_id=leaf_id,
                    as_of=as_of,
                    estimate=float(meta["estimate"]),
                    variance=meta.get("variance"),
                    surprise=meta.get("surprise"),
                    meta=meta,
                )
            )
        else:
            existing_est.estimate = float(meta["estimate"])
            existing_est.variance = meta.get("variance")
            existing_est.surprise = meta.get("surprise")
            existing_est.meta = meta

    if ctx.get("final_probability") is not None:
        existing_snap = (
            session.query(DailySnapshot)
            .filter_by(question_id=q["id"], as_of=as_of)
            .one_or_none()
        )
        if existing_snap is None:
            session.add(
                DailySnapshot(
                    question_id=q["id"],
                    as_of=as_of,
                    probability=float(ctx["final_probability"]),
                    interval_low=ctx.get("interval_low"),
                    interval_high=ctx.get("interval_high"),
                    source_weights=ctx.get("source_weights"),
                    sensitivities=ctx.get("sensitivities"),
                    node_probabilities=ctx.get("node_probabilities"),
                    disclaimer=ctx.get("disclaimer"),
                )
            )
        else:
            existing_snap.probability = float(ctx["final_probability"])
            existing_snap.interval_low = ctx.get("interval_low")
            existing_snap.interval_high = ctx.get("interval_high")
            existing_snap.source_weights = ctx.get("source_weights")
            existing_snap.sensitivities = ctx.get("sensitivities")
            existing_snap.node_probabilities = ctx.get("node_probabilities")
            existing_snap.disclaimer = ctx.get("disclaimer")
    session.commit()


def seed_resolved_and_errors(session: Session, resolved_path: Path) -> None:
    data = load_yaml(resolved_path)
    for item in data.get("resolved_questions") or []:
        if session.get(ResolvedQuestion, item["id"]) is None:
            session.add(
                ResolvedQuestion(
                    id=item["id"],
                    text=item["text"],
                    probability=float(item["probability"]),
                    outcome=int(item["outcome"]),
                    resolved_on=(
                        date.fromisoformat(item["resolved_on"])
                        if item.get("resolved_on")
                        else None
                    ),
                    label=item.get("label", "ILLUSTRATIVE/SYNTHETIC"),
                    baseline_probability=float(item.get("baseline_probability", 0.5)),
                    meta={"illustrative": True},
                )
            )
    # Seed illustrative errors once (avoid duplicating on every cycle).
    if session.query(SourceError).count() == 0:
        for err in data.get("source_errors") or []:
            session.add(
                SourceError(
                    source_id=err["source_id"],
                    resolved_id=err.get("resolved_id"),
                    z=float(err["z"]),
                    x=float(err["x"]),
                )
            )
    session.commit()


def run_offline_cycle(
    seed_path: str | Path | None = None,
    *,
    persist: bool = True,
) -> dict[str, Any]:
    """One-command offline cycle with stub LLM + SQLite/Postgres auto-fallback."""
    settings = get_settings()
    seed_path = Path(seed_path or settings.seed_path)
    seed = load_yaml(seed_path)
    taxonomy = load_yaml(settings.taxonomy_path)
    priors = load_yaml(settings.source_priors_path)

    engine, db_mode = try_init_db()
    session = get_session(fallback_sqlite=(db_mode != "postgres"))

    error_history: dict[str, list[tuple[float, float]]] = {}
    resolved_path = seed_path.parent / "synthetic_resolved.yaml"
    try:
        # Sources first (FK target for source_error_history).
        for src in seed.get("sources") or []:
            if session.get(Source, src["id"]) is None:
                session.add(
                    Source(
                        id=src["id"],
                        name=src["name"],
                        url=src.get("url"),
                        source_class=src.get("source_class", "open"),
                        publisher=src.get("publisher"),
                        active=True,
                    )
                )
        session.commit()

        if resolved_path.exists():
            seed_resolved_and_errors(session, resolved_path)
            for row in session.query(SourceError).all():
                error_history.setdefault(row.source_id, []).append((row.z, row.x))

        leaf_history: dict[str, list[float]] = {}
        for est in session.query(SubQuestionEstimate).all():
            leaf_history.setdefault(est.sub_question_id, []).append(est.estimate)

        cycle = run_agents(
            seed,
            taxonomy=taxonomy,
            source_priors=priors,
            source_error_history=error_history,
            leaf_history=leaf_history,
        )
        cycle["db_mode"] = db_mode
        cycle["engine_url"] = str(engine.url)

        if persist and cycle.get("final_probability") is not None:
            persist_cycle(session, seed, cycle)
        return cycle
    finally:
        session.close()
