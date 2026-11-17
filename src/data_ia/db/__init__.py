"""Database access layer (PostgreSQL + pgvector, SQLite fallback)."""

from data_ia.db.models import (
    Base,
    DailySnapshot,
    ForecastRegistry,
    Observation,
    Question,
    ResolvedQuestion,
    Source,
    SourceError,
    SubQuestion,
    SubQuestionEstimate,
    install_forecast_registry_triggers,
)
from data_ia.db.session import get_session, init_db, try_init_db

__all__ = [
    "Base",
    "DailySnapshot",
    "ForecastRegistry",
    "Observation",
    "Question",
    "ResolvedQuestion",
    "Source",
    "SourceError",
    "SubQuestion",
    "SubQuestionEstimate",
    "get_session",
    "init_db",
    "install_forecast_registry_triggers",
    "try_init_db",
]
