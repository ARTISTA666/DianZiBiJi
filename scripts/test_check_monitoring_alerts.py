from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_monitoring_alerts.py"
SPEC = importlib.util.spec_from_file_location("check_monitoring_alerts", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_evaluate_passes_healthy_metrics() -> None:
    result = MODULE.evaluate(
        {"status": "ok", "total_requests": 100, "status_counts": {"2xx": 100}, "p95_duration_ms": 20, "in_flight": 1},
        200,
        max_p95_ms=2000,
        max_error_rate=0.01,
        max_in_flight=50,
    )

    assert result["ok"] is True
    assert result["derived"]["error_rate"] == 0


def test_evaluate_fails_high_error_rate() -> None:
    result = MODULE.evaluate(
        {"status": "ok", "total_requests": 100, "status_counts": {"2xx": 80, "5xx": 20}, "p95_duration_ms": 20, "in_flight": 1},
        200,
        max_p95_ms=2000,
        max_error_rate=0.01,
        max_in_flight=50,
    )

    assert result["ok"] is False
    assert "error rate" in {item["name"] for item in result["checks"] if not item["passed"]}
