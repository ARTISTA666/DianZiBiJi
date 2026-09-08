from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "freeze"))
SCRIPT = ROOT / "scripts" / "freeze" / "freeze_system_evidence.py"
SPEC = importlib.util.spec_from_file_location("freeze_system_evidence", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


COMMIT = "a" * 40


def write_lockfiles(root: Path) -> dict[str, Path]:
    lockfiles = {
        "backend/Cargo.lock": root / "backend" / "Cargo.lock",
        "frontend/package-lock.json": root / "frontend" / "package-lock.json",
    }
    for relative_path, path in lockfiles.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"locked: {relative_path}\n", encoding="utf-8")
    return lockfiles


def clean_checkout(*_args, **_kwargs) -> dict[str, object]:
    return {"git_commit": COMMIT, "worktree_clean": True}


def test_freezes_and_verifies_evidence_bundle(tmp_path: Path, monkeypatch) -> None:
    write_lockfiles(tmp_path)
    monkeypatch.setattr(MODULE, "git_checkout_state", clean_checkout)
    files = []
    for name in ("system.json", "load.json", "experiment.json"):
        path = tmp_path / name
        path.write_text(json.dumps({"name": name}), encoding="utf-8")
        files.append(path)
    manifest = tmp_path / "manifest.json"

    result = MODULE.freeze(files, manifest, tmp_path, replace=False)
    verified = MODULE.verify_manifest(manifest, tmp_path)

    assert result == {"ok": True, "output": str(manifest), "file_count": 3}
    assert verified["ok"] is True
    assert [item["path"] for item in verified["checks"]] == ["experiment.json", "load.json", "system.json"]


def test_verification_fails_after_evidence_changes(tmp_path: Path, monkeypatch) -> None:
    write_lockfiles(tmp_path)
    monkeypatch.setattr(MODULE, "git_checkout_state", clean_checkout)
    source = tmp_path / "system.json"
    source.write_text("before", encoding="utf-8")
    manifest = tmp_path / "manifest.json"

    MODULE.freeze([source], manifest, tmp_path, replace=False)
    source.write_text("after", encoding="utf-8")
    verified = MODULE.verify_manifest(manifest, tmp_path)

    assert verified["ok"] is False
    assert verified["checks"][0]["sha256_matches"] is False


def test_freeze_records_versioned_checkout_and_lockfile_provenance(tmp_path: Path, monkeypatch) -> None:
    lockfiles = write_lockfiles(tmp_path)
    monkeypatch.setattr(MODULE, "git_checkout_state", clean_checkout)
    source = tmp_path / "system.json"
    source.write_text("{}\n", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"

    MODULE.freeze([source], manifest_path, tmp_path, replace=False)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == MODULE.SYSTEM_MANIFEST_SCHEMA
    assert manifest["schema_version"] == MODULE.SYSTEM_MANIFEST_SCHEMA_VERSION
    assert manifest["generator"] == MODULE.SYSTEM_MANIFEST_GENERATOR
    assert manifest["generator_version"] == MODULE.SYSTEM_MANIFEST_GENERATOR_VERSION
    assert manifest["provenance"]["git_commit"] == COMMIT
    assert manifest["provenance"]["git_worktree_clean"] is True
    assert manifest["provenance"]["lockfiles"] == {
        relative_path: {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for relative_path, path in lockfiles.items()
    }


def test_freeze_rejects_dirty_checkout_without_overwriting_existing_manifest(tmp_path: Path, monkeypatch) -> None:
    write_lockfiles(tmp_path)
    source = tmp_path / "system.json"
    source.write_text("{}\n", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("existing evidence\n", encoding="utf-8")
    monkeypatch.setattr(
        MODULE,
        "git_checkout_state",
        lambda *_args, **_kwargs: {"git_commit": COMMIT, "worktree_clean": False},
    )

    with pytest.raises(RuntimeError, match="dirty"):
        MODULE.freeze([source], manifest_path, tmp_path, replace=True)

    assert manifest_path.read_text(encoding="utf-8") == "existing evidence\n"


def test_system_manifest_verification_rejects_changed_git_commit(tmp_path: Path, monkeypatch) -> None:
    write_lockfiles(tmp_path)
    monkeypatch.setattr(MODULE, "git_checkout_state", clean_checkout)
    source = tmp_path / "system.json"
    source.write_text("{}\n", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    MODULE.freeze([source], manifest_path, tmp_path, replace=False)
    monkeypatch.setattr(
        MODULE,
        "git_checkout_state",
        lambda *_args, **_kwargs: {"git_commit": "b" * 40, "worktree_clean": True},
    )

    verified = MODULE.verify_manifest(manifest_path, tmp_path)

    assert verified["ok"] is False
    assert verified["provenance"]["git_commit_matches"] is False


def test_system_manifest_verification_rejects_dirty_checkout(tmp_path: Path, monkeypatch) -> None:
    write_lockfiles(tmp_path)
    monkeypatch.setattr(MODULE, "git_checkout_state", clean_checkout)
    source = tmp_path / "system.json"
    source.write_text("{}\n", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    MODULE.freeze([source], manifest_path, tmp_path, replace=False)
    monkeypatch.setattr(
        MODULE,
        "git_checkout_state",
        lambda *_args, **_kwargs: {"git_commit": COMMIT, "worktree_clean": False},
    )

    verified = MODULE.verify_manifest(manifest_path, tmp_path)

    assert verified["ok"] is False
    assert verified["provenance"]["current_worktree_clean"] is False


def test_system_manifest_verification_does_not_exempt_manifest_from_dirty_checkout(
    tmp_path: Path,
    monkeypatch,
) -> None:
    write_lockfiles(tmp_path)
    monkeypatch.setattr(MODULE, "git_checkout_state", clean_checkout)
    source = tmp_path / "system.json"
    source.write_text("{}\n", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    MODULE.freeze([source], manifest_path, tmp_path, replace=False)
    monkeypatch.setattr(
        MODULE,
        "git_checkout_state",
        lambda _root, ignored_paths=(): {
            "git_commit": COMMIT,
            "worktree_clean": bool(ignored_paths),
        },
    )

    verified = MODULE.verify_manifest(manifest_path, tmp_path)

    assert verified["ok"] is False
    assert verified["provenance"]["current_worktree_clean"] is False


def test_system_manifest_verification_rejects_changed_lockfile(tmp_path: Path, monkeypatch) -> None:
    lockfiles = write_lockfiles(tmp_path)
    monkeypatch.setattr(MODULE, "git_checkout_state", clean_checkout)
    source = tmp_path / "system.json"
    source.write_text("{}\n", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    MODULE.freeze([source], manifest_path, tmp_path, replace=False)
    lockfiles["backend/Cargo.lock"].write_text("changed dependency graph\n", encoding="utf-8")

    verified = MODULE.verify_manifest(manifest_path, tmp_path)

    assert verified["ok"] is False
    assert verified["provenance"]["lockfiles_match"] is False
    cargo_check = next(
        item
        for item in verified["provenance"]["lockfile_checks"]
        if item["path"] == "backend/Cargo.lock"
    )
    assert cargo_check["sha256_matches"] is False


def test_system_manifest_verification_rejects_non_object_file_entries_without_crashing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    write_lockfiles(tmp_path)
    monkeypatch.setattr(MODULE, "git_checkout_state", clean_checkout)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "format_version": 2,
                "path_base": "root_argument",
                "files": [1],
                "schema": MODULE.SYSTEM_MANIFEST_SCHEMA,
                "schema_version": MODULE.SYSTEM_MANIFEST_SCHEMA_VERSION,
                "generator": MODULE.SYSTEM_MANIFEST_GENERATOR,
                "generator_version": MODULE.SYSTEM_MANIFEST_GENERATOR_VERSION,
                "provenance": {
                    "git_commit": COMMIT,
                    "git_worktree_clean": True,
                    "lockfiles": {
                        relative_path: {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                        for relative_path, path in write_lockfiles(tmp_path).items()
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    verified = MODULE.verify_manifest(manifest_path, tmp_path)

    assert verified["ok"] is False
    assert verified["file_count"] == 0
    assert verified["checks"][0]["error"] == "invalid file manifest structure"


def test_default_evidence_files_include_release_gate_inputs() -> None:
    paths = {path.as_posix() for path in MODULE.DEFAULT_FILES}

    assert any(path.endswith("main-retrieval-evaluation/report.json") for path in paths)
    assert any(path.endswith("main_v8_kg_holdout_experiment_report.json") for path in paths)
    assert any(path.endswith("main_v8_agent_probe_report.json") for path in paths)
    assert any(path.endswith("validation-results.json") for path in paths)


def test_default_manifest_path_uses_ignored_release_output() -> None:
    assert MODULE.DEFAULT_OUTPUT == ROOT / "output" / "release-evidence" / "maturity-evidence-manifest.json"


def test_git_checkout_state_reports_clean_when_status_is_empty(tmp_path: Path, monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_git(_root: Path, arguments: list[str]) -> str:
        calls.append(arguments)
        if arguments == ["rev-parse", "--show-toplevel"]:
            return str(tmp_path)
        if arguments == ["rev-parse", "--verify", "HEAD^{commit}"]:
            return COMMIT
        return ""

    monkeypatch.setattr(MODULE, "_git", fake_git)

    state = MODULE.git_checkout_state(tmp_path)

    assert state == {"git_commit": COMMIT, "worktree_clean": True}
    assert ["status", "--porcelain=v1", "--untracked-files=all", "--", "."] in calls


def test_rust_pilot_readiness_blocks_unbound_candidate_and_emits_required_fields(tmp_path: Path) -> None:
    protocol = tmp_path / "protocol.md"
    questions = tmp_path / "questions.json"
    evaluator = tmp_path / "evaluator.py"
    openapi = tmp_path / "openapi.json"
    runtime = tmp_path / "runtime.json"
    for path, content in (
        (protocol, "protocol"),
        (questions, "[]"),
        (evaluator, "evaluator"),
        (openapi, "{}"),
    ):
        path.write_text(content, encoding="utf-8")
    runtime.write_text(
        json.dumps(
            {
                "revision": "unversioned",
                "runtime": {
                    "api_runtime": "rust-axum",
                    "embedding_backend": "hash",
                    "embedding_model": "rust-hash-512-v1",
                    "embedding_dimension": 512,
                },
            }
        ),
        encoding="utf-8",
    )

    readiness = MODULE.build_rust_pilot_readiness(
        root=tmp_path,
        protocol=protocol,
        questions=questions,
        evaluator=evaluator,
        openapi=openapi,
        runtime_contract=runtime,
        checkout={
            "base_revision": COMMIT,
            "tracked_worktree_clean": False,
            "worktree_clean": False,
        },
    )

    assert readiness["schema"] == MODULE.RUST_PILOT_READINESS_SCHEMA
    assert readiness["overall_verdict"] == "BLOCKED"
    assert readiness["checks"]["base_revision"]["value"] == COMMIT
    assert readiness["checks"]["tracked_worktree_clean"]["status"] == "FAIL"
    assert readiness["checks"]["app_revision"]["value"] is None
    assert readiness["checks"]["image_digest"]["value"] is None
    assert readiness["checks"]["corpus_snapshot_hash"]["value"] is None
    assert readiness["checks"]["graph_snapshot_hash"]["value"] is None
    assert readiness["checks"]["embedding_backend"]["status"] == "BLOCKED"
    assert readiness["gates"]["G5A"]["status"] == "BLOCKED"
    assert readiness["gates"]["G5B"]["status"] == "BLOCKED"


def test_rust_pilot_readiness_does_not_accept_unversioned_or_hash_as_formal_binding(
    tmp_path: Path,
) -> None:
    files = {}
    for name in ("protocol.md", "questions.json", "evaluator.py", "openapi.json"):
        path = tmp_path / name
        path.write_text(name, encoding="utf-8")
        files[name] = path
    runtime = tmp_path / "runtime.json"
    runtime.write_text(
        json.dumps(
            {
                "revision": "unversioned",
                "runtime": {
                    "api_runtime": "rust-axum",
                    "embedding_backend": "hash",
                    "embedding_model": "rust-hash-512-v1",
                    "embedding_dimension": 512,
                },
            }
        ),
        encoding="utf-8",
    )

    readiness = MODULE.build_rust_pilot_readiness(
        root=tmp_path,
        protocol=files["protocol.md"],
        questions=files["questions.json"],
        evaluator=files["evaluator.py"],
        openapi=files["openapi.json"],
        runtime_contract=runtime,
        checkout={
            "base_revision": COMMIT,
            "tracked_worktree_clean": True,
            "worktree_clean": True,
        },
    )

    assert readiness["overall_verdict"] == "BLOCKED"
    assert readiness["checks"]["app_revision"]["status"] == "FAIL"
    assert readiness["checks"]["embedding_backend"]["value"] == "hash"
    assert readiness["checks"]["embedding_model"]["value"] == "rust-hash-512-v1"
    assert readiness["checks"]["embedding_dimension"]["value"] == 512
    assert readiness["checks"]["embedding_backend"]["reason"]


def test_rust_pilot_readiness_reports_in_scope_untracked_files_separately(tmp_path: Path) -> None:
    files = {}
    for name in ("protocol.md", "questions.json", "evaluator.py", "openapi.json"):
        path = tmp_path / name
        path.write_text(name, encoding="utf-8")
        files[name] = path
    runtime = tmp_path / "runtime.json"
    runtime.write_text("{}", encoding="utf-8")

    readiness = MODULE.build_rust_pilot_readiness(
        root=tmp_path,
        protocol=files["protocol.md"],
        questions=files["questions.json"],
        evaluator=files["evaluator.py"],
        openapi=files["openapi.json"],
        runtime_contract=runtime,
        checkout={
            "base_revision": COMMIT,
            "tracked_worktree_clean": True,
            "worktree_clean": True,
            "in_scope_untracked_files": ["docs/experiments/rust-retrieval-pilot-protocol-v1.md"],
        },
    )

    assert readiness["checks"]["in_scope_untracked_files"]["status"] == "FAIL"
    assert readiness["checks"]["in_scope_untracked_files"]["value"] == [
        "docs/experiments/rust-retrieval-pilot-protocol-v1.md"
    ]
    assert readiness["overall_verdict"] == "BLOCKED"


def test_rust_pilot_readiness_writes_atomic_assets_without_mutating_inputs(tmp_path: Path) -> None:
    files = {}
    relative_files = {
        "protocol.md": Path("docs/experiments/rust-retrieval-pilot-protocol-v1.md"),
        "questions.json": Path("data/real/GSE111619/gse111619_questions.json"),
        "evaluator.py": Path("scripts/experiments/evaluate_rust_retrieval.py"),
        "openapi.json": Path("backend/openapi.json"),
    }
    for name, relative_path in relative_files.items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name, encoding="utf-8")
        files[name] = path
    runtime = tmp_path / "runtime.json"
    runtime.write_text("{}", encoding="utf-8")
    before = {path: path.read_bytes() for path in (*files.values(), runtime)}
    readiness = MODULE.build_rust_pilot_readiness(
        root=tmp_path,
        protocol=files["protocol.md"],
        questions=files["questions.json"],
        evaluator=files["evaluator.py"],
        openapi=files["openapi.json"],
        runtime_contract=runtime,
        checkout={
            "base_revision": COMMIT,
            "tracked_worktree_clean": True,
            "worktree_clean": True,
            "in_scope_untracked_files": [],
        },
    )
    output = tmp_path / "preflight.json"
    manifest = tmp_path / "manifest.json"
    gate_script = tmp_path / "scripts" / "freeze" / "freeze_system_evidence.py"
    gate_script.parent.mkdir(parents=True, exist_ok=True)
    gate_script.write_bytes(SCRIPT.read_bytes())

    result = MODULE.write_rust_pilot_readiness(
        readiness,
        output=output,
        manifest_output=manifest,
        manifest_inputs=[files["protocol.md"], files["questions.json"], files["evaluator.py"], files["openapi.json"]],
        gate_script=gate_script,
        root=tmp_path,
    )

    assert result["output"] == str(output)
    assert json.loads(output.read_text(encoding="utf-8"))["overall_verdict"] == "BLOCKED"
    written_manifest = json.loads(manifest.read_text(encoding="utf-8"))
    assert written_manifest["schema"] == MODULE.RUST_PILOT_READINESS_MANIFEST_SCHEMA
    assert written_manifest["preflight_sha256"]
    assert written_manifest["files"]
    assert written_manifest["local_manifest_inputs_complete"] is True
    assert written_manifest["freeze_requirements_complete"] is False
    assert written_manifest["input_failures"] == []
    assert all(not Path(item["path"]).is_absolute() for item in written_manifest["files"])
    assert {item["path"] for item in written_manifest["files"]} == {
        "docs/experiments/rust-retrieval-pilot-protocol-v1.md",
        "data/real/GSE111619/gse111619_questions.json",
        "scripts/experiments/evaluate_rust_retrieval.py",
        "backend/openapi.json",
        "scripts/freeze/freeze_system_evidence.py",
    }
    protocol_entry = next(
        item
        for item in written_manifest["files"]
        if item["path"] == "docs/experiments/rust-retrieval-pilot-protocol-v1.md"
    )
    assert protocol_entry["sha256"] == hashlib.sha256(files["protocol.md"].read_bytes()).hexdigest()
    assert {path: path.read_bytes() for path in (*files.values(), runtime)} == before


def test_rust_pilot_readiness_manifest_includes_runtime_and_implementation_inputs(tmp_path: Path) -> None:
    files = {}
    for name in ("protocol.md", "questions.json", "evaluator.py", "tests.py", "openapi.json", "runtime.json", "method.rs"):
        path = tmp_path / name
        path.write_text("{}" if name.endswith(".json") else name, encoding="utf-8")
        files[name] = path
    readiness = MODULE.build_rust_pilot_readiness(
        root=tmp_path,
        protocol=files["protocol.md"],
        questions=files["questions.json"],
        evaluator=files["evaluator.py"],
        evaluator_tests=files["tests.py"],
        openapi=files["openapi.json"],
        runtime_contract=files["runtime.json"],
        implementation_files=[files["method.rs"]],
        checkout={
            "base_revision": COMMIT,
            "tracked_worktree_clean": True,
            "worktree_clean": True,
            "in_scope_untracked_files": [],
        },
    )
    output = tmp_path / "preflight.json"
    manifest = tmp_path / "manifest.json"
    gate_script = tmp_path / "freeze_system_evidence.py"
    gate_script.write_bytes(SCRIPT.read_bytes())
    MODULE.write_rust_pilot_readiness(
        readiness,
        output=output,
        manifest_output=manifest,
        manifest_inputs=[files[name] for name in ("protocol.md", "questions.json", "evaluator.py", "tests.py", "openapi.json", "runtime.json", "method.rs")],
        gate_script=gate_script,
        root=tmp_path,
    )
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert manifest_payload["local_manifest_inputs_complete"] is True
    assert manifest_payload["freeze_requirements_complete"] is False
    assert readiness["checks"]["implementation_files"]["status"] == "PASS"
    assert readiness["input_hashes"]["implementation_files"][0]["path"] == "method.rs"
    assert {Path(item["path"]).name for item in manifest_payload["files"]} >= {
        "protocol.md",
        "questions.json",
        "evaluator.py",
        "tests.py",
        "openapi.json",
        "runtime.json",
        "method.rs",
        "freeze_system_evidence.py",
    }


def test_rust_pilot_readiness_manifest_marks_missing_required_input_null_and_fail(tmp_path: Path) -> None:
    existing = tmp_path / "docs" / "experiments" / "rust-retrieval-pilot-protocol-v1.md"
    existing.parent.mkdir(parents=True)
    existing.write_text("protocol", encoding="utf-8")
    missing = tmp_path / "data" / "real" / "GSE111619" / "gse111619_questions.json"
    gate_script = tmp_path / "scripts" / "freeze_system_evidence.py"
    gate_script.parent.mkdir(parents=True)
    gate_script.write_bytes(SCRIPT.read_bytes())
    readiness = {"overall_verdict": "BLOCKED", "lifecycle": "NOT_FROZEN"}
    output = tmp_path / "preflight.json"
    manifest = tmp_path / "manifest.json"

    MODULE.write_rust_pilot_readiness(
        readiness,
        output=output,
        manifest_output=manifest,
        manifest_inputs=[existing, missing],
        gate_script=gate_script,
        root=tmp_path,
    )

    payload = json.loads(manifest.read_text(encoding="utf-8"))
    missing_entry = next(
        item
        for item in payload["files"]
        if item["path"] == "data/real/GSE111619/gse111619_questions.json"
    )
    assert missing_entry == {
        "path": "data/real/GSE111619/gse111619_questions.json",
        "sha256": None,
        "status": "FAIL",
    }
    assert payload["local_manifest_inputs_complete"] is False
    assert payload["freeze_requirements_complete"] is False
    assert payload["input_failures"] == ["data/real/GSE111619/gse111619_questions.json"]


def test_rust_pilot_readiness_fails_missing_required_implementation_file(tmp_path: Path) -> None:
    files = {}
    for name in ("protocol.md", "questions.json", "evaluator.py", "openapi.json", "runtime.json"):
        path = tmp_path / name
        path.write_text("{}", encoding="utf-8")
        files[name] = path
    missing = tmp_path / "backend" / "src" / "missing.rs"

    readiness = MODULE.build_rust_pilot_readiness(
        root=tmp_path,
        protocol=files["protocol.md"],
        questions=files["questions.json"],
        evaluator=files["evaluator.py"],
        openapi=files["openapi.json"],
        runtime_contract=files["runtime.json"],
        implementation_files=[missing],
        checkout={"base_revision": COMMIT, "tracked_worktree_clean": True, "worktree_clean": True},
    )

    assert readiness["checks"]["implementation_files"]["status"] == "FAIL"
    assert readiness["input_hashes"]["implementation_files"] == [
        {"path": "backend/src/missing.rs", "sha256": None, "status": "FAIL"}
    ]
    assert readiness["overall_verdict"] == "BLOCKED"


def test_default_system_manifest_contract_does_not_gain_rust_pilot_fields(tmp_path: Path, monkeypatch) -> None:
    write_lockfiles(tmp_path)
    monkeypatch.setattr(MODULE, "git_checkout_state", clean_checkout)
    source = tmp_path / "system.json"
    source.write_text("{}\n", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"

    MODULE.freeze([source], manifest_path, tmp_path, replace=False)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["schema"] == "full-system.system-evidence-manifest"
    assert manifest["schema_version"] == 1
    assert "rust_pilot_readiness" not in manifest
    assert "overall_verdict" not in manifest


def test_rust_pilot_readiness_cli_is_explicit_and_does_not_query_http(tmp_path: Path, monkeypatch) -> None:
    files = {}
    for name in ("protocol.md", "questions.json", "evaluator.py", "tests.py", "openapi.json", "runtime.json"):
        path = tmp_path / name
        path.write_text("{}" if name.endswith(".json") else name, encoding="utf-8")
        files[name] = path
    monkeypatch.setattr(MODULE, "rust_pilot_checkout_state", lambda _root: {
        "base_revision": COMMIT,
        "tracked_worktree_clean": False,
        "worktree_clean": False,
        "in_scope_untracked_files": [],
    })
    readiness = MODULE.build_rust_pilot_readiness(
        root=tmp_path,
        protocol=files["protocol.md"],
        questions=files["questions.json"],
        evaluator=files["evaluator.py"],
        evaluator_tests=files["tests.py"],
        openapi=files["openapi.json"],
        runtime_contract=files["runtime.json"],
    )
    assert readiness["overall_verdict"] == "BLOCKED"


def test_rust_pilot_gate_evidence_requires_self_hash_generator_and_command(tmp_path: Path) -> None:
    gate = tmp_path / "g5a.json"
    gate.write_text(json.dumps({"passed": True}), encoding="utf-8")
    result = MODULE._gate_evidence_check(gate, "G5A")
    assert result["status"] == "BLOCKED"
    assert result["value"] is True


def test_rust_pilot_gate_evidence_accepts_current_hash_bound_report(tmp_path: Path) -> None:
    gate = tmp_path / "g5a.json"
    report = tmp_path / "g5a-report.json"
    report.write_text("{\"passed\": true}\n", encoding="utf-8")
    payload = {
        "passed": True,
        "generator": "test-gate.py",
        "generator_version": 1,
        "command": "test-gate.py --verify",
        "report_sha256": "placeholder",
        "report_path": str(report),
    }
    gate.write_text(json.dumps(payload), encoding="utf-8")
    payload["report_sha256"] = hashlib.sha256(report.read_bytes()).hexdigest()
    gate.write_text(json.dumps(payload), encoding="utf-8")
    result = MODULE._gate_evidence_check(gate, "G5A")
    assert result["status"] == "PASS"
