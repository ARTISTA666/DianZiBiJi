from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_real_llm.py"
SPEC = importlib.util.spec_from_file_location("validate_real_llm", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_evaluate_answer_records_hash_and_required_markers_without_answer() -> None:
    report = MODULE.evaluate_answer(
        {"name": "citation", "required": ("PBS", "[S1]")},
        "PBS [S1]",
        {"model": "test", "request_id": "request-1", "usage": {"total_tokens": 3}},
        12,
    )

    assert report["passed"] is True
    assert report["request_id_present"] is True
    assert report["answer_chars"] == 8
    assert "answer" not in report
    assert len(report["answer_sha256"]) == 64
