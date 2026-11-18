"""List / inspect wave YAML files (read-only; never touch *.sha256)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from data_ia.wave_import import WaveHashError, file_sha256, load_wave, verify_wave_hash


def list_waves(waves_dir: Path) -> dict[str, Any]:
    root = Path(waves_dir)
    if not root.is_dir():
        return {"waves": [], "data_label": "n/a", "message": "waves directory missing"}
    names: list[str] = []
    for path in sorted(root.glob("*.yaml")):
        # Skip bases / proposition files that are not primary wave defs when
        # a matching primary name pattern is clearer — still list hashable waves.
        stem = path.stem
        if stem.endswith("_bases") or "PROPOSITION" in stem or stem.endswith("_valeurs"):
            continue
        names.append(stem)
    items = []
    labels: set[str] = set()
    for name in names:
        try:
            item = get_wave(name, waves_dir=root)
            items.append(item)
            if item.get("data_label"):
                labels.add(str(item["data_label"]))
        except FileNotFoundError:
            continue
    data_label = "REAL" if not labels else (
        next(iter(labels)) if len(labels) == 1 else "mixed: refused"
    )
    return {"waves": items, "data_label": data_label}


def get_wave(wave_id: str, *, waves_dir: Path) -> dict[str, Any]:
    root = Path(waves_dir)
    yaml_path = root / f"{wave_id}.yaml"
    if not yaml_path.exists():
        raise FileNotFoundError(wave_id)
    expected: str | None
    actual = file_sha256(yaml_path)
    hash_ok: bool | None
    hash_error: str | None = None
    try:
        expected = verify_wave_hash(yaml_path)
        hash_ok = True
    except WaveHashError as exc:
        expected = None
        hash_ok = False
        hash_error = str(exc)
        # Still load without requiring hash for display of questions metadata.
    require_hash = hash_ok is True
    try:
        bundle = load_wave(wave_id, waves_dir=root, require_hash=require_hash)
    except WaveHashError as exc:
        raise FileNotFoundError(wave_id) from exc

    questions = []
    for q in bundle.questions:
        if not isinstance(q, dict):
            continue
        questions.append(
            {
                "id": q.get("id"),
                "text": q.get("text"),
                "group": q.get("group"),
                "driver": q.get("driver"),
                # PMI masking is Lot 3; Lot 1 returns structural fields only.
            }
        )
    data_label = "REAL"
    if isinstance(bundle.data, dict) and bundle.data.get("data_label"):
        data_label = str(bundle.data["data_label"])
    return {
        # API id is the file stem (route key); wave field keeps YAML `wave:` value.
        "id": wave_id,
        "wave": bundle.wave_id,
        "path": str(bundle.path),
        "sha256_computed": actual,
        "sha256_expected": expected,
        "hash_ok": hash_ok,
        "hash_error": hash_error,
        "questions": questions,
        "errata_present": bundle.errata_path is not None and bundle.errata_path.exists(),
        "bases_sha256": bundle.bases_sha256,
        "data_label": data_label,
    }
