#!/usr/bin/env python3
"""Check readiness and runtime metrics against deployable alert thresholds."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin


ROOT = Path(__file__).resolve().parents[1]


def get_json(url: str, timeout: int = 10) -> tuple[int | None, dict, str | None]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8")), None
    except urllib.error.HTTPError as exc:
        return exc.code, {}, str(exc)
    except Exception as exc:
        return None, {}, str(exc)


def check(name: str, actual, op: str, expected) -> dict:
    if op == "==":
        passed = actual == expected
    elif op == "<=":
        passed = actual <= expected
    elif op == ">=":
        passed = actual >= expected
    else:
        raise ValueError(f"Unsupported operator: {op}")
    return {"name": name, "actual": actual, "operator": op, "expected": expected, "passed": passed}


def metrics_url_from_base(api_base: str) -> str:
    return urljoin(api_base.rstrip("/") + "/", "metrics")


def ready_url_from_base(api_base: str) -> str:
    return urljoin(api_base.rstrip("/") + "/", "ready")


def evaluate(
    metrics: dict,
    ready_status: int | None,
    *,
    max_p95_ms: int,
    max_error_rate: float,
    max_in_flight: int,
) -> dict:
    total = int(metrics.get("total_requests") or 0)
    status_counts = metrics.get("status_counts") or {}
    errors = sum(int(status_counts.get(key, 0)) for key in ("4xx", "5xx"))
    error_rate = errors / total if total else 0.0
    checks = [
        check("readiness endpoint", ready_status, "==", 200),
        check("metrics status", metrics.get("status"), "==", "ok"),
        check("metrics has traffic", total, ">=", 1),
        check("p95 latency ms", metrics.get("p95_duration_ms", 0), "<=", max_p95_ms),
        check("error rate", round(error_rate, 6), "<=", max_error_rate),
        check("in-flight requests", metrics.get("in_flight", 0), "<=", max_in_flight),
    ]
    return {
        "ok": all(item["passed"] for item in checks),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "thresholds": {
            "max_p95_ms": max_p95_ms,
            "max_error_rate": max_error_rate,
            "max_in_flight": max_in_flight,
        },
        "metrics": metrics,
        "derived": {"total_requests": total, "error_requests": errors, "error_rate": error_rate},
        "checks": checks,
    }


def run(
    api_base: str,
    *,
    max_p95_ms: int,
    max_error_rate: float,
    max_in_flight: int,
    output: Path | None = None,
) -> dict:
    ready_status, _, ready_error = get_json(ready_url_from_base(api_base))
    metrics_status, metrics, metrics_error = get_json(metrics_url_from_base(api_base))
    report = evaluate(metrics, ready_status, max_p95_ms=max_p95_ms, max_error_rate=max_error_rate, max_in_flight=max_in_flight)
    report["sources"] = {
        "ready": {"url": ready_url_from_base(api_base), "status": ready_status, "error": ready_error},
        "metrics": {"url": metrics_url_from_base(api_base), "status": metrics_status, "error": metrics_error},
    }
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default="http://127.0.0.1:8001")
    parser.add_argument("--max-p95-ms", type=int, default=2000)
    parser.add_argument("--max-error-rate", type=float, default=0.01)
    parser.add_argument("--max-in-flight", type=int, default=50)
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "system-evidence" / "monitoring-alerts-latest.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run(
        args.api_base,
        max_p95_ms=args.max_p95_ms,
        max_error_rate=args.max_error_rate,
        max_in_flight=args.max_in_flight,
        output=args.output,
    )
    print(json.dumps({"ok": report["ok"], "output": str(args.output)}, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
