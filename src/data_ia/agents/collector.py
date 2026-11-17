"""Collector: daily pipes — fetch or stub documents with provenance."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

import httpx

from data_ia.agents.base import Agent, AgentResult
from data_ia.config import get_settings
from data_ia.llm import get_llm


class CollectorAgent(Agent):
    name = "collector"
    produces = "Raw docs + stub/LLM extractions with URL, timestamp, hash, extractor version"
    checks = "Hash present; timestamp set; extractor_version set; optional HTTP status"
    on_failure = "Retry once offline with stub body; mark observation failed if still empty"

    def run(self, context: dict[str, Any]) -> AgentResult:
        settings = get_settings()
        sources = context.get("sources") or (context.get("seed") or {}).get("sources") or []
        leaves = [
            n
            for n in (context.get("sub_questions") or [])
            if n.get("node_type", "leaf") == "leaf"
        ]
        llm = get_llm()
        observations: list[dict[str, Any]] = []
        errors: list[str] = []
        checks = ["hash", "timestamp", "extractor_version"]

        for src in sources:
            body, url_used, fetch_note = self._fetch(src, settings.collect_real_sources)
            content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
            for leaf in leaves:
                prompt = (
                    f"Extract a probability signal for sub-question {leaf['id']}: "
                    f"{leaf.get('text')}\nSource: {src.get('name')}\nDoc:\n{body[:2000]}"
                )
                resp = llm.complete(prompt, schema_hint="field: probability")
                structured = resp.structured or {}
                observations.append(
                    {
                        "source_id": src["id"],
                        "sub_question_id": leaf["id"],
                        "raw_doc": body[:4000],
                        "extracted_value": structured.get("value"),
                        "extracted_field": structured.get("field_name", "probability"),
                        "url": url_used,
                        "collected_at": datetime.now(timezone.utc).isoformat(),
                        "content_hash": content_hash,
                        "extractor_version": settings.extractor_version,
                        "status": "raw",
                        "meta": {
                            "fetch_note": fetch_note,
                            "llm_provider": resp.provider,
                            "illustrative": True,
                        },
                    }
                )

        if not observations:
            return AgentResult(
                agent=self.name,
                ok=False,
                checks=checks,
                errors=errors or ["no observations collected"],
                failure_action=self.on_failure,
            )

        return AgentResult(
            agent=self.name,
            ok=True,
            checks=checks,
            errors=errors,
            produced={"observations": observations},
        )

    def _fetch(self, src: dict[str, Any], real: bool) -> tuple[str, str | None, str]:
        url = src.get("url")
        stub_body = (
            f"[STUB DOCUMENT — ILLUSTRATIVE]\nSource: {src.get('name')}\n"
            f"URL: {url}\n"
            f"Note: real collection disabled or failed; offline fixture used.\n"
            f"Seed hint: {src.get('stub_snippet') or 'No public signal quantified.'}\n"
        )
        if not real or not url:
            return stub_body, url, "stubbed"

        try:
            with httpx.Client(timeout=10.0, follow_redirects=True) as client:
                r = client.get(url)
                if r.status_code >= 400:
                    return stub_body, url, f"http_{r.status_code}_fallback_stub"
                text = r.text[:8000]
                return text, str(r.url), "live"
        except Exception as exc:  # noqa: BLE001 — network must not crash pipeline
            return stub_body, url, f"error_fallback_stub:{type(exc).__name__}"
