"""Fail-closed preflight for confirmatory five-mode runs.

This module is the tracked verification boundary.  The runner must call
``confirmatory_preflight`` again at its API creation boundary; no caller-owned
token or binding is accepted as authorization.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


MODES = ("pure_llm", "bm25_rag", "project_rag", "structured_query", "kg_enhanced_rag")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
REVISION = re.compile(r"^[0-9a-f]{40,64}$")
IMAGE_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
AUTHORITY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
FORMAL_STATUSES = frozenset({"AUTHORIZED", "EXTERNALLY_SIGNED", "FROZEN", "FROZEN_EXTERNAL_SETTER"})
AUTHORITY_NAMESPACE = "full-system.confirmatory.v1"
TRUST_ROOT_SCHEMA = "full-system.confirmatory-trust-root-v1"
TOOLING_FILES = (
    "scripts/experiments/run_rag_confirmatory_experiment.py",
    "scripts/gates/confirmatory_preflight.py",
    "docs/experiments/rag-evidence-package-protocol-v1.md",
    "scripts/experiments/evaluate_rust_retrieval.py",
)
# Untracked files are acceptable only when they are explicitly part of the
# frozen input/result boundary.  Source code, configs, and runtime evidence
# remain tracked-only so a local untracked override cannot become T or R.
UNTRACKED_INPUT_PREFIXES = (
    "agent-work/freeze/",
    "agent-work/question-sets/",
    "agent-work/runs/",
    "data/real/",
)
TRACKED_ONLY_DIRECTORIES = ("scripts", "docs/system-evidence")
TRACKED_ONLY_FILES = ("docs/experiments/rag-evidence-package-protocol-v1.md",)
AUTHORITY_PATH_KEYS = (
    "external_authority_artifact",
    "external_authority_signature",
    "allowed_signers",
    "trust_root_policy",
)
AUTHORITY_DYNAMIC_KEYS = frozenset({"captured_at", "created_at", "generated_at", "signed_at_utc", "updated_at", "verified_at_utc"})
AUTHORITY_COMMITMENT_SCHEMA = "full-system.confirmatory-authority-commitment-v1"


class PreflightError(RuntimeError):
    """A local confirmation gate failure; no experiment POST may follow."""


@dataclass(frozen=True)
class PreflightResult:
    head: str
    runtime_source_revision: str
    experiment_tooling_revision: str
    snapshots: dict[str, dict[str, str]]
    question_files: dict[str, Path]
    question_shas: dict[str, str]
    runs_dir: Path


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PreflightError(f"cannot read freeze input {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PreflightError(f"freeze input is not an object: {path}")
    return value


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _require(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def _path(root: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = (root / value).resolve()
    return candidate if candidate.is_relative_to(root) else None


def _valid_utc_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _tracked_worktree_clean(root: Path) -> bool:
    try:
        for args in (("git", "diff", "--quiet"), ("git", "diff", "--cached", "--quiet")):
            subprocess.run(list(args), cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=10)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False
    return True


def _untracked_paths(root: Path) -> list[str] | None:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all", "--ignored=matching", "--", "."],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=True,
            timeout=10,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    paths: list[str] = []
    for line in result.stdout.splitlines():
        if line[:2] == "??":
            paths.append(line[3:])
        elif line[:2] == "!!":
            ignored = line[3:].rstrip("/")
            ignored_parts = Path(ignored).parts
            if ignored_parts and (ignored_parts[0] in TRACKED_ONLY_DIRECTORIES or ignored in TRACKED_ONLY_FILES):
                paths.append(line[3:])
    # Git status can collapse ignored directories. Walk restricted source and
    # evidence trees as a second tracked-only assertion.
    for relative_root in TRACKED_ONLY_DIRECTORIES:
        directory = root / relative_root
        if not directory.is_dir():
            continue
        for candidate in directory.rglob("*"):
            relative = candidate.relative_to(root)
            if any(part in {".pytest_cache", "__pycache__"} for part in relative.parts) or candidate.name == ".DS_Store":
                continue
            if candidate.is_file() and not _tracked_policy_file(root, candidate):
                paths.append(relative.as_posix())
    for relative_file in TRACKED_ONLY_FILES:
        candidate = root / relative_file
        if candidate.is_file() and not _tracked_policy_file(root, candidate):
            paths.append(relative_file)
    return sorted(set(paths))


def _untracked_inputs_allowed(paths: list[str] | None) -> bool:
    return paths is not None and all(path.startswith(UNTRACKED_INPUT_PREFIXES) for path in paths)


def _tracked_policy_file(root: Path, path: Path) -> bool:
    try:
        relative = path.relative_to(root).as_posix()
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", relative],
            cwd=root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _strip_dynamic(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_dynamic(item)
            for key, item in value.items()
            if key not in AUTHORITY_DYNAMIC_KEYS and key != "provenance"
        }
    if isinstance(value, list):
        return [_strip_dynamic(item) for item in value]
    return value


def _relative_path(root: Path, path: Path) -> str | None:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


def _canonical_provenance_path(root: Path, value: Any) -> str | None:
    """Return a provenance path only when it is already canonical POSIX."""
    if not isinstance(value, str) or not value or value.startswith("/") or "\\" in value:
        return None
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return None
    candidate = root.joinpath(*parts)
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    if not resolved.is_relative_to(root):
        return None
    canonical = resolved.relative_to(root).as_posix()
    return canonical if canonical == value else None


def _authority_commitment(
    root: Path,
    freeze_manifest_path: Path,
    freeze_manifest: dict[str, Any],
    question_manifest: dict[str, Any],
    gold_facts: dict[str, Any],
    corpus_manifest: dict[str, Any],
) -> tuple[bytes, str, str]:
    """Return (signed canonical commitment, content hash, commitment hash).

    Authority metadata and timestamps are deliberately excluded from the
    freeze content. All scientific inputs and their current bytes remain in
    the commitment, so changing an input cannot replay an old signature.
    """
    root = root.resolve()
    freeze_dir = freeze_manifest_path.parent.resolve()
    core_manifest = {
        key: _strip_dynamic(value)
        for key, value in freeze_manifest.items()
        if key != "provenance"
    }
    provenance = freeze_manifest.get("provenance") if isinstance(freeze_manifest.get("provenance"), dict) else {}
    excluded_paths = set()
    for key in AUTHORITY_PATH_KEYS:
        canonical = _canonical_provenance_path(root, provenance.get(key))
        if canonical is not None:
            excluded_paths.add(canonical)
    file_sha256 = core_manifest.get("file_sha256")
    if isinstance(file_sha256, dict):
        def canonical_file_sha_path(key: Any) -> str | None:
            if not isinstance(key, str) or not key or key.startswith("/") or "\\" in key:
                return None
            parts = key.split("/")
            if any(part in {"", ".", ".."} for part in parts):
                return None
            candidate = root / key if "/" in key else freeze_dir / key
            try:
                resolved = candidate.resolve()
            except OSError:
                return None
            if not resolved.is_relative_to(root):
                return None
            canonical = resolved.relative_to(root).as_posix()
            # A slash-bearing manifest key is root-relative and must already
            # be canonical.  A bare key is the documented freeze-relative
            # spelling used by the authority artifact entries.
            return canonical if "/" not in key or canonical == key else None

        core_manifest["file_sha256"] = {
            key: value
            for key, value in file_sha256.items()
            if canonical_file_sha_path(key) not in excluded_paths
        }
    linked: list[dict[str, Any]] = []
    for name, payload in (
        ("question-set-manifest.json", question_manifest),
        ("gold-facts.json", gold_facts),
        ("corpus-manifest.json", corpus_manifest),
    ):
        path = freeze_dir / name
        linked.append({"path": _relative_path(root, path) or str(path), "sha256": _sha256_bytes(_canonical_json(_strip_dynamic(payload)))})
    for name in ("questions.json", "run-config.json", "analysis-config.json"):
        path = freeze_dir / name
        if path.is_file():
            try:
                payload = _read_json(path)
                digest = _sha256_bytes(_canonical_json(_strip_dynamic(payload)))
            except PreflightError:
                digest = _sha256(path)
        else:
            digest = None
        linked.append({"path": _relative_path(root, path) or str(path), "sha256": digest})
    question_sources: list[dict[str, Any]] = []
    for item in question_manifest.get("question_sets", []) if isinstance(question_manifest.get("question_sets"), list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            question_sources.append({"path": item.get("path") if isinstance(item, dict) else None, "sha256": None})
            continue
        path = (root / item["path"]).resolve()
        question_sources.append({"path": _relative_path(root, path) or item["path"], "sha256": _sha256(path) if path.is_file() else None})
    corpus_sources: list[dict[str, Any]] = []
    projects = corpus_manifest.get("projects") if isinstance(corpus_manifest.get("projects"), dict) else {}
    for project_id in sorted(projects):
        project = projects[project_id]
        records = project.get("files") if isinstance(project, dict) and isinstance(project.get("files"), list) else []
        for record in records:
            relative = record.get("path") if isinstance(record, dict) else None
            path = (root / relative).resolve() if isinstance(relative, str) else root / "<invalid>"
            corpus_sources.append({"project": project_id, "path": _relative_path(root, path) or relative, "sha256": _sha256(path) if path.is_file() else None})
    content = {
        "schema": "full-system.confirmatory-freeze-content-v1",
        "freeze_manifest": core_manifest,
        "linked_manifests": sorted(linked, key=lambda item: str(item["path"])),
        "question_sources": sorted(question_sources, key=lambda item: str(item["path"])),
        "corpus_sources": sorted(corpus_sources, key=lambda item: (str(item.get("project")), str(item["path"]))),
    }
    content_hash = _sha256_bytes(_canonical_json(content))
    commitment = _canonical_json({"schema": AUTHORITY_COMMITMENT_SCHEMA, "freeze_content_sha256": content_hash})
    return commitment, content_hash, _sha256_bytes(commitment)


def _validate_questions(errors: list[str], payload: dict[str, Any], key: str, expected_count: Any = None) -> list[str]:
    questions = payload.get("questions")
    _require(errors, isinstance(questions, list) and bool(questions), f"question source questions must be a non-empty list for {key}")
    if not isinstance(questions, list):
        return []
    ids: set[str] = set()
    texts: list[str] = []
    for index, question in enumerate(questions, start=1):
        valid = (
            isinstance(question, dict)
            and isinstance(question.get("question_id"), str)
            and bool(question["question_id"].strip())
            and isinstance(question.get("project_id"), str)
            and question["project_id"] == key
            and isinstance(question.get("question"), str)
            and bool(question["question"].strip())
        )
        _require(errors, valid, f"malformed or unbound question {key}#{index}")
        if not valid:
            continue
        question_id = question["question_id"]
        _require(errors, question_id not in ids, f"duplicate question id for {key}: {question_id}")
        ids.add(question_id)
        texts.append(question["question"])
    if isinstance(expected_count, int) and not isinstance(expected_count, bool):
        _require(errors, len(questions) == expected_count, f"question count mismatch for {key}")
    return texts


def _verify_external_authority(
    root: Path,
    provenance: dict[str, Any],
    freeze_manifest_path: Path,
    freeze_manifest: dict[str, Any],
    question_manifest: dict[str, Any],
    gold_facts: dict[str, Any],
    corpus_manifest: dict[str, Any],
    errors: list[str],
) -> None:
    artifact_path = _path(root, provenance.get("external_authority_artifact"))
    signature_path = _path(root, provenance.get("external_authority_signature"))
    allowed_path = _path(root, provenance.get("allowed_signers"))
    trust_path = _path(root, provenance.get("trust_root_policy"))
    for label, path in (
        ("external authority artifact", artifact_path),
        ("external authority signature", signature_path),
        ("approved allowed_signers", allowed_path),
        ("trust-root policy", trust_path),
    ):
        _require(errors, path is not None and path.is_file(), f"{label} is missing/outside root")
    if not all(path is not None and path.is_file() for path in (artifact_path, signature_path, allowed_path, trust_path)):
        return
    assert artifact_path is not None and signature_path is not None and allowed_path is not None and trust_path is not None

    allowed_sha = _sha256(allowed_path)
    trust_sha = _sha256(trust_path)
    artifact_sha = _sha256(artifact_path)
    signature_sha = _sha256(signature_path)
    for field, actual, label in (
        ("allowed_signers_sha256", allowed_sha, "allowed_signers"),
        ("trust_root_policy_sha256", trust_sha, "trust-root policy"),
        ("external_authority_sha256", artifact_sha, "authority artifact"),
        ("external_authority_signature_sha256", signature_sha, "authority signature"),
    ):
        expected = provenance.get(field)
        _require(errors, isinstance(expected, str) and SHA256.fullmatch(expected) is not None and expected == actual, f"{label} SHA is not bound")
    _require(errors, _tracked_policy_file(root, allowed_path), "allowed_signers is not repo-tracked")
    _require(errors, _tracked_policy_file(root, trust_path), "trust-root policy is not repo-tracked")

    authority = _read_json(artifact_path)
    trust_root = _read_json(trust_path)
    commitment, content_hash, commitment_hash = _authority_commitment(
        root, freeze_manifest_path, freeze_manifest, question_manifest, gold_facts, corpus_manifest
    )
    authority_id = authority.get("authority_id")
    _require(errors, isinstance(authority_id, str) and AUTHORITY_ID.fullmatch(authority_id) is not None, "signed authority id is invalid")
    _require(errors, authority_id == provenance.get("external_setter_authority"), "signed authority id is not bound")
    _require(errors, authority.get("setter_id") == provenance.get("external_setter_id"), "signed setter id is not bound")
    _require(errors, authority.get("signed_at_utc") == provenance.get("external_setter_signed_at_utc") and _valid_utc_timestamp(authority.get("signed_at_utc")), "signed timestamp is not bound")
    _require(errors, authority.get("namespace") == AUTHORITY_NAMESPACE, "authority namespace is not fixed")
    _require(errors, authority.get("allowed_signers_sha256") == allowed_sha, "signed allowed_signers is not bound")
    _require(errors, authority.get("trust_root_policy_sha256") == trust_sha, "signed trust-root policy is not bound")
    _require(errors, authority.get("freeze_content_sha256") == content_hash, "signed freeze content hash is not bound")
    _require(errors, authority.get("commitment_sha256") == commitment_hash, "authority commitment hash is not bound")
    _require(errors, trust_root.get("schema") == TRUST_ROOT_SCHEMA, "trust-root policy schema is invalid")
    _require(errors, trust_root.get("namespace") == AUTHORITY_NAMESPACE, "trust-root policy namespace is invalid")
    _require(errors, trust_root.get("allowed_signers_sha256") == allowed_sha, "trust-root policy key set is not bound")
    approved = trust_root.get("approved_authorities")
    _require(errors, isinstance(approved, list) and authority.get("authority_id") in approved, "authority is not approved by trust-root policy")
    _require(errors, shutil.which("ssh-keygen") is not None, "ssh-keygen is unavailable")
    if shutil.which("ssh-keygen") is None:
        return
    try:
        verified = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", str(allowed_path), "-I", str(authority.get("authority_id")), "-n", AUTHORITY_NAMESPACE, "-s", str(signature_path)],
            input=commitment.decode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        _require(errors, False, f"authority signature verification failed: {exc}")
    else:
        _require(errors, verified.returncode == 0, "authority signature verification failed")


def confirmatory_preflight(
    project_keys: list[str],
    *,
    root: Path,
    freeze_manifest_path: Path,
    runs_dir: Path,
    current_revision: str | None = None,
    summary_path: Path | None = None,
    reserved_output: Path | None = None,
) -> PreflightResult:
    """Recompute all local bindings; result is data, never an authorization token."""
    root = root.resolve()
    freeze_manifest_path = freeze_manifest_path.resolve()
    errors: list[str] = []
    _require(errors, freeze_manifest_path.is_relative_to(root), "freeze manifest is outside repository root")
    freeze_manifest = _read_json(freeze_manifest_path)
    freeze_dir = freeze_manifest_path.parent.resolve()
    question_manifest = _read_json(freeze_dir / "question-set-manifest.json")
    gold_facts = _read_json(freeze_dir / "gold-facts.json")
    corpus_manifest = _read_json(freeze_dir / "corpus-manifest.json")
    for label, payload in (("freeze manifest", freeze_manifest), ("question-set manifest", question_manifest), ("gold-facts manifest", gold_facts), ("corpus manifest", corpus_manifest)):
        _require(errors, payload.get("formal_use_allowed") is True, f"{label} formal_use_allowed is not true")
        status = str(payload.get("status") or payload.get("freeze_status") or "").upper()
        _require(errors, status in FORMAL_STATUSES, f"{label} status is not an approved formal status: {status or '<missing>'}")

    provenance = freeze_manifest.get("provenance") if isinstance(freeze_manifest.get("provenance"), dict) else {}
    external_setter_id = provenance.get("external_setter_id")
    external_authority = provenance.get("external_setter_authority")
    _require(errors, isinstance(external_setter_id, str) and bool(external_setter_id.strip()), "external setter id is missing")
    _require(errors, isinstance(external_authority, str) and bool(external_authority.strip()), "external setter authority is missing")
    _require(errors, not (isinstance(external_setter_id, str) and external_setter_id.upper().startswith("AGENT_DRAFT")), "external setter id is AGENT_DRAFT")
    _require(errors, not (isinstance(external_authority, str) and external_authority.upper().startswith("AGENT_DRAFT")), "external setter authority is AGENT_DRAFT")
    _require(errors, _valid_utc_timestamp(provenance.get("external_setter_signed_at_utc")), "external setter signature timestamp is invalid")
    _require(errors, not str(provenance.get("setter_id") or "").upper().startswith("AGENT_DRAFT"), "setter_id is AGENT_DRAFT")
    for label, payload in (("question-set", question_manifest), ("gold-facts", gold_facts), ("corpus", corpus_manifest)):
        setter = payload.get("external_setter")
        _require(errors, isinstance(setter, dict), f"{label} external setter binding is missing")
        if isinstance(setter, dict):
            _require(errors, setter.get("setter_id") == provenance.get("external_setter_id"), f"{label} setter id is not bound")
            _require(errors, setter.get("authority") == provenance.get("external_setter_authority"), f"{label} setter authority is not bound")
            _require(errors, setter.get("signed_at_utc") == provenance.get("external_setter_signed_at_utc"), f"{label} setter timestamp is not bound")
    _verify_external_authority(
        root,
        provenance,
        freeze_manifest_path,
        freeze_manifest,
        question_manifest,
        gold_facts,
        corpus_manifest,
        errors,
    )

    try:
        actual_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True, timeout=10).strip()
    except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired) as exc:
        raise PreflightError(f"cannot resolve current Git HEAD: {exc}") from exc
    head = current_revision or actual_head
    _require(errors, head == actual_head, "current revision override does not equal Git HEAD")
    _require(errors, _tracked_worktree_clean(root), "tracked worktree is dirty")
    untracked = _untracked_paths(root)
    _require(errors, _untracked_inputs_allowed(untracked), "untracked files outside explicit freeze/corpus/results inputs are present")
    runtime_binding = freeze_manifest.get("runtime_binding") if isinstance(freeze_manifest.get("runtime_binding"), dict) else {}
    runtime_source_revision = runtime_binding.get("runtime_source_revision")
    _require(
        errors,
        isinstance(runtime_source_revision, str) and REVISION.fullmatch(runtime_source_revision.lower()) is not None,
        "freeze runtime_binding.runtime_source_revision is missing or invalid",
    )
    tooling_binding = freeze_manifest.get("tooling_binding") if isinstance(freeze_manifest.get("tooling_binding"), dict) else {}
    tooling_revision = tooling_binding.get("experiment_tooling_revision")
    _require(
        errors,
        isinstance(tooling_revision, str) and REVISION.fullmatch(tooling_revision.lower()) is not None and tooling_revision == head,
        "freeze tooling_binding.experiment_tooling_revision is missing or stale",
    )
    tooling_records = tooling_binding.get("files") if isinstance(tooling_binding.get("files"), list) else []
    tooling_by_path = {record.get("path"): record for record in tooling_records if isinstance(record, dict)}
    _require(errors, set(tooling_by_path) >= set(TOOLING_FILES), "freeze tooling binding does not cover runner/preflight/protocol/evaluator")
    for name in TOOLING_FILES:
        record = tooling_by_path.get(name)
        path = _path(root, name)
        expected = record.get("sha256") if isinstance(record, dict) else None
        _require(errors, path is not None and path.is_file(), f"tooling input is missing: {name}")
        _require(errors, _tracked_policy_file(root, path) if path is not None else False, f"tooling input is not repo-tracked: {name}")
        _require(errors, isinstance(expected, str) and SHA256.fullmatch(expected) is not None, f"tooling SHA is invalid: {name}")
        if path is not None and path.is_file() and isinstance(expected, str):
            _require(errors, _sha256(path) == expected, f"tooling SHA mismatch: {name}")
    image_digest = runtime_binding.get("image_digest")
    _require(errors, isinstance(image_digest, str) and IMAGE_DIGEST.fullmatch(image_digest) is not None, "freeze runtime image digest is missing or mutable")
    image_path = root / "docs" / "system-evidence" / "container-image-latest.json"
    if image_path.is_file():
        image = _read_json(image_path)
        _require(errors, image.get("image_digest") == image_digest, "freeze image digest does not match container image evidence")
        for field in ("runtime_source_revision", "endpoint_revision", "oci_revision", "app_revision", "runtime_revision", "build_revision"):
            value = image.get(field)
            _require(errors, isinstance(value, str) and REVISION.fullmatch(value.lower()) is not None and value == runtime_source_revision, f"container image {field} is missing, invalid, or not bound to R")
        tooling_value = image.get("experiment_tooling_revision")
        _require(errors, isinstance(tooling_value, str) and REVISION.fullmatch(tooling_value.lower()) is not None and tooling_value == tooling_revision, "container image experiment_tooling_revision is missing, invalid, or not bound to T")
        nested = image.get("image", {}).get("image_id") if isinstance(image.get("image"), dict) else None
        _require(errors, nested in (None, image_digest), "container image id does not match image digest")
    else:
        errors.append(f"container image evidence is missing: {image_path}")
    runtime_config_path = root / "docs" / "system-evidence" / "runtime-config-latest.json"
    if runtime_config_path.is_file():
        runtime_config = _read_json(runtime_config_path)
        for field in ("runtime_source_revision", "build_revision", "app_revision", "runtime_revision"):
            value = runtime_config.get(field)
            _require(errors, isinstance(value, str) and REVISION.fullmatch(value.lower()) is not None and value == runtime_source_revision, f"runtime config {field} is missing, invalid, or not bound to R")
        tooling_value = runtime_config.get("experiment_tooling_revision")
        _require(errors, isinstance(tooling_value, str) and REVISION.fullmatch(tooling_value.lower()) is not None and tooling_value == tooling_revision, "runtime config experiment_tooling_revision is missing, invalid, or not bound to T")
    else:
        errors.append(f"runtime config evidence is missing: {runtime_config_path}")
    contract_path = root / "docs" / "system-evidence" / "rust-runtime-contract-latest.json"
    if contract_path.is_file():
        contract = _read_json(contract_path)
        for field in ("runtime_source_revision", "revision", "endpoint_revision", "app_revision", "runtime_revision", "build_revision"):
            value = contract.get(field)
            _require(errors, isinstance(value, str) and REVISION.fullmatch(value.lower()) is not None and value == runtime_source_revision, f"runtime contract {field} is missing, invalid, or not bound to R")
        tooling_value = contract.get("experiment_tooling_revision")
        _require(errors, isinstance(tooling_value, str) and REVISION.fullmatch(tooling_value.lower()) is not None and tooling_value == tooling_revision, "runtime contract experiment_tooling_revision is missing, invalid, or not bound to T")
    else:
        errors.append(f"runtime contract is missing: {contract_path}")

    question_sets = question_manifest.get("question_sets")
    _require(errors, isinstance(question_sets, list) and bool(question_sets), "question-set manifest has no question sets")
    _require(errors, len(project_keys) == len(set(project_keys)), "duplicate project key requested")
    design = freeze_manifest.get("design") if isinstance(freeze_manifest.get("design"), dict) else {}
    frozen_projects = set(design.get("projects") or [])
    _require(errors, design.get("modes") == list(MODES), "freeze design modes do not match the five-mode runner")
    _require(errors, design.get("repetitions") == 1, "freeze design repetitions do not match the runner")
    corpus_projects = corpus_manifest.get("projects") if isinstance(corpus_manifest.get("projects"), dict) else {}
    question_set_sha256 = freeze_manifest.get("question_set_sha256") if isinstance(freeze_manifest.get("question_set_sha256"), dict) else {}
    _require(errors, isinstance(freeze_manifest.get("question_set_sha256"), dict), "freeze question_set_sha256 binding is missing")
    snapshots: dict[str, dict[str, str]] = {}
    question_files: dict[str, Path] = {}
    question_shas: dict[str, str] = {}
    for key in project_keys:
        _require(errors, key in frozen_projects, f"project is not in the current freeze: {key}")
        matching = [item for item in question_sets if isinstance(item, dict) and item.get("project_id") == key]
        _require(errors, len(matching) == 1, f"question-set manifest must contain exactly one set for {key}")
        if matching:
            item = matching[0]
            path = _path(root, item.get("path"))
            _require(errors, path is not None and path.is_file(), f"question source is missing/outside root for {key}")
            expected = item.get("sha256")
            _require(errors, isinstance(expected, str) and SHA256.fullmatch(expected) is not None, f"question SHA is missing/invalid for {key}")
            bound = question_set_sha256.get(key)
            _require(errors, bound == expected and isinstance(bound, str) and SHA256.fullmatch(bound) is not None, f"freeze question SHA is not bound for {key}")
            expected_count = item.get("question_count")
            _require(errors, isinstance(expected_count, int) and not isinstance(expected_count, bool) and expected_count > 0, f"question count is missing/invalid for {key}")
            if path is not None and path.is_file() and isinstance(expected, str):
                _require(errors, _sha256(path) == expected, f"question source SHA mismatch for {key}")
                question_files[key] = path
                question_shas[key] = expected
                source = _read_json(path)
                source_status = str(source.get("document_status") or source.get("status") or "").upper()
                _require(errors, source.get("formal_use_allowed") is True and source_status in FORMAL_STATUSES, f"question source is not formal for {key}")
                _validate_questions(errors, source, key, expected_count)
        project = corpus_projects.get(key)
        _require(errors, isinstance(project, dict), f"corpus manifest has no project entry for {key}")
        if isinstance(project, dict):
            corpus_hash = project.get("formal_corpus_snapshot_hash")
            graph_hash = project.get("formal_graph_snapshot_hash")
            _require(errors, isinstance(corpus_hash, str) and SHA256.fullmatch(corpus_hash) is not None, f"formal corpus snapshot is missing/invalid for {key}")
            _require(errors, isinstance(graph_hash, str) and SHA256.fullmatch(graph_hash) is not None, f"formal graph snapshot is missing/invalid for {key}")
            snapshots[key] = {"corpus_snapshot_hash": corpus_hash, "graph_snapshot_hash": graph_hash}
        output = (runs_dir / key).resolve()
        if reserved_output is not None and output == reserved_output.resolve():
            _require(errors, output.is_dir() and not any(output.iterdir()), f"reserved result directory is not empty for {key}")
        else:
            _require(errors, not output.exists(), f"result directory already exists for {key}: {output}")

    run_root = runs_dir.resolve()
    _require(errors, run_root == (root / "agent-work" / "runs").resolve(), "result directory root is not the approved runner output path")
    if summary_path is not None:
        _require(errors, summary_path.resolve().is_relative_to(run_root), "summary output is outside the approved result path")
        _require(errors, not summary_path.exists(), f"summary output already exists: {summary_path}")
    for key, project in corpus_projects.items():
        if not isinstance(project, dict):
            continue
        records = project.get("files")
        _require(errors, isinstance(records, list), f"corpus source file list is invalid: {key}")
        for record in records if isinstance(records, list) else []:
            relative = record.get("path") if isinstance(record, dict) else None
            expected = record.get("sha256") if isinstance(record, dict) else None
            candidate = _path(root, relative)
            _require(errors, candidate is not None and candidate.is_file(), f"corpus source is missing/outside root: {key}/{relative}")
            _require(errors, isinstance(expected, str) and SHA256.fullmatch(expected) is not None, f"corpus source SHA is invalid: {key}/{relative}")
            if candidate is not None and candidate.is_file() and isinstance(expected, str):
                _require(errors, _sha256(candidate) == expected, f"corpus source SHA mismatch: {key}/{relative}")
    file_sha256 = freeze_manifest.get("file_sha256") if isinstance(freeze_manifest.get("file_sha256"), dict) else {}
    for name, expected in file_sha256.items():
        if expected is None:
            continue
        path = _path(root, name) if "/" in str(name) else (freeze_dir / str(name)).resolve()
        _require(errors, path is not None and path.is_file(), f"freeze input is missing/outside root: {name}")
        _require(errors, isinstance(expected, str) and SHA256.fullmatch(expected) is not None, f"freeze input SHA is invalid: {name}")
        if path is not None and path.is_file() and isinstance(expected, str):
            _require(errors, _sha256(path) == expected, f"freeze input SHA mismatch: {name}")
    for name in ("gold-facts.json", "questions.json", "run-config.json", "analysis-config.json"):
        expected = file_sha256.get(name)
        path = freeze_dir / name
        _require(errors, isinstance(expected, str) and SHA256.fullmatch(expected) is not None and path.is_file() and _sha256(path) == expected, f"{name} SHA is not bound to freeze manifest")
        if path.is_file():
            payload = _read_json(path)
            status = str(payload.get("status") or payload.get("freeze_status") or "").upper()
            _require(errors, payload.get("formal_use_allowed") is True and status in FORMAL_STATUSES, f"{name} is not formal")
    if errors:
        raise PreflightError("confirmatory preflight blocked:\n- " + "\n- ".join(errors))
    assert isinstance(runtime_source_revision, str)
    assert isinstance(tooling_revision, str)
    return PreflightResult(head=head, runtime_source_revision=runtime_source_revision, experiment_tooling_revision=tooling_revision, snapshots=snapshots, question_files=question_files, question_shas=question_shas, runs_dir=run_root)


def load_verified_questions(result: PreflightResult, key: str) -> list[str]:
    """Hash the exact bytes parsed for the POST payload; do not reread later."""
    path = result.question_files[key]
    raw = path.read_bytes()
    if _sha256_bytes(raw) != result.question_shas[key]:
        raise PreflightError(f"question source changed after preflight for {key}")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PreflightError(f"question source changed or became invalid for {key}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PreflightError(f"question source is not an object for {key}")
    errors: list[str] = []
    questions = _validate_questions(errors, payload, key)
    if errors:
        raise PreflightError("confirmatory question validation blocked:\n- " + "\n- ".join(errors))
    return questions
