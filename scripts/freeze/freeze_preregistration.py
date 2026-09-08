"""Create a SHA-256 manifest for a preregistered experiment bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


WINDOWS_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[\\/]")


def _canonical_manifest_path(stored_path: object, root: Path) -> str | None:
    """Return the only accepted repo-relative POSIX spelling for a file."""
    if not isinstance(stored_path, str) or not stored_path:
        return None
    if stored_path.startswith("/") or WINDOWS_ABSOLUTE_PATH.match(stored_path) or "\\" in stored_path:
        return None
    parts = stored_path.split("/")
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
    return canonical if canonical == stored_path else None


def _evidence_revision(files: list[dict], runtime_source_revision: str | None, experiment_tooling_revision: str | None) -> dict:
    ordered = sorted(
        [
            {"path": item["path"], "sha256": item["sha256"]}
            for item in files
            if isinstance(item, dict) and isinstance(item.get("path"), str) and isinstance(item.get("sha256"), str)
        ],
        key=lambda item: (item["path"], item["sha256"]),
    )
    content = {
        "files": ordered,
        "runtime_source_revision": runtime_source_revision,
        "experiment_tooling_revision": experiment_tooling_revision,
    }
    encoded = json.dumps(content, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return {"schema": "full-system.evidence-revision-v1", **content, "sha256": hashlib.sha256(encoded).hexdigest()}


def build_manifest(
    files: list[Path],
    root: Path | None = None,
    *,
    runtime_source_revision: str | None = None,
    experiment_tooling_revision: str | None = None,
    manifest_path: Path | None = None,
) -> dict:
    root = (root or Path.cwd()).resolve()
    resolved = [path.resolve() for path in files]
    missing = [str(path) for path in resolved if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing files: " + ", ".join(missing))
    outside_root = [str(path) for path in resolved if not path.is_relative_to(root)]
    if outside_root:
        raise ValueError("Files must be inside the manifest root: " + ", ".join(outside_root))
    manifest_resolved = manifest_path.resolve() if manifest_path is not None else None
    entries = [
        {
            "path": path.relative_to(root).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(resolved, key=lambda item: str(item).lower())
        if manifest_resolved is None or path != manifest_resolved
    ]
    return {
        "format_version": 2,
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "path_base": "root_argument",
        "runtime_source_revision": runtime_source_revision,
        "experiment_tooling_revision": experiment_tooling_revision,
        "files": entries,
        "evidence_revision": _evidence_revision(entries, runtime_source_revision, experiment_tooling_revision),
    }


def write_manifest(manifest: dict, output: Path, replace: bool = False) -> None:
    if output.exists() and not replace:
        raise FileExistsError(f"Manifest already exists: {output}. Use --replace only for an intentional new freeze.")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def verify_manifest(manifest_path: Path, root: Path | None = None) -> dict:
    root = (root or Path.cwd()).resolve()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "verified_at_utc": datetime.now(timezone.utc).isoformat(),
            "manifest": str(manifest_path.resolve()),
            "ok": False,
            "file_count": 0,
            "checks": [{"path": str(manifest_path), "inside_root": True, "exists": manifest_path.is_file(), "error": str(exc)}],
        }
    if not isinstance(manifest, dict):
        return {
            "verified_at_utc": datetime.now(timezone.utc).isoformat(),
            "manifest": str(manifest_path.resolve()),
            "ok": False,
            "file_count": 0,
            "checks": [{"path": str(manifest_path), "inside_root": True, "exists": manifest_path.is_file(), "error": "manifest must contain a JSON object"}],
        }
    checks = []
    files = manifest.get("files") if isinstance(manifest.get("files"), list) else []
    manifest_relative = None
    try:
        manifest_relative = manifest_path.resolve().relative_to(root).as_posix()
    except ValueError:
        pass
    self_paths = {manifest_relative} if manifest_relative else set()
    seen_paths: set[str] = set()
    duplicate_paths: set[str] = set()
    canonical_entries: list[dict] = []
    for entry in files:
        stored_path = entry.get("path") if isinstance(entry, dict) else None
        stored_path = stored_path if isinstance(stored_path, str) else ""
        if stored_path in self_paths:
            continue
        canonical_path = _canonical_manifest_path(stored_path, root)
        if canonical_path is not None:
            if canonical_path in seen_paths:
                duplicate_paths.add(canonical_path)
            seen_paths.add(canonical_path)
            canonical_entries.append({"path": canonical_path, "sha256": entry.get("sha256")})
        actual_path = root / canonical_path if canonical_path is not None else Path(stored_path)
        inside_root = canonical_path is not None
        exists = inside_root and actual_path.is_file()
        actual_size = actual_path.stat().st_size if exists else None
        actual_sha256 = sha256_file(actual_path) if exists else None
        expected_size = entry.get("size_bytes")
        expected_sha256 = entry.get("sha256")
        checks.append(
            {
                "path": stored_path,
                "canonical_path": canonical_path,
                "inside_root": inside_root,
                "exists": exists,
                "size_matches": exists and actual_size == expected_size,
                "sha256_matches": exists and actual_sha256 == expected_sha256,
                "expected_size_bytes": expected_size,
                "actual_size_bytes": actual_size,
                "expected_sha256": expected_sha256,
                "actual_sha256": actual_sha256,
                "duplicate_path": canonical_path in duplicate_paths if canonical_path is not None else False,
            }
        )
    valid_shape = manifest.get("format_version") == 2 and manifest.get("path_base") == "root_argument" and isinstance(manifest.get("files"), list)
    evidence = manifest.get("evidence_revision")
    expected_evidence = _evidence_revision(
        canonical_entries,
        manifest.get("runtime_source_revision"),
        manifest.get("experiment_tooling_revision"),
    )
    evidence_ok = isinstance(evidence, dict) and evidence == expected_evidence
    ok = valid_shape and bool(checks) and not duplicate_paths and evidence_ok and all(
        item["inside_root"] and item["exists"] and item["size_matches"] and item["sha256_matches"]
        for item in checks
    )
    return {
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "manifest": str(manifest_path.resolve()),
        "ok": ok,
        "file_count": len(checks),
        "format_version": manifest.get("format_version"),
        "path_base": manifest.get("path_base"),
        "valid_shape": valid_shape,
        "evidence_revision_valid": evidence_ok,
        "duplicate_paths": sorted(duplicate_paths),
        "checks": checks,
    }


def self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "rules.txt"
        path.write_text("frozen rules\n", encoding="utf-8")
        manifest = build_manifest([path], Path(tmp), runtime_source_revision="r" * 40, experiment_tooling_revision="t" * 40)
        assert len(manifest["files"]) == 1
        assert manifest["files"][0]["path"] == "rules.txt"
        assert manifest["files"][0]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        output = Path(tmp) / "manifest.json"
        write_manifest(manifest, output)
        assert verify_manifest(output, Path(tmp))["ok"] is True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path, help="Files to freeze.")
    parser.add_argument("-o", "--output", type=Path, required=False, help="JSON manifest path.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Root used for portable manifest paths.")
    parser.add_argument("--verify", type=Path, help="Verify an existing manifest instead of creating one.")
    parser.add_argument("--replace", action="store_true", help="Replace an existing manifest intentionally.")
    parser.add_argument("--runtime-source-revision", help="R: revision of the deployed runtime source.")
    parser.add_argument("--experiment-tooling-revision", help="T: clean checkout revision for experiment tooling.")
    parser.add_argument("--self-test", action="store_true", help="Run built-in checks.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        print("self-test passed")
        return 0
    if args.verify:
        report = verify_manifest(args.verify, args.root)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1
    if not args.files or not args.output:
        raise SystemExit("Provide files and --output, use --verify, or use --self-test.")
    manifest = build_manifest(
        args.files,
        args.root,
        runtime_source_revision=args.runtime_source_revision,
        experiment_tooling_revision=args.experiment_tooling_revision,
        manifest_path=args.output,
    )
    write_manifest(manifest, args.output, replace=args.replace)
    print(f"wrote {args.output} with {len(manifest['files'])} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
