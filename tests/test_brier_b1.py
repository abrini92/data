"""B1/B2/E: brier rejects post-resolution forecasts; one row per question; issue label."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest
import yaml

from data_ia.db.session import reset_engine
from data_ia.freeze_calendar import clear_freeze_calendar_cache


@pytest.fixture()
def brier_env(tmp_path, monkeypatch):
    db = tmp_path / "brier.db"
    head = tmp_path / "head.jsonl"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db.as_posix()}")
    monkeypatch.setenv("REGISTRY_CHAIN_HEAD_PATH", str(head))
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    monkeypatch.setenv("COLLECT_REAL_SOURCES", "false")
    monkeypatch.setenv("USE_SYNTHETIC", "false")
    from data_ia.config import get_settings

    get_settings.cache_clear()
    clear_freeze_calendar_cache()
    reset_engine()
    yield tmp_path
    get_settings.cache_clear()
    clear_freeze_calendar_cache()
    reset_engine()


def test_evaluation_cheat_scenario_gives_n_zero(brier_env, monkeypatch):
    """Synthetic Evaluation scenario: p=outcome written after resolution → n=0."""
    from data_ia.cli import main
    from data_ia.db.models import Question, ResolvedQuestion
    from data_ia.db.session import get_session, try_init_db
    from data_ia.forecast_registry import append_forecast

    try_init_db()
    session = get_session()
    try:
        # Six questions resolved in 2025; cheat forecasts written 18 Nov 2026
        for i in range(6):
            qid = f"cheat_q{i}"
            session.add(Question(id=qid, text=f"Q{i}", status="resolved"))
            session.add(
                ResolvedQuestion(
                    id=qid,
                    text=f"Q{i}",
                    outcome=1 if i % 2 == 0 else 0,
                    resolved_on=date(2025, 6, 1),
                    label="SYNTHETIC",
                    data_label="SYNTHETIC",
                    question_class="cheat",
                )
            )
        session.flush()
        for i in range(6):
            for _ in range(6):  # multiple lines per question (old bug)
                o = 1 if i % 2 == 0 else 0
                append_forecast(
                    session,
                    question_id=f"cheat_q{i}",
                    forecast_at=datetime(2026, 11, 18, tzinfo=timezone.utc),
                    data_cutoff=datetime(2026, 11, 17, tzinfo=timezone.utc),
                    observation_ids=[],
                    probability=float(o),
                    interval_low=None,
                    interval_high=None,
                    data_label="REAL",  # misleading label on forecast
                    git_commit="a" * 40,
                    p_base=0.5,
                    baseline_method="cheat",
                    export_head=True,
                )
        session.commit()
    finally:
        session.close()

    outcomes = brier_env / "outcomes.yaml"
    outcomes.write_text(
        yaml.safe_dump(
            {
                "resolved_questions": [
                    {
                        "id": f"cheat_q{i}",
                        "outcome": 1 if i % 2 == 0 else 0,
                        "resolved_on": "2025-06-01",
                        "data_label": "SYNTHETIC",
                        "label": "SYNTHETIC",
                        "question_class": "cheat",
                        "text": f"Q{i}",
                    }
                    for i in range(6)
                ]
            }
        ),
        encoding="utf-8",
    )
    code = main(["brier", "--path", str(outcomes), "--min-n", "30"])
    assert code == 0
    # Re-run capturing stdout
    import io
    import json
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        main(["brier", "--path", str(outcomes), "--min-n", "30"])
    payload = json.loads(buf.getvalue())
    assert payload["n"] == 0
    assert payload["matched"] == 0


def test_one_forecast_per_question_uses_stored_p_base(brier_env):
    from data_ia.db.models import Question, ResolvedQuestion
    from data_ia.db.session import get_session, try_init_db
    from data_ia.freeze import freeze_question
    from data_ia.math.brier_match import match_registry_to_resolved
    from data_ia.db.models import ForecastRegistry

    try_init_db()
    session = get_session()
    try:
        session.add(Question(id="P15", text="P15", status="active"))
        session.add(
            ResolvedQuestion(
                id="P15",
                text="P15",
                outcome=1,
                resolved_on=date(2027, 2, 1),
                label="SYNTHETIC",
                data_label="SYNTHETIC",
                question_class="misc",
            )
        )
        session.flush()
        # Two freezes before deadline; last eligible wins
        freeze_question(
            session,
            question_id="P15",
            probability=0.3,
            data_cutoff="2026-11-18T00:00:00+03:00",
            forecast_at="2026-12-01T00:00:00+03:00",
            series_id="s15",
            vintage_sha256="c" * 64,
            data_label="SYNTHETIC",
            event_history=[1, 0, 1, 1, 0, 1],
            baseline_method="frequency",
            allow_dirty=True,
        )
        freeze_question(
            session,
            question_id="P15",
            probability=0.7,
            data_cutoff="2026-11-18T00:00:00+03:00",
            forecast_at="2026-12-10T00:00:00+03:00",
            series_id="s15",
            vintage_sha256="d" * 64,
            data_label="SYNTHETIC",
            event_history=[1, 0, 1, 1, 0, 1],
            baseline_method="frequency",
            p_base_override=0.61,
            allow_dirty=True,
        )
        session.commit()
        rows = session.query(ForecastRegistry).all()
        outcomes = {
            "P15": {
                "id": "P15",
                "outcome": 1,
                "resolved_on": "2027-02-01",
                "data_label": "SYNTHETIC",
                "question_class": "misc",
            }
        }
        forecasts, meta = match_registry_to_resolved(rows, outcomes)
        assert len(forecasts) == 1
        assert forecasts[0].probability == pytest.approx(0.7)
        assert forecasts[0].baseline_probability == pytest.approx(0.61)
        assert forecasts[0].label == "SYNTHETIC"
    finally:
        session.close()


def test_naive_base_excludes_self_and_future(brier_env):
    from data_ia.math.brier_match import prior_outcomes_before_cutoff

    outcomes = [
        {"id": "A", "outcome": 1, "resolved_on": "2024-01-01", "question_class": "c"},
        {"id": "B", "outcome": 0, "resolved_on": "2024-06-01", "question_class": "c"},
        {"id": "C", "outcome": 1, "resolved_on": "2025-01-01", "question_class": "c"},
        {"id": "self", "outcome": 1, "resolved_on": "2024-03-01", "question_class": "c"},
    ]
    priors = prior_outcomes_before_cutoff(
        outcomes,
        question_id="self",
        data_cutoff="2024-07-01",
        question_class="c",
    )
    # Only A (before cutoff); B is before cutoff too; self excluded; C after
    assert priors == [1, 0]
