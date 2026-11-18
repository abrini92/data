"""Import frozen proof-question waves with SHA-256 verification."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.orm import Session

from data_ia.config import REPO_ROOT
from data_ia.db.models import Question

WAVES_DIR = REPO_ROOT / "waves"


class WaveHashError(ValueError):
    """Raised when a wave file does not match its committed .sha256 sidecar."""


@dataclass
class WaveBundle:
    wave_id: str
    path: Path
    sha256: str
    data: dict[str, Any]
    questions: list[dict[str, Any]] = field(default_factory=list)
    errata_path: Path | None = None
    errata_text: str | None = None
    bases_path: Path | None = None
    bases_sha256: str | None = None
    bases: dict[str, Any] | None = None


def _parse_sha256_file(path: Path) -> str:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise WaveHashError(f"empty sha256 file: {path}")
    # Formats: "<hex>  name" or bare hex
    m = re.match(r"^([0-9a-fA-F]{64})\b", text)
    if not m:
        raise WaveHashError(f"unrecognised sha256 sidecar: {path}")
    return m.group(1).lower()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_wave_hash(yaml_path: Path, sha_path: Path | None = None) -> str:
    """Return hex digest if yaml matches sidecar; else raise WaveHashError."""
    sidecar = sha_path or yaml_path.with_suffix(yaml_path.suffix + ".sha256")
    if not sidecar.exists():
        # also accept name.yaml → name.sha256
        alt = yaml_path.with_suffix(".sha256")
        sidecar = alt if alt.exists() else sidecar
    if not sidecar.exists():
        raise WaveHashError(f"missing sha256 sidecar for {yaml_path.name}")
    expected = _parse_sha256_file(sidecar)
    actual = file_sha256(yaml_path)
    if actual != expected:
        raise WaveHashError(
            f"SHA-256 mismatch for {yaml_path.name}: "
            f"expected {expected}, got {actual}"
        )
    return actual


def load_wave(
    name: str = "vague1",
    *,
    waves_dir: Path | None = None,
    require_hash: bool = True,
) -> WaveBundle:
    """Load a wave YAML, verifying its .sha256 sidecar when require_hash."""
    root = waves_dir or WAVES_DIR
    yaml_path = root / f"{name}.yaml"
    if not yaml_path.exists():
        raise FileNotFoundError(f"wave not found: {yaml_path}")
    digest = verify_wave_hash(yaml_path) if require_hash else file_sha256(yaml_path)
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    questions = list(data.get("questions") or [])
    wave_id = str(data.get("wave") or name)

    errata_path = root / f"{name}_errata.md"
    errata_text = errata_path.read_text(encoding="utf-8") if errata_path.exists() else None

    bases_path = root / f"{name}_bases.yaml"
    bases = None
    bases_sha = None
    if bases_path.exists():
        bases_sha = verify_wave_hash(bases_path) if require_hash else file_sha256(bases_path)
        with open(bases_path, encoding="utf-8") as f:
            bases = yaml.safe_load(f) or {}

    return WaveBundle(
        wave_id=wave_id,
        path=yaml_path,
        sha256=digest,
        data=data,
        questions=questions,
        errata_path=errata_path if errata_path.exists() else None,
        errata_text=errata_text,
        bases_path=bases_path if bases_path.exists() else None,
        bases_sha256=bases_sha,
        bases=bases,
    )


def import_waves(
    session: Session,
    *,
    names: list[str] | None = None,
    waves_dir: Path | None = None,
) -> dict[str, Any]:
    """Verify hashes and upsert Question rows for wave 1 and 1b (default)."""
    root = waves_dir or WAVES_DIR
    to_load = names or ["vague1", "vague1b"]
    imported: list[dict[str, Any]] = []
    for name in to_load:
        bundle = load_wave(name, waves_dir=root, require_hash=True)
        for q in bundle.questions:
            qid = str(q["id"])
            existing = session.get(Question, qid)
            fields = {
                "text": str(q.get("text") or qid),
                "horizon": str(q.get("deadline") or ""),
                "region": "SAU",
                "zone": f"wave_{bundle.wave_id}",
                "target_variable": str(q.get("series") or ""),
                "threshold": (
                    float(q["threshold"])
                    if isinstance(q.get("threshold"), (int, float))
                    else None
                ),
                "unit": str(q.get("threshold_unit") or ""),
                "resolution_source": str(q.get("resolution_source") or ""),
                "resolution_rule": str(q.get("comparator") or ""),
                "status": "active",
                "illustrative": False,
            }
            if existing is None:
                session.add(Question(id=qid, **fields))
            else:
                for k, v in fields.items():
                    setattr(existing, k, v)
        imported.append(
            {
                "wave": bundle.wave_id,
                "file": bundle.path.name,
                "sha256": bundle.sha256,
                "n_questions": len(bundle.questions),
                "errata": None if bundle.errata_path is None else bundle.errata_path.name,
                "bases_sha256": bundle.bases_sha256,
            }
        )
    session.flush()
    return {"ok": True, "waves": imported}
