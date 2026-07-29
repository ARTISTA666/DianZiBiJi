#!/usr/bin/env python3
"""Validate long-soak evidence before confirmatory human review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


MIN_DURATION_SECONDS = 4 * 60 * 60
MIN_REQUESTS = 1000
MAX_P95_MS = 2000


def metric(value: Any) -> int | float:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def validate_report(report: dict[str, Any]) -> dict[str, Any]:
    summary = report.get("summary") or {}
    cycles = report.get("cycles") if isinstance(report.get("cycles"), list) else []
    duration = metric(report.get("duration_seconds") or summary.get("duration_seconds"))
    requests = metric(summary.get("requests", report.get("requests")))
    successful = metric(summary.get("successful", report.get("successful")))
    errors = summary.get("errors", report.get("errors", [])) or []
    p95_present = "p95_ms" in summary or "p95_ms" in report
    p95_ms = metric(summary.get("p95_ms", report.get("p95_ms")))
    cycle_requests = sum(metric(cycle.get("requests")) for cycle in cycles if isinstance(cycle, dict))
    cycle_successful = sum(metric(cycle.get("successful")) for cycle in cycles if isinstance(cycle, dict))
    cycle_errors = [
        error
        for cycle in cycles
        if isinstance(cycle, dict)
        for error in (cycle.get("errors") if isinstance(cycle.get("errors"), list) else [])
    ]
    cycle_p95_values = [metric(cycle.get("p95_ms")) for cycle in cycles if isinstance(cycle, dict) and "p95_ms" in cycle]
    all_cycle_p95_present = len(cycle_p95_values) == len(cycles) and bool(cycles)
    max_cycle_p95 = max(cycle_p95_values or [0])
    checks = [
        {"name": "report ok", "passed": bool(report.get("ok", summary.get("ok")))},
        {"name": "duration seconds", "passed": duration >= MIN_DURATION_SECONDS, "actual": duration, "expected": MIN_DURATION_SECONDS},
        {"name": "request count", "passed": requests >= MIN_REQUESTS, "actual": requests, "expected": MIN_REQUESTS},
        {"name": "cycle records present", "passed": bool(cycles), "actual": len(cycles)},
        {"name": "summary cycle count matches records", "passed": summary.get("cycles") == len(cycles), "actual": summary.get("cycles"), "expected": len(cycles)},
        {"name": "summary requests match cycles", "passed": requests == cycle_requests, "actual": requests, "expected": cycle_requests},
        {"name": "summary successful match cycles", "passed": successful == cycle_successful, "actual": successful, "expected": cycle_successful},
        {"name": "no errors", "passed": not errors, "actual": len(errors)},
        {"name": "cycle errors match summary", "passed": errors == cycle_errors, "actual": len(errors), "expected": len(cycle_errors)},
        {"name": "all cycle requests succeeded", "passed": cycle_requests == cycle_successful and cycle_requests > 0, "actual": cycle_successful, "expected": cycle_requests},
        {"name": "p95 latency present", "passed": p95_present},
        {"name": "p95 latency ms", "passed": p95_present and p95_ms <= MAX_P95_MS, "actual": p95_ms, "expected": MAX_P95_MS},
        {"name": "all cycle p95 latency present", "passed": all_cycle_p95_present, "actual": len(cycle_p95_values), "expected": len(cycles)},
        {"name": "all cycle p95 latency ms", "passed": all_cycle_p95_present and max_cycle_p95 <= MAX_P95_MS, "actual": max_cycle_p95, "expected": MAX_P95_MS},
    ]
    return {"ok": all(item["passed"] for item in checks), "checks": checks}


def validate_path(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"ok": False, "checks": [{"name": "report exists", "passed": False, "detail": str(path)}]}
    report = json.loads(path.read_text(encoding="utf-8"))
    result = validate_report(report)
    return {"source": str(path), **report, **result}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate_path(args.report)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
