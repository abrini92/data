"""B5: stub extraction always SYNTHETIC; missing published_at refused; GASTAT REAL off."""

from __future__ import annotations

import pytest

from data_ia.db.session import reset_engine
from data_ia.math.labels import SYNTHETIC


@pytest.fixture()
def env(tmp_path, monkeypatch):
    db = tmp_path / "b5.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db.as_posix()}")
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    monkeypatch.setenv("COLLECT_REAL_SOURCES", "false")
    monkeypatch.setenv("USE_SYNTHETIC", "false")
    from data_ia.config import get_settings

    get_settings.cache_clear()
    reset_engine()
    yield
    get_settings.cache_clear()
    reset_engine()


def test_live_fetch_with_stub_extract_is_synthetic(env, monkeypatch):
    from data_ia.agents.collector import CollectorAgent
    from data_ia.llm.stub import StubLLM

    agent = CollectorAgent()

    def fake_fetch(src, real):
        return ("LIVE BODY HTTP 200", "https://example.com/doc", "live")

    monkeypatch.setattr(agent, "_fetch", fake_fetch)
    monkeypatch.setattr("data_ia.agents.collector.get_llm", lambda: StubLLM())

    ctx = {
        "sources": [{"id": "s1", "name": "Example", "url": "https://example.com"}],
        "sub_questions": [{"id": "leaf1", "text": "t", "node_type": "leaf"}],
        "question": {"unit": "probability"},
        "forecast_at": "2026-11-18T12:00:00+00:00",
        "data_cutoff": "2026-11-18T12:00:00+00:00",
    }
    result = agent.run(ctx)
    assert result.ok
    obs = result.produced["observations"]
    assert obs
    assert all(o["data_label"] == SYNTHETIC for o in obs)
    assert all(o["meta"].get("stub_extract") is True for o in obs)


def test_missing_published_at_refused(env, monkeypatch):
    from data_ia.agents.collector import CollectorAgent
    from data_ia.llm.base import LLMResponse

    class NoPubLLM:
        provider = "real-ish"

        def complete(self, prompt, *, schema_hint=None):
            return LLMResponse(
                content="{}",
                structured={
                    "field_name": "probability",
                    "value": 0.5,
                    "unit": "probability",
                    # no published_at
                    "source_passage": "x",
                    "provider": "openai",
                },
                model="x",
                provider="openai",
            )

    agent = CollectorAgent()
    monkeypatch.setattr(agent, "_fetch", lambda src, real: ("body", "u", "live"))
    monkeypatch.setattr("data_ia.agents.collector.get_llm", lambda: NoPubLLM())

    ctx = {
        "sources": [{"id": "s1", "name": "Example", "url": "https://example.com"}],
        "sub_questions": [{"id": "leaf1", "text": "t", "node_type": "leaf"}],
        "question": {"unit": "probability"},
        "forecast_at": "2026-11-18T12:00:00+00:00",
        "data_cutoff": "2026-11-18T12:00:00+00:00",
    }
    result = agent.run(ctx)
    obs = result.produced["observations"]
    assert obs
    assert all(o.get("status") == "rejected" for o in obs)
    assert all(o.get("rejection_reason") == "missing_published_at" for o in obs)
    assert any("missing published_at" in e for e in result.errors)


def test_gastat_real_disabled():
    from data_ia.connectors.gastat import GastatConnector

    payload = GastatConnector()._collect_live()
    assert payload.ok is False
    assert payload.provenance.fetch_mode == "skipped"
    assert "gastatapi" in (payload.skipped_reason or "").lower() or "disabled" in (
        payload.skipped_reason or ""
    ).lower()
    assert (payload.meta or {}).get("real_disabled") is True


def test_pydantic_settings_error_hides_env_values(monkeypatch, capsys):
    from data_ia.cli import main
    from data_ia.config import SETTINGS_ERROR_MESSAGE, get_settings

    monkeypatch.setenv("COLLECT_REAL_SOURCES", "true")
    monkeypatch.setenv("USE_SYNTHETIC", "true")
    monkeypatch.setenv("LLM_API_KEY", "super-secret-key-do-not-leak")
    get_settings.cache_clear()
    code = main(["cycle"])
    err = capsys.readouterr().err
    assert code == 2
    assert "super-secret-key-do-not-leak" not in err
    assert "input_value" not in err
    get_settings.cache_clear()
