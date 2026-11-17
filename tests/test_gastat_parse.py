"""GASTAT cardsinfo live-shaped fixture maps to series records."""

from __future__ import annotations

import json

from data_ia.config import REPO_ROOT
from data_ia.connectors.gastat import parse_gastat_payload
from data_ia.connectors.registry import get_connector


def test_parse_live_shaped_cardsinfo_fixture():
    path = REPO_ROOT / "tests" / "fixtures" / "connectors" / "gastat_cardsinfo_live.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = parse_gastat_payload(payload)
    assert len(rows) == 6
    pop = next(r for r in rows if r["indicator_id"] == "131")
    assert pop["value"] == 35013414.0
    assert pop["period"] == "2020"
    assert pop["indicator"] == "Population"
    infl = next(r for r in rows if r["indicator_id"] == "253")
    assert infl["value"] == 5.3
    assert "%" in infl["unit"] or "Year-to-Year" in infl["unit"]


def test_gastat_fixture_collect_parses_live_shape(monkeypatch):
    monkeypatch.setenv("COLLECT_REAL_SOURCES", "false")
    from data_ia.config import get_settings

    get_settings.cache_clear()
    result = get_connector("gastat").collect(real=False)
    get_settings.cache_clear()
    assert result.ok
    assert len(result.records) >= 6
    assert all("indicator_id" in r or "series" in r for r in result.records)
