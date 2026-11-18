"""Freeze deadlines (Riyadh time) loaded from config/freeze_calendar.yaml."""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from data_ia.config import get_settings


class FreezeDeadlineError(ValueError):
    """Raised when a freeze is attempted after the question's deadline."""


def _calendar_path() -> Path:
    settings = get_settings()
    return Path(settings.freeze_calendar_path)


@lru_cache
def load_freeze_calendar(path: str | None = None) -> dict[str, Any]:
    p = Path(path) if path else _calendar_path()
    with open(p, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if "deadlines" not in data:
        raise ValueError(f"freeze calendar missing deadlines: {p}")
    return data


def clear_freeze_calendar_cache() -> None:
    load_freeze_calendar.cache_clear()


def freeze_deadline_for(question_id: str, *, path: str | None = None) -> datetime | None:
    cal = load_freeze_calendar(path)
    raw = (cal.get("deadlines") or {}).get(question_id)
    if raw is None:
        return None
    text = str(raw).replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def baseline_method_for(question_id: str, *, path: str | None = None) -> str:
    cal = load_freeze_calendar(path)
    if question_id in (cal.get("persist_v3_questions") or []):
        return "persist_v3"
    if question_id in (cal.get("frequency_questions") or []):
        return "frequency"
    return "0,5 + justification"


def assert_before_freeze_deadline(
    question_id: str,
    forecast_at: datetime,
    *,
    path: str | None = None,
) -> None:
    deadline = freeze_deadline_for(question_id, path=path)
    if deadline is None:
        return
    if forecast_at.tzinfo is None:
        forecast_at = forecast_at.replace(tzinfo=timezone.utc)
    else:
        forecast_at = forecast_at.astimezone(timezone.utc)
    dl = deadline.astimezone(timezone.utc)
    if forecast_at > dl:
        raise FreezeDeadlineError(
            f"freeze refused: forecast_at {forecast_at.isoformat()} is after "
            f"freeze deadline {dl.isoformat()} for {question_id}"
        )
