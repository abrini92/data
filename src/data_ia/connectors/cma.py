"""CMA OpenDataAPIs — funds, licences, rating agencies (no key)."""

from __future__ import annotations

import json
from typing import Any

from data_ia.connectors.base import BaseConnector, CollectPayload
from data_ia.connectors.http_util import get_json

BASE = "https://opendataapi.cma.gov.sa"
ENDPOINTS = {
    "public_funds": "/api/PublicFunds/GetAllPublicFunds",
    "private_funds": "/api/PrivateFunds/GetAllPrivateFunds",
    "licenses": "/api/Licenses/GetAllOrganizations",
    "rating_agencies": "/api/CRACompanies/GetAllCRACompanies",
}


class CMAConnector(BaseConnector):
    source_id = "cma"
    name = "CMA OpenDataAPIs"

    def _url(self) -> str:
        return f"{BASE}{ENDPOINTS['public_funds']}?lang=en"

    def _parse(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, dict) and "series" in payload:
            return [
                {
                    "series": r.get("indicator", "cma"),
                    "indicator": r.get("indicator", "cma"),
                    "country": "SAU",
                    "date": str(r.get("date")),
                    "value": float(r["value"]),
                    "unit": r.get("unit", "count"),
                }
                for r in payload["series"]
                if r.get("value") is not None
            ]
        records: list[dict[str, Any]] = []
        if not isinstance(payload, dict):
            return records
        for label, block in payload.items():
            rows = block if isinstance(block, list) else []
            if isinstance(block, dict):
                for key in ("data", "result", "items", "value"):
                    if isinstance(block.get(key), list):
                        rows = block[key]
                        break
            records.append(
                {
                    "series": f"cma_{label}_count",
                    "indicator": f"cma_{label}_count",
                    "country": "SAU",
                    "date": "",
                    "value": float(len(rows)),
                    "unit": "count",
                }
            )
        return records

    def _collect_live(self) -> CollectPayload:
        bundled: dict[str, Any] = {}
        last_url = self._url()
        for label, path in ENDPOINTS.items():
            url = f"{BASE}{path}?lang=en"
            payload, final_url, _text = get_json(url)
            bundled[label] = payload
            last_url = final_url
        text = self.dumps(bundled)
        self.write_cache("cma.json", text)
        records = self._parse(bundled)
        return self._finish(
            url=last_url,
            raw_text=text,
            raw=bundled,
            records=records,
            fetch_mode="live",
            ok=bool(records),
            meta={"license": "CMA open data terms", "swagger": f"{BASE}/swagger/index.html"},
        )

    def _collect_fixture(self) -> CollectPayload:
        path = self.fixture_path("cma_sau.json")
        text = path.read_text(encoding="utf-8")
        payload = json.loads(text)
        return self._finish(
            url=self._url(),
            raw_text=text,
            raw=payload,
            records=self._parse(payload),
            fetch_mode="fixture",
            ok=True,
            meta={"fixture": path.name, "illustrative": True},
        )
