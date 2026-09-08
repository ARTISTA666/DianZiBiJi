from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SCRIPT = ROOT / "scripts" / "freeze_rag_evidence.py"
SPEC = importlib.util.spec_from_file_location("freeze_rag_evidence", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def report() -> dict:
    configuration = {
        "candidate_k": 30,
        "embedding_backend": "openai_compatible",
        "embedding_model": "BAAI/bge-m3",
        "embedding_dimension": 1024,
    }
    return {
        "configuration": configuration,
        "corpus": {"sha256": "c" * 64},
        "questions_sha256": "d" * 64,
        "reproducibility_verified": True,
        "runtime": {
            "api_runtime": "rust-axum",
            "embedding_backend": "openai_compatible",
            "embedding_model": "BAAI/bge-m3",
            "embedding_dimension": 1024,
        },
    }


def kwargs() -> dict[str, str]:
    return {
        "image_digest": "sha256:" + "a" * 64,
        "git_revision": "b" * 40,
        "embedding_model_sha256": "e" * 64,
    }


def test_freeze_writes_report_and_manifest(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report()), encoding="utf-8")
    frozen_report = tmp_path / "frozen-report.json"
    manifest_path = tmp_path / "runtime-manifest.json"

    manifest = MODULE.freeze(report_path, frozen_report, manifest_path, **kwargs())

    frozen = json.loads(frozen_report.read_text(encoding="utf-8"))
    assert frozen["evidence_bindings"] == manifest["evidence_bindings"]
    assert manifest["report_sha256"]
    assert MODULE.validate(frozen, json.loads(manifest_path.read_text(encoding="utf-8"))) == []


def test_freeze_rejects_non_rust_or_non_bge_report(tmp_path: Path) -> None:
    invalid = deepcopy(report())
    invalid["configuration"]["embedding_backend"] = "hash"
    invalid["configuration"]["embedding_model"] = "rust-hash-512-v1"
    invalid["configuration"]["embedding_dimension"] = 512
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(invalid), encoding="utf-8")

    try:
        MODULE.freeze(report_path, tmp_path / "frozen.json", tmp_path / "manifest.json", **kwargs())
    except ValueError as error:
        assert "embedding backend" in str(error)
    else:
        raise AssertionError("non-production embedding report was accepted")


def test_freeze_rejects_malformed_digest(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report()), encoding="utf-8")
    invalid = {**kwargs(), "image_digest": "sha256:not-a-digest"}

    try:
        MODULE.freeze(report_path, tmp_path / "frozen.json", tmp_path / "manifest.json", **invalid)
    except ValueError as error:
        assert "image_digest" in str(error)
    else:
        raise AssertionError("malformed image digest was accepted")


def test_freeze_rejects_runtime_configuration_drift(tmp_path: Path) -> None:
    invalid = report()
    invalid["runtime"]["embedding_dimension"] = 512
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(invalid), encoding="utf-8")

    try:
        MODULE.freeze(report_path, tmp_path / "frozen.json", tmp_path / "manifest.json", **kwargs())
    except ValueError as error:
        assert "runtime" in str(error)
    else:
        raise AssertionError("runtime/configuration drift was accepted")
