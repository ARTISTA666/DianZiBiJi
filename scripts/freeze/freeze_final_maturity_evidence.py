#!/usr/bin/env python3
"""Freeze or verify the files consumed by the final maturity gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from freeze_preregistration import build_manifest, verify_manifest, write_manifest


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "docs" / "experiments" / "final-maturity-evidence-manifest.json"
DEFAULT_FILES = [
    ROOT / "docs" / "experiments" / "main-maturity-gate-latest.json",
    ROOT / "docs" / "system-evidence" / "validation-results.json",
    ROOT / "docs" / "system-evidence" / "production-config-latest.json",
    ROOT / "docs" / "experiments" / "confirmatory-human-review-freeze.json",
    ROOT / "docs" / "system-evidence" / "long-soak-latest.json",
    ROOT / "docs" / "system-evidence" / "tls-deployment-latest.json",
    ROOT / "docs" / "system-evidence" / "offsite-backup-latest.json",
]


def freeze(files: list[Path], output: Path, root: Path, replace: bool) -> dict:
    manifest = build_manifest(files, root)
    write_manifest(manifest, output, replace=replace)
    return {"ok": True, "output": str(output), "file_count": len(manifest["files"])}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path, help="Override the default final evidence file list.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--verify", type=Path, help="Verify an existing final evidence manifest instead of freezing.")
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
