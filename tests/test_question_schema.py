"""Computable question schema + empty-tree not-ready target question."""

from __future__ import annotations

from data_ia.agents.orchestrator import OrchestratorAgent, REQUIRED_QUESTION_FIELDS
from data_ia.agents.pipeline import load_yaml
from data_ia.config import REPO_ROOT


def test_required_slide2_fields():
    assert "target_variable" in REQUIRED_QUESTION_FIELDS
    assert "resolution_rule" in REQUIRED_QUESTION_FIELDS


def test_orchestrator_refuses_missing_fields():
    agent = OrchestratorAgent()
    result = agent.run(
        {
            "seed": {
                "question": {"id": "q", "text": "hello"},
                "sub_questions": [
                    {"id": "root", "text": "r", "node_type": "leaf", "weight": 1.0}
                ],
            }
        }
    )
    assert result.ok is False
    assert any("slide-2" in e or "missing" in e for e in result.errors)


def test_ksa_nonoil_seed_not_ready():
    seed = load_yaml(REPO_ROOT / "seeds" / "ksa_nonoil_growth_2027.yaml")
    assert seed["question"]["text"].startswith(
        "Will Saudi real non-oil activities grow by at least 4.5%"
    )
    assert seed["sub_questions"] == []
    agent = OrchestratorAgent()
    result = agent.run({"seed": seed})
    assert result.ok is False
    assert result.produced.get("not_ready") is True
    assert any("not ready" in e.lower() for e in result.errors)


def test_macro_seed_has_slide2_fields():
    seed = load_yaml(REPO_ROOT / "seeds" / "ksa_macro_2026.yaml")
    q = seed["question"]
    for field in REQUIRED_QUESTION_FIELDS:
        assert q.get(field) not in (None, ""), field
