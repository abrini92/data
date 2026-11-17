"""GASTAT open statistics — try public cards; skip gracefully if auth required."""

from __future__ import annotations

import json
from typing import Any

from data_ia.config import get_settings
from data_ia.connectors.base import BaseConnector, CollectPayload
from data_ia.connectors.http_util import get_json

CARDS_URL = "https://database.stats.gov.sa/gastatapi/portal/api/v1/indicators/cardsinfo"
PORTAL = "https://dp.stats.gov.sa/opendata"


class GastatConnector(BaseConnector):
    source_id = "gastat"
    name = "GASTAT (stats.gov.sa)"

    def _parse(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, dict) and "series" in payload:
            return [
                {
                    "series": r.get("indicator", "gastat"),
                    "indicator": r.get("indicator", "gastat"),
                    "country": "SAU",
                    "date": str(r.get("date")),
                    "value": float(r["value"]),
                    "unit": r.get("unit", ""),
                }
                for r in payload["series"]
                if r.get("value") is not None
            ]
        rows: list[Any]
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict):
            rows = (
                payload.get("data")
                or payload.get("result")
                or payload.get("indicators")
                or payload.get("cards")
                or []
            )
        else:
            rows = []
        out: list[dict[str, Any]] = []
        for i, row in enumerate(rows[:20]):
            if not isinstance(row, dict):
                continue
            value = (
                row.get("value")
                or row.get("Value")
                or row.get("indicatorValue")
                or row.get("latestValue")
            )
            if value is None:
                continue
            try:
                num = float(str(value).replace(",", ""))
            except (TypeError, ValueError):
                continue
            out.append(
                {
                    "series": str(
                        row.get("id")
                        or row.get("indicatorId")
                        or row.get("title_en")
                        or f"gastat_{i}"
                    ),
                    "indicator": str(row.get("title_en") or row.get("id") or f"gastat_{i}"),
                    "country": "SAU",
                    "date": str(row.get("period") or row.get("year") or row.get("date") or ""),
                    "value": num,
                    "unit": row.get("unit") or "",
                }
            )
        return out

    def _collect_live(self) -> CollectPayload:
        settings = get_settings()
        key = (settings.gastat_api_key or "").strip()
        headers: dict[str, str] = {}
        if key:
            headers["Ocp-Apim-Subscription-Key"] = key
            headers["Authorization"] = f"Bearer {key}"
        try:
            payload, final_url, text = get_json(CARDS_URL, headers=headers)
            self.write_cache("gastat.json", text)
            return self._finish(
                url=final_url,
                raw_text=text,
                raw=payload,
                records=self._parse(payload),
                fetch_mode="live",
                ok=True,
                meta={"license": "GASTAT open data terms", "portal": PORTAL},
            )
        except Exception as exc:  # noqa: BLE001
            reason = f"gastat_unreachable:{type(exc).__name__}:{exc}"
            if not key:
                reason = (
                    f"{reason}; set GASTAT_API_KEY if the developer portal requires one ({PORTAL})"
                )
            return self._finish(
                url=CARDS_URL,
                raw_text="",
                raw=None,
                records=[],
                fetch_mode="skipped",
                ok=False,
                skipped_reason=reason,
                meta={"skipped": True, "portal": PORTAL},
            )

    def _collect_fixture(self) -> CollectPayload:
        path = self.fixture_path("gastat_sau.json")
        text = path.read_text(encoding="utf-8")
        payload = json.loads(text)
        return self._finish(
            url=CARDS_URL,
            raw_text=text,
            raw=payload,
            records=self._parse(payload),
            fetch_mode="fixture",
            ok=True,
            meta={"fixture": path.name},
        )
