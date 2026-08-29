#!/usr/bin/env python3
"""Create and verify a fail-closed, pre-run G5A runtime-freeze package."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "full-system.rust-g5a-runtime-freeze"
MANIFEST_SCHEMA = "full-system.rust-g5a-runtime-freeze-manifest"
REVISION = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
IMAGE_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
# The current protocol has no authorized completed status; awaiting authority is not ready.
AUTHORIZED_FREEZE_STATUSES: frozenset[str] = frozenset()
DEFAULT_RUNTIME_CONTRACT = ROOT / "docs/system-evidence/rust-runtime-contract-latest.json"
DEFAULT_RUNTIME_CONFIG = ROOT / "docs/system-evidence/runtime-config-latest.json"
DEFAULT_CONTAINER_IMAGE = ROOT / "docs/system-evidence/container-image-latest.json"
DEFAULT_CORPUS_MANIFEST = ROOT / "data/real/experiment-5/corpus-manifest.json"


def sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return None, str(exc)
    return (value, None) if isinstance(value, dict) else (None, "JSON root must be an object")


def git(root: Path, args: list[str]) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False, timeout=10)
    if result.returncode:
        raise RuntimeError(f"git inspection failed: {' '.join(args)}")
    return result.stdout.strip()


def checkout_state(root: Path) -> dict[str, Any]:
    root = root.resolve()
    if Path(git(root, ["rev-parse", "--show-toplevel"])).resolve() != root:
        raise RuntimeError("root must be the Git repository root")
    head = git(root, ["rev-parse", "--verify", "HEAD^{commit}"]).lower()
    if not REVISION.fullmatch(head):
        raise RuntimeError("HEAD is not a full commit SHA")
    status = git(root, ["status", "--porcelain=v1", "--untracked-files=all", "--", "."])
    return {
        "head_revision": head,
        "tracked_worktree_clean": not any(line and not line.startswith("?? ") for line in status.splitlines()),
        "worktree_clean": not bool(status),
    }


def source(path: Path, root: Path) -> dict[str, Any]:
    resolved, root = path.resolve(), root.resolve()
    inside = resolved.is_relative_to(root)
    digest = sha256_file(resolved) if inside else None
    result: dict[str, Any] = {
        "path": resolved.relative_to(root).as_posix() if inside else str(resolved),
        "inside_root": inside,
        "exists": digest is not None,
        "sha256": digest,
        "status": "PASS" if digest else "BLOCKED",
    }
    if not inside:
        result["reason"] = "input must be inside repository root"
    elif not digest:
        result["reason"] = "input is missing or unreadable"
    return result


def binding(name: str, value: Any, evidence: dict[str, Any], passed: bool, reason: str | None = None) -> dict[str, Any]:
    result = {"name": name, "value": value, "source": evidence, "status": "PASS" if passed else "BLOCKED"}
    if reason:
        result["reason"] = reason
    return result


def corpus_snapshot_sha256(entries: list[tuple[str, str]]) -> str:
    canonical = [{"path": path, "sha256": digest} for path, digest in sorted(entries)]
    encoded = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def artifact_binding(
    name: str,
    path: Path,
    root: Path,
    value: Callable[[dict[str, Any]], Any],
    valid: Callable[[dict[str, Any]], bool],
    missing_reason: str,
) -> dict[str, Any]:
    evidence = source(path, root)
    payload, error = read_json(path) if evidence["exists"] else (None, evidence.get("reason"))
    passed = bool(evidence["exists"] and payload is not None and valid(payload))
    return binding(name, value(payload) if payload else None, evidence, passed, None if passed else error or missing_reason)


def corpus_binding(path: Path, root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    evidence = source(path, root)
    payload, error = read_json(path) if evidence["exists"] else (None, evidence.get("reason"))
    extra_sources: list[dict[str, Any]] = []
    snapshot = payload.get("snapshot_sha256") or payload.get("corpus_sha256") if payload else None
    dataset_id = payload.get("dataset_id") or payload.get("corpus_id") if payload else None
    provenance = payload.get("provenance") if payload else None
    records = payload.get("files") if payload else None
    valid = (
        evidence["exists"]
        and payload is not None
        and isinstance(dataset_id, str)
        and bool(dataset_id.strip())
        and isinstance(provenance, (str, dict))
        and bool(provenance)
        and isinstance(snapshot, str)
        and bool(SHA256.fullmatch(snapshot))
        and isinstance(records, list)
        and bool(records)
    )
    checked_records: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    if valid:
        for record in records:
            relative = record.get("path") if isinstance(record, dict) else None
            expected = record.get("sha256") if isinstance(record, dict) else None
            candidate = root / relative if isinstance(relative, str) and not Path(relative).is_absolute() else root / "<invalid>"
            file_source = source(candidate, root)
            actual = file_source.get("sha256")
            normalized = file_source.get("path") if file_source.get("inside_root") else None
            record_valid = (
                isinstance(relative, str)
                and bool(relative)
                and isinstance(normalized, str)
                and normalized not in seen_paths
                and isinstance(expected, str)
                and bool(SHA256.fullmatch(expected))
                and file_source["exists"]
                and actual == expected
            )
            if isinstance(normalized, str):
                seen_paths.add(normalized)
            checked_records.append({"path": relative, "normalized": normalized, "sha256_matches": record_valid, "source": file_source})
            extra_sources.append(file_source)
            valid = valid and record_valid
    snapshot_entries = [
        (item["normalized"], item["source"]["sha256"])
        for item in checked_records
        if item["sha256_matches"] and isinstance(item["normalized"], str) and isinstance(item["source"].get("sha256"), str)
    ]
    computed_snapshot = corpus_snapshot_sha256(snapshot_entries) if valid else None
    snapshot_matches = bool(valid and computed_snapshot == snapshot)
    valid = valid and snapshot_matches
    value = {
        "manifest_sha256": evidence.get("sha256"),
        "snapshot_sha256": snapshot,
        "computed_snapshot_sha256": computed_snapshot,
        "snapshot_matches": snapshot_matches,
        "dataset_id": dataset_id,
        "file_count": len(records) if isinstance(records, list) else 0,
    }
    if checked_records:
        value["files"] = [{"path": item["normalized"], "sha256_matches": item["sha256_matches"]} for item in checked_records]
    reason = None if valid else error or "corpus manifest snapshot must equal the digest of normalized real file paths and recomputed SHA-256 entries"
    return binding("corpus_manifest", value if evidence["exists"] else None, evidence, valid, reason), extra_sources


def authority_is_well_formed(authority: Any) -> bool:
    if not isinstance(authority, dict):
        return False
    authority_id = authority.get("authority_id")
    signature = authority.get("signature")
    if not isinstance(authority_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", authority_id):
        return False
    if not isinstance(signature, str) or not signature.strip() or any(char.isspace() for char in signature):
        return False
    return all(
        isinstance(value, str) and bool(SHA256.fullmatch(value))
        for key, value in authority.items()
        if key == "sha256" or key.endswith("_sha256")
    )


def build_package(
    *,
    root: Path,
    runtime_contract: Path,
    runtime_config: Path,
    container_image: Path,
    corpus_manifest: Path | None,
    authority_evidence: Path | None = None,
    checkout: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    checkout = checkout or checkout_state(root)
    contract_source = source(runtime_contract, root)
    contract, contract_error = read_json(runtime_contract) if contract_source["exists"] else (None, contract_source.get("reason"))
    app_revision = contract.get("app_revision") if contract else None
    runtime_revision = contract.get("runtime_revision") if contract else None
    head = checkout.get("head_revision")
    revisions_match = (
        all(isinstance(value, str) and REVISION.fullmatch(value.lower()) for value in (app_revision, runtime_revision, head))
        and app_revision.lower() == runtime_revision.lower() == head.lower()
    )
    checks: dict[str, dict[str, Any]] = {
        "runtime_contract": binding(
            "runtime_contract",
            {"sha256": contract_source["sha256"]},
            contract_source,
            bool(contract_source["exists"] and contract),
            contract_error,
        ),
        "app_revision": binding(
            "app_revision",
            app_revision if isinstance(app_revision, str) and REVISION.fullmatch(app_revision.lower()) else None,
            contract_source,
            revisions_match,
            "runtime contract must explicitly export app_revision equal to runtime_revision and checkout HEAD",
        ),
        "runtime_revision": binding(
            "runtime_revision",
            runtime_revision if isinstance(runtime_revision, str) and REVISION.fullmatch(runtime_revision.lower()) else None,
            contract_source,
            revisions_match,
            "runtime contract must explicitly export runtime_revision equal to app_revision and checkout HEAD",
        ),
        "revision_match": binding(
            "revision_match",
            {"checkout_head": head, "app_revision": app_revision, "runtime_revision": runtime_revision},
            contract_source,
            revisions_match,
            "the three revision identities do not match",
        ),
        "runtime": binding(
            "runtime",
            contract.get("runtime", {}).get("api_runtime") if isinstance(contract, dict) and isinstance(contract.get("runtime"), dict) else None,
            contract_source,
            bool(contract and isinstance(contract.get("runtime"), dict) and contract["runtime"].get("api_runtime") == "rust-axum"),
            "runtime contract must identify the Rust Axum runtime",
        ),
        "runtime_config": artifact_binding(
            "runtime_config",
            runtime_config,
            root,
            lambda payload: {"sha256": sha256_file(runtime_config), "app_revision": payload.get("app_revision"), "runtime_revision": payload.get("runtime_revision")},
            lambda payload: all(payload.get(key) == expected for key, expected in (("app_revision", app_revision), ("runtime_revision", runtime_revision))),
            "runtime config must explicitly bind both revisions",
        ),
        "container_image": artifact_binding(
            "container_image",
            container_image,
            root,
            lambda payload: {"image_digest": payload.get("image_digest")},
            lambda payload: bool(
                isinstance(payload.get("image_digest"), str)
                and IMAGE_DIGEST.fullmatch(payload["image_digest"])
                and payload.get("app_revision") == app_revision
                and payload.get("runtime_revision") == runtime_revision
                and payload.get("oci_revision") == app_revision
                and payload.get("endpoint_revision") == app_revision
                and isinstance(payload.get("projection_sha256"), str)
                and SHA256.fullmatch(payload["projection_sha256"])
            ),
            "container image evidence requires immutable digest, OCI/endpoint revisions, and a stable projection hash",
        ),
        "worktree_clean": binding(
            "worktree_clean",
            checkout.get("worktree_clean"),
            {"path": ".git", "status": "PASS" if checkout.get("worktree_clean") else "BLOCKED"},
            checkout.get("worktree_clean") is True,
            "all tracked and untracked checkout changes must be absent before formal run",
        ),
    }
    extra_sources: list[dict[str, Any]] = []
    if corpus_manifest is None:
        checks["corpus_manifest"] = binding("corpus_manifest", None, {"path": None, "status": "BLOCKED"}, False, "no real corpus manifest was supplied")
    else:
        checks["corpus_manifest"], extra_sources = corpus_binding(corpus_manifest, root)
    if authority_evidence is None:
        checks["external_authority"] = {"name": "external_authority", "value": None, "status": "AWAITING_AUTHORITY", "reason": "no external trust-root evidence supplied; package cannot self-authorize"}
    else:
        authority_source = source(authority_evidence, root)
        authority, error = read_json(authority_evidence) if authority_source["exists"] else (None, authority_source.get("reason"))
        authority_valid = authority_is_well_formed(authority)
        checks["external_authority"] = {
            "name": "external_authority",
            "value": {"authority_id": authority.get("authority_id"), "authority_sha256": authority_source.get("sha256")} if authority else None,
            "source": authority_source,
            "status": "AWAITING_AUTHORITY" if authority_valid else "BLOCKED",
            "reason": "authority evidence is well-formed but external trust-root verification is still required" if authority_valid else error or "supplied authority evidence has invalid required fields, formats, or SHA-256 values",
        }
    blockers = [name for name, item in checks.items() if item["status"] in {"BLOCKED", "FAIL"}]
    sources = []
    seen_paths: set[str] = set()
    for item in [*checks.values(), *({"source": evidence} for evidence in extra_sources)]:
        evidence = item.get("source")
        if isinstance(evidence, dict) and evidence.get("inside_root") and evidence.get("path") not in seen_paths:
            sources.append(evidence)
            seen_paths.add(evidence["path"])
    runtime_config_payload, _ = read_json(runtime_config) if source(runtime_config, root)["exists"] else (None, None)
    secrets_disclosed = bool(
        isinstance(runtime_config_payload, dict) and runtime_config_payload.get("secrets_disclosed") is True
    )
    secret_remediation = (
        runtime_config_payload.get("secret_remediation")
        if isinstance(runtime_config_payload, dict)
        else None
    )
    package = {
        "schema": SCHEMA,
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lifecycle": "PRE_RUN",
        "status": "BLOCKED" if blockers else "STRUCTURE_VALID_AWAITING_AUTHORITY",
        "checkout": checkout,
        "bindings": {name: checks[name] for name in ("app_revision", "runtime_revision", "runtime_config", "container_image")},
        "checks": checks,
        "blockers": blockers,
        "source_files": sources,
        "secrets_disclosed": secrets_disclosed,
        "scope": "Exp5/G5A Rust retrieval-only runtime freeze; no retrieval queries executed",
        "external_authority_policy": "absence or unverifiable authority never upgrades status",
    }
    if secret_remediation is not None:
        package["secret_remediation"] = secret_remediation
    return package


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def write_package(package: dict[str, Any], output: Path, manifest_output: Path, root: Path) -> dict[str, Any]:
    if output.exists() or manifest_output.exists():
        raise FileExistsError("refusing to overwrite an existing G5A package")
    write_json(output, package)
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "schema_version": 1,
        "generator": "freeze_rust_g5a_runtime.py",
        "package_sha256": sha256_file(output),
        "package_file": output.name,
        "root": str(root.resolve()),
        "files": package["source_files"],
        "status": package["status"],
    }
    write_json(manifest_output, manifest)
    return {"package": str(output), "manifest": str(manifest_output), "status": package["status"]}


def verify_package(package_path: Path, manifest_path: Path, root: Path) -> dict[str, Any]:
    package, package_error = read_json(package_path)
    manifest, manifest_error = read_json(manifest_path)
    package_hash = sha256_file(package_path)
    recorded_package_hash = manifest.get("package_sha256") if manifest else None
    checks: list[dict[str, Any]] = [
        {"name": "package_hash", "passed": bool(isinstance(recorded_package_hash, str) and SHA256.fullmatch(recorded_package_hash) and package_hash == recorded_package_hash)},
        {"name": "package_schema", "passed": bool(package and package.get("schema") == SCHEMA and package.get("schema_version") == 1)},
        {"name": "manifest_schema", "passed": bool(manifest and manifest.get("schema") == MANIFEST_SCHEMA and manifest.get("schema_version") == 1)},
    ]
    package_files = package.get("source_files") if package and isinstance(package.get("source_files"), list) else None
    manifest_files = manifest.get("files") if manifest and isinstance(manifest.get("files"), list) else None
    lists_match = (
        package_files is not None
        and manifest_files is not None
        and package_files == manifest_files
        and all(isinstance(record, dict) for record in package_files)
    )
    checks.append({"name": "manifest_package_file_list", "passed": lists_match})
    package_status = package.get("status") if package else None
    identity_match = bool(
        manifest
        and manifest.get("generator") == "freeze_rust_g5a_runtime.py"
        and manifest.get("package_file") == package_path.name
        and manifest.get("root") == str(root.resolve())
        and manifest.get("status") == package_status
    )
    checks.append({"name": "manifest_package_identity", "passed": identity_match})
    file_checks = []
    for record in manifest_files or []:
        relative = record.get("path") if isinstance(record, dict) else None
        expected = record.get("sha256") if isinstance(record, dict) else None
        path = (root / relative).resolve() if isinstance(relative, str) and not Path(relative).is_absolute() else root / "<invalid>"
        inside = path.is_relative_to(root.resolve())
        actual = sha256_file(path) if inside else None
        recorded_missing = isinstance(record, dict) and record.get("status") == "BLOCKED" and expected is None and actual is None
        valid_hash = isinstance(expected, str) and bool(SHA256.fullmatch(expected))
        file_checks.append({"path": relative, "inside_root": inside, "sha256_matches": bool(inside and ((valid_hash and actual == expected) or recorded_missing))})
    checks.append({"name": "input_hashes", "passed": bool(file_checks) and all(item["sha256_matches"] for item in file_checks), "files": file_checks})
    integrity_ok = all(item["passed"] for item in checks)
    freeze_status = package.get("status") if package else None
    freeze_ready = bool(integrity_ok and freeze_status in AUTHORIZED_FREEZE_STATUSES)
    return {
        "ok": integrity_ok,
        "integrity_ok": integrity_ok,
        "freeze_ready": freeze_ready,
        "freeze_status": freeze_status,
        "package_error": package_error,
        "manifest_error": manifest_error,
        "checks": checks,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--runtime-contract", type=Path, default=DEFAULT_RUNTIME_CONTRACT)
    parser.add_argument("--runtime-config", type=Path, default=DEFAULT_RUNTIME_CONFIG)
    parser.add_argument("--container-image", type=Path, default=DEFAULT_CONTAINER_IMAGE)
    parser.add_argument("--corpus-manifest", type=Path, default=DEFAULT_CORPUS_MANIFEST)
    parser.add_argument("--authority-evidence", type=Path)
    parser.add_argument("--output", type=Path, default=Path("g5a-runtime-freeze.json"))
    parser.add_argument("--manifest-output", type=Path, default=Path("g5a-runtime-freeze-manifest.json"))
    parser.add_argument("--verify", nargs=2, metavar=("PACKAGE", "MANIFEST"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.verify:
        report = verify_package(Path(args.verify[0]), Path(args.verify[1]), args.root)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["integrity_ok"] and report["freeze_ready"] else 1
    package = build_package(
        root=args.root,
        runtime_contract=args.runtime_contract,
        runtime_config=args.runtime_config,
        container_image=args.container_image,
        corpus_manifest=args.corpus_manifest,
        authority_evidence=args.authority_evidence,
    )
    print(json.dumps(write_package(package, args.output, args.manifest_output, args.root), ensure_ascii=False, sort_keys=True))
    return 1 if package["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
