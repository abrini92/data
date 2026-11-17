"""Controller validation: schema, range, and chi-squared consistency.

Deck slide 8: Controller applies Python schema and range rules plus a
chi-squared consistency check using source reliability (bias, variance).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np
from scipy import stats

from data_ia.math.sources import SourceReliability, fuse_observations


@dataclass(frozen=True)
class ExtractionSchema:
    """Allowed shape for an LLM-extracted numeric observation."""

    field_name: str
    value_min: float
    value_max: float
    value_type: str = "float"  # float | probability | int
    expected_unit: str | None = None


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
    flags: tuple[str, ...] = ()

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
    published_at: str | None = None
    source_passage: str | None = None
    raw_text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def validate_schema_and_range(
    obs: ExtractedObservation,
    schema: ExtractionSchema,
    *,
    require_extraction_fields: bool = False,
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

    if require_extraction_fields:
        if obs.unit is None or str(obs.unit).strip() == "":
            issues.append(
                ValidationIssue(
                    code="missing_unit",
                    message="extraction missing unit",
                    severity="reject",
                )
            )
        if not obs.published_at:
            issues.append(
                ValidationIssue(
                    code="missing_published_at",
                    message="extraction missing published_at / date",
                    severity="reject",
                )
            )
        if not obs.source_passage:
            issues.append(
                ValidationIssue(
                    code="missing_source_passage",
                    message="extraction missing source passage",
                    severity="reject",
                )
            )
        if issues:
            return ValidationResult(False, "reject", tuple(issues))

        if schema.expected_unit is not None:
            got = str(obs.unit).strip().lower()
            exp = str(schema.expected_unit).strip().lower()
            if got != exp:
                issues.append(
                    ValidationIssue(
                        code="unit_mismatch",
                        message=f"unit {obs.unit!r} does not match question unit {schema.expected_unit!r}",
                        severity="reject",
                    )
                )
                return ValidationResult(False, "reject", tuple(issues))

    try:
        if schema.value_type == "int":
            value = int(obs.value)
            value_f = float(value)
        else:
            value_f = float(obs.value)
            value = value_f
    except (TypeError, ValueError):
        issues.append(
            ValidationIssue(
                code="schema_type",
                message=f"value {obs.value!r} is not {schema.value_type}",
                severity="reject",
            )
        )
        return ValidationResult(False, "reject", tuple(issues))

    # Check non-finite BEFORE range so the branch is reachable (NaN/Inf).
    if not np.isfinite(value_f):
        issues.append(
            ValidationIssue(
                code="non_finite",
                message="value is not finite",
                severity="quarantine",
            )
        )
        return ValidationResult(False, "quarantine", tuple(issues))

    if schema.value_type == "probability" and not 0.0 <= value_f <= 1.0:
        issues.append(
            ValidationIssue(
                code="range_probability",
                message=f"probability {value_f} outside [0, 1]",
                severity="reject",
            )
        )
        return ValidationResult(False, "reject", tuple(issues))

    if not schema.value_min <= value_f <= schema.value_max:
        issues.append(
            ValidationIssue(
                code="range_bounds",
                message=(
                    f"value {value_f} outside [{schema.value_min}, {schema.value_max}]"
                ),
                severity="reject",
            )
        )
        return ValidationResult(False, "reject", tuple(issues))

    return ValidationResult(True, "accept", tuple(issues), cleaned_value=float(value_f))


def chi_squared_consistency(
    values: Sequence[float],
    *,
    reliabilities: Sequence[SourceReliability] | None = None,
    biases: Sequence[float] | None = None,
    variances: Sequence[float] | None = None,
    alpha: float = 0.01,
) -> ValidationResult:
    """χ² consistency using source reliability.

    Statistic: Σ_s (z_s - b_s - x̂)² / σ_s² where x̂ is the precision-weighted
    fused value of the debiased readings, df = n - 1.

    A single observation is accepted with a ``single_source`` flag (not
    quarantined).
    """
    arr = np.asarray(list(values), dtype=float)
    if arr.size == 0:
        return ValidationResult(
            False,
            "quarantine",
            (
                ValidationIssue(
                    code="chi2_empty",
                    message="no observations for chi-squared check",
                    severity="quarantine",
                ),
            ),
        )

    if arr.size == 1:
        return ValidationResult(
            True,
            "accept",
            (
                ValidationIssue(
                    code="single_source",
                    message="single observation — chi-squared skipped",
                    severity="warn",
                ),
            ),
            cleaned_value=float(arr[0]),
            flags=("single_source",),
        )

    if reliabilities is not None:
        if len(reliabilities) != arr.size:
            raise ValueError("reliabilities must match values length")
        b = np.asarray([r.bias for r in reliabilities], dtype=float)
        var = np.asarray([max(r.variance, 1e-12) for r in reliabilities], dtype=float)
        readings = {f"s{i}": float(arr[i]) for i in range(arr.size)}
        rel_map = {f"s{i}": reliabilities[i] for i in range(arr.size)}
        fused = fuse_observations(readings, rel_map)
        x_hat = fused.estimate
    else:
        if biases is None:
            b = np.zeros(arr.size, dtype=float)
        else:
            b = np.asarray(list(biases), dtype=float)
            if b.shape != arr.shape:
                raise ValueError("biases must match values length")
        if variances is None:
            # Fallback: equal unit variance (tests / legacy callers).
            var = np.ones(arr.size, dtype=float)
        else:
            var = np.asarray(list(variances), dtype=float)
            if var.shape != arr.shape:
                raise ValueError("variances must match values length")
            var = np.maximum(var, 1e-12)
        # Precision-weighted fused value of debiased readings.
        tau = 1.0 / var
        debiased = arr - b
        x_hat = float(np.sum(tau * debiased) / np.sum(tau))

    statistic = float(np.sum((arr - b - x_hat) ** 2 / var))
    df = int(arr.size - 1)
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

    return ValidationResult(True, "accept", cleaned_value=float(x_hat))


def validate_extraction_batch(
    observations: Sequence[ExtractedObservation],
    schemas: Mapping[str, ExtractionSchema],
    *,
    run_chi2: bool = True,
    chi2_alpha: float = 0.01,
    reliabilities: Mapping[str, SourceReliability] | None = None,
) -> dict[str, ValidationResult]:
    """Validate each observation, then optional chi2 across accepted values."""
    results: dict[str, ValidationResult] = {}
    accepted_vals: list[float] = []
    accepted_rels: list[SourceReliability] = []

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
            if reliabilities and obs.source_id in reliabilities:
                accepted_rels.append(reliabilities[obs.source_id])

    if run_chi2 and accepted_vals:
        if len(accepted_rels) == len(accepted_vals) and accepted_rels:
            chi = chi_squared_consistency(
                accepted_vals, reliabilities=accepted_rels, alpha=chi2_alpha
            )
        else:
            chi = chi_squared_consistency(accepted_vals, alpha=chi2_alpha)
        results["__chi2__"] = chi

    return results
