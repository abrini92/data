"""Canonical hashing for the append-only forecast registry."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


# Fields that enter the canonical payload (order matters for stability).
CANONICAL_FIELDS: tuple[str, ...] = (
    "question_id",
    "forecast_at",
    "data_cutoff",
    "git_commit",
    "config_hash",
    "extractor_version",
    "observation_ids",
    "probability",
    "interval_low",
    "interval_high",
    "data_label",
)


def _normalize(value: Any) -> Any:
    if isinstance(value, float):
        # Round-trip through format that matches JSON dumps defaults
        return float(value)
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _normalize(value[k]) for k in sorted(value)}
    return value


def canonical_forecast_payload(fields: Mapping[str, Any]) -> dict[str, Any]:
    """Build the canonical dict used for sha256 (excludes id / sha256)."""
    payload: dict[str, Any] = {}
    for key in CANONICAL_FIELDS:
        if key not in fields:
            raise KeyError(f"missing canonical field: {key}")
        payload[key] = _normalize(fields[key])
    return payload


def canonical_json(fields: Mapping[str, Any]) -> str:
    payload = canonical_forecast_payload(fields)
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def forecast_sha256(fields: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(fields).encode("utf-8")).hexdigest()
