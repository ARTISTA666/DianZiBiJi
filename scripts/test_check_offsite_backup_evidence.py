from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_offsite_backup_evidence.py"
SPEC = importlib.util.spec_from_file_location("check_offsite_backup_evidence", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_accepts_remote_encrypted_backup_with_restore_hash(tmp_path: Path) -> None:
    restore = tmp_path / "restore.json"
    restore.write_text('{"ok": true, "generated_at": "2026-07-18T00:00:00+00:00", "checks": [{"name": "restore", "passed": true}]}\n', encoding="utf-8")
    report = {
        "ok": True,
        "encrypted": True,
        "offsite": True,
        "target_uri": "s3://eln-backups/latest",
        "retention_policy_configured": True,
        "latest_restore_drill_passed": True,
        "restore_drill_report": "restore.json",
        "restore_drill_sha256": hashlib.sha256(restore.read_bytes()).hexdigest(),
    }

    result = MODULE.validate_report(report, root=tmp_path)

    assert result["ok"] is True


def test_rejects_remote_target_without_object_path(tmp_path: Path) -> None:
    restore = tmp_path / "restore.json"
    restore.write_text('{"ok": true, "generated_at": "2026-07-18T00:00:00+00:00", "checks": [{"name": "restore", "passed": true}]}\n', encoding="utf-8")
    report = {
        "ok": True,
        "encrypted": True,
        "offsite": True,
        "target_uri": "s3://eln-backups",
        "retention_policy_configured": True,
        "latest_restore_drill_passed": True,
        "restore_drill_report": "restore.json",
        "restore_drill_sha256": hashlib.sha256(restore.read_bytes()).hexdigest(),
    }

    result = MODULE.validate_report(report, root=tmp_path)

    failed = {item["name"] for item in result["checks"] if not item["passed"]}
    assert "remote target uri" in failed


def test_rejects_restore_report_without_drill_shape(tmp_path: Path) -> None:
    restore = tmp_path / "restore.json"
    restore.write_text('{"ok": true}\n', encoding="utf-8")
    report = {
        "ok": True,
        "encrypted": True,
        "offsite": True,
        "target_uri": "s3://eln-backups/latest",
        "retention_policy_configured": True,
        "latest_restore_drill_passed": True,
        "restore_drill_report": "restore.json",
        "restore_drill_sha256": hashlib.sha256(restore.read_bytes()).hexdigest(),
    }

    result = MODULE.validate_report(report, root=tmp_path)

    failed = {item["name"] for item in result["checks"] if not item["passed"]}
    assert "restore drill report ok" in failed


def test_rejects_local_unhashed_backup(tmp_path: Path) -> None:
    report = {
        "ok": True,
        "encrypted": True,
        "offsite": True,
        "target_uri": "file:///tmp/backup",
        "retention_policy_configured": True,
        "latest_restore_drill_passed": True,
    }

    result = MODULE.validate_report(report, root=tmp_path)

    failed = {item["name"] for item in result["checks"] if not item["passed"]}
    assert "remote target uri" in failed
    assert "restore drill report hash" in failed


def test_rejects_restore_report_outside_evidence_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "restore-outside.json"
    outside.write_text('{"ok": true}\n', encoding="utf-8")
    report = {
        "ok": True,
        "encrypted": True,
        "offsite": True,
        "target_uri": "s3://eln-backups/latest",
        "retention_policy_configured": True,
        "latest_restore_drill_passed": True,
        "restore_drill_report": f"../{outside.name}",
        "restore_drill_sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
    }

    result = MODULE.validate_report(report, root=tmp_path)

    failed = {item["name"] for item in result["checks"] if not item["passed"]}
    assert "restore drill report inside evidence root" in failed
    assert "restore drill report hash" in failed


def test_validate_path_preserves_raw_fields_for_final_gate(tmp_path: Path) -> None:
    restore = tmp_path / "restore.json"
    restore.write_text('{"ok": true, "generated_at": "2026-07-18T00:00:00+00:00", "checks": [{"name": "restore", "passed": true}]}\n', encoding="utf-8")
    report = tmp_path / "raw-backup.json"
    report.write_text(
        (
            '{"ok": true, "encrypted": true, "offsite": true, '
            '"target_uri": "s3://eln-backups/latest", '
            '"retention_policy_configured": true, '
            '"latest_restore_drill_passed": true, '
            '"restore_drill_report": "restore.json", '
            f'"restore_drill_sha256": "{hashlib.sha256(restore.read_bytes()).hexdigest()}"'
            "}\n"
        ),
        encoding="utf-8",
    )

    result = MODULE.validate_path(report, root=tmp_path)

    assert result["ok"] is True
    assert result["encrypted"] is True
    assert result["target_uri"] == "s3://eln-backups/latest"
