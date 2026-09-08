"""Pytest configuration for scripts test suites.

Ensures that repository root, backend/legacy, and all scripts subdirectories
are available on sys.path so modules can import sibling tools and legacy services.
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent

for path in [
    REPO_ROOT,
    REPO_ROOT / "backend" / "legacy",
    SCRIPTS_DIR,
    SCRIPTS_DIR / "gates",
    SCRIPTS_DIR / "freeze",
    SCRIPTS_DIR / "experiments",
    SCRIPTS_DIR / "data",
    SCRIPTS_DIR / "render",
    SCRIPTS_DIR / "ops",
    SCRIPTS_DIR / "audit",
]:
    p_str = str(path)
    if p_str not in sys.path:
        sys.path.insert(0, p_str)
