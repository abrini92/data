"""Registry verification — same function as `data-ia verify-registry`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from data_ia.forecast_registry import verify_registry


def verify_registry_report(
    session: Session,
    *,
    chain_head_path: Path | None = None,
) -> dict[str, Any]:
    """Return the live verify report (never stored in the registry)."""
    report = verify_registry(session, chain_head_path=chain_head_path)
    verdict = "OK" if report.get("ok") else "ÉCHEC"
    return {
        **report,
        "verdict": verdict,
        "data_label": _label_from_annotations(report),
    }


def _label_from_annotations(report: dict[str, Any]) -> str:
    # Verification itself is about hashes; label reflects annotated rows if any.
    anns = report.get("annotations") or []
    if any(a.get("label") == "TEST" for a in anns if isinstance(a, dict)):
        return "TEST"
    return "REAL"
