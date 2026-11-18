"""SQLAlchemy ORM models for Data IA.

Tables: questions/sub-question tree, sources, observations (with provenance),
resolved questions, source error history, daily answer snapshots, and the
append-only forecast_registry.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    horizon: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    zone: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    target_variable: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    threshold: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    resolution_source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolution_rule: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    illustrative: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    nodes: Mapped[list[SubQuestion]] = relationship(back_populates="question")
    snapshots: Mapped[list[DailySnapshot]] = relationship(back_populates="question")
    forecasts: Mapped[list[ForecastRegistry]] = relationship(back_populates="question")


class SubQuestion(Base):
    __tablename__ = "sub_questions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"), index=True)
    parent_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("sub_questions.id"), nullable=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    node_type: Mapped[str] = mapped_column(String(32), default="leaf")
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    illustrative: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    question: Mapped[Question] = relationship(back_populates="nodes")
    estimates: Mapped[list[SubQuestionEstimate]] = relationship(
        back_populates="sub_question"
    )


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_class: Mapped[str] = mapped_column(String(64), default="open")
    publisher: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    freshness_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    usage_rights: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    meta: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    observations: Mapped[list[Observation]] = relationship(back_populates="source")
    errors: Mapped[list[SourceError]] = relationship(back_populates="source")


class Observation(Base):
    __tablename__ = "observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    sub_question_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("sub_questions.id"), nullable=True, index=True
    )
    raw_doc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extracted_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    extracted_field: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    source_passage: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    extractor_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="raw")
    # raw | accepted | rejected | quarantined
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    data_label: Mapped[str] = mapped_column(String(32), default="SYNTHETIC")
    meta: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    source: Mapped[Source] = relationship(back_populates="observations")


class ResolvedQuestion(Base):
    __tablename__ = "resolved_questions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Hand-written YAML probabilities are NOT used for engine proof scoring.
    # Kept optional for legacy synthetic seed loading only.
    probability: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    outcome: Mapped[int] = mapped_column(Integer, nullable=False)
    resolved_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    label: Mapped[str] = mapped_column(String(64), default="ILLUSTRATIVE/SYNTHETIC")
    data_label: Mapped[str] = mapped_column(String(32), default="SYNTHETIC")
    question_class: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    baseline_probability: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    meta: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)


class SourceError(Base):
    __tablename__ = "source_error_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    resolved_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("resolved_questions.id"), nullable=True
    )
    z: Mapped[float] = mapped_column(Float, nullable=False)
    x: Mapped[float] = mapped_column(Float, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    data_label: Mapped[str] = mapped_column(String(32), default="SYNTHETIC")

    source: Mapped[Source] = relationship(back_populates="errors")


class SubQuestionEstimate(Base):
    __tablename__ = "sub_question_estimates"
    __table_args__ = (
        UniqueConstraint("sub_question_id", "as_of", name="uq_sq_estimate_day"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sub_question_id: Mapped[str] = mapped_column(
        ForeignKey("sub_questions.id"), index=True
    )
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    estimate: Mapped[float] = mapped_column(Float, nullable=False)
    variance: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    surprise: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    meta: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    sub_question: Mapped[SubQuestion] = relationship(back_populates="estimates")


class DailySnapshot(Base):
    """Convenience latest-view rows. Audit trail is forecast_registry (append-only)."""

    __tablename__ = "daily_answer_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"), index=True)
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    probability: Mapped[float] = mapped_column(Float, nullable=False)
    interval_low: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    interval_high: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source_weights: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    sensitivities: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    node_probabilities: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )
    disclaimer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    data_label: Mapped[str] = mapped_column(String(32), default="SYNTHETIC")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    question: Mapped[Question] = relationship(back_populates="snapshots")


class ForecastRegistry(Base):
    """Append-only frozen forecast rows. No UPDATE/DELETE (enforced by DB triggers)."""

    __tablename__ = "forecast_registry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"), index=True)
    forecast_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data_cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    git_commit: Mapped[str] = mapped_column(String(64), nullable=False)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(32), nullable=False)
    observation_ids: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    probability: Mapped[float] = mapped_column(Float, nullable=False)
    interval_low: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    interval_high: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    data_label: Mapped[str] = mapped_column(String(32), nullable=False)
    # B3/B4: chained hash payload + baseline / vintage metadata
    prev_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    p_base: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    baseline_method: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    series_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    vintage_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    observations_content_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    seed_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    wave_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    question: Mapped[Question] = relationship(back_populates="forecasts")


def install_forecast_registry_triggers(engine: Engine) -> None:
    """Reject UPDATE/DELETE on forecast_registry (SQLite + Postgres)."""
    dialect = engine.dialect.name
    if dialect == "sqlite":
        stmts = [
            """
            CREATE TRIGGER IF NOT EXISTS forecast_registry_no_update
            BEFORE UPDATE ON forecast_registry
            BEGIN
              SELECT RAISE(ABORT, 'forecast_registry is append-only: UPDATE rejected');
            END;
            """,
            """
            CREATE TRIGGER IF NOT EXISTS forecast_registry_no_delete
            BEFORE DELETE ON forecast_registry
            BEGIN
              SELECT RAISE(ABORT, 'forecast_registry is append-only: DELETE rejected');
            END;
            """,
        ]
    elif dialect in {"postgresql", "postgres"}:
        stmts = [
            """
            CREATE OR REPLACE FUNCTION forecast_registry_reject_mutation()
            RETURNS trigger AS $$
            BEGIN
              RAISE EXCEPTION 'forecast_registry is append-only: % rejected', TG_OP;
            END;
            $$ LANGUAGE plpgsql;
            """,
            """
            DROP TRIGGER IF EXISTS forecast_registry_no_update ON forecast_registry;
            CREATE TRIGGER forecast_registry_no_update
            BEFORE UPDATE ON forecast_registry
            FOR EACH ROW EXECUTE FUNCTION forecast_registry_reject_mutation();
            """,
            """
            DROP TRIGGER IF EXISTS forecast_registry_no_delete ON forecast_registry;
            CREATE TRIGGER forecast_registry_no_delete
            BEFORE DELETE ON forecast_registry
            FOR EACH ROW EXECUTE FUNCTION forecast_registry_reject_mutation();
            """,
        ]
    else:
        return

    with engine.begin() as conn:
        for stmt in stmts:
            conn.execute(text(stmt))


@event.listens_for(Base.metadata, "after_create")
def _install_triggers_after_create(target, connection, **kw):  # type: ignore[no-untyped-def]
    # Installed explicitly via install_forecast_registry_triggers in init_db.
    _ = (target, connection, kw)
