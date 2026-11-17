"""UN Comtrade public preview API — KSA trade flows (no key, limited)."""

from __future__ import annotations

import json
from typing import Any

from data_ia.connectors.base import BaseConnector, CollectPayload
from data_ia.connectors.http_util import get_json

BASE = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"


class ComtradeConnector(BaseConnector):
    source_id = "comtrade"
    name = "UN Comtrade public preview (SAU)"

    def _url(self) -> str:
        return f"{BASE}?reporterCode=682&period=2023&partnerCode=0&cmdCode=TOTAL&flowCode=M"

    def _parse(self, payload: Any) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        if isinstance(payload, dict) and "series" in payload:
            for row in payload["series"]:
                records.append(
                    {
                        "series": row.get("indicator", "import_value"),
                        "indicator": row.get("indicator", "import_value"),
                        "country": "SAU",
                        "date": str(row.get("date")),
                        "value": float(row["value"]),
                        "unit": row.get("unit", "USD"),
                    }
                )
            return records
        data = []
        if isinstance(payload, dict):
            data = payload.get("data") or payload.get("dataset") or []
        if isinstance(payload, list):
            data = payload
        for row in data[:50]:
            val = row.get("primaryValue") or row.get("tradeValue") or row.get("value")
            if val is None:
                continue
            records.append(
                {
                    "series": "trade_value",
                    "indicator": "trade_value",
                    "country": "SAU",
                    "date": str(row.get("period") or row.get("refYear") or ""),
                    "value": float(val),
                    "unit": "USD",
                    "flow": row.get("flowCode") or row.get("flowDesc"),
                }
            )
        return records

    def _collect_live(self) -> CollectPayload:
        url = self._url()
        payload, final_url, text = get_json(url)
        self.write_cache("comtrade_sau.json", text)
        records = self._parse(payload)
        return self._finish(
            url=final_url,
            raw_text=text,
            raw=payload,
            records=records,
            fetch_mode="live",
            ok=True,
            meta={"license": "UN Comtrade public preview (rate-limited)"},
        )

    def _collect_fixture(self) -> CollectPayload:
        path = self.fixture_path("comtrade_sau.json")
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
            meta={"fixture": path.name},
        )
