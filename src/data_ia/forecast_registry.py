"""Append-only forecast registry: write, verify hashes, replay engine."""

from __future__ import annotations

import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.orm import Session

from data_ia.config import REPO_ROOT, get_settings
from data_ia.db.models import ForecastRegistry, Observation
from data_ia.math.registry_hash import forecast_sha256


def git_commit_sha() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT),
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()[:40]
    except Exception:  # noqa: BLE001
        return "unknown"


def config_hash(
    *,
    taxonomy_path: str | Path | None = None,
    priors_path: str | Path | None = None,
    sources_path: str | Path | None = None,
    prior_mapping_path: str | Path | None = None,
) -> str:
    """Hash taxonomy + priors + source registry (+ prior mapping)."""
    settings = get_settings()
    paths = [
        Path(taxonomy_path or settings.taxonomy_path),
        Path(priors_path or settings.source_priors_path),
        Path(sources_path or settings.sources_registry_path),
        Path(prior_mapping_path or settings.prior_mapping_path),
    ]
    h = hashlib.sha256()
    for path in paths:
        h.update(path.name.encode("utf-8"))
        if path.exists():
            h.update(path.read_bytes())
        else:
            h.update(b"missing")
    return h.hexdigest()


def _canon_dt(value: datetime | str) -> str:
    """Canonical UTC ISO timestamp (SQLite may drop tzinfo on round-trip)."""
    if isinstance(value, str):
        text = value.replace("Z", "+00:00")
        value = datetime.fromisoformat(text)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    # Drop microseconds for stable hashing across backends.
    value = value.replace(microsecond=0)
    return value.isoformat().replace("+00:00", "Z")


def row_fields(row: ForecastRegistry) -> dict[str, Any]:
    return {
        "question_id": row.question_id,
        "forecast_at": _canon_dt(row.forecast_at),
        "data_cutoff": _canon_dt(row.data_cutoff),
        "git_commit": row.git_commit,
        "config_hash": row.config_hash,
        "extractor_version": row.extractor_version,
        "observation_ids": list(row.observation_ids or []),
        "probability": float(row.probability),
        "interval_low": None if row.interval_low is None else float(row.interval_low),
        "interval_high": None if row.interval_high is None else float(row.interval_high),
        "data_label": row.data_label,
    }


def append_forecast(
    session: Session,
    *,
    question_id: str,
    forecast_at: datetime,
    data_cutoff: datetime,
    observation_ids: list[int],
    probability: float,
    interval_low: float | None,
    interval_high: float | None,
    data_label: str,
    extractor_version: str | None = None,
    git_commit: str | None = None,
    cfg_hash: str | None = None,
) -> ForecastRegistry:
    """Insert one append-only registry row (never UPDATE)."""
    settings = get_settings()
    if forecast_at.tzinfo is None:
        forecast_at = forecast_at.replace(tzinfo=timezone.utc)
    else:
        forecast_at = forecast_at.astimezone(timezone.utc)
    if data_cutoff.tzinfo is None:
        data_cutoff = data_cutoff.replace(tzinfo=timezone.utc)
    else:
        data_cutoff = data_cutoff.astimezone(timezone.utc)
    forecast_at = forecast_at.replace(microsecond=0)
    data_cutoff = data_cutoff.replace(microsecond=0)
    fields = {
        "question_id": question_id,
        "forecast_at": _canon_dt(forecast_at),
        "data_cutoff": _canon_dt(data_cutoff),
        "git_commit": git_commit or git_commit_sha(),
        "config_hash": cfg_hash or config_hash(),
        "extractor_version": extractor_version or settings.extractor_version,
        "observation_ids": list(observation_ids),
        "probability": float(probability),
        "interval_low": None if interval_low is None else float(interval_low),
        "interval_high": None if interval_high is None else float(interval_high),
        "data_label": data_label,
    }
    digest = forecast_sha256(fields)
    row = ForecastRegistry(
        question_id=fields["question_id"],
        forecast_at=forecast_at,
        data_cutoff=data_cutoff,
        git_commit=fields["git_commit"],
        config_hash=fields["config_hash"],
        extractor_version=fields["extractor_version"],
        observation_ids=fields["observation_ids"],
        probability=fields["probability"],
        interval_low=fields["interval_low"],
        interval_high=fields["interval_high"],
        data_label=fields["data_label"],
        sha256=digest,
    )
    session.add(row)
    session.flush()
    return row


def verify_registry(session: Session) -> dict[str, Any]:
    """Recompute every hash; return report. ok=False on any mismatch."""
    rows = session.query(ForecastRegistry).order_by(ForecastRegistry.id).all()
    mismatches: list[dict[str, Any]] = []
    for row in rows:
        expected = forecast_sha256(row_fields(row))
        if expected != row.sha256:
            mismatches.append(
                {
                    "id": row.id,
                    "stored": row.sha256,
                    "computed": expected,
                }
            )
    return {
        "ok": len(mismatches) == 0,
        "n": len(rows),
        "mismatches": mismatches,
    }


def replay_forecast(
    session: Session,
    forecast_id: int,
    *,
    seed: dict[str, Any] | None = None,
    taxonomy: dict[str, Any] | None = None,
    source_priors: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Re-run fusion/aggregation from stored observation ids; check probability."""
    from data_ia.agents.pipeline import run_agents
    from data_ia.config import get_settings

    row = session.get(ForecastRegistry, forecast_id)
    if row is None:
        raise KeyError(f"forecast_id {forecast_id} not found")

    settings = get_settings()
    obs_rows = (
        session.query(Observation)
        .filter(Observation.id.in_(list(row.observation_ids or [])))
        .all()
    )
    if len(obs_rows) != len(set(row.observation_ids or [])):
        missing = set(row.observation_ids or []) - {o.id for o in obs_rows}
        raise ValueError(f"missing observation ids for replay: {sorted(missing)}")

    # Rebuild accepted observation dicts for Strategist.
    observations = []
    for o in obs_rows:
        observations.append(
            {
                "id": o.id,
                "source_id": o.source_id,
                "sub_question_id": o.sub_question_id,
                "extracted_value": o.extracted_value,
                "extracted_field": o.extracted_field or "probability",
                "unit": o.unit,
                "published_at": o.published_at.isoformat() if o.published_at else None,
                "source_passage": o.source_passage,
                "status": "accepted",
                "data_label": o.data_label,
                "content_hash": o.content_hash,
                "extractor_version": o.extractor_version,
            }
        )

    if seed is None:
        seed_path = Path(settings.seed_path)
        with open(seed_path, encoding="utf-8") as f:
            seed = yaml.safe_load(f) or {}

    # Replay path: skip Orchestrator→Collector; feed accepted obs into Strategist stack.
    # Use Investigator + Strategist only with pre-accepted observations.
    context: dict[str, Any] = {
        "seed": seed,
        "taxonomy": taxonomy,
        "source_priors": source_priors,
        "source_error_history": {},
        "leaf_history": {},
        "question": seed.get("question"),
        "sub_questions": seed.get("sub_questions") or [],
        "sources": seed.get("sources") or [],
        "accepted_observations": observations,
        "rejected_observations": [],
        "quarantined_observations": [],
        "data_cutoff": row.data_cutoff.isoformat(),
        "forecast_at": row.forecast_at.isoformat(),
        "replay_mode": True,
    }
    # Run investigator + strategist
    from data_ia.agents.investigator import InvestigatorAgent
    from data_ia.agents.strategist import StrategistAgent

    for agent in (InvestigatorAgent(), StrategistAgent()):
        result = agent.run(context)
        context.update(result.produced)
        if not result.ok and agent.name == "strategist":
            return {
                "ok": False,
                "forecast_id": forecast_id,
                "stored_probability": row.probability,
                "replayed_probability": None,
                "errors": result.errors,
            }

    replayed = context.get("final_probability")
    match = (
        replayed is not None
        and abs(float(replayed) - float(row.probability)) < 1e-9
    )
    return {
        "ok": bool(match),
        "forecast_id": forecast_id,
        "stored_probability": float(row.probability),
        "replayed_probability": None if replayed is None else float(replayed),
        "observation_ids": list(row.observation_ids or []),
        "tolerance": 1e-9,
    }
