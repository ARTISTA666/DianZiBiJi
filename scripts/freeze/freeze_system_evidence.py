#!/usr/bin/env python3
"""Freeze or verify the evidence files consumed by the maturity gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from freeze_preregistration import (
    build_manifest,
    sha256_file,
    verify_manifest as verify_file_manifest,
    write_manifest,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "output" / "release-evidence" / "maturity-evidence-manifest.json"
DEFAULT_FILES = [
    ROOT / "docs" / "system-evidence" / "validation-results.json",
    ROOT / "docs" / "system-evidence" / "validation-results.md",
    ROOT / "docs" / "system-evidence" / "load-smoke-latest.json",
    ROOT / "docs" / "system-evidence" / "soak-smoke-latest.json",
    ROOT / "docs" / "system-evidence" / "npm-audit-latest.json",
    ROOT / "docs" / "system-evidence" / "production-config-latest.json",
    ROOT / "docs" / "system-evidence" / "secret-hygiene-latest.json",
    ROOT / "docs" / "system-evidence" / "secret-rotation-latest.json",
    ROOT / "docs" / "system-evidence" / "backup-policy-latest.json",
    ROOT / "docs" / "system-evidence" / "monitoring-alerts-latest.json",
    ROOT / "docs" / "system-evidence" / "reverse-proxy-latest.json",
    ROOT / "docs" / "system-evidence" / "restore-drill-latest.json",
    ROOT / "data" / "real" / "GSE111619" / "main-retrieval-evaluation" / "report.json",
    ROOT / "data" / "real" / "GSE111619" / "main_v8_kg_holdout_experiment_report.json",
    ROOT / "data" / "real" / "GSE111619" / "main_v8_agent_probe_report.json",
]
SYSTEM_MANIFEST_SCHEMA = "full-system.system-evidence-manifest"
SYSTEM_MANIFEST_SCHEMA_VERSION = 1
SYSTEM_MANIFEST_GENERATOR = "freeze_system_evidence.py"
SYSTEM_MANIFEST_GENERATOR_VERSION = 1
REQUIRED_LOCKFILES = ("backend/Cargo.lock", "frontend/package-lock.json")
GIT_COMMIT = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
RUST_PILOT_READINESS_SCHEMA = "full-system.rust-retrieval-pilot-freeze-readiness"
RUST_PILOT_READINESS_SCHEMA_VERSION = 1
RUST_PILOT_READINESS_MANIFEST_SCHEMA = "full-system.rust-retrieval-pilot-freeze-readiness-manifest"
RUST_PILOT_READINESS_MANIFEST_VERSION = 1
RUST_PILOT_READINESS_GENERATOR = "freeze_system_evidence.py"
RUST_PILOT_READINESS_GENERATOR_VERSION = 1
RUST_PILOT_SCOPE_PREFIXES = (
    "docs/experiments/rust-retrieval-pilot-protocol-v1.md",
    "scripts/experiments/evaluate_rust_retrieval.py",
    "scripts/experiments/test_evaluate_rust_retrieval.py",
    "scripts/freeze/freeze_system_evidence.py",
    "scripts/freeze/test_freeze_system_evidence.py",
    "backend/openapi.json",
    "frontend/src/lib/api-schema.d.ts",
    "backend/src/",
    "scripts/render/update_rag_evidence_openapi.py",
    "scripts/render/test_update_rag_evidence_openapi.py",
    "docs/system-evidence/rust-runtime-contract-latest.json",
)
DEFAULT_RUST_PILOT_PROTOCOL = ROOT / "docs/experiments/rust-retrieval-pilot-protocol-v1.md"
DEFAULT_RUST_PILOT_QUESTIONS = ROOT / "data/real/GSE111619/gse111619_questions.json"
DEFAULT_RUST_PILOT_EVALUATOR = ROOT / "scripts/experiments/evaluate_rust_retrieval.py"
DEFAULT_RUST_PILOT_EVALUATOR_TESTS = ROOT / "scripts/experiments/test_evaluate_rust_retrieval.py"
DEFAULT_RUST_PILOT_OPENAPI = ROOT / "backend/openapi.json"
DEFAULT_RUST_PILOT_RUNTIME = ROOT / "docs/system-evidence/rust-runtime-contract-latest.json"
DEFAULT_RUST_PILOT_PREFLIGHT = ROOT / "docs/experiments/rust-retrieval-pilot-freeze-readiness-latest.json"
DEFAULT_RUST_PILOT_MANIFEST = ROOT / "docs/experiments/rust-retrieval-pilot-freeze-readiness-manifest-latest.json"
DEFAULT_RUST_PILOT_IMPLEMENTATION_FILES = (
    ROOT / "backend/src/rag.rs",
    ROOT / "backend/src/api/rag.rs",
    ROOT / "backend/src/api/mod.rs",
    ROOT / "backend/src/models.rs",
    ROOT / "backend/src/state.rs",
    ROOT / "backend/src/embedding.rs",
    ROOT / "backend/rust-toolchain.toml",
    ROOT / "backend/Cargo.lock",
    ROOT / "frontend/src/lib/api-schema.d.ts",
    ROOT / "frontend/src/lib/api.ts",
    ROOT / "scripts/experiments/evaluate_retrieval.py",
)


def _git(root: Path, arguments: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Unable to inspect the Git checkout") from exc
    if result.returncode != 0:
        raise RuntimeError(f"Git checkout inspection failed: {' '.join(arguments[:2])}")
    return result.stdout.strip()


def git_checkout_state(root: Path) -> dict[str, Any]:
    """Return the checked-out commit and cleanliness without exposing status contents."""

    root = root.resolve()
    repository_root = Path(_git(root, ["rev-parse", "--show-toplevel"])).resolve()
    if repository_root != root:
        raise RuntimeError("Manifest root must be the Git repository root")
    commit = _git(root, ["rev-parse", "--verify", "HEAD^{commit}"]).lower()
    if not GIT_COMMIT.fullmatch(commit):
        raise RuntimeError("Git returned an invalid commit identifier")
    status = _git(
        root,
        [
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            ".",
        ],
    )
    return {"git_commit": commit, "worktree_clean": not bool(status)}


def rust_pilot_checkout_state(root: Path) -> dict[str, Any]:
    """Read checkout provenance for the explicit Rust-pilot readiness mode.

    This is intentionally separate from ``git_checkout_state`` so the default
    system-evidence manifest keeps its existing schema and byte-level output.
    """

    root = root.resolve()
    repository_root = Path(_git(root, ["rev-parse", "--show-toplevel"])).resolve()
    if repository_root != root:
        raise RuntimeError("Manifest root must be the Git repository root")
    base_revision = _git(root, ["rev-parse", "--verify", "HEAD^{commit}"]).lower()
    if not GIT_COMMIT.fullmatch(base_revision):
        raise RuntimeError("Git returned an invalid commit identifier")
    status = _git(
        root,
        ["status", "--porcelain=v1", "--untracked-files=all", "--", "."],
    )
    tracked_dirty: list[str] = []
    untracked: list[str] = []
    for line in status.splitlines():
        if not line:
            continue
        if line.startswith("?? "):
            untracked.append(line[3:])
        else:
            tracked_dirty.append(line)
    in_scope_untracked = sorted(
        path
        for path in untracked
        if any(path == prefix or path.startswith(prefix) for prefix in RUST_PILOT_SCOPE_PREFIXES)
    )
    return {
        "base_revision": base_revision,
        "tracked_worktree_clean": not tracked_dirty,
        "worktree_clean": not status,
        "in_scope_untracked_files": in_scope_untracked,
    }


def _sha256_file_or_none(path: Path) -> str | None:
    if not path.is_file():
        return None
    return sha256_file(path)


def _read_runtime_contract(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"runtime": {}, "_read_error": f"runtime contract is unreadable: {path}: {exc}"}
    if not isinstance(value, dict):
        return {"runtime": {}, "_read_error": "runtime contract must be a JSON object"}
    return value


def _readiness_check(
    value: Any,
    *,
    status: str,
    reason: str | None = None,
    evidence: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"status": status, "value": value}
    if reason is not None:
        result["reason"] = reason
    if evidence is not None:
        result["evidence"] = evidence
    return result


def _hash_check(path: Path) -> dict[str, Any]:
    digest = _sha256_file_or_none(path)
    if digest is None:
        return _readiness_check(None, status="FAIL", reason=f"missing input: {path}", evidence=str(path))
    return _readiness_check(digest, status="PASS", evidence=str(path))


def _relative_checkout_path(path: Path, root: Path) -> str:
    """Return a manifest path that is anchored to this checkout, never to /tmp."""

    resolved_root = root.resolve()
    resolved_path = path.resolve()
    try:
        relative = resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"readiness input is outside the checkout: {path}") from exc
    return relative.as_posix()


def _required_input_records(paths: list[Path] | tuple[Path, ...], root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in paths:
        relative_path = _relative_checkout_path(path, root)
        digest = _sha256_file_or_none(path)
        records.append(
            {
                "path": relative_path,
                "sha256": digest,
                "status": "PASS" if digest is not None else "FAIL",
            }
        )
    return records


def _gate_evidence_check(path: Path | None, gate: str) -> dict[str, Any]:
    if path is None:
        return _readiness_check(
            None,
            status="BLOCKED",
            reason=f"no current {gate} gate evidence was supplied",
        )
    if not path.is_file():
        return _readiness_check(None, status="BLOCKED", reason=f"missing gate evidence: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _readiness_check(None, status="FAIL", reason=f"invalid {gate} gate evidence: {exc}", evidence=str(path))
    if not isinstance(payload, dict):
        return _readiness_check(None, status="FAIL", reason=f"{gate} gate evidence must be an object", evidence=str(path))
    passed = payload.get("passed") is True or payload.get("status") == "PASS"
    generator = payload.get("generator")
    generator_version = payload.get("generator_version")
    command = payload.get("command") or payload.get("test_command")
    report_path_value = payload.get("report_path")
    report_path = Path(report_path_value) if isinstance(report_path_value, str) else None
    if report_path is not None and not report_path.is_absolute():
        report_path = path.parent / report_path
    report_sha256 = payload.get("report_sha256")
    actual_sha256 = sha256_file(report_path) if report_path is not None and report_path.is_file() else None
    if (
        not passed
        or not isinstance(generator, str)
        or not generator
        or not isinstance(generator_version, (str, int))
        or not isinstance(command, str)
        or not command
        or not isinstance(report_sha256, str)
        or not SHA256.fullmatch(report_sha256)
        or actual_sha256 is None
        or report_sha256 != actual_sha256
    ):
        return _readiness_check(
            payload.get("status", payload.get("passed")),
            status="BLOCKED",
            reason=f"{gate} evidence lacks a current hash-bound report, generator version, or command",
            evidence=str(path),
        )
    return _readiness_check(payload.get("status", "PASS"), status="PASS", evidence=str(path))


def build_rust_pilot_readiness(
    *,
    root: Path,
    protocol: Path,
    questions: Path,
    evaluator: Path,
    openapi: Path,
    runtime_contract: Path,
    evaluator_tests: Path | None = None,
    checkout: dict[str, Any] | None = None,
    image_digest: str | None = None,
    corpus_snapshot_hash: str | None = None,
    graph_snapshot_hash: str | None = None,
    g5a_evidence: Path | None = None,
    g5b_evidence: Path | None = None,
    implementation_files: list[Path] | tuple[Path, ...] = (),
) -> dict[str, Any]:
    """Build a read-only, non-pilot freeze-readiness report.

    The report deliberately distinguishes the current HEAD (``base_revision``)
    from a runtime/build-bound ``app_revision``.  It never derives corpus or
    graph identity from local files and never performs HTTP requests.
    """

    root = root.resolve()
    checkout = checkout or rust_pilot_checkout_state(root)
    runtime_payload = _read_runtime_contract(runtime_contract)
    runtime = runtime_payload.get("runtime") if isinstance(runtime_payload.get("runtime"), dict) else {}
    base_revision = checkout.get("base_revision")
    app_revision = runtime_payload.get("revision")
    app_revision_bound = (
        isinstance(app_revision, str)
        and bool(GIT_COMMIT.fullmatch(app_revision.lower()))
        and app_revision.lower() == str(base_revision).lower()
        and app_revision.lower() != "unversioned"
    )
    image_bound = isinstance(image_digest, str) and bool(re.fullmatch(r"sha256:[0-9a-f]{64}", image_digest))
    runtime_value = runtime.get("api_runtime")
    backend = runtime.get("embedding_backend")
    model = runtime.get("embedding_model")
    dimension = runtime.get("embedding_dimension")
    formal_embedding = backend == "openai_compatible" and model == "BAAI/bge-m3" and dimension == 1024
    implementation_records = _required_input_records(implementation_files, root)
    implementation_missing = [
        record["path"] for record in implementation_records if record["sha256"] is None
    ]
    checks: dict[str, dict[str, Any]] = {
        "base_revision": _readiness_check(
            base_revision,
            status="PASS" if isinstance(base_revision, str) and GIT_COMMIT.fullmatch(base_revision) else "FAIL",
            reason=None if isinstance(base_revision, str) and GIT_COMMIT.fullmatch(base_revision) else "HEAD is not a full commit SHA",
        ),
        "app_revision": _readiness_check(
            app_revision if isinstance(app_revision, str) and app_revision != "unversioned" else None,
            status="PASS" if app_revision_bound else "FAIL",
            reason=None if app_revision_bound else "runtime app_revision is missing, unversioned, or does not equal base_revision",
            evidence=str(runtime_contract),
        ),
        "tracked_worktree_clean": _readiness_check(
            checkout.get("tracked_worktree_clean"),
            status="PASS" if checkout.get("tracked_worktree_clean") is True else "FAIL",
            reason=None if checkout.get("tracked_worktree_clean") is True else "tracked files are modified",
        ),
        "in_scope_untracked_files": _readiness_check(
            checkout.get("in_scope_untracked_files", []),
            status="PASS" if not checkout.get("in_scope_untracked_files", []) else "FAIL",
            reason=None if not checkout.get("in_scope_untracked_files", []) else "in-scope untracked candidate files exist",
        ),
        "runtime": _readiness_check(
            runtime_value,
            status="PASS" if runtime_value == "rust-axum" else "FAIL",
            reason=None if runtime_value == "rust-axum" else "runtime is not identified as rust-axum",
            evidence=str(runtime_contract),
        ),
        "image_digest": _readiness_check(
            image_digest,
            status="PASS" if image_bound else "BLOCKED",
            reason=None if image_bound else "no immutable sha256 image digest was supplied",
        ),
        "embedding_backend": _readiness_check(
            backend,
            status="PASS" if formal_embedding else "BLOCKED",
            reason=None if formal_embedding else "runtime is not a hash-bound formal BGE-M3 artifact",
            evidence=str(runtime_contract),
        ),
        "embedding_model": _readiness_check(
            model,
            status="PASS" if formal_embedding else "BLOCKED",
            reason=None if formal_embedding else "runtime model is not a formally bound BAAI/bge-m3 artifact",
            evidence=str(runtime_contract),
        ),
        "embedding_dimension": _readiness_check(
            dimension,
            status="PASS" if formal_embedding else "BLOCKED",
            reason=None if formal_embedding else "embedding dimension is not the formally bound 1024-dimensional model",
            evidence=str(runtime_contract),
        ),
        "protocol_sha256": _hash_check(protocol),
        "questions_sha256": _hash_check(questions),
        "evaluator_sha256": _hash_check(evaluator),
        "openapi_sha256": _hash_check(openapi),
        "runtime_contract_sha256": _hash_check(runtime_contract),
        "implementation_files": _readiness_check(
            implementation_records,
            status="FAIL" if implementation_missing else "PASS",
            reason=(
                "required implementation input is missing: "
                + ", ".join(implementation_missing)
                if implementation_missing
                else None
            ),
        ),
        "corpus_snapshot_hash": _readiness_check(
            corpus_snapshot_hash,
            status="PASS" if isinstance(corpus_snapshot_hash, str) and SHA256.fullmatch(corpus_snapshot_hash) else "FAIL",
            reason=None if isinstance(corpus_snapshot_hash, str) and SHA256.fullmatch(corpus_snapshot_hash) else "no formally frozen database corpus snapshot was supplied",
        ),
        "graph_snapshot_hash": _readiness_check(
            graph_snapshot_hash,
            status="PASS" if isinstance(graph_snapshot_hash, str) and SHA256.fullmatch(graph_snapshot_hash) else "FAIL",
            reason=None if isinstance(graph_snapshot_hash, str) and SHA256.fullmatch(graph_snapshot_hash) else "no formally frozen database graph snapshot was supplied",
        ),
        "G5A": _gate_evidence_check(g5a_evidence, "G5A"),
        "G5B": _gate_evidence_check(g5b_evidence, "G5B"),
    }
    if evaluator_tests is not None:
        checks["evaluator_tests_sha256"] = _hash_check(evaluator_tests)
    hard_failures = [name for name, check in checks.items() if check["status"] in {"FAIL", "BLOCKED"}]
    return {
        "schema": RUST_PILOT_READINESS_SCHEMA,
        "schema_version": RUST_PILOT_READINESS_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "protocol_status": "DRAFT",
        "lifecycle": "NOT_FROZEN",
        "base_revision": base_revision,
        "app_revision": app_revision if isinstance(app_revision, str) and app_revision != "unversioned" else None,
        "tracked_worktree_clean": checkout.get("tracked_worktree_clean"),
        "in_scope_untracked_files": checkout.get("in_scope_untracked_files", []),
        "runtime": runtime_value,
        "image_digest": image_digest,
        "embedding": {
            "backend": backend,
            "model": model,
            "dimension": dimension,
        },
        "input_hashes": {
            "protocol": checks["protocol_sha256"]["value"],
            "questions": checks["questions_sha256"]["value"],
            "evaluator": checks["evaluator_sha256"]["value"],
            "evaluator_tests": checks.get("evaluator_tests_sha256", {}).get("value"),
            "openapi": checks["openapi_sha256"]["value"],
            "runtime_contract": checks["runtime_contract_sha256"]["value"],
            "implementation_files": implementation_records,
            "corpus": corpus_snapshot_hash,
            "graph": graph_snapshot_hash,
        },
        "overall_verdict": "BLOCKED" if hard_failures else "PASS",
        "freeze_requirements_complete": not hard_failures,
        "checks": checks,
        "gates": {"G5A": checks["G5A"], "G5B": checks["G5B"]},
        "blockers": hard_failures,
        "scope": "INTERNAL_EXPLORATORY Rust retrieval-only candidate; no retrieval queries executed",
    }


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def write_rust_pilot_readiness(
    readiness: dict[str, Any],
    *,
    output: Path,
    manifest_output: Path,
    manifest_inputs: list[Path],
    gate_script: Path,
    root: Path,
) -> dict[str, Any]:
    """Persist readiness and its non-self-referential input manifest atomically."""

    rendered = json.dumps(readiness, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    _write_text_atomic(output, rendered)
    root = root.resolve()
    files = []
    for path in [*manifest_inputs, gate_script]:
        relative_path = _relative_checkout_path(path, root)
        digest = _sha256_file_or_none(path)
        files.append(
            {
                "path": relative_path,
                "sha256": digest,
                "status": "PASS" if digest is not None else "FAIL",
            }
        )
    input_failures = [item["path"] for item in files if item["sha256"] is None]
    manifest = {
        "schema": RUST_PILOT_READINESS_MANIFEST_SCHEMA,
        "schema_version": RUST_PILOT_READINESS_MANIFEST_VERSION,
        "generator": RUST_PILOT_READINESS_GENERATOR,
        "generator_version": RUST_PILOT_READINESS_GENERATOR_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "preflight_path": _relative_checkout_path(output, root),
        "preflight_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "files": files,
        "local_manifest_inputs_complete": not input_failures,
        "freeze_requirements_complete": (
            readiness.get("freeze_requirements_complete") is True and not input_failures
        ),
        "input_failures": input_failures,
        "overall_verdict": readiness.get("overall_verdict"),
        "lifecycle": readiness.get("lifecycle"),
    }
    _write_text_atomic(
        manifest_output,
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return {"output": str(output), "manifest": str(manifest_output), "overall_verdict": readiness.get("overall_verdict")}


def run_rust_pilot_readiness(args: argparse.Namespace) -> int:
    """Run the explicit readiness audit; zero means report generation succeeded."""

    readiness = build_rust_pilot_readiness(
        root=args.root,
        protocol=args.protocol,
        questions=args.questions,
        evaluator=args.evaluator,
        evaluator_tests=args.evaluator_tests,
        openapi=args.openapi,
        runtime_contract=args.runtime_contract,
        image_digest=args.image_digest,
        corpus_snapshot_hash=args.corpus_snapshot_hash,
        graph_snapshot_hash=args.graph_snapshot_hash,
        g5a_evidence=args.g5a_evidence,
        g5b_evidence=args.g5b_evidence,
        implementation_files=DEFAULT_RUST_PILOT_IMPLEMENTATION_FILES,
    )
    manifest_inputs = [
        args.protocol,
        args.questions,
        args.evaluator,
        args.evaluator_tests,
        args.openapi,
        args.runtime_contract,
        *DEFAULT_RUST_PILOT_IMPLEMENTATION_FILES,
    ]
    result = write_rust_pilot_readiness(
        readiness,
        output=args.preflight_output,
        manifest_output=args.manifest_output,
        manifest_inputs=[path for path in manifest_inputs if path is not None],
        gate_script=Path(__file__),
        root=args.root,
    )
    print(json.dumps({**result, "protocol_status": readiness["protocol_status"]}, ensure_ascii=False, sort_keys=True))
    return 0


def _lockfile_path(root: Path, relative_path: str) -> Path:
    path = (root / relative_path).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise FileNotFoundError(f"Required lockfile is missing: {relative_path}")
    return path


def capture_provenance(root: Path) -> dict[str, Any]:
    root = root.resolve()
    checkout = git_checkout_state(root)
    if checkout.get("worktree_clean") is not True:
        raise RuntimeError("Refusing to freeze system evidence from a dirty Git checkout")
    commit = checkout.get("git_commit")
    if not isinstance(commit, str) or not GIT_COMMIT.fullmatch(commit):
        raise RuntimeError("Refusing to freeze system evidence without a valid Git commit")
    return {
        "git_commit": commit,
        "git_worktree_clean": True,
        "lockfiles": {
            relative_path: {"sha256": sha256_file(_lockfile_path(root, relative_path))}
            for relative_path in REQUIRED_LOCKFILES
        },
    }


def build_system_manifest(files: list[Path], root: Path) -> dict[str, Any]:
    root = root.resolve()
    provenance = capture_provenance(root)
    manifest = build_manifest(files, root)
    manifest.update(
        {
            "schema": SYSTEM_MANIFEST_SCHEMA,
            "schema_version": SYSTEM_MANIFEST_SCHEMA_VERSION,
            "generator": SYSTEM_MANIFEST_GENERATOR,
            "generator_version": SYSTEM_MANIFEST_GENERATOR_VERSION,
            "provenance": provenance,
        }
    )
    return manifest


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _lockfile_verification(
    root: Path,
    recorded_lockfiles: Any,
) -> tuple[list[dict[str, Any]], bool]:
    recorded = recorded_lockfiles if isinstance(recorded_lockfiles, dict) else {}
    checks: list[dict[str, Any]] = []
    for relative_path in REQUIRED_LOCKFILES:
        entry = recorded.get(relative_path)
        expected = entry.get("sha256") if isinstance(entry, dict) else None
        try:
            actual_path = _lockfile_path(root, relative_path)
        except FileNotFoundError:
            actual_path = None
        actual = sha256_file(actual_path) if actual_path is not None else None
        checks.append(
            {
                "path": relative_path,
                "exists": actual_path is not None,
                "expected_sha256": expected,
                "actual_sha256": actual,
                "sha256_matches": bool(
                    isinstance(expected, str)
                    and SHA256.fullmatch(expected)
                    and actual == expected
                ),
            }
        )
    exact_paths = set(recorded) == set(REQUIRED_LOCKFILES)
    return checks, exact_paths and all(item["sha256_matches"] for item in checks)


def verify_manifest(manifest_path: Path, root: Path | None = None) -> dict[str, Any]:
    """Verify evidence files and bind the manifest to the current clean checkout."""

    root = (root or Path.cwd()).resolve()
    try:
        file_report = verify_file_manifest(manifest_path, root)
    except Exception:
        file_report = {
            "verified_at_utc": datetime.now(timezone.utc).isoformat(),
            "manifest": str(manifest_path.resolve()),
            "ok": False,
            "file_count": 0,
            "checks": [
                {
                    "path": str(manifest_path),
                    "inside_root": True,
                    "exists": manifest_path.is_file(),
                    "error": "invalid file manifest structure",
                }
            ],
        }
    file_manifest_ok = bool(file_report.get("ok"))
    manifest = _load_manifest(manifest_path)
    provenance = manifest.get("provenance") if isinstance(manifest.get("provenance"), dict) else {}
    expected_commit = provenance.get("git_commit")
    recorded_clean = provenance.get("git_worktree_clean") is True
    checkout_error: str | None = None
    try:
        checkout = git_checkout_state(root)
    except (OSError, RuntimeError, ValueError) as exc:
        checkout = {}
        checkout_error = str(exc)
    current_commit = checkout.get("git_commit")
    current_clean = checkout.get("worktree_clean") is True
    commit_matches = bool(
        isinstance(expected_commit, str)
        and GIT_COMMIT.fullmatch(expected_commit)
        and isinstance(current_commit, str)
        and expected_commit == current_commit
    )
    lockfile_checks, lockfiles_match = _lockfile_verification(root, provenance.get("lockfiles"))
    schema_matches = bool(
        manifest.get("schema") == SYSTEM_MANIFEST_SCHEMA
        and manifest.get("schema_version") == SYSTEM_MANIFEST_SCHEMA_VERSION
    )
    generator_matches = bool(
        manifest.get("generator") == SYSTEM_MANIFEST_GENERATOR
        and manifest.get("generator_version") == SYSTEM_MANIFEST_GENERATOR_VERSION
    )
    provenance_ok = bool(
        schema_matches
        and generator_matches
        and recorded_clean
        and current_clean
        and commit_matches
        and lockfiles_match
    )
    file_report["file_manifest_ok"] = file_manifest_ok
    file_report["provenance"] = {
        "ok": provenance_ok,
        "schema_matches": schema_matches,
        "generator_matches": generator_matches,
        "recorded_worktree_clean": recorded_clean,
        "current_worktree_clean": current_clean,
        "expected_git_commit": expected_commit,
        "current_git_commit": current_commit,
        "git_commit_matches": commit_matches,
        "lockfiles_match": lockfiles_match,
        "lockfile_checks": lockfile_checks,
        "checkout_error": checkout_error,
    }
    file_report["ok"] = file_manifest_ok and provenance_ok
    return file_report


def freeze(files: list[Path], output: Path, root: Path, replace: bool) -> dict:
    manifest = build_system_manifest(files, root)
    write_manifest(manifest, output, replace=replace)
    return {"ok": True, "output": str(output), "file_count": len(manifest["files"])}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rust-pilot-readiness",
        action="store_true",
        help="Run the read-only Rust retrieval pilot freeze-readiness audit.",
    )
    parser.add_argument("files", nargs="*", type=Path, help="Override the default maturity evidence file list.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--verify", type=Path, help="Verify an existing evidence manifest instead of freezing.")
    parser.add_argument("--replace", action="store_true", help="Replace an existing manifest intentionally.")
    parser.add_argument("--protocol", type=Path, default=DEFAULT_RUST_PILOT_PROTOCOL)
    parser.add_argument("--questions", type=Path, default=DEFAULT_RUST_PILOT_QUESTIONS)
    parser.add_argument("--evaluator", type=Path, default=DEFAULT_RUST_PILOT_EVALUATOR)
    parser.add_argument("--evaluator-tests", type=Path, default=DEFAULT_RUST_PILOT_EVALUATOR_TESTS)
    parser.add_argument("--openapi", type=Path, default=DEFAULT_RUST_PILOT_OPENAPI)
    parser.add_argument("--runtime-contract", type=Path, default=DEFAULT_RUST_PILOT_RUNTIME)
    parser.add_argument("--preflight-output", type=Path, default=DEFAULT_RUST_PILOT_PREFLIGHT)
    parser.add_argument("--manifest-output", type=Path, default=DEFAULT_RUST_PILOT_MANIFEST)
    parser.add_argument("--image-digest")
    parser.add_argument("--corpus-snapshot-hash")
    parser.add_argument("--graph-snapshot-hash")
    parser.add_argument("--g5a-evidence", type=Path)
    parser.add_argument("--g5b-evidence", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.rust_pilot_readiness:
        return run_rust_pilot_readiness(args)
    if args.verify:
        report = verify_manifest(args.verify, args.root)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1
    report = freeze(args.files or DEFAULT_FILES, args.output, args.root, args.replace)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
