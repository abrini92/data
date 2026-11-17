"""IMF SDMX 3.0 data API — WEO KSA macro series."""

from __future__ import annotations

import json
from typing import Any

from data_ia.connectors.base import BaseConnector, CollectPayload
from data_ia.connectors.http_util import get_json

DEFAULT_KEY = "SAU.NGDP_RPCH.A"
BASE = "https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.RES/WEO/+"


class IMFConnector(BaseConnector):
    source_id = "imf"
    name = "IMF SDMX 3.0 WEO (SAU)"

    def __init__(self, series_key: str = DEFAULT_KEY) -> None:
        self.series_key = series_key

    def _url(self) -> str:
        return f"{BASE}/{self.series_key}?startPeriod=2018&endPeriod=2026&format=jsondata"

    def _parse(self, payload: Any) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        if isinstance(payload, dict) and "series" in payload:
            for row in payload["series"]:
                records.append(
                    {
                        "series": row.get("indicator", "NGDP_RPCH"),
                        "indicator": row.get("indicator", "NGDP_RPCH"),
                        "country": row.get("country", "SAU"),
                        "date": str(row.get("date")),
                        "value": float(row["value"]),
                        "unit": row.get("unit", "percent"),
                    }
                )
            return records
        try:
            data_sets = ((payload or {}).get("data") or {}).get("dataSets") or []
            if not data_sets:
                return records
            series_block = data_sets[0].get("series") or {}
            if isinstance(series_block, dict):
                for _, cell in list(series_block.items())[:20]:
                    if isinstance(cell, dict) and "observations" in cell:
                        for period, vals in cell["observations"].items():
                            if vals and vals[0] is not None:
                                records.append(
                                    {
                                        "series": "NGDP_RPCH",
                                        "indicator": "NGDP_RPCH",
                                        "country": "SAU",
                                        "date": str(period),
                                        "value": float(vals[0]),
                                        "unit": "percent",
                                    }
                                )
        except Exception:
            return records
        return records

    def _collect_live(self) -> CollectPayload:
        url = self._url()
        payload, final_url, text = get_json(
            url,
            headers={
                "Accept": "application/vnd.sdmx.data+json;version=2.0.0,application/json"
            },
        )
        self.write_cache("imf_weo_sau.json", text)
        records = self._parse(payload)
        return self._finish(
            url=final_url,
            raw_text=text,
            raw=payload,
            records=records,
            fetch_mode="live",
            ok=True,
            meta={"series_key": self.series_key, "license": "IMF data terms"},
        )

    def _collect_fixture(self) -> CollectPayload:
        path = self.fixture_path("imf_weo_sau.json")
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
            meta={"series_key": self.series_key, "fixture": path.name},
        )
