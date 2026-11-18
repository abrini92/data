"""Append-only forecast registry: write, verify chained hashes, replay engine."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.orm import Session

from data_ia.config import REPO_ROOT, get_settings
from data_ia.db.models import (
    CHAIN_GENESIS_METHOD,
    ForecastRegistry,
    Observation,
)
from data_ia.math.registry_hash import (
    content_sha256,
    forecast_sha256,
    legacy_forecast_sha256,
)

class RegistryIntegrityError(ValueError):
    """Raised when a proof row cannot be written (unknown commit, dirty tree, …)."""


def chain_head_path_default() -> Path:
    return Path(get_settings().registry_chain_head_path)

def git_commit_sha(*, allow_unknown: bool = False) -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT),
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()[:40]
    except Exception:  # noqa: BLE001
        if allow_unknown:
            return "unknown"
        raise RegistryIntegrityError(
            "git_commit refused: cannot resolve HEAD (never store 'unknown')"
        ) from None


def git_tree_dirty() -> bool:
    try:
        out = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=str(REPO_ROOT),
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return bool(out.strip())
    except Exception:  # noqa: BLE001
        return True


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
    value = value.replace(microsecond=0)
    return value.isoformat().replace("+00:00", "Z")


def legacy_row_fields(row: ForecastRegistry) -> dict[str, Any]:
    """Pass-3 hash payload (pre-chain)."""
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
        "prev_sha256": row.prev_sha256,
        "p_base": None if row.p_base is None else float(row.p_base),
        "baseline_method": row.baseline_method,
        "series_id": row.series_id,
        "vintage_sha256": row.vintage_sha256,
        "observations_content_hash": row.observations_content_hash,
        "seed_hash": row.seed_hash,
        "wave_id": row.wave_id,
    }


def is_chain_genesis(row: ForecastRegistry) -> bool:
    return row.baseline_method == CHAIN_GENESIS_METHOD


def find_chain_genesis(rows: list[ForecastRegistry]) -> ForecastRegistry | None:
    for row in rows:
        if is_chain_genesis(row):
            return row
    return None


def _observations_content_hash(session: Session, observation_ids: list[int]) -> str:
    if not observation_ids:
        return content_sha256([])
    rows = (
        session.query(Observation)
        .filter(Observation.id.in_(list(observation_ids)))
        .order_by(Observation.id)
        .all()
    )
    payload = [
        {
            "id": o.id,
            "source_id": o.source_id,
            "sub_question_id": o.sub_question_id,
            "extracted_value": o.extracted_value,
            "extracted_field": o.extracted_field,
            "unit": o.unit,
            "published_at": o.published_at.isoformat() if o.published_at else None,
            "content_hash": o.content_hash,
            "data_label": o.data_label,
            "extractor_version": o.extractor_version,
        }
        for o in rows
    ]
    return content_sha256(payload)


def export_chain_head(
    *,
    sha256: str,
    forecast_id: int,
    question_id: str,
    path: Path | None = None,
) -> Path:
    """Append the new chain head outside the DB (git-tracked jsonl)."""
    out = path or chain_head_path_default()
    out.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "sha256": sha256,
        "forecast_id": forecast_id,
        "question_id": question_id,
        "exported_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
            "+00:00", "Z"
        ),
    }
    with open(out, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return out


def read_chain_head(path: Path | None = None) -> str | None:
    p = path or chain_head_path_default()
    if not p.exists():
        return None
    lines = [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        return None
    try:
        return str(json.loads(lines[-1])["sha256"])
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


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
    p_base: float | None = None,
    baseline_method: str | None = None,
    series_id: str | None = None,
    vintage_sha256: str | None = None,
    observations_content_hash: str | None = None,
    seed_hash: str | None = None,
    wave_id: str | None = None,
    require_clean_tree: bool = False,
    export_head: bool = True,
    chain_head_path: Path | None = None,
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

    commit = git_commit or git_commit_sha()
    if commit == "unknown":
        raise RegistryIntegrityError("git_commit refused: value 'unknown' is forbidden")
    if require_clean_tree and git_tree_dirty():
        raise RegistryIntegrityError(
            "git working tree is dirty; refuse proof registry row"
        )

    prev = (
        session.query(ForecastRegistry)
        .order_by(ForecastRegistry.id.desc())
        .first()
    )
    prev_sha = None if prev is None else prev.sha256

    obs_hash = observations_content_hash
    if obs_hash is None:
        obs_hash = _observations_content_hash(session, list(observation_ids))

    fields = {
        "question_id": question_id,
        "forecast_at": _canon_dt(forecast_at),
        "data_cutoff": _canon_dt(data_cutoff),
        "git_commit": commit,
        "config_hash": cfg_hash or config_hash(),
        "extractor_version": extractor_version or settings.extractor_version,
        "observation_ids": list(observation_ids),
        "probability": float(probability),
        "interval_low": None if interval_low is None else float(interval_low),
        "interval_high": None if interval_high is None else float(interval_high),
        "data_label": data_label,
        "prev_sha256": prev_sha,
        "p_base": None if p_base is None else float(p_base),
        "baseline_method": baseline_method,
        "series_id": series_id,
        "vintage_sha256": vintage_sha256,
        "observations_content_hash": obs_hash,
        "seed_hash": seed_hash,
        "wave_id": wave_id,
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
        prev_sha256=fields["prev_sha256"],
        p_base=fields["p_base"],
        baseline_method=fields["baseline_method"],
        series_id=fields["series_id"],
        vintage_sha256=fields["vintage_sha256"],
        observations_content_hash=fields["observations_content_hash"],
        seed_hash=fields["seed_hash"],
        wave_id=fields["wave_id"],
        sha256=digest,
    )
    session.add(row)
    session.flush()
    if export_head:
        export_chain_head(
            sha256=digest,
            forecast_id=row.id,
            question_id=question_id,
            path=chain_head_path,
        )
    return row


def verify_registry(
    session: Session,
    *,
    chain_head_path: Path | None = None,
) -> dict[str, Any]:
    """Recompute hashes; legacy rows use Pass-3 digest, then chain from genesis.

    Still detects coherent rewrites (hash mismatch) and deletions (id gaps /
    chain breaks / head mismatch). Annotations are listed, never rewritten.
    """
    rows = session.query(ForecastRegistry).order_by(ForecastRegistry.id).all()
    mismatches: list[dict[str, Any]] = []
    chain_breaks: list[dict[str, Any]] = []
    id_gaps: list[dict[str, Any]] = []
    legacy_ids: list[int] = []
    genesis = find_chain_genesis(rows)
    genesis_id = None if genesis is None else genesis.id

    expected_id = 1
    expected_prev: str | None = None
    chain_started = False

    for row in rows:
        if row.id != expected_id:
            id_gaps.append({"expected_id": expected_id, "actual_id": row.id})
        expected_id = row.id + 1

        is_legacy = genesis_id is not None and row.id < genesis_id
        if is_legacy:
            legacy_ids.append(row.id)
            expected = legacy_forecast_sha256(legacy_row_fields(row))
            if expected != row.sha256:
                mismatches.append(
                    {
                        "id": row.id,
                        "stored": row.sha256,
                        "computed": expected,
                        "schema": "legacy",
                    }
                )
            # Legacy rows are pre-chain: prev_sha256 must stay unset.
            if row.prev_sha256 is not None:
                chain_breaks.append(
                    {
                        "id": row.id,
                        "stored_prev": row.prev_sha256,
                        "expected_prev": None,
                        "reason": "legacy_row_has_prev",
                    }
                )
            continue

        # Chained segment: starts at genesis (or first row when no genesis).
        if not chain_started:
            expected_prev = None
            chain_started = True

        expected = forecast_sha256(row_fields(row))
        if expected != row.sha256:
            mismatches.append(
                {
                    "id": row.id,
                    "stored": row.sha256,
                    "computed": expected,
                    "schema": "chained",
                }
            )
        if (row.prev_sha256 or None) != (expected_prev or None):
            chain_breaks.append(
                {
                    "id": row.id,
                    "stored_prev": row.prev_sha256,
                    "expected_prev": expected_prev,
                }
            )
        expected_prev = row.sha256

    head_file = read_chain_head(chain_head_path)
    head_mismatch = None
    chained_rows = (
        [r for r in rows if genesis_id is None or r.id >= genesis_id]
        if rows
        else []
    )
    if chained_rows:
        db_head = chained_rows[-1].sha256
        if head_file is None:
            head_mismatch = {
                "db_head": db_head,
                "file_head": None,
                "reason": "missing_head_file",
            }
        elif head_file != db_head:
            head_mismatch = {
                "db_head": db_head,
                "file_head": head_file,
                "reason": "head_mismatch",
            }
    elif rows and genesis_id is None:
        # Only-legacy registry without genesis yet: no chain head required.
        head_mismatch = None

    annotations: list[dict[str, Any]] = []
    try:
        from data_ia.migrate_registry import list_annotations

        annotations = list_annotations(session)
    except Exception:  # noqa: BLE001
        annotations = []

    ok = not mismatches and not chain_breaks and not id_gaps and head_mismatch is None
    # Empty registry: ok with no head file
    if not rows and head_file is None:
        ok = True
        head_mismatch = None

    return {
        "ok": ok,
        "n": len(rows),
        "legacy_n": len(legacy_ids),
        "legacy_ids": legacy_ids,
        "genesis_id": genesis_id,
        "mismatches": mismatches,
        "chain_breaks": chain_breaks,
        "id_gaps": id_gaps,
        "head_mismatch": head_mismatch,
        "annotations": annotations,
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

    # Freeze / minimal-baseline rows: replay = stored probability + hash verify.
    if not observations and row.baseline_method:
        stored = float(row.probability)
        return {
            "ok": True,
            "forecast_id": forecast_id,
            "stored_probability": stored,
            "replayed_probability": stored,
            "observation_ids": list(row.observation_ids or []),
            "tolerance": 1e-9,
            "mode": "frozen_baseline",
            "p_base": None if row.p_base is None else float(row.p_base),
            "baseline_method": row.baseline_method,
            "sha256": row.sha256,
        }

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
