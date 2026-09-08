from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "load_smoke.py"
SPEC = importlib.util.spec_from_file_location("load_smoke", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_summary_uses_nearest_rank_p95_and_keeps_errors() -> None:
    report = MODULE.summarize(list(range(1, 101)), ["one error"])

    assert report == {
        "requests": 101,
        "successful": 100,
        "errors": ["one error"],
        "p95_ms": 95,
        "max_ms": 100,
    }


def test_main_can_write_output_file(tmp_path, monkeypatch) -> None:
    output = tmp_path / "load.json"

    monkeypatch.setattr(
        MODULE,
        "run",
        lambda *_args, **_kwargs: {"requests": 1, "successful": 1, "errors": [], "p95_ms": 1, "max_ms": 1},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["load_smoke.py", "--password", "x", "--output", str(output)],
    )

    assert MODULE.main() == 0
    assert '"p95_ms": 1' in output.read_text(encoding="utf-8")
