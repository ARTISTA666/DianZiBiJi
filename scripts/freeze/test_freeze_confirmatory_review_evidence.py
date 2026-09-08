from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SCRIPT = ROOT / "scripts" / "freeze_confirmatory_review_evidence.py"
SPEC = importlib.util.spec_from_file_location("freeze_confirmatory_review_evidence", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_freezes_and_verifies_review_evidence_bundle(tmp_path: Path) -> None:
    final_gate = tmp_path / "final-gate.json"
    freeze = tmp_path / "freeze.json"
    export = tmp_path / "export.csv"
    final_gate.write_text('{"passed": true}', encoding="utf-8")
    freeze.write_text("{}", encoding="utf-8")
    export.write_text("question_index,mode\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"

    result = MODULE.freeze([final_gate, freeze, export], manifest, tmp_path, replace=False)
    verified = MODULE.verify_manifest(manifest, tmp_path)

    assert result == {"ok": True, "output": str(manifest), "file_count": 3}
    assert verified["ok"] is True


def test_default_review_evidence_files_include_final_gate() -> None:
    names = {path.name for path in MODULE.DEFAULT_FILES}

    assert "final-maturity-gate-latest.json" in names
    assert "confirmatory-human-review-freeze.json" in names
    assert "confirmatory-human-review-export.csv" in names


def test_verification_fails_after_review_export_changes(tmp_path: Path) -> None:
    export = tmp_path / "export.csv"
    export.write_text("before", encoding="utf-8")
    manifest = tmp_path / "manifest.json"

    MODULE.freeze([export], manifest, tmp_path, replace=False)
    export.write_text("after", encoding="utf-8")
    verified = MODULE.verify_manifest(manifest, tmp_path)

    assert verified["ok"] is False
    assert verified["checks"][0]["sha256_matches"] is False
