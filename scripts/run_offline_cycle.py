#!/usr/bin/env python
"""Convenience wrapper: python scripts/run_offline_cycle.py"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from data_ia.agents.pipeline import run_offline_cycle  # noqa: E402


def main() -> int:
    result = run_offline_cycle(persist=True)
    print(
        json.dumps(
            {
                "db_mode": result.get("db_mode"),
                "final_probability": result.get("final_probability"),
                "disclaimer": result.get("disclaimer"),
            },
            indent=2,
        )
    )
    return 0 if result.get("final_probability") is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
