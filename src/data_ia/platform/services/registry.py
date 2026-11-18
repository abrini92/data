"""Read forecast_registry rows (no writes)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_ia.db.models import ForecastAnnotation, ForecastRegistry


def _annotation_maps(session: Session) -> dict[int, list[dict[str, Any]]]:
    rows = session.execute(select(ForecastAnnotation)).scalars().all()
    out: dict[int, list[dict[str, Any]]] = {}
    for a in rows:
        out.setdefault(a.forecast_id, []).append(
            {
                "id": a.id,
                "label": a.label,
                "reason": a.reason,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
        )
    return out


def _row_status(row: ForecastRegistry, genesis_id: int | None) -> str:
    if genesis_id is not None and row.id < genesis_id:
        return "legacy"
    if row.question_id == "__registry_chain_genesis__":
        return "genesis"
    if row.prev_sha256 is None and (genesis_id is None or row.id == genesis_id):
        # First chained row may be genesis or first freeze.
        from data_ia.db.models import CHAIN_GENESIS_QUESTION_ID

        if row.question_id == CHAIN_GENESIS_QUESTION_ID:
            return "genesis"
    if row.prev_sha256 is None:
        return "genesis" if genesis_id == row.id else "chain"
    return "chain"


def _serialize_row(
    row: ForecastRegistry,
    *,
    annotations: list[dict[str, Any]],
    genesis_id: int | None,
) -> dict[str, Any]:
    return {
        "id": row.id,
        "question_id": row.question_id,
        "wave_id": row.wave_id,
        "forecast_at": row.forecast_at.isoformat() if row.forecast_at else None,
        "data_cutoff": row.data_cutoff.isoformat() if row.data_cutoff else None,
        "probability": row.probability,
        "interval_low": row.interval_low,
        "interval_high": row.interval_high,
        "p_base": row.p_base,
        "baseline_method": row.baseline_method,
        "data_label": row.data_label,
        "sha256": row.sha256,
        "prev_sha256": row.prev_sha256,
        "git_commit": row.git_commit,
        "config_hash": row.config_hash,
        "series_id": row.series_id,
        "vintage_sha256": row.vintage_sha256,
        "observations_content_hash": row.observations_content_hash,
        "seed_hash": row.seed_hash,
        "status": _row_status(row, genesis_id),
        "annotations": annotations,
    }


def _find_genesis_id(rows: list[ForecastRegistry]) -> int | None:
    from data_ia.db.models import CHAIN_GENESIS_QUESTION_ID

    for row in rows:
        if row.question_id == CHAIN_GENESIS_QUESTION_ID:
            return row.id
    return None


def list_registry_rows(
    session: Session,
    *,
    offset: int = 0,
    limit: int = 100,
) -> dict[str, Any]:
    all_rows = list(
        session.execute(select(ForecastRegistry).order_by(ForecastRegistry.id))
        .scalars()
        .all()
    )
    genesis_id = _find_genesis_id(all_rows)
    ann = _annotation_maps(session)
    total = len(all_rows)
    page = all_rows[offset : offset + limit]
    items = [
        _serialize_row(r, annotations=ann.get(r.id, []), genesis_id=genesis_id)
        for r in page
    ]
    labels = {r.data_label for r in page if r.data_label}
    data_label = _aggregate_label(labels)
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "rows": items,
        "data_label": data_label,
    }


def get_registry_row(session: Session, row_id: int) -> dict[str, Any] | None:
    all_rows = list(
        session.execute(select(ForecastRegistry).order_by(ForecastRegistry.id))
        .scalars()
        .all()
    )
    genesis_id = _find_genesis_id(all_rows)
    row = next((r for r in all_rows if r.id == row_id), None)
    if row is None:
        return None
    ann = _annotation_maps(session)
    payload = _serialize_row(
        row, annotations=ann.get(row.id, []), genesis_id=genesis_id
    )
    payload["data_label"] = row.data_label
    return payload


def _aggregate_label(labels: set[str]) -> str:
    if not labels:
        return "n/a"
    if len(labels) == 1:
        return next(iter(labels))
    if "REAL" in labels and "SYNTHETIC" in labels:
        return "mixed: refused"
    return "mixed: refused" if len(labels) > 1 else next(iter(labels))
