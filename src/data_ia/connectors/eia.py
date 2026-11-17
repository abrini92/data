"""EIA API — KSA energy series (free key, public domain)."""

from __future__ import annotations

import json
from typing import Any

from data_ia.config import get_settings
from data_ia.connectors.base import BaseConnector, CollectPayload
from data_ia.connectors.http_util import get_json

BASE = "https://api.eia.gov/v2"
SERIES_ID = "INTL.53-1-SAU-TBPD.M"


class EIAConnector(BaseConnector):
    source_id = "eia"
    name = "EIA Open Data (KSA energy)"

    def _parse(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, dict) and "series" in payload:
            return [
                {
                    "series": r.get("indicator", "energy"),
                    "indicator": r.get("indicator", "energy"),
                    "country": "SAU",
                    "date": str(r.get("date")),
                    "value": float(r["value"]),
                    "unit": r.get("unit", ""),
                }
                for r in payload["series"]
                if r.get("value") is not None
            ]
        rows = ((payload or {}).get("response") or {}).get("data") or []
        out: list[dict[str, Any]] = []
        for row in rows:
            if row.get("value") is None:
                continue
            out.append(
                {
                    "series": SERIES_ID,
                    "indicator": SERIES_ID,
                    "country": "SAU",
                    "date": str(row.get("period")),
                    "value": float(row["value"]),
                    "unit": row.get("unit") or "thousand barrels per day",
                }
            )
        return out

    def _collect_live(self) -> CollectPayload:
        settings = get_settings()
        key = (settings.eia_api_key or "").strip()
        if not key:
            return self._finish(
                url=None,
                raw_text="",
                raw=None,
                records=[],
                fetch_mode="skipped",
                ok=False,
                skipped_reason="EIA_API_KEY missing — skipped gracefully",
                meta={"skipped": True, "signup": "https://www.eia.gov/opendata/"},
            )
        url = f"{BASE}/seriesid/{SERIES_ID}"
        payload, final_url, text = get_json(url, params={"api_key": key})
        safe_url = str(final_url).split("api_key=")[0] + "api_key=REDACTED"
        self.write_cache("eia_sau.json", text)
        return self._finish(
            url=safe_url,
            raw_text=text,
            raw=payload,
            records=self._parse(payload),
            fetch_mode="live",
            ok=True,
            meta={"license": "U.S. EIA public domain", "series_id": SERIES_ID},
        )

    def _collect_fixture(self) -> CollectPayload:
        path = self.fixture_path("eia_sau.json")
        text = path.read_text(encoding="utf-8")
        payload = json.loads(text)
        return self._finish(
            url=f"{BASE}/seriesid/{SERIES_ID}",
            raw_text=text,
            raw=payload,
            records=self._parse(payload),
            fetch_mode="fixture",
            ok=True,
            meta={"fixture": path.name},
        )
