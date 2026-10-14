#!/usr/bin/env python3
"""Bounded request smoke with raw, reproducible per-attempt timings."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import math
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import httpx


def summarize(latencies_ms: list[int], errors: list[str]) -> dict:
    ordered = sorted(latencies_ms)
    p95 = ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)] if ordered else 0
    return {
        "requests": len(latencies_ms) + len(errors),
        "successful": len(latencies_ms),
        "errors": errors,
        "p95_ms": p95,
        "max_ms": max(ordered, default=0),
    }


def percentiles(latencies_ms: list[float]) -> dict:
    ordered = sorted(latencies_ms)
    return {
        f"p{rank}_ms": ordered[max(0, math.ceil(len(ordered) * rank / 100) - 1)] if ordered else 0
        for rank in (50, 95, 99)
    }


def validate_plan(plan: list[dict] | None) -> list[dict]:
    if plan is None:
        plan = [{"path": path} for path in ("/health", "/ready", "/projects")]
    if not isinstance(plan, list) or not plan:
        raise ValueError("request plan must be a nonempty list")
    normalized = []
    for entry in plan:
        path = entry.get("path", "")
        if not isinstance(path, str) or not path.startswith("/") or path.startswith("//"):
            raise ValueError("request paths must be relative to the selected API base")
        method = entry.get("method", "GET").upper()
        if method not in {"GET", "POST", "PATCH", "PUT"}:
            raise ValueError("unsupported request plan method")
        expected = entry.get("expected_status", 200)
        if not isinstance(expected, int) or isinstance(expected, bool) or not 200 <= expected < 300:
            raise ValueError("expected_status must be a successful HTTP status")
        normalized.append({**entry, "path": path, "method": method, "expected_status": expected})
    return normalized


def run(api_base: str, username: str, password: str, requests: int, concurrency: int,
        *, request_plan: list[dict] | None = None, identity: dict | None = None) -> dict:
    if requests < 1 or concurrency < 1:
        raise ValueError("requests and concurrency must be positive")
    plan = validate_plan(request_plan)
    run_id = uuid4().hex
    started_at = datetime.now(timezone.utc).isoformat()
    started = perf_counter()
    with httpx.Client(base_url=api_base, timeout=15, trust_env=False) as client:
        login = client.post("/auth/login", json={"username": username, "password": password})
        login.raise_for_status()
        token = login.json()["access_token"]

        def request_once(index: int) -> dict:
            entry = plan[index % len(plan)]
            path = entry["path"]
            request_id = f"load-{run_id}-{index}"
            headers = {"X-Request-ID": request_id}
            if path not in {"/health", "/ready"}:
                headers["Authorization"] = f"Bearer {token}"
            record = {"run_id": run_id, "index": index, "method": entry["method"], "path": path,
                      "request_id": request_id, "expected_status": entry["expected_status"],
                      "status_code": None, "response_request_id": None, "error": None,
                      "request_payload_sha256": hashlib.sha256(json.dumps(entry.get("json"), sort_keys=True,
                          ensure_ascii=False, separators=(",", ":")).encode()).hexdigest(),
                      "monotonic_start": perf_counter()}
            try:
                response = client.request(entry["method"], path, headers=headers, json=entry.get("json"))
                record["status_code"] = response.status_code
                record["response_request_id"] = response.headers.get("x-request-id")
                if response.status_code != entry["expected_status"]:
                    record["error"] = f"{path}: HTTP {response.status_code}"
                elif record["response_request_id"] != request_id:
                    record["error"] = f"{path}: request id mismatch"
            except httpx.HTTPError as exc:
                record["error"] = f"{path}: {type(exc).__name__}"
            finally:
                record["monotonic_end"] = perf_counter()
                record["latency_ms"] = (record["monotonic_end"] - record["monotonic_start"]) * 1000
            return record

        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            records = list(pool.map(request_once, range(requests)))
    elapsed = perf_counter() - started
    latencies = [r["latency_ms"] for r in records]
    successful = [r for r in records if r["error"] is None]
    endpoint_metrics = {}
    for key in sorted({f'{r["method"]} {r["path"]}' for r in records}):
        group = [r for r in records if f'{r["method"]} {r["path"]}' == key]
        endpoint_metrics[key] = {"requests": len(group), "successful": sum(r["error"] is None for r in group),
                                 **percentiles([r["latency_ms"] for r in group])}
    return {"run_id": run_id, "started_at": started_at, "ended_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": elapsed, "requests": len(records), "successful": len(successful),
            "errors": [r["error"] for r in records if r["error"] is not None], **percentiles(latencies),
            "max_ms": max(latencies, default=0), "latency_population": "all_attempts",
            "throughput_requests_per_second": len(records) / elapsed if elapsed else 0,
            "throughput_window": "login_and_all_requests", "concurrency": concurrency,
            "request_plan": plan, "identity": identity or {"status": "not_supplied"},
            "endpoint_metrics": endpoint_metrics, "records": records}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default="http://127.0.0.1:8001")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", required=True)
    parser.add_argument("--requests", type=int, default=90)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--max-p95-ms", type=int, default=2000)
    parser.add_argument("--output")
    parser.add_argument("--raw-output", type=Path)
    parser.add_argument("--request-plan", type=Path, help="JSON array of relative API requests; repeat in this order")
    parser.add_argument("--identity", type=Path, help="JSON runtime/data identity for this new batch")
    args = parser.parse_args()
    if args.raw_output and args.raw_output.exists():
        raise FileExistsError(args.raw_output)
    report = run(args.api_base, args.username, args.password, args.requests, args.concurrency,
                 request_plan=json.loads(args.request_plan.read_text()) if args.request_plan else None,
                 identity=json.loads(args.identity.read_text()) if args.identity else None)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    if args.raw_output:
        args.raw_output.parent.mkdir(parents=True, exist_ok=True)
        with args.raw_output.open("x", encoding="utf-8") as stream:
            for record in report["records"]:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(payload)
    return 0 if not report["errors"] and report["p95_ms"] <= args.max_p95_ms else 1


if __name__ == "__main__":
    raise SystemExit(main())
