from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_backup_policy.py"
SPEC = importlib.util.spec_from_file_location("check_backup_policy", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_accepts_repository_runbook() -> None:
    result = MODULE.check_runbook(ROOT / "docs" / "operations" / "backup-restore.md")

    assert result["ok"] is True


def test_rejects_incomplete_runbook(tmp_path: Path) -> None:
    runbook = tmp_path / "backup-restore.md"
    runbook.write_text("restore_drill.py only\n", encoding="utf-8")

    result = MODULE.check_runbook(runbook)

    failed = {item["name"] for item in result["checks"] if not item["passed"]}
    assert "encrypted backup copy" in failed
    assert "retention policy" in failed
