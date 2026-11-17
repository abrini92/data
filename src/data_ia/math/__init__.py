"""Reproducible maths: source reliability, fusion, aggregation, scoring."""

from data_ia.math.aggregation import AggregationResult, evaluate_taxonomy, logit, sigmoid
from data_ia.math.brier import BrierReport, ResolvedForecast, brier_score, evaluate_proof
from data_ia.math.controller_rules import (
    ExtractedObservation,
    ExtractionSchema,
    ValidationResult,
    chi_squared_consistency,
    validate_extraction_batch,
    validate_schema_and_range,
)
from data_ia.math.sources import (
    ClassPrior,
    ErrorObservation,
    FusionResult,
    SourceEstimate,
    SourceReliability,
    estimate_source_reliability,
    fuse_observations,
    precision_weight,
    shrink_toward_prior,
)
from data_ia.math.surprise import SurpriseResult, gaussian_surprise

__all__ = [
    "AggregationResult",
    "BrierReport",
    "ClassPrior",
    "ErrorObservation",
    "ExtractedObservation",
    "ExtractionSchema",
    "FusionResult",
    "ResolvedForecast",
    "SourceEstimate",
    "SourceReliability",
    "SurpriseResult",
    "ValidationResult",
    "brier_score",
    "chi_squared_consistency",
    "estimate_source_reliability",
    "evaluate_proof",
    "evaluate_taxonomy",
    "fuse_observations",
    "gaussian_surprise",
    "logit",
    "precision_weight",
    "shrink_toward_prior",
    "sigmoid",
    "validate_extraction_batch",
    "validate_schema_and_range",
]
