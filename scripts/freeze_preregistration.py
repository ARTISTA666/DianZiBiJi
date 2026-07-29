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


def build_manifest(files: list[Path], root: Path | None = None) -> dict:
    root = (root or Path.cwd()).resolve()
    resolved = [path.resolve() for path in files]
    missing = [str(path) for path in resolved if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing files: " + ", ".join(missing))
    outside_root = [str(path) for path in resolved if not path.is_relative_to(root)]
    if outside_root:
        raise ValueError("Files must be inside the manifest root: " + ", ".join(outside_root))
    return {
        "format_version": 2,
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "path_base": "root_argument",
        "files": [
            {
                "path": path.relative_to(root).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in sorted(resolved, key=lambda item: str(item).lower())
        ],
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
    seen_paths: set[str] = set()
    duplicate_paths: set[str] = set()
    for entry in files:
        stored_path = str(entry.get("path", ""))
        if stored_path in seen_paths:
            duplicate_paths.add(stored_path)
        seen_paths.add(stored_path)
        path = Path(stored_path)
        inside_root = bool(stored_path) and not path.is_absolute() and not WINDOWS_ABSOLUTE_PATH.match(stored_path)
        actual_path = (root / path).resolve() if inside_root else path
        inside_root = inside_root and actual_path.is_relative_to(root)
        exists = inside_root and actual_path.is_file()
        actual_size = actual_path.stat().st_size if exists else None
        actual_sha256 = sha256_file(actual_path) if exists else None
        expected_size = entry.get("size_bytes")
        expected_sha256 = entry.get("sha256")
        checks.append(
            {
                "path": stored_path,
                "inside_root": inside_root,
                "exists": exists,
                "size_matches": exists and actual_size == expected_size,
                "sha256_matches": exists and actual_sha256 == expected_sha256,
                "expected_size_bytes": expected_size,
                "actual_size_bytes": actual_size,
                "expected_sha256": expected_sha256,
                "actual_sha256": actual_sha256,
                "duplicate_path": stored_path in duplicate_paths,
            }
        )
    valid_shape = manifest.get("format_version") == 2 and manifest.get("path_base") == "root_argument" and isinstance(manifest.get("files"), list)
    ok = valid_shape and bool(checks) and not duplicate_paths and all(
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
        "duplicate_paths": sorted(duplicate_paths),
        "checks": checks,
    }


def self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "rules.txt"
        path.write_text("frozen rules\n", encoding="utf-8")
        manifest = build_manifest([path], Path(tmp))
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
    manifest = build_manifest(args.files, args.root)
    write_manifest(manifest, args.output, replace=args.replace)
    print(f"wrote {args.output} with {len(manifest['files'])} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
