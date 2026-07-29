from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_production_config.py"
SPEC = importlib.util.spec_from_file_location("check_production_config", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


@pytest.fixture(autouse=True)
def accept_rust_runtime_config(monkeypatch) -> None:
    monkeypatch.setattr(
        MODULE,
        "rust_runtime_config_check",
        lambda _values, _checker=None: {
            "passed": True,
            "available": True,
            "exit_code": 0,
            "checker_sha256": "test-double",
            "timed_out": False,
        },
    )


def write_env(path: Path, **values: str) -> Path:
    path.write_text("\n".join(f"{key}={value}" for key, value in values.items()) + "\n", encoding="utf-8")
    return path


def safe_production_values(**overrides: str) -> dict[str, str]:
    values = {
        "APP_ENV": "production",
        "SECRET_KEY": "s" * 32,
        "BOOTSTRAP_ADMIN_PASSWORD": "a-secure-bootstrap-password",
        "POSTGRES_PASSWORD": "a-secure-database-password",
        "SEED_DEMO_DATA": "false",
        "DEEPSEEK_API_BASE_URL": "https://api.deepseek.com",
        "DEEPSEEK_API_KEY": "production-api-key",
        "APP_REVISION": "release-2026.07.29",
        "CORS_ORIGINS": "https://eln.example.org",
        "NEXT_PUBLIC_API_BASE_URL": "/api",
        "EMBEDDING_BACKEND": "hash",
        "EMBEDDING_MODEL": "rust-hash-512-v1",
        "EMBEDDING_DIMENSION": "512",
    }
    values.update(overrides)
    return values


def test_production_rejects_browser_api_pointing_at_user_localhost(tmp_path: Path) -> None:
    env = write_env(
        tmp_path / ".env",
        **safe_production_values(NEXT_PUBLIC_API_BASE_URL="http://localhost:8001"),
    )

    result = MODULE.check(env)

    assert result["ok"] is False
    assert result["checks"]["frontend_api_is_same_origin"] is False


def test_production_rejects_rust_incompatible_embedding(tmp_path: Path) -> None:
    env = write_env(
        tmp_path / ".env",
        **safe_production_values(EMBEDDING_MODEL="BAAI/bge-small-zh-v1.5"),
    )

    result = MODULE.check(env)

    assert result["ok"] is False
    assert result["checks"]["embedding_matches_rust_runtime"] is False


def test_production_fails_when_rust_runtime_rejects_config(
    tmp_path: Path, monkeypatch
) -> None:
    env = write_env(
        tmp_path / ".env",
        **safe_production_values(DEEPSEEK_MAX_CONCURRENCY="0"),
    )
    monkeypatch.setattr(
        MODULE,
        "rust_runtime_config_check",
        lambda _values, _checker=None: {"passed": False, "available": True},
        raising=False,
    )

    result = MODULE.check(env)

    assert result["ok"] is False
    assert result["checks"]["rust_runtime_settings_accepted"] is False


def test_compose_ports_must_bind_to_loopback() -> None:
    unsafe = 'ports:\n  - "${BACKEND_PORT:-8001}:8000"\n  - "${FRONTEND_PORT:-3000}:3000"\n'
    safe = 'ports:\n  - "127.0.0.1:${BACKEND_PORT:-8001}:8000"\n  - "127.0.0.1:${FRONTEND_PORT:-3000}:3000"\n'

    assert MODULE.compose_ports_are_loopback(unsafe) is False
    assert MODULE.compose_ports_are_loopback(safe) is True


def test_non_production_is_explicitly_skipped(tmp_path: Path) -> None:
    env = write_env(tmp_path / ".env", APP_ENV="development")

    result = MODULE.check(env)

    assert result["ok"] is True
    assert result["status"] == "skipped_non_production"
    assert result["env_file_sha256"] == MODULE.sha256(env)
    assert result["checks"]["app_env_is_production"] is False


def test_production_rejects_unsafe_defaults(tmp_path: Path) -> None:
    env = write_env(tmp_path / ".env", APP_ENV="production", SEED_DEMO_DATA="true")

    result = MODULE.check(env)

    assert result["ok"] is False
    assert "SECRET_KEY" in result["message"]
    assert "SEED_DEMO_DATA" in result["message"]
    assert result["checks"]["secret_key_non_default"] is False
    assert result["checks"]["seed_demo_data_disabled"] is False


def test_production_requires_env_file_to_cover_all_required_keys(tmp_path: Path) -> None:
    env = write_env(
        tmp_path / ".env",
        APP_ENV="production",
        SECRET_KEY="s" * 32,
        BOOTSTRAP_ADMIN_PASSWORD="a-secure-bootstrap-password",
        POSTGRES_PASSWORD="a-secure-database-password",
        SEED_DEMO_DATA="false",
        DEEPSEEK_API_KEY="production-api-key",
    )

    result = MODULE.check(env)

    assert result["ok"] is False
    assert result["status"] == "failed"
    supplied = {
        "APP_ENV",
        "SECRET_KEY",
        "BOOTSTRAP_ADMIN_PASSWORD",
        "POSTGRES_PASSWORD",
        "SEED_DEMO_DATA",
        "DEEPSEEK_API_KEY",
    }
    assert set(result["missing_checked_keys"]) == MODULE.REQUIRED_PRODUCTION_KEYS - supplied
    assert "one env file" in result["message"]


def test_production_accepts_safe_values(tmp_path: Path) -> None:
    env = write_env(tmp_path / ".env", **safe_production_values())

    result = MODULE.check(env)

    assert result["ok"] is True
    assert result["status"] == "passed"
    assert set(result["checked_keys"]) == MODULE.REQUIRED_PRODUCTION_KEYS
    assert set(result["checks"]) == MODULE.REQUIRED_PRODUCTION_CHECKS
    assert result["missing_checked_keys"] == []
    assert all(result["checks"].values())
