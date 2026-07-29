#!/usr/bin/env python3
"""Freeze or verify the evidence files consumed by the maturity gate."""

from __future__ import annotations

import argparse
import json
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


ROOT = Path(__file__).resolve().parents[1]
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
    parser.add_argument("files", nargs="*", type=Path, help="Override the default maturity evidence file list.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--verify", type=Path, help="Verify an existing evidence manifest instead of freezing.")
    parser.add_argument("--replace", action="store_true", help="Replace an existing manifest intentionally.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.verify:
        report = verify_manifest(args.verify, args.root)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1
    report = freeze(args.files or DEFAULT_FILES, args.output, args.root, args.replace)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
