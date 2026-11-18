"""Pair registry forecasts with resolved outcomes (B1 / B2 / E).

Rules:
- Match by wave_id + question_id when available, else question_id.
- One forecast per question: last frozen with forecast_at <= freeze deadline
  (and strictly before resolution).
- Reject forecasts written at/after resolution or after the freeze deadline.
- Label comes from the *issue* (resolved outcome), not the forecast row.
- Naive base uses only outcomes resolved strictly before data_cutoff,
  excluding the question itself; prefer stored p_base from the registry.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Iterable, Sequence

from data_ia.freeze_calendar import freeze_deadline_for
from data_ia.math.brier import ResolvedForecast, class_base_rate
from data_ia.math.labels import MixedLabelError, assert_homogeneous_labels, normalize_label


def _as_dt(value: datetime | date | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    else:
        text = str(value).replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            d = date.fromisoformat(text[:10])
            dt = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _issue_label(item: dict[str, Any]) -> str:
    raw = item.get("data_label") or item.get("label") or "SYNTHETIC"
    # normalize_label accepts REAL / SYNTHETIC; strip ILLUSTRATIVE/ prefix noise
    try:
        return normalize_label(raw)
    except ValueError:
        upper = str(raw).upper()
        if "REAL" in upper and "SYNTHETIC" not in upper:
            return "REAL"
        return "SYNTHETIC"


def select_eligible_forecasts(
    registry_rows: Sequence[Any],
    outcomes_by_id: dict[str, dict[str, Any]],
) -> tuple[list[Any], list[dict[str, Any]]]:
    """Return (eligible_rows, rejections) — at most one row per question_id."""
    rejections: list[dict[str, Any]] = []
    by_q: dict[str, list[Any]] = {}
    for row in registry_rows:
        by_q.setdefault(row.question_id, []).append(row)

    chosen: list[Any] = []
    for qid, rows in by_q.items():
        outcome = outcomes_by_id.get(qid)
        deadline = freeze_deadline_for(qid)
        resolved_on = _as_dt(outcome.get("resolved_on")) if outcome else None

        ranked = sorted(rows, key=lambda r: (_as_dt(r.forecast_at) or datetime.min.replace(tzinfo=timezone.utc), r.id))
        pick = None
        for row in ranked:
            fat = _as_dt(row.forecast_at)
            if fat is None:
                rejections.append(
                    {"forecast_id": row.id, "question_id": qid, "reason": "missing_forecast_at"}
                )
                continue
            if deadline is not None and fat > deadline.astimezone(timezone.utc):
                rejections.append(
                    {
                        "forecast_id": row.id,
                        "question_id": qid,
                        "reason": "after_freeze_deadline",
                    }
                )
                continue
            if resolved_on is not None and fat >= resolved_on:
                rejections.append(
                    {
                        "forecast_id": row.id,
                        "question_id": qid,
                        "reason": "forecast_at_on_or_after_resolution",
                    }
                )
                continue
            pick = row  # last eligible chronologically
        if pick is not None:
            chosen.append(pick)
        elif outcome is not None and qid in by_q:
            # Had rows but none eligible → explicit rejection for scoring
            rejections.append(
                {"forecast_id": None, "question_id": qid, "reason": "no_eligible_forecast"}
            )
    return chosen, rejections


def prior_outcomes_before_cutoff(
    outcomes: Iterable[dict[str, Any]],
    *,
    question_id: str,
    data_cutoff: datetime | date | str,
    question_class: str | None,
) -> list[int]:
    """Issues resolved strictly before data_cutoff, excluding the question itself."""
    cutoff = _as_dt(data_cutoff)
    if cutoff is None:
        return []
    out: list[int] = []
    for item in outcomes:
        if item.get("id") == question_id:
            continue
        if question_class is not None:
            cls = item.get("question_class") or "default"
            if cls != question_class:
                continue
        resolved_on = _as_dt(item.get("resolved_on"))
        if resolved_on is None or resolved_on >= cutoff:
            continue
        out.append(int(item["outcome"]))
    return out


def match_registry_to_resolved(
    registry_rows: Sequence[Any],
    outcomes_by_id: dict[str, dict[str, Any]],
) -> tuple[list[ResolvedForecast], dict[str, Any]]:
    """Build ResolvedForecast list under B1/B2 rules; report rejections."""
    eligible, rejections = select_eligible_forecasts(registry_rows, outcomes_by_id)
    forecasts: list[ResolvedForecast] = []
    skipped_unresolved = 0

    all_outcomes = list(outcomes_by_id.values())

    for row in eligible:
        outcome_item = outcomes_by_id.get(row.question_id)
        if outcome_item is None:
            skipped_unresolved += 1
            continue

        # Wave match when both sides carry a wave id
        row_wave = getattr(row, "wave_id", None)
        issue_wave = outcome_item.get("wave_id")
        if row_wave and issue_wave and str(row_wave) != str(issue_wave):
            rejections.append(
                {
                    "forecast_id": row.id,
                    "question_id": row.question_id,
                    "reason": "wave_id_mismatch",
                }
            )
            continue

        issue_label = _issue_label(outcome_item)
        forecast_label = normalize_label(row.data_label) if row.data_label else issue_label
        # Mixed forecast/issue labels → refuse the pair
        try:
            assert_homogeneous_labels([forecast_label, issue_label], context="brier_pair")
        except (MixedLabelError, ValueError):
            rejections.append(
                {
                    "forecast_id": row.id,
                    "question_id": row.question_id,
                    "reason": "mixed_forecast_issue_label",
                }
            )
            continue

        cls = outcome_item.get("question_class") or "default"
        stored_base = getattr(row, "p_base", None)
        if stored_base is not None:
            base = float(stored_base)
        else:
            priors = prior_outcomes_before_cutoff(
                all_outcomes,
                question_id=row.question_id,
                data_cutoff=row.data_cutoff,
                question_class=cls,
            )
            base = class_base_rate(priors, default=0.5)

        forecasts.append(
            ResolvedForecast(
                question_id=row.question_id,
                probability=float(row.probability),
                outcome=int(outcome_item["outcome"]),
                label=issue_label,
                baseline_probability=float(base),
                forecast_id=row.id,
                question_class=cls,
            )
        )

    meta = {
        "matched": len(forecasts),
        "rejected": rejections,
        "n_eligible_rows": len(eligible),
        "skipped_unresolved": skipped_unresolved,
        "n_questions": len({f.question_id for f in forecasts}),
    }
    return forecasts, meta
