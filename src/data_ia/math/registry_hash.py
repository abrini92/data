"""Canonical hashing for the append-only forecast registry."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence


# Pass-3 / pre-chain schema (production rows before migrate-registry).
LEGACY_CANONICAL_FIELDS: tuple[str, ...] = (
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

# Fields that enter the canonical payload (order matters for stability).
# B3: chain prev_sha256; cover observations content, seed, p_base, series, vintage.
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
    "prev_sha256",
    "p_base",
    "baseline_method",
    "series_id",
    "vintage_sha256",
    "observations_content_hash",
    "seed_hash",
    "wave_id",
)


def _normalize(value: Any) -> Any:
    if isinstance(value, float):
        return float(value)
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _normalize(value[k]) for k in sorted(value)}
    return value


def _payload_for(fields: Mapping[str, Any], keys: Sequence[str]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in keys:
        if key not in fields:
            raise KeyError(f"missing canonical field: {key}")
        payload[key] = _normalize(fields[key])
    return payload


def canonical_forecast_payload(fields: Mapping[str, Any]) -> dict[str, Any]:
    """Build the canonical dict used for sha256 (excludes id / sha256)."""
    return _payload_for(fields, CANONICAL_FIELDS)


def canonical_json(fields: Mapping[str, Any]) -> str:
    payload = canonical_forecast_payload(fields)
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def forecast_sha256(fields: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(fields).encode("utf-8")).hexdigest()


def legacy_canonical_forecast_payload(fields: Mapping[str, Any]) -> dict[str, Any]:
    """Pre-chain (Pass 3) payload — original sha256 of production rows."""
    return _payload_for(fields, LEGACY_CANONICAL_FIELDS)


def legacy_canonical_json(fields: Mapping[str, Any]) -> str:
    payload = legacy_canonical_forecast_payload(fields)
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def legacy_forecast_sha256(fields: Mapping[str, Any]) -> str:
    return hashlib.sha256(legacy_canonical_json(fields).encode("utf-8")).hexdigest()


def content_sha256(payload: Any) -> str:
    """Stable hash of arbitrary JSON-serialisable content (observations, seed)."""
    normalized = _normalize(payload)
    blob = json.dumps(normalized, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
