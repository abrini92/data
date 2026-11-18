"""Wave import with SHA-256 verification (Priority 0 A)."""

from __future__ import annotations

import shutil

import pytest

from data_ia.config import REPO_ROOT
from data_ia.wave_import import WaveHashError, load_wave, verify_wave_hash


def test_vague1_and_vague1b_hashes_ok():
    b1 = load_wave("vague1", require_hash=True)
    assert b1.sha256.startswith("36d214bb")
    assert any(q["id"] == "P1" for q in b1.questions)
    assert b1.errata_text is not None
    assert b1.bases_sha256 is not None
    assert b1.bases_sha256.startswith("ed3b0714")

    b1b = load_wave("vague1b", require_hash=True)
    assert b1b.sha256.startswith("95c1f375")
    ids = {q["id"] for q in b1b.questions}
    assert ids == {"P6", "P17"}


def test_hash_mismatch_refused(tmp_path):
    src = REPO_ROOT / "waves" / "vague1.yaml"
    dst = tmp_path / "vague1.yaml"
    sha = tmp_path / "vague1.sha256"
    shutil.copy(src, dst)
    sha.write_text("0" * 64 + "  vague1.yaml\n", encoding="utf-8")
    with pytest.raises(WaveHashError, match="mismatch"):
        verify_wave_hash(dst, sha)


def test_cli_import_verify_only():
    from data_ia.cli import main

    code = main(["import-waves", "--verify-only"])
    assert code == 0


def test_cli_import_refuses_tampered(tmp_path, monkeypatch, capsys):
    from data_ia.cli import main
    from data_ia.wave_import import WAVES_DIR

    # Point a fake waves dir with bad hash
    waves = tmp_path / "waves"
    waves.mkdir()
    good = (WAVES_DIR / "vague1.yaml").read_bytes()
    (waves / "vague1.yaml").write_bytes(good + b"\n# tampered\n")
    (waves / "vague1.sha256").write_text(
        (WAVES_DIR / "vague1.sha256").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.setattr("data_ia.wave_import.WAVES_DIR", waves)
    # load_wave uses WAVES_DIR; also patch in cli path via import
    code = main(["import-waves", "--verify-only", "--wave", "vague1"])
    assert code == 1
    err = capsys.readouterr().err
    assert "mismatch" in err.lower() or "SHA-256" in err
