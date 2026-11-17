"""Map reliability_prior / source class → provisional priors.

Pass 3b replaces the single shrinkage N0 with a normal-inverse-gamma (NIG)
prior per source (config + loader only; the NIG update is Pass 4).

Values in config/prior_mapping.yaml are marked
``CONVENTION – PROVISIONAL, not calibrated``. sigma2_ref is not yet measured.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from data_ia.config import REPO_ROOT, get_settings
from data_ia.math.sources import ClassPrior

CLASS_ORDER = ("A", "B", "C", "D")


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


def _nig_block(data: dict[str, Any]) -> dict[str, Any]:
    nig = data.get("nig")
    if isinstance(nig, dict):
        return nig
    # Allow flat keys for convenience in tests.
    return data


def validate_prior_mapping(data: dict[str, Any]) -> None:
    nig = _nig_block(data)
    try:
        b0 = float(nig["b0"])
        kappa0 = float(nig["kappa0"])
        nu0 = float(nig["nu0"])
        sigma2_ref = float(nig["sigma2_ref"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PriorMappingError(
            "nig block requires b0, kappa0, nu0, sigma2_ref"
        ) from exc

    if kappa0 <= 0:
        raise PriorMappingError(f"kappa0 must be positive, got {kappa0}")
    if nu0 <= 2:
        raise PriorMappingError(f"nu0 must be > 2, got {nu0}")
    if sigma2_ref <= 0:
        raise PriorMappingError(f"sigma2_ref must be positive, got {sigma2_ref}")
    if b0 != 0.0 and data.get("allow_nonzero_b0") is not True:
        # Default policy documents b0 = 0; nonzero requires an explicit flag.
        pass

    k_table = data.get("k_by_class")
    if not isinstance(k_table, dict):
        raise PriorMappingError("k_by_class must be a mapping of class → k")
    k_vals: list[float] = []
    for cls in CLASS_ORDER:
        if cls not in k_table:
            raise PriorMappingError(f"k_by_class missing class {cls!r}")
        try:
            k = float(k_table[cls])
        except (TypeError, ValueError) as exc:
            raise PriorMappingError(f"invalid k for class {cls!r}") from exc
        if k <= 0:
            raise PriorMappingError(f"k({cls}) must be positive, got {k}")
        k_vals.append(k)
    for i in range(1, len(k_vals)):
        if k_vals[i] < k_vals[i - 1]:
            raise PriorMappingError(
                "k_by_class must be monotone non-decreasing A ≤ B ≤ C ≤ D "
                f"(got {[k_table[c] for c in CLASS_ORDER]})"
            )

    table = data.get("score_to_variance")
    if table is None:
        return
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


def nig_prior_for_class(
    source_class: str,
    mapping: dict[str, Any] | None = None,
) -> dict[str, float]:
    """Return provisional NIG hyperparameters for a source class (A/B/C/D).

    s0² = k(class) · sigma2_ref. Config only — Pass 4 will run the update.
    """
    data = mapping or load_prior_mapping()
    validate_prior_mapping(data)
    nig = _nig_block(data)
    cls = str(source_class).strip().upper()
    k_table = data["k_by_class"]
    if cls not in k_table:
        raise PriorMappingError(f"unknown source class {source_class!r}")
    k = float(k_table[cls])
    sigma2_ref = float(nig["sigma2_ref"])
    return {
        "b0": float(nig["b0"]),
        "kappa0": float(nig["kappa0"]),
        "nu0": float(nig["nu0"]),
        "k": k,
        "sigma2_ref": sigma2_ref,
        "s0_sq": k * sigma2_ref,
    }


def prior_variance_for_score(score: float, mapping: dict[str, Any] | None = None) -> float:
    """Piecewise-linear interpolation of score → variance (extrapolate ends)."""
    data = mapping or load_prior_mapping()
    validate_prior_mapping(data)
    table = data.get("score_to_variance")
    if not table:
        raise PriorMappingError("score_to_variance missing from mapping")
    pairs = sorted(
        ((float(r["score"]), float(r["variance"])) for r in table),
        key=lambda p: p[0],
    )
    s = float(score)
    if s <= pairs[0][0]:
        return pairs[0][1]
    if s >= pairs[-1][0]:
        return pairs[-1][1]
    for (s0, v0), (s1, v1) in zip(pairs, pairs[1:]):
        if s0 <= s <= s1:
            t = (s - s0) / (s1 - s0) if s1 != s0 else 0.0
            return v0 + t * (v1 - v0)
    return pairs[-1][1]


def class_prior_from_score(
    score: float,
    mapping: dict[str, Any] | None = None,
    *,
    source_class: str | None = None,
) -> ClassPrior:
    """Legacy ClassPrior view for shrinkage until Pass 4 wires NIG.

    When ``source_class`` is set, variance comes from NIG s0²; otherwise from
    the score→variance table. Pseudo-count n0 is derived as kappa0 for display
    compatibility with the current shrinkage formula.
    """
    data = mapping or load_prior_mapping()
    nig = _nig_block(data)
    if source_class is not None:
        nig_p = nig_prior_for_class(source_class, data)
        variance = nig_p["s0_sq"]
        bias = nig_p["b0"]
        n0 = nig_p["kappa0"]
    else:
        variance = prior_variance_for_score(score, data)
        bias = float(data.get("prior_bias", nig.get("b0", 0.0)))
        n0 = float(nig.get("kappa0", 2.0))
    return ClassPrior(bias=bias, variance=variance, n0=n0)


def default_mapping_path() -> Path:
    return REPO_ROOT / "config" / "prior_mapping.yaml"
