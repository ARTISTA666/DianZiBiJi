#!/usr/bin/env python3
"""Validate that the secret-rotation runbook covers required production steps."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNBOOK = ROOT / "docs" / "operations" / "secret-rotation.md"
REQUIRED_TERMS = {
    "SECRET_KEY": "JWT signing key rotation",
    "BOOTSTRAP_ADMIN_PASSWORD": "bootstrap/admin password handling",
    "POSTGRES_PASSWORD": "database password rotation",
    "DEEPSEEK_API_KEY": "external model API key rotation",
    "auth_version": "token invalidation mechanism",
    "backup-system.sh": "backup before rotation",
    "check_production_config.py": "post-rotation production preflight",
    "check_secret_hygiene.py": "post-rotation leak check",
    "check_monitoring_alerts.py": "post-rotation monitoring check",
    "回滚": "rollback steps",
    "撤销旧": "old credential revocation",
    "重新登录": "user re-login impact",
}


def check_runbook(path: Path = DEFAULT_RUNBOOK) -> dict:
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    checks = [{"name": "runbook exists", "passed": path.is_file(), "detail": str(path)}]
    checks.extend(
        {"name": label, "passed": term in text, "detail": term}
        for term, label in REQUIRED_TERMS.items()
    )
    return {
        "ok": all(item["passed"] for item in checks),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runbook": str(path),
        "checks": checks,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runbook", type=Path, default=DEFAULT_RUNBOOK)
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "system-evidence" / "secret-rotation-latest.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = check_runbook(args.runbook)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "output": str(args.output)}, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
