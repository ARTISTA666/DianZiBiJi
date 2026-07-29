#!/usr/bin/env python3
"""Validate offsite encrypted backup evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


REMOTE_SCHEMES = {"s3", "gs", "az", "azure", "b2", "rclone", "https"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_report(report: dict[str, Any], *, root: Path) -> dict[str, Any]:
    target_uri = str(report.get("target_uri") or "")
    parsed_target = urlparse(target_uri)
    scheme = parsed_target.scheme
    remote_target = scheme in REMOTE_SCHEMES and bool(parsed_target.netloc) and parsed_target.path not in {"", "/"}
    restore_report = str(report.get("restore_drill_report") or "")
    expected_hash = str(report.get("restore_drill_sha256") or "")
    root_resolved = root.resolve()
    restore_path = (root / restore_report).resolve()
    restore_inside_root = bool(restore_report) and not Path(restore_report).is_absolute() and restore_path.is_relative_to(root_resolved)
    restore_hash_ok = restore_inside_root and restore_path.is_file() and bool(expected_hash) and sha256(restore_path) == expected_hash
    restore_payload: dict[str, Any] = {}
    if restore_hash_ok:
        try:
            restore_payload = json.loads(restore_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            restore_payload = {}
    restore_drill_ok = (
        restore_payload.get("ok") is True
        and isinstance(restore_payload.get("generated_at"), str)
        and bool(restore_payload.get("checks"))
    )
    checks = [
        {"name": "report ok", "passed": bool(report.get("ok"))},
        {"name": "backup encrypted", "passed": bool(report.get("encrypted"))},
        {"name": "backup offsite", "passed": bool(report.get("offsite"))},
        {"name": "remote target uri", "passed": remote_target, "actual": target_uri},
        {"name": "retention policy configured", "passed": bool(report.get("retention_policy_configured"))},
        {"name": "latest restore drill passed", "passed": bool(report.get("latest_restore_drill_passed"))},
        {"name": "restore drill report inside evidence root", "passed": restore_inside_root, "actual": restore_report},
        {"name": "restore drill report hash", "passed": restore_hash_ok, "actual": restore_report},
        {"name": "restore drill report ok", "passed": restore_drill_ok, "actual": restore_report},
    ]
    return {"ok": all(item["passed"] for item in checks), "checks": checks}


def validate_path(path: Path, *, root: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"ok": False, "checks": [{"name": "report exists", "passed": False, "detail": str(path)}]}
    report = json.loads(path.read_text(encoding="utf-8"))
    result = validate_report(report, root=root)
    return {"source": str(path), **report, **result}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate_path(args.report, root=args.root)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
