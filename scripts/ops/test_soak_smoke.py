from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "soak_smoke.py"
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
