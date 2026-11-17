"""Shared HTTP helpers: User-Agent, timeouts, optional key injection."""

from __future__ import annotations

from typing import Any

import httpx

from data_ia.connectors.base import USER_AGENT

DEFAULT_TIMEOUT = 20.0


def get_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[Any, str, str]:
    """GET JSON. Returns (payload, final_url, raw_text)."""
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})}
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=hdrs) as client:
        r = client.get(url, params=params)
        r.raise_for_status()
        text = r.text
        try:
            payload = r.json()
        except Exception:
            payload = None
        return payload, str(r.url), text
