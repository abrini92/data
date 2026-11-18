"""JSON response envelope fields required by BRIEF-5 §4.4."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

RIYADH = ZoneInfo("Asia/Riyadh")


def generated_at_riyadh() -> str:
    """ISO 8601 timestamp with +03:00 (Asia/Riyadh)."""
    return datetime.now(RIYADH).isoformat()


def envelope(
    payload: dict[str, Any],
    *,
    env: str,
    data_label: str,
    masked: list[str] | None = None,
) -> dict[str, Any]:
    out = {
        "data_label": data_label,
        "env": env,
        "generated_at": generated_at_riyadh(),
        **payload,
    }
    if masked:
        out["masked"] = list(masked)
    return out
