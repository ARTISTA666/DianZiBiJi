#!/usr/bin/env python3
"""Gate for a controlled beta launch without confirmatory human review.

This is intentionally separate from ``final_maturity_gate.py``.  A beta may
collect real-user feedback before the confirmatory review program is available,
but it must still satisfy the technical safety and reproducibility checks.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RELEASE_GATE = ROOT / "docs/experiments/main-maturity-gate-latest.json"
DEFAULT_PRODUCTION_CONFIG = ROOT / "docs/system-evidence/production-config-latest.json"
DEFAULT_TLS = ROOT / "docs/system-evidence/tls-deployment-latest.json"
DEFAULT_BACKUP = ROOT / "docs/system-evidence/offsite-backup-latest.json"
DEFAULT_OUTPUT = ROOT / "docs/experiments/controlled-beta-gate-latest.json"
DEFAULT_MARKDOWN = ROOT / "docs/experiments/controlled-beta-gate-latest.md"


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def check(name: str, passed: bool, detail: Any) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def report_passes(path: Path, expected_scope: str | None = None) -> dict[str, Any]:
    report = load_json(path)
    passed = bool(
        report
        and report.get("passed") is True
        and report.get("failures") == []
        and (expected_scope is None or report.get("scope") == expected_scope)
    )
    return check(
        f"evidence report passed: {path.name}",
        passed,
        {
            "source": str(path),
            "exists": path.is_file(),
            "passed": report.get("passed") if report else None,
            "failures": report.get("failures") if report else None,
            "scope": report.get("scope") if report else None,
        },
    )


def production_config_passes(path: Path) -> dict[str, Any]:
    report = load_json(path)
    required = {
        "app_env_is_production",
        "secret_key_non_default",
        "bootstrap_admin_password_non_default",
        "postgres_password_non_default",
        "seed_demo_data_disabled",
        "deepseek_api_key_present",
        "app_revision_present",
    }
    checks = report.get("checks") if report else {}
    checks = checks if isinstance(checks, dict) else {}
    passed = bool(
        report
        and report.get("ok") is True
        and report.get("status") == "passed"
        and required.issubset(checks)
        and all(checks.get(name) is True for name in required)
    )
    return check(
        "production configuration passed",
        passed,
        {
            "source": str(path),
            "status": report.get("status") if report else None,
            "checks": checks,
            "missing_checks": sorted(required - set(checks)),
        },
    )


def http_check(url: str, required_header: tuple[str, str] | None = None) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            body = response.read(4096).decode("utf-8", errors="replace")
            headers = {key.lower(): value for key, value in response.headers.items()}
            header_ok = required_header is None or headers.get(required_header[0].lower()) == required_header[1]
            passed = response.status == 200 and header_ok
            detail = {"url": url, "status": response.status, "header_ok": header_ok, "body": body}
    except (OSError, urllib.error.URLError, ValueError) as exc:
        passed = False
        detail = {"url": url, "error": str(exc)}
    return check(f"runtime endpoint healthy: {url}", passed, detail)


def compose_check(root: Path) -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["docker", "compose", "config", "--quiet"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        detail = {"returncode": result.returncode, "stderr": result.stderr[-1000:]}
        return check("Docker Compose configuration valid", result.returncode == 0, detail)
    except (OSError, subprocess.SubprocessError) as exc:
        return check("Docker Compose configuration valid", False, {"error": str(exc)})


def build_report(args: argparse.Namespace, runtime_checks: bool = True) -> dict[str, Any]:
    checks: list[dict[str, Any]] = [
        report_passes(args.release_gate, "full-system release-candidate maturity gate"),
        production_config_passes(args.production_config),
        report_passes(args.tls, "real TLS deployment evidence"),
        report_passes(args.backup, "offsite encrypted backup evidence"),
    ]
    if runtime_checks:
        checks.extend(
            [
                http_check(f"{args.base_url.rstrip('/')}/health", ("x-backend-runtime", "axum")),
                http_check(f"{args.base_url.rstrip('/')}/ready"),
                compose_check(args.root),
            ]
        )
    failures = [item for item in checks if not item["passed"]]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": not failures,
        "scope": "controlled beta launch readiness; human review is post-launch",
        "human_review": "post_launch_pending",
        "checks": checks,
        "failures": failures,
        "launch_policy": {
            "human_review_required": False,
            "technical_safety_checks_required": True,
            "user_feedback_collection": "required after launch",
        },
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Controlled beta launch gate",
        "",
        f"Result: {'PASS' if report['passed'] else 'FAIL'}",
        "",
        "人工评审不是受控试运行的前置条件；生产安全与自动化门禁仍是前置条件。",
        "",
        "| Check | Status | Detail |",
        "| --- | --- | --- |",
    ]
    for item in report["checks"]:
        detail = json.dumps(item["detail"], ensure_ascii=False, sort_keys=True)
        lines.append(f"| {item['name']} | {'PASS' if item['passed'] else 'FAIL'} | `{detail}` |")
    if report["failures"]:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- {item['name']}" for item in report["failures"])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-gate", type=Path, default=DEFAULT_RELEASE_GATE)
    parser.add_argument("--production-config", type=Path, default=DEFAULT_PRODUCTION_CONFIG)
    parser.add_argument("--tls", type=Path, default=DEFAULT_TLS)
    parser.add_argument("--backup", type=Path, default=DEFAULT_BACKUP)
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.markdown.write_text(markdown(report), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "failures": len(report["failures"]), "output": str(args.output)}, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
