#!/usr/bin/env python3
"""Short concurrent read smoke test for a running full-system stack."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import math
from time import perf_counter

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


def run(api_base: str, username: str, password: str, requests: int, concurrency: int) -> dict:
    with httpx.Client(base_url=api_base, timeout=15, trust_env=False) as client:
        login = client.post("/auth/login", json={"username": username, "password": password})
        login.raise_for_status()
        token = login.json()["access_token"]

        def request_once(index: int) -> tuple[int | None, str | None]:
            path = ("/health", "/ready", "/projects")[index % 3]
            request_id = f"load-{index}"
            headers = {"X-Request-ID": request_id}
            if path == "/projects":
                headers["Authorization"] = f"Bearer {token}"
            started = perf_counter()
            try:
                response = client.get(path, headers=headers)
                elapsed = round((perf_counter() - started) * 1000)
                if response.status_code != 200:
                    return None, f"{path}: HTTP {response.status_code}"
                if response.headers.get("x-request-id") != request_id:
                    return None, f"{path}: request id mismatch"
                return elapsed, None
            except httpx.HTTPError as exc:
                return None, f"{path}: {type(exc).__name__}"

        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            results = list(pool.map(request_once, range(requests)))
    return summarize(
        [latency for latency, error in results if latency is not None and error is None],
        [error for _, error in results if error is not None],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default="http://127.0.0.1:8001")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", required=True)
    parser.add_argument("--requests", type=int, default=90)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--max-p95-ms", type=int, default=2000)
    parser.add_argument("--output")
    args = parser.parse_args()
    report = run(args.api_base, args.username, args.password, args.requests, args.concurrency)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        from pathlib import Path

        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if not report["errors"] and report["p95_ms"] <= args.max_p95_ms else 1


if __name__ == "__main__":
    raise SystemExit(main())
