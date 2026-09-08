#!/usr/bin/env python3
"""Validate a real HTTPS deployment endpoint."""

from __future__ import annotations

import argparse
import ipaddress
import json
import socket
import ssl
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen


MIN_HSTS_MAX_AGE = 31_536_000


def public_endpoint_hostname(hostname: str | None) -> bool:
    if not hostname:
        return False
    normalized = hostname.rstrip(".").lower()
    if normalized in {"localhost", "127.0.0.1", "::1"} or normalized.endswith(".local"):
        return False
    try:
        return ipaddress.ip_address(normalized).is_global
    except ValueError:
        return True


def certificate_not_expired(hostname: str, port: int, timeout: float) -> dict[str, Any]:
    context = ssl.create_default_context()
    with socket.create_connection((hostname, port), timeout=timeout) as sock:
        with context.wrap_socket(sock, server_hostname=hostname) as tls:
            cert = tls.getpeercert()
    not_after = cert.get("notAfter")
    expires_at = ssl.cert_time_to_seconds(not_after) if not_after else 0
    return {
        "not_after": not_after,
        "certificate_valid": expires_at > datetime.now(timezone.utc).timestamp(),
    }


def fetch_headers(url: str, timeout: float) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": "full-system-final-maturity-gate"})
    with urlopen(request, timeout=timeout) as response:
        return {"status": response.status, "headers": dict(response.headers)}


def hsts_max_age(value: str) -> int:
    for part in value.split(";"):
        key, separator, raw = part.strip().partition("=")
        if separator and key.lower() == "max-age":
            try:
                return int(raw)
            except ValueError:
                return 0
    return 0


def validate_report(report: dict[str, Any]) -> dict[str, Any]:
    check_map = {item.get("name"): item for item in report.get("checks", []) if isinstance(item, dict)}
    required_checks = {"https url", "public endpoint", "certificate valid", "http status", "hsts enabled"}
    parsed = urlparse(str(report.get("https_url") or ""))
    checks = [
        {"name": "report ok", "passed": bool(report.get("ok"))},
        {"name": "https url", "passed": parsed.scheme == "https" and bool(parsed.hostname), "actual": report.get("https_url")},
        {"name": "public endpoint", "passed": public_endpoint_hostname(parsed.hostname), "actual": parsed.hostname},
        {"name": "certificate valid", "passed": report.get("certificate_valid") is True},
        {"name": "hsts enabled", "passed": report.get("hsts_enabled") is True},
        {
            "name": "hsts max age",
            "passed": int(report.get("hsts_max_age") or 0) >= MIN_HSTS_MAX_AGE,
            "actual": report.get("hsts_max_age"),
            "expected": MIN_HSTS_MAX_AGE,
        },
        {"name": "required check records present", "passed": required_checks.issubset(check_map), "actual": sorted(check_map)},
        {
            "name": "required check records passed",
            "passed": all(check_map.get(name, {}).get("passed") is True for name in required_checks),
        },
    ]
    return {"ok": all(item["passed"] for item in checks), "checks": checks}


def check_url(url: str, *, timeout: float = 10.0) -> dict[str, Any]:
    parsed = urlparse(url)
    checks: list[dict[str, Any]] = [{"name": "https url", "passed": parsed.scheme == "https", "actual": url}]
    if parsed.scheme != "https" or not parsed.hostname:
        return {"ok": False, "https_url": url, "checks": checks}
    if not public_endpoint_hostname(parsed.hostname):
        checks.append({"name": "public endpoint", "passed": False, "actual": parsed.hostname})
        return {"ok": False, "https_url": url, "checks": checks}
    checks.append({"name": "public endpoint", "passed": True, "actual": parsed.hostname})
    port = parsed.port or 443
    hsts_age = 0
    try:
        cert = certificate_not_expired(parsed.hostname, port, timeout)
        fetched = fetch_headers(url, timeout)
        headers = {key.lower(): value for key, value in fetched["headers"].items()}
        hsts_age = hsts_max_age(headers.get("strict-transport-security", ""))
        hsts = hsts_age >= MIN_HSTS_MAX_AGE
        checks.extend(
            [
                {"name": "certificate valid", "passed": cert["certificate_valid"], "detail": cert.get("not_after")},
                {"name": "http status", "passed": 200 <= fetched["status"] < 400, "actual": fetched["status"]},
                {"name": "hsts enabled", "passed": hsts, "actual_max_age": hsts_age, "expected_max_age": MIN_HSTS_MAX_AGE},
            ]
        )
    except Exception as exc:  # pragma: no cover - exact network errors vary by platform
        checks.append({"name": "deployment reachable", "passed": False, "detail": str(exc)})
    return {
        "ok": all(item["passed"] for item in checks),
        "https_url": url,
        "certificate_valid": any(item["name"] == "certificate valid" and item["passed"] for item in checks),
        "hsts_enabled": any(item["name"] == "hsts enabled" and item["passed"] for item in checks),
        "hsts_max_age": hsts_age,
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = check_url(args.url, timeout=args.timeout)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
