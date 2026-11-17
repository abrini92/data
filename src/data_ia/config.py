"""Runtime settings from environment / .env (no secrets in repo)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Default to SQLite so Windows hosts without Docker still run offline.
    database_url: str = Field(
        default=f"sqlite:///{(REPO_ROOT / 'data' / 'dataia.db').as_posix()}",
        alias="DATABASE_URL",
    )
    llm_provider: str = Field(default="stub", alias="LLM_PROVIDER")
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_base_url: str = Field(default="", alias="LLM_BASE_URL")
    llm_model: str = Field(default="stub-deterministic", alias="LLM_MODEL")
    collect_real_sources: bool = Field(default=False, alias="COLLECT_REAL_SOURCES")
    extractor_version: str = Field(default="0.1.0", alias="EXTRACTOR_VERSION")
    scheduler_enabled: bool = Field(default=False, alias="SCHEDULER_ENABLED")
    dashboard_port: int = Field(default=8501, alias="DASHBOARD_PORT")
    seed_path: str = Field(
        default=str(REPO_ROOT / "seeds" / "ksa_macro_illustrative.yaml"),
        alias="SEED_PATH",
    )
    taxonomy_path: str = Field(
        default=str(REPO_ROOT / "config" / "taxonomy.yaml"),
        alias="TAXONOMY_PATH",
    )
    source_priors_path: str = Field(
        default=str(REPO_ROOT / "config" / "source_priors.yaml"),
        alias="SOURCE_PRIORS_PATH",
    )
    sources_registry_path: str = Field(
        default=str(REPO_ROOT / "config" / "sources.yaml"),
        alias="SOURCES_REGISTRY_PATH",
    )
    eia_api_key: str = Field(default="", alias="EIA_API_KEY")
    gastat_api_key: str = Field(default="", alias="GASTAT_API_KEY")
    sama_api_key: str = Field(default="", alias="SAMA_API_KEY")


@lru_cache
def get_settings() -> Settings:
    return Settings()
