-- Reference DDL (SQLAlchemy models are authoritative).
-- PostgreSQL + optional pgvector; SQLite is used automatically without Docker.

CREATE EXTENSION IF NOT EXISTS vector;  -- Postgres only

-- questions, sub_questions, sources, observations,
-- resolved_questions, source_error_history,
-- sub_question_estimates, daily_answer_snapshots
-- are created via data_ia.db.models / init_db().
