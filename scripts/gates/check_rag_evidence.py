#!/usr/bin/env python3
"""Fail closed when a retrieval report is not bound to the deployed runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


REQUIRED_BINDINGS = (
    "api_runtime",
    "image_digest",
    "git_revision",
    "embedding_backend",
    "embedding_model",
    "embedding_dimension",
    "embedding_model_sha256",
    "corpus_sha256",
    "questions_sha256",
    "retrieval_parameters_sha256",
)


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def validate(report: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    report_bindings = report.get("evidence_bindings")
    manifest_bindings = manifest.get("evidence_bindings")
    if not isinstance(report_bindings, dict):
        failures.append("report.evidence_bindings is missing")
        report_bindings = {}
    if not isinstance(manifest_bindings, dict):
        failures.append("runtime manifest.evidence_bindings is missing")
        manifest_bindings = {}

    for key in REQUIRED_BINDINGS:
        report_value = report_bindings.get(key)
        manifest_value = manifest_bindings.get(key)
        if not report_value:
            failures.append(f"report binding missing: {key}")
        if not manifest_value:
            failures.append(f"runtime binding missing: {key}")
        if report_value and manifest_value and report_value != manifest_value:
            failures.append(f"binding mismatch: {key}")

    configuration = report.get("configuration")
    corpus = report.get("corpus")
    if report_bindings.get("api_runtime") != "rust-axum":
        failures.append("report is not identified as a deployed rust-axum run")
    runtime = report.get("runtime")
    if not isinstance(runtime, dict):
        failures.append("report.runtime is missing")
        runtime = {}
    for key in ("api_runtime", "embedding_backend", "embedding_model", "embedding_dimension"):
        if runtime.get(key) != report_bindings.get(key):
            failures.append(f"runtime.{key} does not match binding")
    if not isinstance(configuration, dict):
        failures.append("report.configuration is missing")
    else:
        for key in ("embedding_backend", "embedding_model", "embedding_dimension"):
            if configuration.get(key) != report_bindings.get(key):
                failures.append(f"configuration.{key} does not match binding")
        if report_bindings.get("retrieval_parameters_sha256") != canonical_sha256(configuration):
            failures.append("retrieval parameter hash does not match report.configuration")
    if not isinstance(corpus, dict) or corpus.get("sha256") != report_bindings.get("corpus_sha256"):
        failures.append("corpus hash does not match binding")
    if report.get("questions_sha256") != report_bindings.get("questions_sha256"):
        failures.append("question-set hash does not match binding")
    if report.get("reproducibility_verified") is not True:
        failures.append("report.reproducibility_verified must be true")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--runtime-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    manifest = json.loads(args.runtime_manifest.read_text(encoding="utf-8"))
    failures = validate(report, manifest)
    result = {
        "passed": not failures,
        "report": str(args.report),
        "runtime_manifest": str(args.runtime_manifest),
        "failures": failures,
    }
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
