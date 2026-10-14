#!/usr/bin/env python3
"""Repeat load_smoke for a bounded soak window and write a machine-readable report."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from load_smoke import run as run_load
from load_smoke import percentiles


def summarize(cycles: list[dict]) -> dict:
    errors = [error for cycle in cycles for error in cycle.get("errors", [])]
    max_cycle_p95 = max((cycle.get("p95_ms", 0) for cycle in cycles), default=0)
    raw_complete = bool(cycles) and all(len(cycle.get("records", [])) == cycle.get("requests", 0) for cycle in cycles)
    records = [record for cycle in cycles for record in cycle.get("records", [])] if raw_complete else []
    result = {
        "cycles": len(cycles),
        "requests": sum(cycle.get("requests", 0) for cycle in cycles),
        "successful": sum(cycle.get("successful", 0) for cycle in cycles),
        "errors": errors,
        "p95_ms": max_cycle_p95,
        "max_ms": max((cycle.get("max_ms", 0) for cycle in cycles), default=0),
        "ok": bool(cycles) and not errors,
        "max_cycle_p95_ms": max_cycle_p95,
        "p95_aggregation": "max_cycle_p95_legacy_no_raw_records",
    }
    if raw_complete:
        result.update(percentiles([r["latency_ms"] for r in records]))
        result.update({"p95_aggregation": "pooled_requests", "latency_population": "all_attempts",
                       "record_count": len(records)})
    return result


def run_soak(
    *,
    api_base: str,
    username: str,
    password: str,
    requests: int,
    concurrency: int,
    duration_seconds: float,
    interval_seconds: float,
    runner: Callable[[str, str, str, int, int], dict] = run_load,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict:
    if duration_seconds <= 0 or interval_seconds < 0:
        raise ValueError("duration must be positive and interval nonnegative")
    started_at = datetime.now(timezone.utc).isoformat()
    started = clock()
    deadline = started + duration_seconds
    cycles = []
    while True:
        cycles.append(runner(api_base, username, password, requests, concurrency))
        if clock() >= deadline:
            break
        sleep(max(0.0, min(interval_seconds, deadline - clock())))
    return {
        "started_at": started_at,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": clock() - started,
        "target_duration_seconds": duration_seconds,
        "interval_seconds": interval_seconds,
        "requests_per_cycle": requests,
        "concurrency": concurrency,
        "cycles": cycles,
        "summary": summarize(cycles),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default="http://127.0.0.1:8001")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", required=True)
    parser.add_argument("--requests", type=int, default=90)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--duration-seconds", type=float, default=300)
    parser.add_argument("--interval-seconds", type=float, default=30)
    parser.add_argument("--max-p95-ms", type=int, default=2000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_soak(
        api_base=args.api_base,
        username=args.username,
        password=args.password,
        requests=args.requests,
        concurrency=args.concurrency,
        duration_seconds=args.duration_seconds,
        interval_seconds=args.interval_seconds,
    )
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    summary = report["summary"]
    return 0 if summary["ok"] and summary["p95_ms"] <= args.max_p95_ms else 1


if __name__ == "__main__":
    raise SystemExit(main())
