#!/usr/bin/env python3
"""Fail-closed freshness check for SHA-256 tables embedded in paper material."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


FINGERPRINT_ROW = re.compile(
    r"^\|\s*(?P<name>[^|]+?)\s*\|\s*`(?P<path>[^`]+)`\s*\|\s*`(?P<digest>[^`]+)`\s*\|\s*$"
)
SHA256 = re.compile(r"^[0-9a-f]{64}$")
FINGERPRINT_SECTION = "## 输入材料指纹"
FINGERPRINT_HEADER = ("材料", "路径", "SHA-256")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_table_separator(line: str) -> bool:
    cells = _table_cells(line)
    return bool(cells) and all(cell and set(cell) <= {"-", ":"} for cell in cells)


def _parse_fingerprint_table(material_path: Path) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    rows: list[dict[str, str]] = []
    errors: list[dict[str, Any]] = []
    in_section = False
    section_found = False
    for line_number, line in enumerate(material_path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if stripped == FINGERPRINT_SECTION:
            in_section = True
            section_found = True
            continue
        if in_section and stripped.startswith("## "):
            break
        if not in_section or not stripped or not stripped.startswith("|"):
            continue
        cells = _table_cells(line)
        if tuple(cells) == FINGERPRINT_HEADER or _is_table_separator(line):
            continue
        match = FINGERPRINT_ROW.match(line)
        if match and match.group("name") != "材料":
            rows.append({key: value.strip() for key, value in match.groupdict().items()})
        else:
            errors.append({"reason": "malformed_fingerprint_row", "line": line_number})

    if not section_found:
        errors.append({"reason": "missing_fingerprint_section"})
    elif not rows and not errors:
        errors.append({"reason": "empty_fingerprint_table"})
    return rows, errors


def fingerprint_rows(material_path: Path) -> list[dict[str, str]]:
    rows, _ = _parse_fingerprint_table(material_path)
    return rows


def _relative_to_root(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return Path(os.path.relpath(path.resolve(), root.resolve())).as_posix()


def check_material(material_path: Path, root: Path) -> dict[str, Any]:
    material_path = material_path.resolve()
    root = root.resolve()
    rows, parse_errors = _parse_fingerprint_table(material_path)
    mismatches: list[dict[str, Any]] = list(parse_errors)
    try:
        material_path.relative_to(root)
    except ValueError:
        mismatches.append({"reason": "material_outside_root"})
    seen_names: set[str] = set()

    for row in rows:
        name = row["name"]
        expected = row["digest"]
        if name in seen_names:
            mismatches.append({"name": name, "reason": "duplicate_name"})
        seen_names.add(name)
        if not SHA256.fullmatch(expected):
            mismatches.append(
                {"name": name, "path": row["path"], "reason": "malformed_digest", "expected_sha256": expected}
            )

        source_path = Path(row["path"])
        resolved = source_path.resolve() if source_path.is_absolute() else (root / source_path).resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            mismatches.append(
                {"name": name, "path": row["path"], "reason": "outside_root", "expected_sha256": expected}
            )
            continue
        if not resolved.is_file():
            mismatches.append(
                {"name": name, "path": row["path"], "reason": "missing_input", "expected_sha256": expected}
            )
            continue
        actual = sha256_file(resolved)
        if SHA256.fullmatch(expected) and actual != expected:
            mismatches.append(
                {
                    "name": name,
                    "path": row["path"],
                    "reason": "digest_mismatch",
                    "expected_sha256": expected,
                    "actual_sha256": actual,
                }
            )

    return {
        "schema_version": "paper-material-freshness-v1",
        "material": _relative_to_root(material_path, root),
        "root": ".",
        "fingerprints": len(rows),
        "checked": sum(
            1
            for row in rows
            if SHA256.fullmatch(row["digest"])
            and (root / row["path"]).resolve().is_file()
            and (root / row["path"]).resolve().is_relative_to(root)
        ),
        "passed": bool(rows) and not mismatches,
        "mismatches": mismatches,
    }


def run_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("material", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = check_material(args.material, args.root)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(run_cli())
