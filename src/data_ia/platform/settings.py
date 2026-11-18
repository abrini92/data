"""Platform settings. Errors never echo env values (BRIEF-5 Lots 1–2)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from data_ia.config import REPO_ROOT
from data_ia.platform.auth import MIN_SECRET_LEN, default_users_path

PROD_DB_PATH = (REPO_ROOT / "data" / "dataia.db").resolve()
DEFAULT_TEST_DB_PATH = REPO_ROOT / "data" / "test" / "dataia.db"
DEFAULT_UI_PORT = 8520
DEFAULT_LOG_DIR = REPO_ROOT / "logs"

PLATFORM_SETTINGS_ERROR = (
    "Invalid platform configuration. Check DATAIA_ENV / DATAIA_UI_* "
    "without printing their values."
)
SECRET_KEY_MISSING = "DATAIA_UI_SECRET_KEY is missing or too short"
SECRET_KEY_TOO_SHORT = "DATAIA_UI_SECRET_KEY is missing or too short"


class PlatformConfigError(ValueError):
    """Raised for refused env/DB combinations (public message, no secrets)."""


class PlatformSettings(BaseSettings):
    """Safe defaults: DATAIA_ENV=test; listen on 127.0.0.1 only."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
        hide_input_in_errors=True,
    )

    env: Literal["test", "prod"] = Field(default="test", alias="DATAIA_ENV")
    ui_host: str = Field(default="127.0.0.1", alias="DATAIA_UI_HOST")
    ui_port: int = Field(default=DEFAULT_UI_PORT, alias="DATAIA_UI_PORT")
    ui_secret_key: str = Field(default="", alias="DATAIA_UI_SECRET_KEY")
    ui_users_path: str = Field(
        default="",
        alias="DATAIA_UI_USERS_PATH",
    )
    ui_session_minutes: int = Field(default=480, alias="DATAIA_UI_SESSION_MINUTES")
    ui_default_locale: Literal["ar", "en"] = Field(
        default="en", alias="DATAIA_UI_DEFAULT_LOCALE"
    )
    ui_database_url: str = Field(default="", alias="DATAIA_UI_DATABASE_URL")
    ui_test_db_path: str = Field(
        default=str(DEFAULT_TEST_DB_PATH),
        alias="DATAIA_UI_TEST_DB_PATH",
    )
    ui_log_dir: str = Field(default=str(DEFAULT_LOG_DIR), alias="DATAIA_UI_LOG_DIR")
    registry_chain_head_path: str = Field(
        default=str(REPO_ROOT / "data" / "registry_chain_head.jsonl"),
        alias="REGISTRY_CHAIN_HEAD_PATH",
    )
    waves_dir: str = Field(default=str(REPO_ROOT / "waves"), alias="DATAIA_UI_WAVES_DIR")
    freeze_calendar_path: str = Field(
        default=str(REPO_ROOT / "config" / "freeze_calendar.yaml"),
        alias="FREEZE_CALENDAR_PATH",
    )
    resolution_path: str = Field(
        default=str(REPO_ROOT / "config" / "resolution.yaml"),
        alias="DATAIA_UI_RESOLUTION_PATH",
    )
    # Set True only when caller passes --env prod or constructs settings for prod.
    prod_explicit: bool = Field(default=False, alias="DATAIA_UI_PROD_EXPLICIT")

    @field_validator("ui_host")
    @classmethod
    def _localhost_only(cls, value: str) -> str:
        host = (value or "").strip() or "127.0.0.1"
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError(
                "DATAIA_UI_HOST must be a loopback address unless overridden carefully"
            )
        return host

    @field_validator("ui_secret_key")
    @classmethod
    def _secret_present(cls, value: str) -> str:
        key = value or ""
        if len(key) < MIN_SECRET_LEN:
            # Never include the key (or its length detail beyond the public message).
            raise ValueError(SECRET_KEY_TOO_SHORT)
        return key

    @model_validator(mode="after")
    def _prod_requires_explicit(self) -> PlatformSettings:
        if self.env == "prod" and not self.prod_explicit:
            import os

            if os.environ.get("DATAIA_ENV", "").strip().lower() != "prod":
                raise ValueError(
                    "prod requires an explicit request (--env prod or DATAIA_ENV=prod)"
                )
            object.__setattr__(self, "prod_explicit", True)
        return self

    def users_file(self) -> Path:
        raw = (self.ui_users_path or "").strip()
        if raw:
            path = Path(raw)
            return path if path.is_absolute() else (REPO_ROOT / path).resolve()
        return default_users_path()

    def session_max_age_seconds(self) -> int:
        return max(60, int(self.ui_session_minutes) * 60)

    def log_directory(self) -> Path:
        path = Path(self.ui_log_dir)
        return path if path.is_absolute() else (REPO_ROOT / path).resolve()

    def resolved_sqlite_path(self) -> Path | None:
        """Return the SQLite file path the UI may open, or None if URL is non-SQLite."""
        if self.ui_database_url.strip():
            url = self.ui_database_url.strip()
            if url.startswith("postgresql"):
                return None
            if url.startswith("sqlite:///"):
                raw = url.split("sqlite:///", 1)[-1]
                path = Path(
                    raw[1:]
                    if raw.startswith("/") and len(raw) > 2 and raw[2] == ":"
                    else raw
                )
                if not path.is_absolute():
                    path = (Path.cwd() / path).resolve()
                else:
                    path = path.resolve()
                self._refuse_prod_db_in_test(path)
                return path
            raise PlatformConfigError("unsupported DATAIA_UI_DATABASE_URL scheme")
        if self.env == "test":
            path = Path(self.ui_test_db_path)
            if not path.is_absolute():
                path = (REPO_ROOT / path).resolve()
            else:
                path = path.resolve()
            self._refuse_prod_db_in_test(path)
            return path
        return PROD_DB_PATH

    def _refuse_prod_db_in_test(self, path: Path) -> None:
        if self.env == "test" and path.resolve() == PROD_DB_PATH:
            raise PlatformConfigError(
                "DATAIA_ENV=test refuses production database data/dataia.db; "
                "use data/test/ or a tmp_path database"
            )


def load_platform_settings(**overrides: object) -> PlatformSettings:
    """Load settings; wrap ValidationError without leaking input values."""
    try:
        return PlatformSettings(**overrides)  # type: ignore[arg-type]
    except ValidationError as exc:
        # Map secret-key failures to a dedicated public message (A2.7).
        err_text = str(exc)
        if "DATAIA_UI_SECRET_KEY" in err_text or SECRET_KEY_TOO_SHORT in err_text:
            raise PlatformConfigError(SECRET_KEY_MISSING) from exc
        raise PlatformConfigError(PLATFORM_SETTINGS_ERROR) from exc
