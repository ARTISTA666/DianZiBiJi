#!/usr/bin/env python3
"""Check that local .env secret values were not written into shareable artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


SECRET_KEYS = (
    "SECRET_KEY",
    "BOOTSTRAP_ADMIN_PASSWORD",
    "POSTGRES_PASSWORD",
    "DEEPSEEK_API_KEY",
)
DEFAULT_SCAN_ROOTS = ("README.md", "docs", "scripts", "backend", "frontend")
SKIP_PARTS = {".git", "node_modules", ".next", ".venv", "__pycache__"}
TEXT_SUFFIXES = {
    ".csv",
    ".env",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".ts",
    ".tsx",
    ".txt",
    ".yml",
    ".yaml",
}


def read_env(path: Path) -> dict[str, str]:
    values = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key.strip()] = value.strip()
    return values


def sensitive_values(env: dict[str, str]) -> dict[str, str]:
    result = {}
    for key in SECRET_KEYS:
        value = env.get(key, "")
        if len(value) >= 8 and value not in {"admin123", "eln_password", "change-me-in-production"}:
            result[key] = value
    return result


def iter_scan_files(root: Path, targets: list[str]) -> list[Path]:
    files: list[Path] = []
    for target in targets:
        path = root / target
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            for candidate in path.rglob("*"):
                if candidate.is_file() and candidate.suffix in TEXT_SUFFIXES and not (SKIP_PARTS & set(candidate.parts)):
                    files.append(candidate)
    return files


def check(root: Path, env_file: Path, targets: list[str] | None = None) -> dict:
    secrets = sensitive_values(read_env(env_file))
    leaks = []
    for path in iter_scan_files(root, targets or list(DEFAULT_SCAN_ROOTS)):
        if path.resolve() == env_file.resolve():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for key, value in secrets.items():
            if value and value in text:
                leaks.append({"secret_key": key, "path": str(path.relative_to(root))})
    return {
        "ok": not leaks,
        "checked_secret_keys": sorted(secrets),
        "scan_targets": targets or list(DEFAULT_SCAN_ROOTS),
        "leaks": leaks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--target", action="append", dest="targets")
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    env_file = args.env_file if args.env_file.is_absolute() else root / args.env_file
    result = check(root, env_file, args.targets)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
