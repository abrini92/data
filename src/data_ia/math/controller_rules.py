"""Controller validation: schema, range, and chi-squared consistency.

Deck slide 8 / BRIEF deliverable 3: Controller applies Python schema and
range rules plus a chi-squared consistency check; rejects/quarantines failures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np
from scipy import stats


@dataclass(frozen=True)
class ExtractionSchema:
    """Allowed shape for an LLM-extracted numeric observation."""

    field_name: str
    value_min: float
    value_max: float
    value_type: str = "float"  # float | probability | int


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    severity: str  # reject | quarantine | warn


@dataclass(frozen=True)
class ValidationResult:
    accepted: bool
    action: str  # accept | reject | quarantine
    issues: tuple[ValidationIssue, ...] = ()
    cleaned_value: float | None = None

    @property
    def ok(self) -> bool:
        return self.accepted


@dataclass
class ExtractedObservation:
    """Candidate extraction before Controller acceptance."""

    source_id: str
    field_name: str
    value: Any
    unit: str | None = None
    raw_text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def validate_schema_and_range(
    obs: ExtractedObservation,
    schema: ExtractionSchema,
) -> ValidationResult:
    """Reject if type/range fail; quarantine if soft anomalies appear."""
    issues: list[ValidationIssue] = []

    if obs.field_name != schema.field_name:
        issues.append(
            ValidationIssue(
                code="schema_field",
                message=f"expected field {schema.field_name!r}, got {obs.field_name!r}",
                severity="reject",
            )
        )
        return ValidationResult(False, "reject", tuple(issues))

    try:
        if schema.value_type == "int":
            value = int(obs.value)
        else:
            value = float(obs.value)
    except (TypeError, ValueError):
        issues.append(
            ValidationIssue(
                code="schema_type",
                message=f"value {obs.value!r} is not {schema.value_type}",
                severity="reject",
            )
        )
        return ValidationResult(False, "reject", tuple(issues))

    if schema.value_type == "probability" and not 0.0 <= value <= 1.0:
        issues.append(
            ValidationIssue(
                code="range_probability",
                message=f"probability {value} outside [0, 1]",
                severity="reject",
            )
        )
        return ValidationResult(False, "reject", tuple(issues))

    if not schema.value_min <= value <= schema.value_max:
        issues.append(
            ValidationIssue(
                code="range_bounds",
                message=(
                    f"value {value} outside [{schema.value_min}, {schema.value_max}]"
                ),
                severity="reject",
            )
        )
        return ValidationResult(False, "reject", tuple(issues))

    # Soft quarantine: exact boundary hits on wide ranges are fine; NaN already
    # caught by float(); flag non-finite explicitly.
    if not np.isfinite(value):
        issues.append(
            ValidationIssue(
                code="non_finite",
                message="value is not finite",
                severity="quarantine",
            )
        )
        return ValidationResult(False, "quarantine", tuple(issues))

    return ValidationResult(True, "accept", tuple(issues), cleaned_value=float(value))


def chi_squared_consistency(
    values: Sequence[float],
    expected: Sequence[float] | None = None,
    *,
    alpha: float = 0.01,
) -> ValidationResult:
    """Chi-squared consistency check across source readings on one node.

    If ``expected`` is omitted, the mean of ``values`` is used as the expected
    level (deck silent; common for same-quantity cross-source check).
    Low counts (<2) are quarantined rather than rejected.
    """
    arr = np.asarray(list(values), dtype=float)
    if arr.size < 2:
        return ValidationResult(
            False,
            "quarantine",
            (
                ValidationIssue(
                    code="chi2_insufficient",
                    message="need at least two observations for chi-squared check",
                    severity="quarantine",
                ),
            ),
        )

    if expected is None:
        mu = float(np.mean(arr))
        exp = np.full_like(arr, mu)
    else:
        exp = np.asarray(list(expected), dtype=float)
        if exp.shape != arr.shape:
            raise ValueError("expected must match values length")

    # Pearson chi-squared with variance floor for continuous proxy bins
    var = float(np.var(arr)) if arr.size > 1 else 1.0
    var = max(var, 1e-6)
    statistic = float(np.sum((arr - exp) ** 2 / var))
    df = max(arr.size - 1, 1)
    p_value = float(1.0 - stats.chi2.cdf(statistic, df))

    if p_value < alpha:
        return ValidationResult(
            False,
            "quarantine",
            (
                ValidationIssue(
                    code="chi2_inconsistent",
                    message=(
                        f"chi-squared inconsistency: stat={statistic:.4f}, "
                        f"df={df}, p={p_value:.4g} < alpha={alpha}"
                    ),
                    severity="quarantine",
                ),
            ),
        )

    return ValidationResult(True, "accept", cleaned_value=float(np.mean(arr)))


def validate_extraction_batch(
    observations: Sequence[ExtractedObservation],
    schemas: Mapping[str, ExtractionSchema],
    *,
    run_chi2: bool = True,
    chi2_alpha: float = 0.01,
) -> dict[str, ValidationResult]:
    """Validate each observation, then optional chi2 across accepted values."""
    results: dict[str, ValidationResult] = {}
    accepted_vals: list[float] = []

    for i, obs in enumerate(observations):
        key = f"{obs.source_id}:{obs.field_name}:{i}"
        schema = schemas.get(obs.field_name)
        if schema is None:
            results[key] = ValidationResult(
                False,
                "reject",
                (
                    ValidationIssue(
                        code="unknown_field",
                        message=f"no schema for field {obs.field_name!r}",
                        severity="reject",
                    ),
                ),
            )
            continue
        result = validate_schema_and_range(obs, schema)
        results[key] = result
        if result.accepted and result.cleaned_value is not None:
            accepted_vals.append(result.cleaned_value)

    if run_chi2 and len(accepted_vals) >= 2:
        chi = chi_squared_consistency(accepted_vals, alpha=chi2_alpha)
        results["__chi2__"] = chi

    return results
