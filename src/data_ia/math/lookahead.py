"""No look-ahead rules: observations and error history must predate the forecast."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Iterable, Sequence


class LookAheadError(ValueError):
    """Raised when an observation or resolution would leak future information."""


def _as_aware(dt: datetime | date | str | None) -> datetime | None:
    if dt is None:
        return None
    if isinstance(dt, str):
        text = dt.replace("Z", "+00:00")
        parsed: datetime | date
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            parsed = date.fromisoformat(text)
        dt = parsed
    if isinstance(dt, date) and not isinstance(dt, datetime):
        dt = datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def assert_cutoff_ordering(
    *,
    published_at: datetime | date | str | None,
    data_cutoff: datetime | date | str,
    forecast_at: datetime | date | str,
) -> None:
    """Enforce published_at <= data_cutoff <= forecast_at."""
    pub = _as_aware(published_at)
    cutoff = _as_aware(data_cutoff)
    forecast = _as_aware(forecast_at)
    if cutoff is None or forecast is None:
        raise LookAheadError("data_cutoff and forecast_at are required")
    if cutoff > forecast:
        raise LookAheadError(
            f"data_cutoff {cutoff.isoformat()} must be <= forecast_at {forecast.isoformat()}"
        )
    if pub is None:
        raise LookAheadError("observation missing published_at")
    if pub > cutoff:
        raise LookAheadError(
            f"published_at {pub.isoformat()} is after data_cutoff {cutoff.isoformat()}"
        )


def filter_observations_no_lookahead(
    observations: Sequence[dict[str, Any]],
    *,
    data_cutoff: datetime | date | str,
    forecast_at: datetime | date | str,
    refuse: bool = True,
) -> list[dict[str, Any]]:
    """Return observations that satisfy published_at <= cutoff <= forecast_at.

    If ``refuse`` is True (default), raise LookAheadError on any violation.
    """
    kept: list[dict[str, Any]] = []
    for obs in observations:
        # B5: never fall back to collected_at — missing published_at is a hard refuse.
        pub = obs.get("published_at")
        try:
            assert_cutoff_ordering(
                published_at=pub,
                data_cutoff=data_cutoff,
                forecast_at=forecast_at,
            )
        except LookAheadError:
            if refuse:
                raise
            continue
        kept.append(obs)
    return kept


def filter_resolved_before(
    resolved: Iterable[dict[str, Any]],
    forecast_at: datetime | date | str,
) -> list[dict[str, Any]]:
    """Keep resolved questions with resolved_on strictly before forecast_at."""
    forecast = _as_aware(forecast_at)
    if forecast is None:
        raise LookAheadError("forecast_at is required")
    out: list[dict[str, Any]] = []
    for item in resolved:
        resolved_on = item.get("resolved_on")
        if resolved_on is None:
            continue
        ts = _as_aware(resolved_on)
        if ts is None:
            continue
        if ts < forecast:
            out.append(item)
    return out


def assert_resolution_before_forecast(
    resolved_on: datetime | date | str | None,
    forecast_at: datetime | date | str,
) -> None:
    forecast = _as_aware(forecast_at)
    ts = _as_aware(resolved_on)
    if forecast is None:
        raise LookAheadError("forecast_at is required")
    if ts is None:
        raise LookAheadError("resolved_on is required for source-error stats")
    if ts >= forecast:
        raise LookAheadError(
            f"resolved_on {ts.isoformat()} must be before forecast_at {forecast.isoformat()}"
        )
