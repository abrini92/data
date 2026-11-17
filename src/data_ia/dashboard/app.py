"""Streamlit dashboard: tree, leaf history, final P + interval, source weights."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st
from sqlalchemy import desc

# Allow `streamlit run` without editable install
_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from data_ia.db.models import (  # noqa: E402
    DailySnapshot,
    Question,
    Source,
    SubQuestion,
    SubQuestionEstimate,
)
from data_ia.db.session import try_init_db, get_session  # noqa: E402

st.set_page_config(page_title="Data IA", layout="wide")
st.title("Data IA — decision engine (v1)")
st.caption(
    "ILLUSTRATIVE offline outputs unless real collection is enabled. "
    "No LLM number enters maths without Controller validation."
)

engine, db_mode = try_init_db()
session = get_session(fallback_sqlite=(db_mode != "postgres"))

try:
    questions = session.query(Question).all()
    if not questions:
        st.warning(
            "No questions in the database. Run `data-ia cycle` (or "
            "`python -m data_ia.cli cycle`) first."
        )
        st.stop()

    q_labels = {q.id: q.text[:80] for q in questions}
    qid = st.selectbox("Question", options=list(q_labels.keys()), format_func=lambda i: q_labels[i])
    question = session.get(Question, qid)
    assert question is not None

    if question.illustrative:
        st.info("This question is labelled ILLUSTRATIVE.")

    snap = (
        session.query(DailySnapshot)
        .filter_by(question_id=qid)
        .order_by(desc(DailySnapshot.created_at), desc(DailySnapshot.as_of))
        .first()
    )

    col1, col2, col3 = st.columns(3)
    if snap:
        col1.metric("Final probability", f"{snap.probability:.3f}")
        lo = snap.interval_low if snap.interval_low is not None else float("nan")
        hi = snap.interval_high if snap.interval_high is not None else float("nan")
        col2.metric("95% interval (approx.)", f"[{lo:.3f}, {hi:.3f}]")
        col3.metric("As of", str(snap.as_of))
        if snap.disclaimer:
            st.caption(snap.disclaimer)
    else:
        st.warning("No daily snapshot yet for this question.")

    st.subheader("Sub-question tree")
    nodes = (
        session.query(SubQuestion)
        .filter_by(question_id=qid)
        .order_by(SubQuestion.sort_order)
        .all()
    )
    for n in nodes:
        prefix = "· " * (0 if n.parent_id is None else 1)
        tag = n.node_type
        est = (
            session.query(SubQuestionEstimate)
            .filter_by(sub_question_id=n.id)
            .order_by(desc(SubQuestionEstimate.as_of))
            .first()
        )
        est_txt = f" — p̂={est.estimate:.3f}" if est else ""
        st.write(f"{prefix}**{n.id}** ({tag}){est_txt}: {n.text}")

    st.subheader("Leaf estimate history")
    leaves = [n for n in nodes if n.node_type == "leaf"]
    if leaves:
        leaf_id = st.selectbox("Leaf", [n.id for n in leaves])
        history = (
            session.query(SubQuestionEstimate)
            .filter_by(sub_question_id=leaf_id)
            .order_by(SubQuestionEstimate.as_of)
            .all()
        )
        if history:
            chart_data = {"as_of": [h.as_of.isoformat() for h in history],
                          "estimate": [h.estimate for h in history]}
            st.line_chart(chart_data, x="as_of", y="estimate")
            st.dataframe(
                [
                    {
                        "as_of": h.as_of.isoformat(),
                        "estimate": h.estimate,
                        "variance": h.variance,
                        "surprise": h.surprise,
                    }
                    for h in history
                ]
            )
        else:
            st.write("No history yet.")

    st.subheader("Source weights (latest snapshot)")
    if snap and snap.source_weights:
        st.bar_chart(snap.source_weights)
        sources = {s.id: s for s in session.query(Source).all()}
        st.dataframe(
            [
                {
                    "source_id": sid,
                    "name": (sources.get(sid).name if sources.get(sid) else sid),
                    "weight": w,
                }
                for sid, w in sorted(
                    snap.source_weights.items(), key=lambda kv: -kv[1]
                )
            ]
        )
    else:
        st.write("No source weights stored.")

    st.subheader("Sensitivities dP/dx_k")
    if snap and snap.sensitivities:
        st.dataframe(
            [
                {"leaf": k, "dP/dx": v}
                for k, v in sorted(snap.sensitivities.items(), key=lambda kv: -abs(kv[1]))
            ]
        )

    st.caption(f"DB mode: {db_mode} · engine: {engine.url}")
finally:
    session.close()
