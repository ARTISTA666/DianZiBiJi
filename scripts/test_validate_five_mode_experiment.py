from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_five_mode_experiment.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("validate_five_mode_experiment", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_bootstrap_ci_is_deterministic_and_contains_constant_mean() -> None:
    assert MODULE.bootstrap_mean_ci([0.5, 0.5, 0.5]) == (0.5, 0.5)
    first = MODULE.bootstrap_mean_ci([0.0, 0.5, 1.0], samples=1000)
    second = MODULE.bootstrap_mean_ci([0.0, 0.5, 1.0], samples=1000)
    assert first == second
