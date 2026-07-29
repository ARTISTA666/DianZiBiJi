from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_long_soak_report.py"
SPEC = importlib.util.spec_from_file_location("check_long_soak_report", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_accepts_long_enough_clean_soak() -> None:
    result = MODULE.validate_report(
        {
            "ok": True,
            "duration_seconds": MODULE.MIN_DURATION_SECONDS,
            "cycles": [
                {"requests": 500, "successful": 500, "errors": [], "p95_ms": 80},
                {"requests": 500, "successful": 500, "errors": [], "p95_ms": 100},
            ],
            "summary": {"cycles": 2, "requests": MODULE.MIN_REQUESTS, "successful": MODULE.MIN_REQUESTS, "errors": [], "p95_ms": 100},
        }
    )

    assert result["ok"] is True


def test_rejects_short_smoke_as_long_soak() -> None:
    result = MODULE.validate_report({"ok": True, "duration_seconds": 60, "summary": {"requests": 90, "errors": [], "p95_ms": 10}})

    failed = {item["name"] for item in result["checks"] if not item["passed"]}
    assert "duration seconds" in failed
    assert "request count" in failed


def test_rejects_summary_without_cycle_records() -> None:
    result = MODULE.validate_report(
        {
            "ok": True,
            "duration_seconds": MODULE.MIN_DURATION_SECONDS,
            "summary": {"cycles": 2, "requests": MODULE.MIN_REQUESTS, "successful": MODULE.MIN_REQUESTS, "errors": [], "p95_ms": 100},
        }
    )

    failed = {item["name"] for item in result["checks"] if not item["passed"]}
    assert "cycle records present" in failed
    assert "summary requests match cycles" in failed


def test_rejects_summary_that_disagrees_with_cycle_records() -> None:
    result = MODULE.validate_report(
        {
            "ok": True,
            "duration_seconds": MODULE.MIN_DURATION_SECONDS,
            "cycles": [{"requests": 500, "successful": 500, "errors": [], "p95_ms": 100}],
            "summary": {"cycles": 1, "requests": MODULE.MIN_REQUESTS, "successful": MODULE.MIN_REQUESTS, "errors": [], "p95_ms": 100},
        }
    )

    failed = {item["name"] for item in result["checks"] if not item["passed"]}
    assert "summary requests match cycles" in failed
    assert "summary successful match cycles" in failed


def test_rejects_missing_p95_latency() -> None:
    result = MODULE.validate_report(
        {
            "ok": True,
            "duration_seconds": MODULE.MIN_DURATION_SECONDS,
            "cycles": [{"requests": MODULE.MIN_REQUESTS, "successful": MODULE.MIN_REQUESTS, "errors": []}],
            "summary": {"cycles": 1, "requests": MODULE.MIN_REQUESTS, "successful": MODULE.MIN_REQUESTS, "errors": []},
        }
    )

    failed = {item["name"] for item in result["checks"] if not item["passed"]}
    assert "p95 latency present" in failed
    assert "all cycle p95 latency present" in failed


def test_rejects_missing_cycle_p95_latency() -> None:
    result = MODULE.validate_report(
        {
            "ok": True,
            "duration_seconds": MODULE.MIN_DURATION_SECONDS,
            "cycles": [{"requests": MODULE.MIN_REQUESTS, "successful": MODULE.MIN_REQUESTS, "errors": []}],
            "summary": {"cycles": 1, "requests": MODULE.MIN_REQUESTS, "successful": MODULE.MIN_REQUESTS, "errors": [], "p95_ms": 100},
        }
    )

    failed = {item["name"] for item in result["checks"] if not item["passed"]}
    assert "all cycle p95 latency present" in failed


def test_rejects_slow_cycle_hidden_by_summary_p95() -> None:
    result = MODULE.validate_report(
        {
            "ok": True,
            "duration_seconds": MODULE.MIN_DURATION_SECONDS,
            "cycles": [
                {"requests": 500, "successful": 500, "errors": [], "p95_ms": 100},
                {"requests": 500, "successful": 500, "errors": [], "p95_ms": MODULE.MAX_P95_MS + 1},
            ],
            "summary": {"cycles": 2, "requests": MODULE.MIN_REQUESTS, "successful": MODULE.MIN_REQUESTS, "errors": [], "p95_ms": 100},
        }
    )

    failed = {item["name"] for item in result["checks"] if not item["passed"]}
    assert "all cycle p95 latency ms" in failed


def test_validate_path_preserves_raw_fields_for_final_gate(tmp_path: Path) -> None:
    report = tmp_path / "raw-soak.json"
    report.write_text(
        (
            '{"ok": true, "duration_seconds": 14400, '
            '"cycles": [{"requests": 1000, "successful": 1000, "errors": [], "p95_ms": 100}], '
            '"summary": {"cycles": 1, "requests": 1000, "successful": 1000, "errors": [], "p95_ms": 100}}\n'
        ),
        encoding="utf-8",
    )

    result = MODULE.validate_path(report)

    assert result["ok"] is True
    assert result["duration_seconds"] == MODULE.MIN_DURATION_SECONDS
    assert result["summary"]["requests"] == MODULE.MIN_REQUESTS
