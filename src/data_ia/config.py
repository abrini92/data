"""Runtime settings from environment / .env (no secrets in repo)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]

# Fixed message — never echo env input_value (I8 / BRIEF-4 addendum).
SETTINGS_ERROR_MESSAGE = (
    "Invalid configuration. Check environment variables "
    "(COLLECT_REAL_SOURCES, USE_SYNTHETIC, DATABASE_URL, …) "
    "without printing their values."
)


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
    use_synthetic: bool = Field(default=False, alias="USE_SYNTHETIC")
    extractor_version: str = Field(default="0.1.0", alias="EXTRACTOR_VERSION")
    scheduler_enabled: bool = Field(default=False, alias="SCHEDULER_ENABLED")
    dashboard_port: int = Field(default=8501, alias="DASHBOARD_PORT")
    seed_path: str = Field(
        default=str(REPO_ROOT / "seeds" / "ksa_macro_2026.yaml"),
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
    prior_mapping_path: str = Field(
        default=str(REPO_ROOT / "config" / "prior_mapping.yaml"),
        alias="PRIOR_MAPPING_PATH",
    )
    freeze_calendar_path: str = Field(
        default=str(REPO_ROOT / "config" / "freeze_calendar.yaml"),
        alias="FREEZE_CALENDAR_PATH",
    )
    registry_chain_head_path: str = Field(
        default=str(REPO_ROOT / "data" / "registry_chain_head.jsonl"),
        alias="REGISTRY_CHAIN_HEAD_PATH",
    )
    brier_min_n: int = Field(default=30, alias="BRIER_MIN_N")
    cma_timeout_seconds: float = Field(default=15.0, alias="CMA_TIMEOUT_SECONDS")
    eia_api_key: str = Field(default="", alias="EIA_API_KEY")
    gastat_api_key: str = Field(default="", alias="GASTAT_API_KEY")
    sama_api_key: str = Field(default="", alias="SAMA_API_KEY")

    @model_validator(mode="after")
    def _refuse_synthetic_with_real_collect(self) -> Settings:
        if self.collect_real_sources and self.use_synthetic:
            raise ValueError(
                "COLLECT_REAL_SOURCES=true and USE_SYNTHETIC=true is forbidden: "
                "synthetic data is blocked outright when collecting real sources"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        # Do not surface pydantic input_value (may contain secrets).
        raise ValueError(SETTINGS_ERROR_MESSAGE) from exc


def settings_error_public_message(exc: BaseException) -> str:
    """Return a log-safe error string (never dump env values)."""
    if isinstance(exc, ValidationError):
        return SETTINGS_ERROR_MESSAGE
    text = str(exc)
    if "input_value" in text or "Ctx" in text:
        return SETTINGS_ERROR_MESSAGE
    return text