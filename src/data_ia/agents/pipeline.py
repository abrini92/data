"""Run the six agents end-to-end and persist append-only forecast registry rows."""

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
from data_ia.forecast_registry import append_forecast
from data_ia.math.labels import SYNTHETIC, normalize_label
from data_ia.math.lookahead import LookAheadError, assert_resolution_before_forecast


class SyntheticBlockedError(RuntimeError):
    """Raised when synthetic data is requested alongside real collection."""


def load_yaml(path: str | Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"expected mapping in {path}")
    return data


def assert_synthetic_policy() -> None:
    """Hard-refuse COLLECT_REAL_SOURCES + USE_SYNTHETIC."""
    # Re-read settings (may raise from pydantic validator).
    settings = get_settings()
    if settings.collect_real_sources and settings.use_synthetic:
        raise SyntheticBlockedError(
            "COLLECT_REAL_SOURCES=true and USE_SYNTHETIC=true is forbidden"
        )


def run_agents(seed: dict[str, Any], *, taxonomy: dict[str, Any] | None = None,
               source_priors: dict[str, Any] | None = None,
               source_error_history: dict[str, list[tuple[float, float]]] | None = None,
               leaf_history: dict[str, list[float]] | None = None,
               forecast_at: datetime | None = None,
               data_cutoff: datetime | None = None) -> dict[str, Any]:
    """Execute Orchestrator → Scout → Collector → Controller → Investigator → Strategist."""
    now = forecast_at or datetime.now(timezone.utc)
    cutoff = data_cutoff or now
    context: dict[str, Any] = {
        "seed": seed,
        "taxonomy": taxonomy,
        "source_priors": source_priors,
        "source_error_history": source_error_history or {},
        "leaf_history": leaf_history or {},
        "forecast_at": now.isoformat(),
        "data_cutoff": cutoff.isoformat(),
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
        result = agent.run(context)
        results.append(result)
        context.update(result.produced)
        if not result.ok and agent.name in {
            "orchestrator", "scout", "collector", "controller", "strategist"
        }:
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
        "not_ready": bool(context.get("not_ready")),
        "forecast_at": context.get("forecast_at"),
        "data_cutoff": context.get("data_cutoff"),
    }


def _parse_horizon(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def persist_cycle(session: Session, seed: dict[str, Any], cycle: dict[str, Any],
                  as_of: date | None = None) -> dict[str, Any]:
    """Write question tree, sources, observations, estimates, append-only registry."""
    as_of = as_of or date.today()
    ctx = cycle["context"]
    q = seed["question"]
    settings = get_settings()

    existing = session.get(Question, q["id"])
    if existing is None:
        session.add(
            Question(
                id=q["id"],
                text=q["text"],
                horizon=_parse_horizon(q.get("horizon")),
                region=q.get("region") or q.get("zone"),
                zone=q.get("zone") or q.get("region"),
                target_variable=q.get("target_variable"),
                threshold=None if q.get("threshold") is None else float(q["threshold"]),
                unit=q.get("unit"),
                resolution_source=q.get("resolution_source"),
                resolution_rule=q.get("resolution_rule"),
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

    obs_ids: list[int] = []
    for obs in (
        list(ctx.get("accepted_observations") or [])
        + list(ctx.get("rejected_observations") or [])
        + list(ctx.get("quarantined_observations") or [])
    ):
        collected = obs.get("collected_at")
        if isinstance(collected, str):
            collected_dt = datetime.fromisoformat(collected.replace("Z", "+00:00"))
        else:
            collected_dt = datetime.now(timezone.utc)
        published = obs.get("published_at")
        if isinstance(published, str):
            published_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
        elif isinstance(published, datetime):
            published_dt = published
        else:
            published_dt = collected_dt

        row = Observation(
            source_id=obs["source_id"],
            sub_question_id=obs.get("sub_question_id"),
            raw_doc=obs.get("raw_doc"),
            extracted_value=obs.get("extracted_value"),
            extracted_field=obs.get("extracted_field"),
            unit=obs.get("unit"),
            source_passage=obs.get("source_passage"),
            url=obs.get("url"),
            collected_at=collected_dt,
            published_at=published_dt,
            content_hash=obs.get("content_hash"),
            extractor_version=obs.get("extractor_version"),
            status=obs.get("status", "raw"),
            rejection_reason=obs.get("rejection_reason"),
            data_label=normalize_label(obs.get("data_label")),
            meta=obs.get("meta"),
        )
        session.add(row)
        session.flush()
        if obs.get("status") == "accepted":
            obs_ids.append(int(row.id))

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
            # Estimates for the same calendar day may refresh; registry stays append-only.
            existing_est.estimate = float(meta["estimate"])
            existing_est.variance = meta.get("variance")
            existing_est.surprise = meta.get("surprise")
            existing_est.meta = meta

    registry_row = None
    if ctx.get("final_probability") is not None:
        # Always append a snapshot row (no UniqueConstraint overwrite).
        data_label = normalize_label(
            (ctx.get("accepted_observations") or [{}])[0].get("data_label")
            if ctx.get("accepted_observations")
            else SYNTHETIC
        )
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
                data_label=data_label,
            )
        )

        forecast_at = ctx.get("forecast_at")
        data_cutoff = ctx.get("data_cutoff")
        if isinstance(forecast_at, str):
            forecast_dt = datetime.fromisoformat(forecast_at.replace("Z", "+00:00"))
        else:
            forecast_dt = datetime.now(timezone.utc)
        if isinstance(data_cutoff, str):
            cutoff_dt = datetime.fromisoformat(data_cutoff.replace("Z", "+00:00"))
        else:
            cutoff_dt = forecast_dt

        registry_row = append_forecast(
            session,
            question_id=q["id"],
            forecast_at=forecast_dt,
            data_cutoff=cutoff_dt,
            observation_ids=obs_ids,
            probability=float(ctx["final_probability"]),
            interval_low=ctx.get("interval_low"),
            interval_high=ctx.get("interval_high"),
            data_label=data_label,
            extractor_version=settings.extractor_version,
        )

    session.commit()
    return {
        "forecast_registry_id": None if registry_row is None else registry_row.id,
        "observation_ids": obs_ids,
    }


def seed_resolved_and_errors(session: Session, resolved_path: Path) -> None:
    data = load_yaml(resolved_path)
    for item in data.get("resolved_questions") or []:
        if session.get(ResolvedQuestion, item["id"]) is None:
            session.add(
                ResolvedQuestion(
                    id=item["id"],
                    text=item["text"],
                    probability=(
                        None
                        if item.get("probability") is None
                        else float(item["probability"])
                    ),
                    outcome=int(item["outcome"]),
                    resolved_on=(
                        date.fromisoformat(item["resolved_on"])
                        if item.get("resolved_on")
                        else None
                    ),
                    label=item.get("label", "ILLUSTRATIVE/SYNTHETIC"),
                    data_label=normalize_label(item.get("data_label") or item.get("label")),
                    question_class=item.get("question_class"),
                    baseline_probability=(
                        None
                        if item.get("baseline_probability") is None
                        else float(item["baseline_probability"])
                    ),
                    meta={"illustrative": True},
                )
            )
    if session.query(SourceError).count() == 0:
        for err in data.get("source_errors") or []:
            if session.get(Source, err["source_id"]) is None:
                continue
            session.add(
                SourceError(
                    source_id=err["source_id"],
                    resolved_id=err.get("resolved_id"),
                    z=float(err["z"]),
                    x=float(err["x"]),
                    data_label=normalize_label(err.get("data_label"), default=SYNTHETIC),
                )
            )
    session.commit()


def _error_history_before_forecast(
    session: Session,
    forecast_at: datetime,
) -> dict[str, list[tuple[float, float]]]:
    """Source errors only from questions resolved strictly before forecast_at.

    Rows without a resolution date are excluded (no look-ahead in backtests).
    """
    history: dict[str, list[tuple[float, float]]] = {}
    rows = (
        session.query(SourceError, ResolvedQuestion)
        .outerjoin(ResolvedQuestion, SourceError.resolved_id == ResolvedQuestion.id)
        .all()
    )
    for err, resolved in rows:
        if resolved is None or resolved.resolved_on is None:
            continue
        try:
            assert_resolution_before_forecast(resolved.resolved_on, forecast_at)
        except LookAheadError:
            continue
        history.setdefault(err.source_id, []).append((err.z, err.x))
    return history


def _forecast_day(forecast_at: datetime | date) -> date:
    if isinstance(forecast_at, datetime):
        if forecast_at.tzinfo is not None:
            return forecast_at.astimezone(timezone.utc).date()
        return forecast_at.date()
    return forecast_at


def leaf_history_before(
    estimates: list[tuple[str, date, float]],
    forecast_at: datetime | date,
) -> dict[str, list[float]]:
    """Sort by as_of and keep only rows with as_of strictly earlier than forecast day.

    ``estimates`` is a list of (sub_question_id, as_of, estimate). Same-day rows
    (as_of == forecast day) are excluded.
    """
    t = _forecast_day(forecast_at)
    ordered = sorted(
        ((sid, as_of, est) for sid, as_of, est in estimates if as_of < t),
        key=lambda row: (row[0], row[1]),
    )
    history: dict[str, list[float]] = {}
    for sid, _as_of, est in ordered:
        history.setdefault(sid, []).append(float(est))
    return history


def _leaf_history_before_forecast(
    session: Session,
    forecast_at: datetime | date,
) -> dict[str, list[float]]:
    rows = session.query(SubQuestionEstimate).all()
    return leaf_history_before(
        [(est.sub_question_id, est.as_of, float(est.estimate)) for est in rows],
        forecast_at,
    )


def run_offline_cycle(
    seed_path: str | Path | None = None,
    *,
    persist: bool = True,
    forecast_at: datetime | None = None,
) -> dict[str, Any]:
    """One-command offline cycle with stub LLM + SQLite/Postgres auto-fallback."""
    assert_synthetic_policy()
    settings = get_settings()
    seed_path = Path(seed_path or settings.seed_path)
    seed = load_yaml(seed_path)
    taxonomy = load_yaml(settings.taxonomy_path)
    priors = load_yaml(settings.source_priors_path)

    engine, db_mode = try_init_db()
    session = get_session(fallback_sqlite=(db_mode != "postgres"))

    now = forecast_at or datetime.now(timezone.utc)
    error_history: dict[str, list[tuple[float, float]]] = {}
    resolved_path = seed_path.parent / "synthetic_resolved.yaml"
    try:
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

        # Synthetic resolved set / error history only when USE_SYNTHETIC=true.
        if settings.use_synthetic and resolved_path.exists():
            seed_resolved_and_errors(session, resolved_path)
            error_history = _error_history_before_forecast(session, now)

        leaf_history = _leaf_history_before_forecast(session, now)

        cycle = run_agents(
            seed,
            taxonomy=taxonomy,
            source_priors=priors,
            source_error_history=error_history,
            leaf_history=leaf_history,
            forecast_at=now,
            data_cutoff=now,
        )
        cycle["db_mode"] = db_mode
        cycle["engine_url"] = str(engine.url)

        if persist and cycle.get("final_probability") is not None:
            persisted = persist_cycle(session, seed, cycle)
            cycle["forecast_registry_id"] = persisted.get("forecast_registry_id")
            cycle["persisted_observation_ids"] = persisted.get("observation_ids")
        return cycle
    finally:
        session.close()
