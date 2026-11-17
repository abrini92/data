"""Pass 3b bug-fix regressions."""

from __future__ import annotations

import math
from datetime import date, datetime, timezone

import pytest

from data_ia.agents.controller import ControllerAgent
from data_ia.agents.pipeline import leaf_history_before
from data_ia.agents.strategist import StrategistAgent
from data_ia.math.aggregation import evaluate_taxonomy, logit, taxonomy_leaf_ids
from data_ia.math.constants import PROB_EPS
from data_ia.math.controller_rules import (
    ExtractedObservation,
    ExtractionSchema,
    validate_extraction_batch,
    validate_schema_and_range,
)
from data_ia.math.lookahead import LookAheadError, assert_resolution_before_forecast
from data_ia.math.sources import SourceReliability, fuse_observations, n_eff


def test_non_finite_reachable_before_range():
    schema = ExtractionSchema("probability", 0.0, 1.0, "probability")
    for bad in (math.nan, math.inf, -math.inf):
        result = validate_schema_and_range(
            ExtractedObservation("s", "probability", bad), schema
        )
        assert result.action == "quarantine"
        assert any(i.code == "non_finite" for i in result.issues)


def test_validate_extraction_batch_groups_by_subquestion_and_field():
    """Two fields on one leaf get separate chi2 groups."""
    schemas = {
        "probability": ExtractionSchema("probability", 0.0, 1.0, "probability"),
        "growth": ExtractionSchema("growth", 0.0, 1.0, "probability"),
    }
    obs = [
        ExtractedObservation(
            "a", "probability", 0.40, sub_question_id="leaf1"
        ),
        ExtractedObservation(
            "b", "probability", 0.42, sub_question_id="leaf1"
        ),
        ExtractedObservation("a", "growth", 0.55, sub_question_id="leaf1"),
        ExtractedObservation("b", "growth", 0.58, sub_question_id="leaf1"),
    ]
    results = validate_extraction_batch(obs, schemas, run_chi2=True)
    assert "__chi2__:leaf1:probability" in results
    assert "__chi2__:leaf1:growth" in results
    assert results["__chi2__:leaf1:probability"].accepted is True
    assert results["__chi2__:leaf1:growth"].accepted is True
    # Must not collapse both fields into a single __chi2__ key.
    assert "__chi2__" not in results


def test_missing_leaf_after_quarantine_is_stale_not_crash():
    agent = StrategistAgent()
    taxonomy = {
        "root": {
            "type": "weighted_logit",
            "children": [
                {"id": "kept", "weight": 1.0},
                {"id": "gone", "weight": 1.0},
            ],
        },
        "kept": {"type": "leaf"},
        "gone": {"type": "leaf"},
    }
    context = {
        "taxonomy": taxonomy,
        "source_priors": {"open": {"bias": 0.0, "variance": 0.1, "n0": 5}},
        "sources": [{"id": "a", "source_class": "open"}],
        "accepted_observations": [
            {
                "source_id": "a",
                "sub_question_id": "kept",
                "extracted_value": 0.6,
                "data_label": "SYNTHETIC",
            }
        ],
        "seed": {"question": {"id": "q-test"}},
    }
    result = agent.run(context)
    assert result.ok is False
    assert result.produced.get("stale") is True
    assert result.produced.get("not_publishable") is True
    assert "gone" in result.produced.get("missing_leaves", [])
    assert result.produced.get("final_probability") is None


def test_evaluate_taxonomy_still_raises_on_missing_leaf():
    taxonomy = {
        "root": {"type": "and", "children": [{"id": "a"}, {"id": "b"}]},
        "a": {"type": "leaf"},
        "b": {"type": "leaf"},
    }
    with pytest.raises(KeyError, match="missing leaf"):
        evaluate_taxonomy(taxonomy, {"a": 0.5})


def test_leaf_history_sorts_and_excludes_same_day():
    rows = [
        ("leaf1", date(2026, 11, 18), 0.9),  # same day — drop
        ("leaf1", date(2026, 11, 17), 0.4),
        ("leaf1", date(2026, 11, 10), 0.2),
        ("leaf1", date(2026, 11, 15), 0.3),  # out of order
        ("leaf2", date(2026, 11, 1), 0.5),
    ]
    t = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
    history = leaf_history_before(rows, t)
    assert history["leaf1"] == [0.2, 0.3, 0.4]
    assert history["leaf2"] == [0.5]


def test_source_error_resolution_must_predate_forecast():
    assert_resolution_before_forecast("2026-01-01", "2026-06-01T00:00:00+00:00")
    with pytest.raises(LookAheadError):
        assert_resolution_before_forecast("2026-12-01", "2026-06-01T00:00:00+00:00")
    with pytest.raises(LookAheadError):
        assert_resolution_before_forecast(None, "2026-06-01T00:00:00+00:00")


def test_source_error_history_filters_future_resolutions(tmp_path, monkeypatch):
    from data_ia.agents.pipeline import _error_history_before_forecast
    from data_ia.config import get_settings
    from data_ia.db.models import ResolvedQuestion, Source, SourceError
    from data_ia.db.session import get_session, reset_engine, try_init_db

    db = tmp_path / "la.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db.as_posix()}")
    get_settings.cache_clear()
    reset_engine()
    try_init_db()
    session = get_session()
    try:
        session.add(Source(id="s1", name="S1", source_class="open"))
        session.add(
            ResolvedQuestion(
                id="past",
                text="past",
                outcome=1,
                resolved_on=date(2026, 1, 1),
                data_label="SYNTHETIC",
            )
        )
        session.add(
            ResolvedQuestion(
                id="future",
                text="future",
                outcome=0,
                resolved_on=date(2026, 12, 1),
                data_label="SYNTHETIC",
            )
        )
        session.flush()
        session.add(SourceError(source_id="s1", resolved_id="past", z=0.6, x=0.5))
        session.add(SourceError(source_id="s1", resolved_id="future", z=0.9, x=0.5))
        session.add(SourceError(source_id="s1", resolved_id=None, z=0.7, x=0.5))
        session.commit()
        forecast_at = datetime(2026, 6, 1, tzinfo=timezone.utc)
        hist = _error_history_before_forecast(session, forecast_at)
        assert hist["s1"] == [(0.6, 0.5)]
    finally:
        session.close()
        get_settings.cache_clear()
        reset_engine()


def test_prob_eps_shared_clips_zero_and_one():
    assert math.isfinite(logit(0.0))
    assert math.isfinite(logit(1.0))
    lo = float(__import__("numpy").clip(0.0, PROB_EPS, 1.0 - PROB_EPS))
    hi = float(__import__("numpy").clip(1.0, PROB_EPS, 1.0 - PROB_EPS))
    assert lo == PROB_EPS
    assert hi == 1.0 - PROB_EPS
    taxonomy = {
        "root": {"type": "leaf"},
    }
    # Bare root leaf via leaf_probs only
    result = evaluate_taxonomy(
        {"root": {"type": "weighted_logit", "children": [{"id": "a", "weight": 1.0}]},
         "a": {"type": "leaf"}},
        {"a": 0.0},
    )
    assert math.isfinite(result.probability)
    result1 = evaluate_taxonomy(
        {"root": {"type": "weighted_logit", "children": [{"id": "a", "weight": 1.0}]},
         "a": {"type": "leaf"}},
        {"a": 1.0},
    )
    assert math.isfinite(result1.probability)


def test_missing_rho_for_group_errors():
    rels = {
        "a": SourceReliability(
            "a", 0.0, 1.0, 1.0, 1, 1.0, False
        ),
        "b": SourceReliability(
            "b", 0.0, 1.0, 1.0, 1, 1.0, False
        ),
    }
    with pytest.raises(ValueError, match="missing rho"):
        fuse_observations(
            {"a": 0.5, "b": 0.5},
            rels,
            correlation_groups={"wire": ["a", "b"]},
            group_rho={},
        )


def test_controller_chi2_separate_fields_same_leaf():
    agent = ControllerAgent()
    context = {
        "require_extraction_fields": True,
        "forecast_at": "2026-11-18T00:00:00+00:00",
        "data_cutoff": "2026-11-18T00:00:00+00:00",
        "question": {"unit": "probability"},
        "source_priors": {"open": {"bias": 0.0, "variance": 0.1, "n0": 5}},
        "sources": [
            {"id": "a", "source_class": "open"},
            {"id": "b", "source_class": "open"},
        ],
        "observations": [
            {
                "source_id": "a",
                "sub_question_id": "leaf1",
                "extracted_field": "probability",
                "extracted_value": 0.40,
                "unit": "probability",
                "published_at": "2026-01-01T00:00:00+00:00",
                "source_passage": "p",
                "data_label": "SYNTHETIC",
            },
            {
                "source_id": "b",
                "sub_question_id": "leaf1",
                "extracted_field": "probability",
                "extracted_value": 0.41,
                "unit": "probability",
                "published_at": "2026-01-01T00:00:00+00:00",
                "source_passage": "p",
                "data_label": "SYNTHETIC",
            },
            {
                "source_id": "a",
                "sub_question_id": "leaf1",
                "extracted_field": "growth",
                "extracted_value": 0.70,
                "unit": "probability",
                "published_at": "2026-01-01T00:00:00+00:00",
                "source_passage": "g",
                "data_label": "SYNTHETIC",
            },
            {
                "source_id": "b",
                "sub_question_id": "leaf1",
                "extracted_field": "growth",
                "extracted_value": 0.71,
                "unit": "probability",
                "published_at": "2026-01-01T00:00:00+00:00",
                "source_passage": "g",
                "data_label": "SYNTHETIC",
            },
        ],
    }
    result = agent.run(context)
    assert result.ok is True
    fields = {o["extracted_field"] for o in result.produced["accepted_observations"]}
    assert fields == {"probability", "growth"}
    assert len(result.produced["accepted_observations"]) == 4


def test_taxonomy_leaf_ids_lists_leaves():
    taxonomy = {
        "root": {
            "type": "weighted_logit",
            "children": [{"id": "a", "weight": 1}, {"id": "b", "weight": 1}],
        },
        "a": {"type": "leaf"},
        "b": {"type": "leaf"},
    }
    assert taxonomy_leaf_ids(taxonomy) == ["a", "b"]
