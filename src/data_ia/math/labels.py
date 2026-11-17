"""REAL | SYNTHETIC data labels — refuse mixed scoring/fusion batches."""

from __future__ import annotations

from typing import Iterable, Sequence

REAL = "REAL"
SYNTHETIC = "SYNTHETIC"
ALLOWED = frozenset({REAL, SYNTHETIC})


class MixedLabelError(ValueError):
    """Raised when a batch mixes REAL and SYNTHETIC labels."""


def normalize_label(label: str | None, *, default: str = SYNTHETIC) -> str:
    if label is None or str(label).strip() == "":
        return default
    text = str(label).strip().upper()
    if text in ALLOWED:
        return text
    # Historical ILLUSTRATIVE/SYNTHETIC → SYNTHETIC
    if "SYNTHETIC" in text or "ILLUSTRATIVE" in text:
        return SYNTHETIC
    raise ValueError(f"unknown data_label {label!r}; expected REAL or SYNTHETIC")


def assert_homogeneous_labels(
    labels: Sequence[str] | Iterable[str],
    *,
    context: str = "batch",
) -> str:
    """Return the single label if homogeneous; raise MixedLabelError otherwise."""
    norms = [normalize_label(lab) for lab in labels]
    if not norms:
        raise ValueError(f"{context}: empty label set")
    unique = set(norms)
    if len(unique) > 1:
        raise MixedLabelError(
            f"{context}: refusing mixed data_label values {sorted(unique)}"
        )
    return next(iter(unique))
