"""JSON platform logs with secret redaction (BRIEF-5 Lot 2)."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

RIYADH = ZoneInfo("Asia/Riyadh")
CORRELATION_HEADER = "X-Correlation-ID"

# Values that must never appear in logs (populated at startup / per request).
_redact_values: set[str] = set()

_SENSITIVE_KEY_RE = re.compile(
    r"(password|secret|token|cookie|authorization|api[_-]?key)",
    re.IGNORECASE,
)


def register_redaction(*values: str | None) -> None:
    for value in values:
        if value and len(value) >= 4:
            _redact_values.add(value)


def clear_redactions() -> None:
    _redact_values.clear()


def _redact_text(text: str) -> str:
    out = text
    for value in sorted(_redact_values, key=len, reverse=True):
        if value and value in out:
            out = out.replace(value, "[REDACTED]")
    return out


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _redact_text(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: _redact_text(str(v)) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    _redact_text(a) if isinstance(a, str) else a for a in record.args
                )
        if record.exc_info and record.exc_info[1] is not None:
            # Exception message may hold env values; keep type only in formatted output.
            pass
        return True


class JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(RIYADH).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": _redact_text(record.getMessage()),
        }
        for key in (
            "route",
            "method",
            "status",
            "duration_ms",
            "user",
            "role",
            "correlation_id",
            "event",
        ):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc_type"] = (
                record.exc_info[0].__name__ if record.exc_info[0] else None
            )
            # Stack without local variable values (traceback.format_exception default
            # still may include messages; redact the whole string).
            formatted = self.formatException(record.exc_info)
            payload["exc"] = _redact_text(formatted)
        return json.dumps(payload, ensure_ascii=False)


def setup_platform_logging(
    *,
    log_dir: Path | None = None,
    level: int = logging.INFO,
) -> logging.Logger:
    logger = logging.getLogger("data_ia.platform")
    logger.handlers.clear()
    logger.setLevel(level)
    logger.propagate = False
    formatter = JsonLineFormatter()
    filt = RedactingFilter()

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    stream.addFilter(filt)
    logger.addHandler(stream)

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / "platform.log"
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.addFilter(filt)
        logger.addHandler(file_handler)

    return logger


def get_platform_logger() -> logging.Logger:
    return logging.getLogger("data_ia.platform")
