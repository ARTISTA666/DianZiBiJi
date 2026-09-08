from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "gates" / "check_rag_evidence.py"
SPEC = importlib.util.spec_from_file_location("check_rag_evidence", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def report_and_manifest() -> tuple[dict, dict]:
    configuration = {
        "candidate_k": 30,
        "embedding_backend": "openai_compatible",
        "embedding_model": "BAAI/bge-m3",
        "embedding_dimension": 1024,
    }
    bindings = {
        "api_runtime": "rust-axum",
        "image_digest": "sha256:image",
        "git_revision": "a" * 40,
        "embedding_backend": "openai_compatible",
        "embedding_model": "BAAI/bge-m3",
        "embedding_dimension": 1024,
        "embedding_model_sha256": "b" * 64,
        "corpus_sha256": "c" * 64,
        "questions_sha256": "d" * 64,
        "retrieval_parameters_sha256": MODULE.canonical_sha256(configuration),
    }
    report = {
        "configuration": configuration,
        "corpus": {"sha256": bindings["corpus_sha256"]},
        "questions_sha256": bindings["questions_sha256"],
        "reproducibility_verified": True,
        "runtime": {
            "api_runtime": "rust-axum",
            "embedding_backend": "openai_compatible",
            "embedding_model": "BAAI/bge-m3",
            "embedding_dimension": 1024,
        },
        "evidence_bindings": bindings,
    }
    return report, {"evidence_bindings": deepcopy(bindings)}


def test_matching_runtime_evidence_passes() -> None:
    report, manifest = report_and_manifest()

    assert MODULE.validate(report, manifest) == []


def test_changed_image_digest_fails_closed() -> None:
    report, manifest = report_and_manifest()
    manifest["evidence_bindings"]["image_digest"] = "sha256:other"

    failures = MODULE.validate(report, manifest)

    assert "binding mismatch: image_digest" in failures


def test_legacy_report_is_not_accepted() -> None:
    report = json.loads((ROOT / "data/real/GSE111619/main-retrieval-evaluation/report.json").read_text())

    failures = MODULE.validate(report, {})

    assert "report.evidence_bindings is missing" in failures
    assert "report.reproducibility_verified must be true" in failures
