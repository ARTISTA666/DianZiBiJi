from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/controlled_beta_gate.py"
SPEC = importlib.util.spec_from_file_location("controlled_beta_gate", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def write_report(path: Path, *, passed: bool = True, scope: str = "scope") -> None:
    path.write_text(
        json.dumps({"passed": passed, "failures": [] if passed else [{"name": "x"}], "scope": scope}),
        encoding="utf-8",
    )


def test_human_review_is_not_a_controlled_beta_check(tmp_path: Path) -> None:
    release = tmp_path / "release.json"
    tls = tmp_path / "tls.json"
    backup = tmp_path / "backup.json"
    config = tmp_path / "config.json"
    write_report(release, scope="full-system release-candidate maturity gate")
    write_report(tls, scope="real TLS deployment evidence")
    write_report(backup, scope="offsite encrypted backup evidence")
    config.write_text(
        json.dumps(
            {
                "ok": True,
                "status": "passed",
                "checks": {
                    name: True
                    for name in (
                        "app_env_is_production",
                        "secret_key_non_default",
                        "bootstrap_admin_password_non_default",
                        "postgres_password_non_default",
                        "seed_demo_data_disabled",
                        "deepseek_api_key_present",
                        "build_revision_present",
                    )
                },
            }
        ),
        encoding="utf-8",
    )
    args = SimpleNamespace(
        release_gate=release,
        production_config=config,
        tls=tls,
        backup=backup,
        root=tmp_path,
        base_url="http://127.0.0.1:1",
    )
    report = MODULE.build_report(args, runtime_checks=False)
    assert report["passed"] is True
    assert report["human_review"] == "post_launch_pending"
    assert report["launch_policy"]["human_review_required"] is False


def test_production_configuration_rejects_development_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"ok": True, "status": "skipped_non_production", "checks": {}}), encoding="utf-8")
    result = MODULE.production_config_passes(path)
    assert result["passed"] is False
    assert result["detail"]["status"] == "skipped_non_production"


def test_report_failure_is_preserved(tmp_path: Path) -> None:
    path = tmp_path / "release.json"
    write_report(path, passed=False, scope="full-system release-candidate maturity gate")
    result = MODULE.report_passes(path, "full-system release-candidate maturity gate")
    assert result["passed"] is False
    assert result["detail"]["failures"]
