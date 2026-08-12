#!/usr/bin/env python3
"""Freeze a Rust runtime retrieval report with reproducibility bindings."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from check_rag_evidence import REQUIRED_BINDINGS, canonical_sha256, validate


SCHEMA = "full-system.rag-runtime-evidence-manifest"
SCHEMA_VERSION = 1
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
IMAGE_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
GIT_REVISION_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def require_hash(name: str, value: str) -> str:
    if not SHA256_RE.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")
    return value


def build_bindings(
    report: dict[str, Any],
    *,
    image_digest: str,
    git_revision: str,
    embedding_model_sha256: str,
) -> dict[str, Any]:
    configuration = report.get("configuration")
    corpus = report.get("corpus")
    if not isinstance(configuration, dict):
        raise ValueError("report.configuration is missing")
    if not isinstance(corpus, dict):
        raise ValueError("report.corpus is missing")
    runtime = report.get("runtime")
    if not isinstance(runtime, dict):
        raise ValueError("report.runtime is missing")
    embedding_backend = configuration.get("embedding_backend")
    embedding_model = configuration.get("embedding_model")
    embedding_dimension = configuration.get("embedding_dimension")
    if embedding_backend != "openai_compatible":
        raise ValueError("the release evaluator must use the openai_compatible embedding backend")
    if embedding_model != "BAAI/bge-m3":
        raise ValueError("the release evaluator must use BAAI/bge-m3")
    if embedding_dimension != 1024:
        raise ValueError("the release evaluator must use 1024-dimensional embeddings")
    expected_runtime = {
        "api_runtime": "rust-axum",
        "embedding_backend": embedding_backend,
        "embedding_model": embedding_model,
        "embedding_dimension": embedding_dimension,
    }
    if any(runtime.get(key) != value for key, value in expected_runtime.items()):
        raise ValueError("report.runtime does not match the retrieval configuration")
    if report.get("reproducibility_verified") is not True:
        raise ValueError("report.reproducibility_verified must be true")
    if not IMAGE_DIGEST_RE.fullmatch(image_digest):
        raise ValueError("image_digest must be sha256:<64 lowercase hex chars>")
    if not GIT_REVISION_RE.fullmatch(git_revision):
        raise ValueError("git_revision must be a 40- or 64-character lowercase hex revision")

    return {
        "api_runtime": "rust-axum",
        "image_digest": image_digest,
        "git_revision": git_revision,
        "embedding_backend": embedding_backend,
        "embedding_model": embedding_model,
        "embedding_dimension": embedding_dimension,
        "embedding_model_sha256": require_hash("embedding_model_sha256", embedding_model_sha256),
        "corpus_sha256": require_hash("corpus.sha256", str(corpus.get("sha256", ""))),
        "questions_sha256": require_hash("questions_sha256", str(report.get("questions_sha256", ""))),
        "retrieval_parameters_sha256": canonical_sha256(configuration),
    }


def freeze(
    report_path: Path,
    report_output: Path,
    manifest_output: Path,
    *,
    image_digest: str,
    git_revision: str,
    embedding_model_sha256: str,
) -> dict[str, Any]:
    report = load_object(report_path)
    bindings = build_bindings(
        report,
        image_digest=image_digest,
        git_revision=git_revision,
        embedding_model_sha256=embedding_model_sha256,
    )
    existing = report.get("evidence_bindings")
    if existing is not None and existing != bindings:
        raise ValueError("report already contains different evidence_bindings")

    frozen_report = {**report, "evidence_bindings": bindings}
    report_output.parent.mkdir(parents=True, exist_ok=True)
    report_output.write_text(
        json.dumps(frozen_report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "report_sha256": sha256_file(report_output),
        "report_path": str(report_output),
        "evidence_bindings": bindings,
        "required_bindings": list(REQUIRED_BINDINGS),
    }
    manifest_output.parent.mkdir(parents=True, exist_ok=True)
    manifest_output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    failures = validate(frozen_report, manifest)
    if failures:
        raise ValueError("frozen RAG evidence failed validation: " + "; ".join(failures))
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--report-output", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path, required=True)
    parser.add_argument("--image-digest", required=True)
    parser.add_argument("--git-revision", required=True)
    parser.add_argument("--embedding-model-sha256", required=True)
    args = parser.parse_args()
    manifest = freeze(
        args.report,
        args.report_output,
        args.manifest_output,
        image_digest=args.image_digest,
        git_revision=args.git_revision,
        embedding_model_sha256=args.embedding_model_sha256,
    )
    print(json.dumps({"passed": True, "manifest": str(args.manifest_output), "report_sha256": manifest["report_sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
