from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SCRIPT = ROOT / "scripts" / "freeze_final_maturity_evidence.py"
SPEC = importlib.util.spec_from_file_location("freeze_final_maturity_evidence", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_freezes_and_verifies_final_evidence_bundle(tmp_path: Path) -> None:
    files = []
    for name in ("release.json", "system.json", "production-config.json", "freeze.json", "long-soak.json", "tls.json", "backup.json"):
        path = tmp_path / name
        path.write_text(json.dumps({"name": name}), encoding="utf-8")
        files.append(path)
    manifest = tmp_path / "manifest.json"

    result = MODULE.freeze(files, manifest, tmp_path, replace=False)
    verified = MODULE.verify_manifest(manifest, tmp_path)

    assert result == {"ok": True, "output": str(manifest), "file_count": 7}
    assert verified["ok"] is True


def test_default_final_evidence_files_include_standalone_production_config() -> None:
    names = {path.name for path in MODULE.DEFAULT_FILES}

    assert "validation-results.json" in names
    assert "production-config-latest.json" in names


def test_verification_fails_after_final_evidence_changes(tmp_path: Path) -> None:
    source = tmp_path / "long-soak.json"
    source.write_text("before", encoding="utf-8")
    manifest = tmp_path / "manifest.json"

    MODULE.freeze([source], manifest, tmp_path, replace=False)
    source.write_text("after", encoding="utf-8")
    verified = MODULE.verify_manifest(manifest, tmp_path)

    assert verified["ok"] is False
    assert verified["checks"][0]["sha256_matches"] is False
