"""Connector contract: raw payload + provenance; network behind COLLECT_REAL_SOURCES."""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from data_ia.config import REPO_ROOT, get_settings
from data_ia.math.controller_rules import (
    ExtractedObservation,
    ExtractionSchema,
    validate_schema_and_range,
)

CONNECTOR_VERSION = "0.2.0"
USER_AGENT = "DataIA/0.2 (+https://github.com/abrini92/data; research; contact=local)"

_SERIES_SCHEMA = ExtractionSchema(
    field_name="value",
    value_min=-1e15,
    value_max=1e15,
    value_type="float",
)


@dataclass(frozen=True)
class Provenance:
    url: str | None
    collected_at: str
    content_hash: str
    connector_version: str
    fetch_mode: str  # live | fixture | skipped


@dataclass
class CollectPayload:
    source_id: str
    ok: bool
    provenance: Provenance
    raw: Any = None
    raw_text: str = ""
    records: list[dict[str, Any]] = field(default_factory=list)
    controller_results: list[dict[str, Any]] = field(default_factory=list)
    skipped_reason: str | None = None
    errors: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BaseConnector(ABC):
    source_id: str
    name: str

    def collect(self, *, real: bool | None = None) -> CollectPayload:
        settings = get_settings()
        live = settings.collect_real_sources if real is None else real
        if live:
            try:
                return self._collect_live()
            except Exception as exc:  # noqa: BLE001
                fixture = self._collect_fixture()
                fixture.ok = False
                fixture.errors = [f"live_failed:{type(exc).__name__}:{exc}"]
                fixture.meta["fallback"] = "fixture"
                # Keep fixture records but mark provenance mode
                fixture.provenance = Provenance(
                    url=fixture.provenance.url,
                    collected_at=fixture.provenance.collected_at,
                    content_hash=fixture.provenance.content_hash,
                    connector_version=CONNECTOR_VERSION,
                    fetch_mode="fixture",
                )
                return fixture
        return self._collect_fixture()

    @abstractmethod
    def _collect_live(self) -> CollectPayload:
        ...

    @abstractmethod
    def _collect_fixture(self) -> CollectPayload:
        ...

    def _finish(
        self,
        *,
        url: str | None,
        raw_text: str,
        raw: Any,
        records: list[dict[str, Any]],
        fetch_mode: str,
        ok: bool = True,
        skipped_reason: str | None = None,
        errors: list[str] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> CollectPayload:
        content_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest() if raw_text else ""
        controller_results = []
        for rec in records:
            obs = ExtractedObservation(
                source_id=self.source_id,
                field_name="value",
                value=rec.get("value"),
            )
            check = validate_schema_and_range(obs, _SERIES_SCHEMA)
            controller_results.append(
                {
                    "accepted": check.accepted,
                    "action": check.action,
                    "value": rec.get("value"),
                    "series": rec.get("series") or rec.get("indicator"),
                }
            )
        return CollectPayload(
            source_id=self.source_id,
            ok=ok,
            provenance=Provenance(
                url=url,
                collected_at=datetime.now(timezone.utc).isoformat(),
                content_hash=content_hash,
                connector_version=CONNECTOR_VERSION,
                fetch_mode=fetch_mode,
            ),
            raw=raw,
            raw_text=raw_text,
            records=records,
            controller_results=controller_results,
            skipped_reason=skipped_reason,
            errors=errors or [],
            meta=meta or {},
        )

    @staticmethod
    def fixture_path(name: str) -> Path:
        return REPO_ROOT / "tests" / "fixtures" / "connectors" / name

    @staticmethod
    def cache_dir() -> Path:
        path = REPO_ROOT / "data" / "cache"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_cache(self, name: str, text: str) -> Path:
        path = self.cache_dir() / name
        path.write_text(text, encoding="utf-8")
        return path

    @staticmethod
    def dumps(obj: Any) -> str:
        return json.dumps(obj, ensure_ascii=False, indent=2, default=str)
