"""GASTAT open statistics via official database.stats.gov.sa portal API.

Respect robots.txt on www.stats.gov.sa (Disallow: /api/) — only use the
developer / database portal routes (dp.stats.gov.sa / database.stats.gov.sa).
"""

from __future__ import annotations

import json
import re
from typing import Any

from data_ia.config import get_settings
from data_ia.connectors.base import BaseConnector, CollectPayload
from data_ia.connectors.http_util import get_json

# Official portal API (same route the GASTAT Angular app uses). Not www.stats.gov.sa/api/.
CARDS_URL = "https://database.stats.gov.sa/gastatapi/portal/api/v1/indicators/cardsinfo"
PORTAL = "https://dp.stats.gov.sa/opendata"


def _parse_number(raw: Any) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "").replace(" ", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        m = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", text)
        if not m:
            return None
        try:
            return float(m.group(0))
        except ValueError:
            return None


def parse_gastat_payload(payload: Any) -> list[dict[str, Any]]:
    """Map GASTAT cardsinfo / fixture payloads to series records.

    Live cardsinfo shape (Nov 2026)::
        {"info": [{"obsvalue": "...", "link": 131, "frequency": "2020",
                   "en_title": "Population", "en_sub_title": "(%)", ...}, ...]}
    """
    if isinstance(payload, dict) and "series" in payload:
        return [
            {
                "series": str(r.get("indicator", "gastat")),
                "indicator": str(r.get("indicator", "gastat")),
                "indicator_id": str(r.get("indicator", "gastat")),
                "country": "SAU",
                "date": str(r.get("date") or r.get("period") or ""),
                "period": str(r.get("date") or r.get("period") or ""),
                "value": float(r["value"]),
                "unit": r.get("unit") or "",
                "published_at": str(r.get("published_at") or r.get("date") or ""),
            }
            for r in payload["series"]
            if r.get("value") is not None
        ]

    rows: list[Any]
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = (
            payload.get("info")
            or payload.get("data")
            or payload.get("result")
            or payload.get("indicators")
            or payload.get("cards")
            or []
        )
    else:
        rows = []

    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        value = _parse_number(
            row.get("obsvalue")
            or row.get("value")
            or row.get("Value")
            or row.get("indicatorValue")
            or row.get("latestValue")
        )
        if value is None:
            continue
        indicator_id = str(
            row.get("link")
            or row.get("id")
            or row.get("indicatorId")
            or row.get("ord")
            or f"gastat_{i}"
        )
        title = str(
            row.get("en_title")
            or row.get("title_en")
            or row.get("title")
            or indicator_id
        )
        period = str(
            row.get("frequency")
            or row.get("period")
            or row.get("year")
            or row.get("date")
            or ""
        )
        unit = str(
            row.get("en_sub_title")
            or row.get("sub_title")
            or row.get("unit")
            or ""
        ).strip()
        out.append(
            {
                "series": indicator_id,
                "indicator": title,
                "indicator_id": indicator_id,
                "country": "SAU",
                "date": period,
                "period": period,
                "value": value,
                "unit": unit,
                "published_at": period,
            }
        )
    return out


class GastatConnector(BaseConnector):
    source_id = "gastat"
    name = "GASTAT (stats.gov.sa)"

    def _parse(self, payload: Any) -> list[dict[str, Any]]:
        return parse_gastat_payload(payload)

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
            records = self._parse(payload)
            return self._finish(
                url=final_url,
                raw_text=text,
                raw=payload,
                records=records,
                fetch_mode="live",
                ok=bool(records),
                errors=[] if records else ["live_ok_but_zero_parsed_records"],
                meta={
                    "license": "GASTAT open data terms [à confirmer]",
                    "portal": PORTAL,
                    "n_parsed": len(records),
                    "endpoint": CARDS_URL,
                },
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
        # Prefer sanitised live-shaped fixture when present.
        live_shaped = self.fixture_path("gastat_cardsinfo_live.json")
        path = live_shaped if live_shaped.exists() else self.fixture_path("gastat_sau.json")
        text = path.read_text(encoding="utf-8")
        payload = json.loads(text)
        return self._finish(
            url=CARDS_URL,
            raw_text=text,
            raw=payload,
            records=self._parse(payload),
            fetch_mode="fixture",
            ok=True,
            meta={"fixture": path.name, "data_label": "SYNTHETIC"},
        )
