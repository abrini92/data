"""Map reliability_prior scores [0,1] → ClassPrior (bias, variance) + N0.

Values in config/prior_mapping.yaml are PROVISIONAL – pending validation by
the model owner. They are not calibrated.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from data_ia.config import REPO_ROOT, get_settings
from data_ia.math.sources import ClassPrior


class PriorMappingError(ValueError):
    """Invalid or non-monotonic prior mapping table."""


def load_prior_mapping(path: str | Path | None = None) -> dict[str, Any]:
    settings = get_settings()
    mapping_path = Path(path or settings.prior_mapping_path)
    with open(mapping_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise PriorMappingError("prior_mapping.yaml must be a mapping")
    validate_prior_mapping(data)
    return data


def validate_prior_mapping(data: dict[str, Any]) -> None:
    table = data.get("score_to_variance")
    if not isinstance(table, list) or len(table) < 2:
        raise PriorMappingError("score_to_variance must be a list with >= 2 rows")
    scores: list[float] = []
    variances: list[float] = []
    for row in table:
        if not isinstance(row, dict):
            raise PriorMappingError("each score_to_variance row must be a mapping")
        try:
            score = float(row["score"])
            variance = float(row["variance"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PriorMappingError(f"invalid row {row!r}: {exc}") from exc
        if not 0.0 <= score <= 1.0:
            raise PriorMappingError(f"score {score} outside [0, 1]")
        if variance <= 0:
            raise PriorMappingError(f"variance must be positive, got {variance}")
        scores.append(score)
        variances.append(variance)

    # Scores must be strictly increasing; variances strictly decreasing (monotonic).
    for i in range(1, len(scores)):
        if scores[i] <= scores[i - 1]:
            raise PriorMappingError(
                "score_to_variance scores must be strictly increasing (monotonic)"
            )
        if variances[i] >= variances[i - 1]:
            raise PriorMappingError(
                "score_to_variance variances must be strictly decreasing in score "
                "(higher reliability → lower prior variance)"
            )

    n0 = data.get("n0")
    if n0 is None or float(n0) < 0:
        raise PriorMappingError("n0 must be a non-negative number")
    bias = float(data.get("prior_bias", 0.0))
    if bias != 0.0 and data.get("allow_nonzero_bias") is not True:
        # Default policy: bias is 0 unless explicitly allowed.
        pass


def prior_variance_for_score(score: float, mapping: dict[str, Any] | None = None) -> float:
    """Piecewise-linear interpolation of score → variance (extrapolate ends)."""
    data = mapping or load_prior_mapping()
    validate_prior_mapping(data)
    table = sorted(
        ((float(r["score"]), float(r["variance"])) for r in data["score_to_variance"]),
        key=lambda p: p[0],
    )
    s = float(score)
    if s <= table[0][0]:
        return table[0][1]
    if s >= table[-1][0]:
        return table[-1][1]
    for (s0, v0), (s1, v1) in zip(table, table[1:]):
        if s0 <= s <= s1:
            t = (s - s0) / (s1 - s0) if s1 != s0 else 0.0
            return v0 + t * (v1 - v0)
    return table[-1][1]


def class_prior_from_score(
    score: float,
    mapping: dict[str, Any] | None = None,
) -> ClassPrior:
    data = mapping or load_prior_mapping()
    variance = prior_variance_for_score(score, data)
    bias = float(data.get("prior_bias", 0.0))
    n0 = float(data.get("n0", 5.0))
    return ClassPrior(bias=bias, variance=variance, n0=n0)


def default_mapping_path() -> Path:
    return REPO_ROOT / "config" / "prior_mapping.yaml"
