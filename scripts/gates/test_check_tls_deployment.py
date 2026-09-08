from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_tls_deployment.py"
SPEC = importlib.util.spec_from_file_location("check_tls_deployment", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_rejects_plain_http_url() -> None:
    result = MODULE.check_url("http://example.test")

    assert result["ok"] is False
    assert result["checks"][0]["name"] == "https url"


def test_rejects_localhost_endpoint() -> None:
    result = MODULE.check_url("https://localhost")

    assert result["ok"] is False
    assert {"name": "public endpoint", "passed": False, "actual": "localhost"} in result["checks"]


def test_rejects_private_ip_endpoint() -> None:
    result = MODULE.check_url("https://10.0.0.5")

    assert result["ok"] is False
    assert {"name": "public endpoint", "passed": False, "actual": "10.0.0.5"} in result["checks"]


def test_accepts_https_with_valid_cert_and_hsts(monkeypatch) -> None:
    monkeypatch.setattr(MODULE, "certificate_not_expired", lambda host, port, timeout: {"certificate_valid": True, "not_after": "ok"})
    monkeypatch.setattr(MODULE, "fetch_headers", lambda url, timeout: {"status": 200, "headers": {"Strict-Transport-Security": "max-age=31536000"}})

    result = MODULE.check_url("https://eln.example.test")

    assert result["ok"] is True
    assert result["certificate_valid"] is True
    assert result["hsts_enabled"] is True
    assert result["hsts_max_age"] == 31536000


def test_rejects_weak_hsts(monkeypatch) -> None:
    monkeypatch.setattr(MODULE, "certificate_not_expired", lambda host, port, timeout: {"certificate_valid": True, "not_after": "ok"})
    monkeypatch.setattr(MODULE, "fetch_headers", lambda url, timeout: {"status": 200, "headers": {"Strict-Transport-Security": "max-age=60"}})

    result = MODULE.check_url("https://eln.example.test")

    assert result["ok"] is False
    assert result["hsts_enabled"] is False


def test_validate_report_rejects_handwritten_top_level_booleans() -> None:
    result = MODULE.validate_report(
        {
            "ok": True,
            "https_url": "https://eln.example.test",
            "certificate_valid": True,
            "hsts_enabled": True,
        }
    )

    failed = {item["name"] for item in result["checks"] if not item["passed"]}
    assert "required check records present" in failed
    assert "hsts max age" in failed


def test_validate_report_rejects_localhost_even_with_passed_checks() -> None:
    report = {
        "ok": True,
        "https_url": "https://localhost",
        "certificate_valid": True,
        "hsts_enabled": True,
        "hsts_max_age": 31536000,
        "checks": [
            {"name": "https url", "passed": True},
            {"name": "public endpoint", "passed": True},
            {"name": "certificate valid", "passed": True},
            {"name": "http status", "passed": True},
            {"name": "hsts enabled", "passed": True},
        ],
    }

    result = MODULE.validate_report(report)

    failed = {item["name"] for item in result["checks"] if not item["passed"]}
    assert "public endpoint" in failed


def test_validate_report_accepts_checker_shape() -> None:
    report = {
        "ok": True,
        "https_url": "https://eln.example.test",
        "certificate_valid": True,
        "hsts_enabled": True,
        "hsts_max_age": 31536000,
        "checks": [
            {"name": "https url", "passed": True},
            {"name": "public endpoint", "passed": True},
            {"name": "certificate valid", "passed": True},
            {"name": "http status", "passed": True},
            {"name": "hsts enabled", "passed": True},
        ],
    }

    result = MODULE.validate_report(report)

    assert result["ok"] is True
