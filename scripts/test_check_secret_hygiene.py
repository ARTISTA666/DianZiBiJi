from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_secret_hygiene.py"
SPEC = importlib.util.spec_from_file_location("check_secret_hygiene", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_detects_env_secret_copied_into_docs(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("DEEPSEEK_API_KEY=real-secret-12345\n", encoding="utf-8")
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "oops.md").write_text("key real-secret-12345 leaked\n", encoding="utf-8")

    result = MODULE.check(tmp_path, tmp_path / ".env", ["docs"])

    assert result["ok"] is False
    assert result["leaks"] == [{"secret_key": "DEEPSEEK_API_KEY", "path": "docs/oops.md"}]


def test_ignores_known_development_defaults(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "SECRET_KEY=change-me-in-production\n"
        "BOOTSTRAP_ADMIN_PASSWORD=admin123\n"
        "POSTGRES_PASSWORD=eln_password\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("admin123 eln_password change-me-in-production\n", encoding="utf-8")

    result = MODULE.check(tmp_path, tmp_path / ".env", ["README.md"])

    assert result["ok"] is True
    assert result["checked_secret_keys"] == []
