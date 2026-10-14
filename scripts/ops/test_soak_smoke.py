from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "soak_smoke.py"
SPEC = importlib.util.spec_from_file_location("soak_smoke", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_summarize_rolls_up_cycles_and_errors() -> None:
    report = MODULE.summarize(
        [
            {"requests": 2, "successful": 2, "errors": [], "p95_ms": 10, "max_ms": 12},
            {"requests": 2, "successful": 1, "errors": ["boom"], "p95_ms": 30, "max_ms": 35},
        ]
    )

    assert report == {
        "cycles": 2,
        "requests": 4,
        "successful": 3,
        "errors": ["boom"],
        "p95_ms": 30,
        "max_ms": 35,
        "ok": False,
        "max_cycle_p95_ms": 30,
        "p95_aggregation": "max_cycle_p95_legacy_no_raw_records",
    }


def test_run_soak_runs_at_least_until_duration() -> None:
    now = {"value": 0.0}

    def clock() -> float:
        return now["value"]

    def sleep(seconds: float) -> None:
        now["value"] += seconds

    def runner(*_args):
        now["value"] += 1.0
        return {"requests": 1, "successful": 1, "errors": [], "p95_ms": 5, "max_ms": 5}

    report = MODULE.run_soak(
        api_base="http://example.test",
        username="admin",
        password="secret",
        requests=1,
        concurrency=1,
        duration_seconds=3,
        interval_seconds=1,
        runner=runner,
        sleep=sleep,
        clock=clock,
    )

    assert report["summary"]["cycles"] == 2
    assert report["summary"]["ok"] is True


def test_pooled_percentile_is_not_maximum_of_unequal_cycle_percentiles() -> None:
    fast = [{"latency_ms": 1, "error": None} for _ in range(100)]
    slow = [{"latency_ms": 1000, "error": None}]
    report = MODULE.summarize([
        {"requests": 100, "successful": 100, "errors": [], "p95_ms": 1, "max_ms": 1, "records": fast},
        {"requests": 1, "successful": 1, "errors": [], "p95_ms": 1000, "max_ms": 1000, "records": slow},
    ])
    assert report["p95_ms"] == 1
    assert report["max_cycle_p95_ms"] == 1000
    assert report["p95_aggregation"] == "pooled_requests"


def test_duration_is_measured_and_start_timestamp_precedes_runner() -> None:
    now = {"value": 0.0}
    timestamps = []

    def runner(*_args):
        from datetime import datetime, timezone
        timestamps.append(datetime.now(timezone.utc).isoformat())
        now["value"] += 5.0
        return {"requests": 1, "successful": 1, "errors": [], "p95_ms": 1, "max_ms": 1}

    report = MODULE.run_soak(api_base="http://local.test", username="admin", password="dummy",
        requests=1, concurrency=1, duration_seconds=2, interval_seconds=0, runner=runner,
        clock=lambda: now["value"])
    assert report["duration_seconds"] == 5.0
    assert report["target_duration_seconds"] == 2
    assert report["started_at"] <= timestamps[0] <= report["ended_at"]
