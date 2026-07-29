from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SCRIPT = ROOT / "scripts" / "freeze_system_evidence.py"
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
