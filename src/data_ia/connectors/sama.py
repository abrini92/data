"""Optional SAMA API — skip live (no scrape); fixture for offline tests."""

from __future__ import annotations

import json
from typing import Any

from data_ia.connectors.base import BaseConnector, CollectPayload

BASE = "https://www.sama.gov.sa"


class SAMAConnector(BaseConnector):
    source_id = "sama"
    name = "SAMA (optional)"

    def _parse(self, payload: Any) -> list[dict[str, Any]]:
        return [
            {
                "series": r.get("indicator", "sama"),
                "indicator": r.get("indicator", "sama"),
                "country": "SAU",
                "date": str(r.get("date")),
                "value": float(r["value"]),
                "unit": r.get("unit", ""),
            }
            for r in (payload.get("series") or [])
            if r.get("value") is not None
        ]

    def _collect_live(self) -> CollectPayload:
        return self._finish(
            url=BASE,
            raw_text="",
            raw=None,
            records=[],
            fetch_mode="skipped",
            ok=False,
            skipped_reason="SAMA JSON API not confirmed reachable without scraping — skipped",
            meta={"optional": True, "no_scrape": True},
        )

    def _collect_fixture(self) -> CollectPayload:
        path = self.fixture_path("sama_sau.json")
        text = path.read_text(encoding="utf-8")
        payload = json.loads(text)
        records = self._parse(payload)
        return self._finish(
            url=BASE,
            raw_text=text,
            raw=payload,
            records=records,
            fetch_mode="fixture",
            ok=bool(records),
            meta={"fixture": path.name, "optional": True},
        )
