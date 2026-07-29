from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_reverse_proxy_config.py"
SPEC = importlib.util.spec_from_file_location("check_reverse_proxy_config", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_accepts_repository_template() -> None:
    result = MODULE.check_template(ROOT / "deploy" / "nginx.conf.template")

    assert result["ok"] is True


def test_rejects_missing_tls_directives(tmp_path: Path) -> None:
    template = tmp_path / "nginx.conf"
    template.write_text("server { listen 80; server_name localhost; }\n", encoding="utf-8")

    result = MODULE.check_template(template)

    failed = {item["name"] for item in result["checks"] if not item["passed"]}
    assert "https listener" in failed
    assert "no localhost public server_name" in failed
