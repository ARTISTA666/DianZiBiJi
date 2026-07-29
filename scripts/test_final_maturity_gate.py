from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from freeze_preregistration import build_manifest  # noqa: E402

SCRIPT = ROOT / "scripts" / "final_maturity_gate.py"
SPEC = importlib.util.spec_from_file_location("final_maturity_gate", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


COMMIT = "a" * 40


def write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def production_config(env_sha: str = "a" * 64) -> dict:
    return {
        "ok": True,
        "status": "passed",
        "env_file_sha256": env_sha,
        "checked_keys": [
            "APP_ENV",
            "SECRET_KEY",
            "BOOTSTRAP_ADMIN_PASSWORD",
            "POSTGRES_PASSWORD",
            "SEED_DEMO_DATA",
            "DEEPSEEK_API_KEY",
            "APP_REVISION",
        ],
        "checks": {
            "app_env_is_production": True,
            "secret_key_non_default": True,
            "bootstrap_admin_password_non_default": True,
            "postgres_password_non_default": True,
            "seed_demo_data_disabled": True,
            "deepseek_api_key_present": True,
            "app_revision_present": True,
        },
    }


def release_gate_report(passed: bool = True, generated_at: str | None = None) -> dict:
    groups = {
        group: [{"name": f"{group} check", "passed": passed, "actual": True, "operator": "==", "expected": True}]
        for group in sorted(MODULE.REQUIRED_RELEASE_GATE_GROUPS)
    }
    return {
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "source_revision": COMMIT,
        "scope": "full-system release-candidate maturity gate",
        "evidence_level": "internal automated gate; not independent human review",
        "groups": groups,
        "passed": passed,
        "failures": [] if passed else [{"group": "system", "name": "system check", "passed": False}],
    }


def args(tmp_path: Path) -> argparse.Namespace:
    corpus = tmp_path / "corpus.json"
    corpus.write_text('{"frozen": true}\n', encoding="utf-8")
    human_freeze = {
        "methods": ["pure_llm", "bm25_rag", "project_rag", "structured_query", "kg_enhanced_rag"],
        "model": "deepseek-v4-flash",
        "prompt_version": "confirmatory-review-v1",
        "random_seed": 20260716,
        "projects": [{"project_id": f"P{i}"} for i in range(3)],
        "questions": [
            {
                "question_id": f"Q{i}",
                "question_index": i,
                "question": f"Frozen question {i}?",
                "project_id": f"P{i % 3}",
                "gold_facts": ["fact"],
            }
            for i in range(60)
        ],
        "reviewers": [
            {
                "reviewer_id": "R1",
                "user_id": 2,
                "involved_in_development": False,
                "can_read": False,
                "can_evaluate": True,
                "can_write": False,
                "can_review": False,
                "can_manage": False,
            },
            {
                "reviewer_id": "R2",
                "user_id": 3,
                "involved_in_development": False,
                "can_read": False,
                "can_evaluate": True,
                "can_write": False,
                "can_review": False,
                "can_manage": False,
            },
        ],
        "files": [{"path": "corpus.json", "sha256": sha256(corpus)}],
    }
    restore = tmp_path / "restore.json"
    restore.write_text(
        '{"ok": true, "generated_at": "2026-07-18T00:00:00+00:00", "checks": [{"name": "restore", "passed": true}]}\n',
        encoding="utf-8",
    )
    production_config_report = production_config()
    gate_args = argparse.Namespace(
        release_gate=write_json(tmp_path / "release.json", release_gate_report()),
        system_evidence=write_json(
            tmp_path / "system.json",
            {"production_config": production_config_report},
        ),
        production_config=write_json(tmp_path / "production-config.json", production_config_report),
        human_freeze=write_json(tmp_path / "freeze.json", human_freeze),
        long_soak=write_json(
            tmp_path / "long-soak.json",
            {
                "ok": True,
                "duration_seconds": 4 * 60 * 60,
                "cycles": [{"requests": 1000, "successful": 1000, "errors": [], "p95_ms": 100}],
                "summary": {"cycles": 1, "requests": 1000, "successful": 1000, "errors": [], "p95_ms": 100},
            },
        ),
        tls_deployment=write_json(
            tmp_path / "tls.json",
            {
                "ok": True,
                "https_url": "https://eln.example.test",
                "certificate_valid": True,
                "hsts_enabled": True,
                "hsts_max_age": 31_536_000,
                "checks": [
                    {"name": "https url", "passed": True},
                    {"name": "public endpoint", "passed": True},
                    {"name": "certificate valid", "passed": True},
                    {"name": "http status", "passed": True},
                    {"name": "hsts enabled", "passed": True},
                ],
            },
        ),
        offsite_backup=write_json(
            tmp_path / "offsite.json",
            {
                "ok": True,
                "encrypted": True,
                "offsite": True,
                "target_uri": "s3://eln-backups/latest",
                "retention_policy_configured": True,
                "latest_restore_drill_passed": True,
                "restore_drill_report": "restore.json",
                "restore_drill_sha256": sha256(restore),
            },
        ),
        root=tmp_path,
    )
    manifest = build_manifest(
        [
            gate_args.release_gate,
            gate_args.system_evidence,
            gate_args.production_config,
            gate_args.human_freeze,
            gate_args.long_soak,
            gate_args.tls_deployment,
            gate_args.offsite_backup,
        ],
        tmp_path,
    )
    gate_args.evidence_manifest = write_json(tmp_path / "final-manifest.json", manifest)
    return gate_args


def test_final_gate_passes_with_all_confirmatory_evidence(tmp_path: Path) -> None:
    report = MODULE.build_report(args(tmp_path))

    assert report["passed"] is True
    assert isinstance(report["generated_at"], str)
    assert report["failures"] == []
    assert report["source_revision"] == COMMIT
    internal_check = next(
        item for item in report["checks"] if item["name"] == "internal release-candidate gate passed"
    )
    assert internal_check["detail"]["source_revision"] == COMMIT


def test_final_gate_rejects_minimal_release_gate_pass(tmp_path: Path) -> None:
    gate_args = args(tmp_path)
    gate_args.release_gate = write_json(tmp_path / "release.json", {"passed": True})
    gate_args.evidence_manifest = write_json(
        tmp_path / "final-manifest.json",
        build_manifest(
            [
                gate_args.release_gate,
                gate_args.system_evidence,
                gate_args.production_config,
                gate_args.human_freeze,
                gate_args.long_soak,
                gate_args.tls_deployment,
                gate_args.offsite_backup,
            ],
            tmp_path,
        ),
    )

    report = MODULE.build_report(gate_args)

    failure_names = {item["name"] for item in report["failures"]}
    assert "internal release-candidate gate passed" in failure_names
    assert report["source_revision"] is None


def test_final_gate_rejects_internal_pass_without_source_revision(tmp_path: Path) -> None:
    payload = release_gate_report()
    payload.pop("source_revision")
    release_gate = write_json(tmp_path / "release.json", payload)

    result = MODULE.release_gate_check(release_gate)

    assert result["passed"] is False
    assert result["detail"]["source_revision"] is None
    assert result["detail"]["source_revision_valid"] is False


def test_final_gate_rejects_malformed_source_revision(tmp_path: Path) -> None:
    payload = release_gate_report()
    payload["source_revision"] = "a" * 41
    release_gate = write_json(tmp_path / "release.json", payload)

    result = MODULE.release_gate_check(release_gate)

    assert result["passed"] is False
    assert result["detail"]["source_revision_valid"] is False


def test_final_gate_rejects_empty_required_release_gate_group(tmp_path: Path) -> None:
    payload = release_gate_report()
    payload["groups"]["evidence_manifest"] = []
    release_gate = write_json(tmp_path / "release.json", payload)

    result = MODULE.release_gate_check(release_gate)

    assert result["passed"] is False
    assert "evidence_manifest" in result["detail"]["empty_or_invalid_required_groups"]


def test_final_gate_rejects_internal_pass_older_than_168_hours(tmp_path: Path) -> None:
    now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    release_gate = write_json(
        tmp_path / "release.json",
        release_gate_report(generated_at=(now - timedelta(hours=169)).isoformat()),
    )

    result = MODULE.release_gate_check(release_gate, now=now)

    assert result["passed"] is False
    assert result["detail"]["age_hours"] == 169.0
    assert result["detail"]["max_age_hours"] == 168


def test_final_gate_accepts_internal_pass_at_168_hour_boundary(tmp_path: Path) -> None:
    now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    release_gate = write_json(
        tmp_path / "release.json",
        release_gate_report(generated_at=(now - timedelta(hours=168)).isoformat()),
    )

    result = MODULE.release_gate_check(release_gate, now=now)

    assert result["passed"] is True
    assert result["detail"]["age_hours"] == 168.0


def test_final_gate_rejects_internal_pass_just_over_168_hour_boundary(tmp_path: Path) -> None:
    now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    release_gate = write_json(
        tmp_path / "release.json",
        release_gate_report(
            generated_at=(now - timedelta(hours=168, microseconds=1)).isoformat()
        ),
    )

    result = MODULE.release_gate_check(release_gate, now=now)

    assert result["passed"] is False
    assert result["detail"]["age_hours"] > 168.0


def test_final_gate_rejects_internal_pass_with_invalid_timestamp(tmp_path: Path) -> None:
    release_gate = write_json(
        tmp_path / "release.json",
        release_gate_report(generated_at="not-an-iso8601-timestamp"),
    )

    result = MODULE.release_gate_check(release_gate)

    assert result["passed"] is False
    assert result["detail"]["timestamp_valid"] is False


def test_final_gate_accepts_checker_output_shape(tmp_path: Path) -> None:
    gate_args = args(tmp_path)
    long_soak_raw = json.loads(gate_args.long_soak.read_text(encoding="utf-8"))
    gate_args.long_soak = write_json(
        tmp_path / "validated-long-soak.json",
        {"source": str(gate_args.long_soak), **long_soak_raw, **MODULE.validate_long_soak(long_soak_raw)},
    )
    offsite_raw = json.loads(gate_args.offsite_backup.read_text(encoding="utf-8"))
    gate_args.offsite_backup = write_json(
        tmp_path / "validated-offsite.json",
        {"source": str(gate_args.offsite_backup), **offsite_raw, **MODULE.validate_offsite_backup(offsite_raw, root=tmp_path)},
    )
    gate_args.evidence_manifest = write_json(
        tmp_path / "final-manifest.json",
        build_manifest(
            [
                gate_args.release_gate,
                gate_args.system_evidence,
                gate_args.production_config,
                gate_args.human_freeze,
                gate_args.long_soak,
                gate_args.tls_deployment,
                gate_args.offsite_backup,
            ],
            tmp_path,
        ),
    )

    report = MODULE.build_report(gate_args)

    assert report["passed"] is True


def test_final_gate_requires_evidence_manifest(tmp_path: Path) -> None:
    gate_args = args(tmp_path)
    gate_args.evidence_manifest = tmp_path / "missing-manifest.json"

    report = MODULE.build_report(gate_args)

    assert "final maturity evidence manifest verified" in {item["name"] for item in report["failures"]}


def test_final_gate_requires_manifest_to_cover_final_evidence_paths(tmp_path: Path) -> None:
    gate_args = args(tmp_path)
    unrelated = tmp_path / "unrelated.json"
    unrelated.write_text("{}", encoding="utf-8")
    gate_args.evidence_manifest = write_json(tmp_path / "unrelated-manifest.json", build_manifest([unrelated], tmp_path))

    report = MODULE.build_report(gate_args)

    manifest_check = next(item for item in report["failures"] if item["name"] == "final maturity evidence manifest verified")
    assert "release.json" in manifest_check["detail"]["missing_required_paths"]
    assert "long-soak.json" in manifest_check["detail"]["missing_required_paths"]


def test_final_gate_rejects_changed_frozen_evidence(tmp_path: Path) -> None:
    gate_args = args(tmp_path)
    gate_args.long_soak.write_text(
        json.dumps(
            {
                "ok": True,
                "duration_seconds": 4 * 60 * 60,
                "cycles": [{"requests": 1000, "successful": 1000, "errors": [], "p95_ms": 101}],
                "summary": {"cycles": 1, "requests": 1000, "successful": 1000, "errors": [], "p95_ms": 101},
            }
        ),
        encoding="utf-8",
    )

    report = MODULE.build_report(gate_args)

    assert "final maturity evidence manifest verified" in {item["name"] for item in report["failures"]}


def test_final_gate_fails_current_missing_external_evidence(tmp_path: Path) -> None:
    gate_args = args(tmp_path)
    gate_args.human_freeze = tmp_path / "missing-freeze.json"
    gate_args.long_soak = write_json(
        tmp_path / "short-soak.json",
        {
            "ok": True,
            "duration_seconds": 60,
            "cycles": [{"requests": 90, "successful": 90, "errors": [], "p95_ms": 10}],
            "summary": {"cycles": 1, "requests": 90, "successful": 90, "errors": [], "p95_ms": 10},
        },
    )
    gate_args.tls_deployment = tmp_path / "missing-tls.json"

    report = MODULE.build_report(gate_args)

    failure_names = {item["name"] for item in report["failures"]}
    assert "external confirmatory human-review freeze passed" in failure_names
    assert "long soak evidence passed" in failure_names
    assert "real TLS deployment evidence passed" in failure_names


def test_final_gate_rejects_tls_report_without_checker_records(tmp_path: Path) -> None:
    gate_args = args(tmp_path)
    gate_args.tls_deployment = write_json(
        tmp_path / "tls.json",
        {"ok": True, "https_url": "https://eln.example.test", "certificate_valid": True, "hsts_enabled": True},
    )

    report = MODULE.build_report(gate_args)

    assert "real TLS deployment evidence passed" in {item["name"] for item in report["failures"]}


def test_final_gate_requires_production_config_not_skipped(tmp_path: Path) -> None:
    gate_args = args(tmp_path)
    gate_args.system_evidence = write_json(
        tmp_path / "system.json",
        {"production_config": {"ok": True, "status": "skipped_non_production"}},
    )

    report = MODULE.build_report(gate_args)

    assert "production configuration was checked in production mode" in {item["name"] for item in report["failures"]}


def test_final_gate_requires_production_config_env_fingerprint(tmp_path: Path) -> None:
    gate_args = args(tmp_path)
    gate_args.system_evidence = write_json(
        tmp_path / "system.json",
        {"production_config": {"ok": True, "status": "passed", "checked_keys": ["APP_ENV"]}},
    )

    report = MODULE.build_report(gate_args)

    assert "production configuration was checked in production mode" in {item["name"] for item in report["failures"]}


def test_final_gate_requires_structured_production_checks(tmp_path: Path) -> None:
    gate_args = args(tmp_path)
    stale_shape = production_config()
    stale_shape.pop("checks")
    gate_args.system_evidence = write_json(tmp_path / "system.json", {"production_config": stale_shape})
    gate_args.production_config = write_json(tmp_path / "production-config.json", stale_shape)

    report = MODULE.build_report(gate_args)

    assert "production configuration was checked in production mode" in {item["name"] for item in report["failures"]}


def test_final_gate_rejects_failed_structured_production_check(tmp_path: Path) -> None:
    gate_args = args(tmp_path)
    unsafe = production_config()
    unsafe["checks"]["seed_demo_data_disabled"] = False
    gate_args.system_evidence = write_json(tmp_path / "system.json", {"production_config": unsafe})
    gate_args.production_config = write_json(tmp_path / "production-config.json", unsafe)

    report = MODULE.build_report(gate_args)

    assert "production configuration was checked in production mode" in {item["name"] for item in report["failures"]}


def test_final_gate_requires_standalone_production_config_report(tmp_path: Path) -> None:
    gate_args = args(tmp_path)
    gate_args.production_config = tmp_path / "missing-production-config.json"

    report = MODULE.build_report(gate_args)

    assert "production configuration was checked in production mode" in {item["name"] for item in report["failures"]}


def test_final_gate_rejects_malformed_production_config_without_crashing(tmp_path: Path) -> None:
    gate_args = args(tmp_path)
    gate_args.system_evidence = write_json(tmp_path / "system.json", {"production_config": "not-a-report"})

    report = MODULE.build_report(gate_args)

    assert "production configuration was checked in production mode" in {item["name"] for item in report["failures"]}


def test_final_gate_rejects_stale_embedded_production_config_snapshot(tmp_path: Path) -> None:
    gate_args = args(tmp_path)
    gate_args.production_config = write_json(tmp_path / "production-config.json", production_config("b" * 64))
    gate_args.evidence_manifest = write_json(
        tmp_path / "final-manifest.json",
        build_manifest(
            [
                gate_args.release_gate,
                gate_args.system_evidence,
                gate_args.production_config,
                gate_args.human_freeze,
                gate_args.long_soak,
                gate_args.tls_deployment,
                gate_args.offsite_backup,
            ],
            tmp_path,
        ),
    )

    report = MODULE.build_report(gate_args)

    production_failure = next(
        item for item in report["failures"] if item["name"] == "production configuration was checked in production mode"
    )
    assert production_failure["detail"]["same_env_file_sha256"] is False


def test_final_gate_reports_corrupt_long_soak_without_crashing(tmp_path: Path) -> None:
    gate_args = args(tmp_path)
    gate_args.long_soak.write_text("{not json", encoding="utf-8")

    report = MODULE.build_report(gate_args)

    assert "long soak evidence passed" in {item["name"] for item in report["failures"]}


def test_final_gate_reports_non_object_tls_without_crashing(tmp_path: Path) -> None:
    gate_args = args(tmp_path)
    gate_args.tls_deployment.write_text("[]", encoding="utf-8")

    report = MODULE.build_report(gate_args)

    assert "real TLS deployment evidence passed" in {item["name"] for item in report["failures"]}


def test_final_gate_reports_corrupt_manifest_without_crashing(tmp_path: Path) -> None:
    gate_args = args(tmp_path)
    gate_args.evidence_manifest.write_text("{not json", encoding="utf-8")

    report = MODULE.build_report(gate_args)

    manifest_failure = next(item for item in report["failures"] if item["name"] == "final maturity evidence manifest verified")
    assert manifest_failure["detail"]["file_count"] == 0


def test_final_gate_reports_malformed_production_config_shape_without_crashing(tmp_path: Path) -> None:
    gate_args = args(tmp_path)
    malformed = production_config()
    malformed["checked_keys"] = 1
    gate_args.system_evidence = write_json(tmp_path / "system.json", {"production_config": malformed})
    gate_args.production_config = write_json(tmp_path / "production-config.json", malformed)

    report = MODULE.build_report(gate_args)

    failure = next(item for item in report["failures"] if item["name"] == "production configuration was checked in production mode")
    assert "error" in failure["detail"]


def test_final_gate_reports_malformed_long_soak_shape_without_crashing(tmp_path: Path) -> None:
    gate_args = args(tmp_path)
    gate_args.long_soak.write_text(
        json.dumps({"ok": True, "duration_seconds": "not-a-number", "summary": {"requests": 1000, "errors": [], "p95_ms": 100}}),
        encoding="utf-8",
    )

    report = MODULE.build_report(gate_args)

    failure = next(item for item in report["failures"] if item["name"] == "long soak evidence passed")
    failed_checks = {item["name"] for item in failure["detail"]["checks"] if not item["passed"]}
    assert "duration seconds" in failed_checks
    assert "cycle records present" in failed_checks
