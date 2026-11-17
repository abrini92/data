"""Logit aggregation and sensitivity tests."""

from __future__ import annotations

import pytest

from data_ia.math.aggregation import evaluate_taxonomy, logit, sigmoid


def test_logit_sigmoid_roundtrip():
    for p in (0.1, 0.5, 0.9):
        assert sigmoid(logit(p)) == pytest.approx(p, abs=1e-9)


def test_weighted_logit_equal_weights():
    taxonomy = {
        "root": {
            "type": "weighted_logit",
            "children": [
                {"id": "a", "weight": 1.0},
                {"id": "b", "weight": 1.0},
            ],
        },
        "a": {"type": "leaf"},
        "b": {"type": "leaf"},
    }
    # equal logits average → same as inputs when equal
    result = evaluate_taxonomy(taxonomy, {"a": 0.7, "b": 0.7})
    assert result.probability == pytest.approx(0.7, abs=1e-6)


def test_and_or_nodes():
    taxonomy = {
        "root": {
            "type": "and",
            "children": [{"id": "a"}, {"id": "b"}],
        },
        "a": {"type": "leaf"},
        "b": {"type": "leaf"},
    }
    assert evaluate_taxonomy(taxonomy, {"a": 0.5, "b": 0.4}).probability == pytest.approx(0.2)

    taxonomy_or = {
        "root": {
            "type": "or",
            "children": [{"id": "a"}, {"id": "b"}],
        },
        "a": {"type": "leaf"},
        "b": {"type": "leaf"},
    }
    # 1 - (1-0.5)*(1-0.4) = 0.7
    assert evaluate_taxonomy(taxonomy_or, {"a": 0.5, "b": 0.4}).probability == pytest.approx(0.7)


def test_sensitivities_positive_for_weighted_logit():
    taxonomy = {
        "root": {
            "type": "weighted_logit",
            "children": [
                {"id": "a", "weight": 2.0},
                {"id": "b", "weight": 1.0},
            ],
        },
        "a": {"type": "leaf"},
        "b": {"type": "leaf"},
    }
    result = evaluate_taxonomy(taxonomy, {"a": 0.4, "b": 0.6})
    assert result.sensitivities["a"] > result.sensitivities["b"] > 0
