#!/usr/bin/env python3
"""Preflight production configuration without printing secrets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import Settings  # noqa: E402


REQUIRED_PRODUCTION_KEYS = {
    "APP_ENV",
    "SECRET_KEY",
    "BOOTSTRAP_ADMIN_PASSWORD",
    "POSTGRES_PASSWORD",
    "SEED_DEMO_DATA",
    "CORS_ORIGINS",
    "NEXT_PUBLIC_API_BASE_URL",
    "DEEPSEEK_API_BASE_URL",
    "DEEPSEEK_API_KEY",
    "APP_REVISION",
    "EMBEDDING_BACKEND",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIMENSION",
}

REQUIRED_PRODUCTION_CHECKS = {
    "app_env_is_production",
    "secret_key_non_default",
    "bootstrap_admin_password_non_default",
    "postgres_password_non_default",
    "seed_demo_data_disabled",
    "cors_origins_are_https",
    "frontend_api_is_same_origin",
    "deepseek_api_uses_https",
    "deepseek_api_key_present",
    "app_revision_present",
    "embedding_matches_rust_runtime",
    "rust_runtime_settings_accepted",
    "compose_ports_bind_loopback",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_keys(env_file: Path | None) -> list[str]:
    if not env_file or not env_file.is_file():
        return []
    keys = []
    for line in env_file.read_text(encoding="utf-8").splitlines():
        key, separator, _value = line.partition("=")
        key = key.strip()
        if separator and key in REQUIRED_PRODUCTION_KEYS:
            keys.append(key)
    return sorted(set(keys))


def read_env_values(env_file: Path | None) -> dict[str, str]:
    if not env_file or not env_file.is_file():
        return {}
    values = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        key = key.strip()
        if separator and key and not key.startswith("#"):
            values[key] = value.strip()
    return values


def compose_ports_are_loopback(text: str) -> bool:
    mappings = [
        match.group(1)
        for match in re.finditer(r'^\s*-\s*["\']?([^"\'\s]+)["\']?\s*$', text, re.MULTILINE)
    ]
    for container_port in ("8000", "3000"):
        exposed = [mapping for mapping in mappings if mapping.endswith(f":{container_port}")]
        if len(exposed) != 1 or not exposed[0].startswith("127.0.0.1:"):
            return False
    return True


def is_https_origin(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.hostname) and parsed.hostname not in {"localhost", "127.0.0.1"}


def rust_runtime_config_check(
    values: dict[str, str], checker: Path | None = None
) -> dict[str, object]:
    if checker is None or not checker.is_file() or not os.access(checker, os.X_OK):
        return {
            "available": False,
            "passed": False,
            "exit_code": None,
            "checker_sha256": sha256(checker) if checker and checker.is_file() else None,
            "timed_out": False,
        }
    runtime_env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    runtime_env.update(values)
    try:
        completed = subprocess.run(
            [str(checker.resolve()), "--check-config"],
            cwd=ROOT,
            env=runtime_env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "available": not isinstance(exc, OSError),
            "passed": False,
            "exit_code": None,
            "checker_sha256": sha256(checker),
            "timed_out": isinstance(exc, subprocess.TimeoutExpired),
        }
    return {
        "available": True,
        "passed": completed.returncode == 0,
        "exit_code": completed.returncode,
        "checker_sha256": sha256(checker),
        "timed_out": False,
    }


def production_checks(
    settings: Settings,
    env_file: Path | None = None,
    runtime_check: dict[str, object] | None = None,
) -> dict[str, bool]:
    values = read_env_values(env_file)
    cors_origins = [origin.strip() for origin in values.get("CORS_ORIGINS", "").split(",") if origin.strip()]
    compose_path = ROOT / "docker-compose.yml"
    compose_safe = compose_path.is_file() and compose_ports_are_loopback(
        compose_path.read_text(encoding="utf-8")
    )
    return {
        "app_env_is_production": settings.app_env == "production",
        "secret_key_non_default": settings.secret_key != "change-me-in-production" and len(settings.secret_key) >= 32,
        "bootstrap_admin_password_non_default": settings.bootstrap_admin_password != "admin123"
        and len(settings.bootstrap_admin_password) >= 12,
        "postgres_password_non_default": settings.postgres_password != "eln_password"
        and len(settings.postgres_password) >= 12,
        "seed_demo_data_disabled": not settings.seed_demo_data,
        "cors_origins_are_https": bool(cors_origins) and all(is_https_origin(origin) for origin in cors_origins),
        "frontend_api_is_same_origin": values.get("NEXT_PUBLIC_API_BASE_URL") == "/api",
        "deepseek_api_uses_https": is_https_origin(values.get("DEEPSEEK_API_BASE_URL", "")),
        "deepseek_api_key_present": bool(settings.deepseek_api_key.strip()),
        "app_revision_present": bool(settings.app_revision.strip()) and settings.app_revision != "unversioned",
        "embedding_matches_rust_runtime": (
            values.get("EMBEDDING_BACKEND") == "hash"
            and values.get("EMBEDDING_MODEL") == "rust-hash-512-v1"
            and values.get("EMBEDDING_DIMENSION") == "512"
        ),
        "rust_runtime_settings_accepted": bool((runtime_check or {}).get("passed")),
        "compose_ports_bind_loopback": compose_safe,
    }


def check(
    env_file: Path | None = None, rust_config_checker: Path | None = None
) -> dict:
    settings = Settings(_env_file=env_file) if env_file else Settings()
    keys = checked_keys(env_file)
    values = read_env_values(env_file)
    runtime_check = (
        rust_runtime_config_check(values, rust_config_checker)
        if settings.app_env == "production"
        else {
            "available": False,
            "passed": False,
            "exit_code": None,
            "checker_sha256": None,
            "timed_out": False,
        }
    )
    evidence = {
        "env_file": str(env_file) if env_file else None,
        "env_file_sha256": sha256(env_file) if env_file and env_file.is_file() else None,
        "checked_keys": keys,
        "missing_checked_keys": sorted(REQUIRED_PRODUCTION_KEYS - set(keys)),
        "checks": production_checks(settings, env_file, runtime_check),
        "rust_runtime_check": runtime_check,
    }
    if settings.app_env != "production":
        return {
            "ok": True,
            "status": "skipped_non_production",
            "app_env": settings.app_env,
            "message": "Production safety checks are enforced only when APP_ENV=production.",
            **evidence,
        }
    problems = []
    if not env_file or not env_file.is_file() or set(keys) != REQUIRED_PRODUCTION_KEYS:
        problems.append("production evidence must come from one env file covering every required key")
    try:
        settings.validate_runtime()
    except RuntimeError as exc:
        problems.append(str(exc))
    failed_checks = sorted(name for name, passed in evidence["checks"].items() if not passed)
    if failed_checks:
        problems.append(f"failed production checks: {', '.join(failed_checks)}")
    if problems:
        return {
            "ok": False,
            "status": "failed",
            "app_env": settings.app_env,
            "message": "; ".join(problems),
            **evidence,
        }
    return {
        "ok": True,
        "status": "passed",
        "app_env": settings.app_env,
        "message": "Production configuration passed safety checks.",
        **evidence,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument(
        "--rust-config-checker",
        type=Path,
        help="Current eln-backend binary used for the fail-closed Rust runtime config check.",
    )
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args()
    result = check(args.env_file, args.rust_config_checker)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
