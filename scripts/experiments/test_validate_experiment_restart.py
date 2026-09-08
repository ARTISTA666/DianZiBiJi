from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_experiment_restart.py"
SPEC = importlib.util.spec_from_file_location("validate_experiment_restart", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_latest_e2e_project_ignores_stale_projects() -> None:
    assert MODULE.latest_e2e_project(
        [
            {"id": 1, "name": "系统级自动化测试项目 old"},
            {"id": 9, "name": "其他项目"},
            {"id": 3, "name": "系统级自动化测试项目 new"},
        ]
    ) == {"id": 3, "name": "系统级自动化测试项目 new"}


def test_latest_e2e_project_accepts_paginated_project_response() -> None:
    assert MODULE.latest_e2e_project(
        {
            "items": [
                {"id": 2, "name": "系统级自动化测试项目 paginated"},
                {"id": 8, "name": "其他项目"},
            ],
            "total": 2,
            "skip": 0,
            "limit": 100,
        }
    ) == {"id": 2, "name": "系统级自动化测试项目 paginated"}


def test_latest_e2e_project_requires_match() -> None:
    try:
        MODULE.latest_e2e_project([{"id": 1, "name": "其他项目"}])
    except RuntimeError as exc:
        assert "No E2E project" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_write_report_persists_machine_readable_result(tmp_path: Path) -> None:
    output = tmp_path / "restart-recovery.json"

    payload = MODULE.write_report(
        {"run_id": 7, "interrupted": True, "resumed_status": "completed"},
        output,
    )

    assert '"run_id": 7' in payload
    assert output.read_text(encoding="utf-8").endswith("\n")
