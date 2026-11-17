"""World Bank Indicators API — country SAU, no key."""

from __future__ import annotations

import json
from typing import Any

from data_ia.connectors.base import BaseConnector, CollectPayload
from data_ia.connectors.http_util import get_json

DEFAULT_INDICATOR = "IT.NET.USER.ZS"
BASE = "https://api.worldbank.org/v2"


class WorldBankConnector(BaseConnector):
    source_id = "worldbank"
    name = "World Bank Indicators (SAU)"

    def __init__(self, indicator: str = DEFAULT_INDICATOR) -> None:
        self.indicator = indicator

    def _url(self) -> str:
        return (
            f"{BASE}/country/SAU/indicator/{self.indicator}"
            f"?format=json&per_page=20&date=2015:2026"
        )

    def _parse(self, payload: Any) -> list[dict[str, Any]]:
        if not isinstance(payload, list) or len(payload) < 2:
            return []
        rows = payload[1] or []
        out: list[dict[str, Any]] = []
        for row in rows:
            if row.get("value") is None:
                continue
            out.append(
                {
                    "series": (row.get("indicator") or {}).get("id", self.indicator),
                    "indicator": (row.get("indicator") or {}).get("id", self.indicator),
                    "country": row.get("countryiso3code") or "SAU",
                    "date": str(row.get("date")),
                    "value": float(row["value"]),
                    "unit": row.get("unit") or "percent",
                }
            )
        return out

    def _collect_live(self) -> CollectPayload:
        url = self._url()
        payload, final_url, text = get_json(url)
        self.write_cache(f"worldbank_{self.indicator}.json", text)
        records = self._parse(payload)
        return self._finish(
            url=final_url,
            raw_text=text,
            raw=payload,
            records=records,
            fetch_mode="live",
            ok=bool(records),
            errors=[] if records else ["no_non_null_observations"],
            meta={"indicator": self.indicator, "license": "World Bank open data"},
        )

    def _collect_fixture(self) -> CollectPayload:
        path = self.fixture_path(f"worldbank_{self.indicator}.json")
        if not path.exists():
            path = self.fixture_path("worldbank_IT.NET.USER.ZS.json")
        text = path.read_text(encoding="utf-8")
        payload = json.loads(text)
        records = self._parse(payload)
        return self._finish(
            url=self._url(),
            raw_text=text,
            raw=payload,
            records=records,
            fetch_mode="fixture",
            ok=bool(records),
            meta={"indicator": self.indicator, "fixture": path.name},
        )
