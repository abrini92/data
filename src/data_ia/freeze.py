"""Freeze a proof-question forecast into the append-only registry (B4)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from sqlalchemy.orm import Session

from data_ia.config import get_settings
from data_ia.db.models import Question
from data_ia.forecast_registry import (
    RegistryIntegrityError,
    append_forecast,
    config_hash,
    git_commit_sha,
)
from data_ia.freeze_calendar import (
    FreezeDeadlineError,
    assert_before_freeze_deadline,
    baseline_method_for,
)
from data_ia.math.persist_v3 import historical_frequency, p_haut
from data_ia.math.registry_hash import content_sha256
from data_ia.wave_import import load_wave


class FreezeError(ValueError):
    pass


def _parse_dt(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(microsecond=0)


def _ensure_question(session: Session, question_id: str, wave_id: str | None) -> Question:
    q = session.get(Question, question_id)
    if q is not None:
        return q
    # Pull text/series from the matching wave when possible.
    text = question_id
    series = None
    for name in ("vague1", "vague1b"):
        try:
            bundle = load_wave(name, require_hash=True)
        except Exception:  # noqa: BLE001
            continue
        for item in bundle.questions:
            if str(item.get("id")) == question_id:
                text = str(item.get("text") or question_id)
                series = item.get("series")
                wave_id = wave_id or bundle.wave_id
                break
    q = Question(
        id=question_id,
        text=text,
        target_variable=str(series or ""),
        zone=f"wave_{wave_id}" if wave_id else None,
        status="active",
        illustrative=False,
    )
    session.add(q)
    session.flush()
    return q


def compute_baseline(
    *,
    question_id: str,
    changes: Sequence[float] | None = None,
    event_history: Sequence[int] | None = None,
    method: str | None = None,
    p_base_override: float | None = None,
    justification: str | None = None,
) -> tuple[float, str]:
    """Compute naive baseline at freeze time (persist_v3 / frequency / 0.5)."""
    chosen = method or baseline_method_for(question_id)
    if p_base_override is not None:
        detail = justification or f"override method={chosen}"
        return float(p_base_override), detail
    if chosen == "persist_v3":
        if not changes:
            raise FreezeError(
                f"persist_v3 baseline for {question_id} requires --series-changes"
            )
        return p_haut(changes)
    if chosen == "frequency":
        if not event_history:
            raise FreezeError(
                f"frequency baseline for {question_id} requires --event-history"
            )
        return historical_frequency(event_history)
    # last resort
    if not justification:
        raise FreezeError(
            "0.5 baseline requires written justification (--baseline-justification)"
        )
    return 0.5, f"0,5 + justification: {justification}"


def freeze_question(
    session: Session,
    *,
    question_id: str,
    probability: float,
    data_cutoff: datetime | str,
    forecast_at: datetime | str | None = None,
    series_id: str,
    vintage_sha256: str,
    data_label: str = "TEST",
    wave_id: str | None = None,
    changes: Sequence[float] | None = None,
    event_history: Sequence[int] | None = None,
    baseline_method: str | None = None,
    p_base_override: float | None = None,
    baseline_justification: str | None = None,
    seed_payload: Any | None = None,
    interval_low: float | None = None,
    interval_high: float | None = None,
    observation_ids: list[int] | None = None,
    allow_dirty: bool = False,
    export_head: bool = True,
    chain_head_path: Path | None = None,
) -> dict[str, Any]:
    """Freeze one question into the registry (append-only).

    ``data_cutoff`` must be distinct from ``forecast_at`` when both are set
    explicitly for a proof freeze (B4). TEST freezes may use allow_dirty.
    """
    if not 0.0 <= float(probability) <= 1.0:
        raise FreezeError("probability must be in [0, 1]")
    if not series_id:
        raise FreezeError("series_id is required")
    if not vintage_sha256 or len(vintage_sha256) < 16:
        raise FreezeError("vintage_sha256 is required (content hash of the millésime)")

    cutoff = _parse_dt(data_cutoff)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    f_at = _parse_dt(forecast_at) if forecast_at is not None else now
    if cutoff > f_at:
        raise FreezeError("data_cutoff must be <= forecast_at")
    if cutoff == f_at:
        raise FreezeError(
            "data_cutoff must be distinct from forecast_at for a proof freeze"
        )

    try:
        assert_before_freeze_deadline(question_id, f_at)
    except FreezeDeadlineError:
        raise

    label = str(data_label).upper()
    require_clean = label not in {"TEST", "SYNTHETIC"} and not allow_dirty
    # Resolve commit early (never unknown).
    commit = git_commit_sha()

    p_base, method_detail = compute_baseline(
        question_id=question_id,
        changes=changes,
        event_history=event_history,
        method=baseline_method,
        p_base_override=p_base_override,
        justification=baseline_justification,
    )
    method_name = baseline_method or baseline_method_for(question_id)
    baseline_method_stored = f"{method_name}: {method_detail}"

    resolved_wave = wave_id
    if resolved_wave is None:
        for name in ("vague1", "vague1b"):
            try:
                bundle = load_wave(name, require_hash=True)
            except Exception:  # noqa: BLE001
                continue
            if any(str(q.get("id")) == question_id for q in bundle.questions):
                resolved_wave = bundle.wave_id
                break

    _ensure_question(session, question_id, resolved_wave)
    seed_hash = None if seed_payload is None else content_sha256(seed_payload)
    # Hash of series id + vintage anchors the millésime without embedding levels.
    series_anchor = content_sha256(
        {"series_id": series_id, "vintage_sha256": vintage_sha256}
    )

    try:
        row = append_forecast(
            session,
            question_id=question_id,
            forecast_at=f_at,
            data_cutoff=cutoff,
            observation_ids=list(observation_ids or []),
            probability=float(probability),
            interval_low=interval_low,
            interval_high=interval_high,
            data_label=label,
            git_commit=commit,
            cfg_hash=config_hash(),
            p_base=float(p_base),
            baseline_method=baseline_method_stored,
            series_id=series_id,
            vintage_sha256=vintage_sha256,
            observations_content_hash=content_sha256(list(observation_ids or [])),
            seed_hash=seed_hash or series_anchor,
            wave_id=resolved_wave,
            require_clean_tree=require_clean,
            export_head=export_head,
            chain_head_path=chain_head_path,
        )
    except RegistryIntegrityError:
        raise

    session.flush()
    return {
        "ok": True,
        "forecast_id": row.id,
        "question_id": question_id,
        "wave_id": resolved_wave,
        "forecast_at": row.forecast_at.isoformat(),
        "data_cutoff": row.data_cutoff.isoformat(),
        "probability": float(row.probability),
        "p_base": float(row.p_base) if row.p_base is not None else None,
        "baseline_method": row.baseline_method,
        "series_id": row.series_id,
        "vintage_sha256": row.vintage_sha256,
        "data_label": row.data_label,
        "git_commit": row.git_commit,
        "sha256": row.sha256,
        "prev_sha256": row.prev_sha256,
        "note": (
            "TEST freeze — not a production proof row"
            if label == "TEST"
            else "frozen"
        ),
    }


def vintage_sha_from_changes(changes: Sequence[float], *, series_id: str) -> str:
    """Deterministic millésime hash from the change vector (no level reprint)."""
    payload = {"series_id": series_id, "changes": [float(x) for x in changes]}
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
