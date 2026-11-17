"""Offline connector tests (fixtures only — no live HTTP)."""

from __future__ import annotations

import pytest

from data_ia.connectors.registry import get_connector, list_sources, load_sources_registry
from data_ia.math.controller_rules import (
    ExtractedObservation,
    ExtractionSchema,
    validate_schema_and_range,
)


def test_registry_lists_first_batch():
    names = {s["name"] for s in list_sources(include_optional=True)}
    assert {"worldbank", "imf", "comtrade", "gastat", "cma", "eia", "sama"} <= names
    # Verified Nov 18 lot also includes open_data_gov_sa, mof, cst (no connectors).
    all_ids = {s["id"] for s in list_sources(include_optional=True)}
    assert {"open_data_gov_sa", "mof", "cst"} <= all_ids
    reg = load_sources_registry()
    assert reg["sources"]
    gastat = next(s for s in reg["sources"] if s["id"] == "gastat")
    assert gastat["reliability_prior"] == 0.95
    assert "[à confirmer]" in str(gastat.get("key_required"))


@pytest.mark.parametrize(
    "name",
    ["worldbank", "imf", "comtrade", "gastat", "cma", "eia", "sama"],
)
def test_connector_fixture_collect_ok(name, monkeypatch):
    monkeypatch.setenv("COLLECT_REAL_SOURCES", "false")
    from data_ia.config import get_settings

    get_settings.cache_clear()
    result = get_connector(name).collect(real=False)
    get_settings.cache_clear()
    assert result.ok
    assert result.provenance.fetch_mode == "fixture"
    assert result.provenance.content_hash
    assert result.provenance.connector_version
    assert result.records
    assert result.controller_results
    assert all(c.get("accepted") for c in result.controller_results)


def test_eia_skips_without_key(monkeypatch):
    monkeypatch.delenv("EIA_API_KEY", raising=False)
    from data_ia.config import get_settings

    get_settings.cache_clear()
    result = get_connector("eia").collect(real=True)
    get_settings.cache_clear()
    assert not result.ok
    assert result.provenance.fetch_mode == "skipped"
    assert result.skipped_reason and "EIA_API_KEY" in result.skipped_reason


def test_series_pass_controller_schema():
    result = get_connector("worldbank").collect(real=False)
    schema = ExtractionSchema(
        field_name="value", value_min=0.0, value_max=1e15, value_type="float"
    )
    for row in result.records:
        obs = ExtractedObservation(
            source_id="worldbank", field_name="value", value=row["value"]
        )
        assert validate_schema_and_range(obs, schema).accepted


def test_cli_collect_fixture(monkeypatch, capsys):
    monkeypatch.setenv("COLLECT_REAL_SOURCES", "false")
    from data_ia.config import get_settings
    from data_ia.cli import main

    get_settings.cache_clear()
    code = main(["collect", "--source", "worldbank"])
    get_settings.cache_clear()
    assert code == 0
    out = capsys.readouterr().out
    assert "worldbank" in out
    assert "fixture" in out
