"""Connector registry keyed by config/sources.yaml."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from data_ia.config import REPO_ROOT
from data_ia.connectors.base import BaseConnector, CollectPayload
from data_ia.connectors.cma import CMAConnector
from data_ia.connectors.comtrade import ComtradeConnector
from data_ia.connectors.eia import EIAConnector
from data_ia.connectors.gastat import GastatConnector
from data_ia.connectors.imf import IMFConnector
from data_ia.connectors.sama import SAMAConnector
from data_ia.connectors.worldbank import WorldBankConnector

CONNECTORS: dict[str, type[BaseConnector]] = {
    "worldbank": WorldBankConnector,
    "imf": IMFConnector,
    "comtrade": ComtradeConnector,
    "gastat": GastatConnector,
    "cma": CMAConnector,
    "eia": EIAConnector,
    "sama": SAMAConnector,
}

SOURCES_YAML = REPO_ROOT / "config" / "sources.yaml"


def load_registry() -> dict[str, Any]:
    with open(SOURCES_YAML, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("sources.yaml must be a mapping")
    return data


def load_sources_registry() -> dict[str, Any]:
    return load_registry()


def list_sources(*, include_optional: bool = False) -> list[dict[str, Any]]:
    data = load_registry()
    out: list[dict[str, Any]] = []
    for src in data.get("sources") or []:
        optional = src.get("id") == "sama" or bool(src.get("optional"))
        if optional and not include_optional:
            continue
        key_req = src.get("key_required")
        out.append(
            {
                "name": src["id"],
                "id": src["id"],
                "title": src.get("name"),
                "url": src.get("url"),
                "class": src.get("class"),
                "reliability_prior": src.get("reliability_prior"),
                "access": src.get("access"),
                "key_required": key_req,
                "key_env": src.get("key_env"),
                "license": src.get("license"),
                "update_frequency": src.get("update_frequency"),
                "priority": src.get("priority"),
                "connector": src.get("connector"),
                "optional": optional,
                "correlation_group": src.get("correlation_group"),
            }
        )
    out.sort(key=lambda s: (s.get("priority") or 99, s["name"]))
    return out


def get_connector(name: str) -> BaseConnector:
    key = name.strip().lower()
    if key not in CONNECTORS:
        known = ", ".join(sorted(CONNECTORS))
        raise KeyError(f"unknown source {name!r}; choose from: {known}")
    return CONNECTORS[key]()


def list_connectors() -> list[str]:
    return sorted(CONNECTORS)


def save_raw_cache(name: str, payload: CollectPayload) -> Path:
    raw_dir = REPO_ROOT / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"{name}.json"
    path.write_text(
        json.dumps(payload.to_dict(), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return path
