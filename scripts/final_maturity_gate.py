#!/usr/bin/env python3
"""Final gate for declaring the project ready for confirmatory human review."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from check_long_soak_report import validate_report as validate_long_soak
from check_offsite_backup_evidence import validate_report as validate_offsite_backup
from check_tls_deployment import validate_report as validate_tls_deployment
from freeze_preregistration import verify_manifest
from validate_human_review_freeze import validate as validate_human_freeze


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RELEASE_GATE = ROOT / "docs" / "experiments" / "main-maturity-gate-latest.json"
DEFAULT_SYSTEM_EVIDENCE = ROOT / "docs" / "system-evidence" / "validation-results.json"
DEFAULT_PRODUCTION_CONFIG = ROOT / "docs" / "system-evidence" / "production-config-latest.json"
DEFAULT_HUMAN_FREEZE = ROOT / "docs" / "experiments" / "confirmatory-human-review-freeze.json"
DEFAULT_LONG_SOAK = ROOT / "docs" / "system-evidence" / "long-soak-latest.json"
DEFAULT_TLS = ROOT / "docs" / "system-evidence" / "tls-deployment-latest.json"
DEFAULT_OFFSITE_BACKUP = ROOT / "docs" / "system-evidence" / "offsite-backup-latest.json"
DEFAULT_EVIDENCE_MANIFEST = ROOT / "docs" / "experiments" / "final-maturity-evidence-manifest.json"
DEFAULT_OUTPUT = ROOT / "docs" / "experiments" / "final-maturity-gate-latest.json"
DEFAULT_MARKDOWN = ROOT / "docs" / "experiments" / "final-maturity-gate-latest.md"
INTERNAL_RELEASE_GATE_MAX_AGE_HOURS = 168
SOURCE_REVISION = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")

REQUIRED_PRODUCTION_CHECKS = {
    "app_env_is_production",
    "secret_key_non_default",
    "bootstrap_admin_password_non_default",
    "postgres_password_non_default",
    "seed_demo_data_disabled",
    "deepseek_api_key_present",
    "app_revision_present",
}
REQUIRED_RELEASE_GATE_GROUPS = {"retrieval", "rag_experiment", "agent", "system", "evidence_manifest"}

def load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def check(name: str, passed: bool, detail: Any) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def safe_check(name: str, fn, *args) -> dict[str, Any]:
    try:
        return fn(*args)
    except Exception as exc:
        return check(name, False, {"error": str(exc)})


def _release_gate_age_hours(value: Any, now: datetime | None = None) -> tuple[bool, float | None]:
    if not isinstance(value, str) or not value.strip():
        return False, None
    try:
        generated_at = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return False, None
    if generated_at.tzinfo is None:
        return False, None
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    age_seconds = (reference.astimezone(timezone.utc) - generated_at.astimezone(timezone.utc)).total_seconds()
    if age_seconds < 0:
        return False, None
    return True, age_seconds / 3600


def release_gate_check(path: Path, now: datetime | None = None) -> dict[str, Any]:
    report = load_json(path)
    groups = report.get("groups") if isinstance(report, dict) and isinstance(report.get("groups"), dict) else {}
    present_groups = set(groups)
    empty_or_invalid_required_groups = sorted(
        name
        for name in REQUIRED_RELEASE_GATE_GROUPS
        if not isinstance(groups.get(name), list) or not groups.get(name)
    )
    group_checks = [
        item
        for group in groups.values()
        if isinstance(group, list)
        for item in group
    ]
    generated_at = report.get("generated_at") if report else None
    timestamp_valid, age_hours = _release_gate_age_hours(generated_at, now=now)
    fresh = bool(
        timestamp_valid
        and age_hours is not None
        and age_hours <= INTERNAL_RELEASE_GATE_MAX_AGE_HOURS
    )
    source_revision = report.get("source_revision") if report else None
    source_revision_valid = bool(
        isinstance(source_revision, str) and SOURCE_REVISION.fullmatch(source_revision)
    )
    passed = bool(
        report
        and report.get("passed") is True
        and fresh
        and source_revision_valid
        and report.get("scope") == "full-system release-candidate maturity gate"
        and report.get("evidence_level") == "internal automated gate; not independent human review"
        and report.get("failures") == []
        and REQUIRED_RELEASE_GATE_GROUPS.issubset(present_groups)
        and not empty_or_invalid_required_groups
        and group_checks
        and all(isinstance(item, dict) and item.get("passed") is True for item in group_checks)
    )
    return check(
        "internal release-candidate gate passed",
        passed,
        {
            "source": str(path),
            "generated_at_present": bool(report and isinstance(report.get("generated_at"), str)),
            "timestamp_valid": timestamp_valid,
            "age_hours": age_hours,
            "max_age_hours": INTERNAL_RELEASE_GATE_MAX_AGE_HOURS,
            "fresh": fresh,
            "source_revision": source_revision,
            "source_revision_valid": source_revision_valid,
            "scope": report.get("scope") if report else None,
            "evidence_level": report.get("evidence_level") if report else None,
            "passed": report.get("passed") if report else None,
            "failures_empty": bool(report and report.get("failures") == []),
            "required_groups_present": sorted(REQUIRED_RELEASE_GATE_GROUPS & present_groups),
            "empty_or_invalid_required_groups": empty_or_invalid_required_groups,
        },
    )


def production_config_passes(config: dict[str, Any], required_keys: set[str]) -> bool:
    checked_keys = set(config.get("checked_keys") or [])
    checks = config.get("checks") if isinstance(config.get("checks"), dict) else {}
    return bool(
        config.get("ok")
        and config.get("status") == "passed"
        and config.get("env_file_sha256")
        and required_keys.issubset(checked_keys)
        and REQUIRED_PRODUCTION_CHECKS.issubset(checks)
        and all(checks.get(name) is True for name in REQUIRED_PRODUCTION_CHECKS)
    )


def production_config_check(system_evidence: Path, production_config: Path) -> dict[str, Any]:
    report = load_json(system_evidence) or {}
    embedded = report.get("production_config") or {}
    standalone = load_json(production_config) or {}
    embedded = embedded if isinstance(embedded, dict) else {}
    standalone = standalone if isinstance(standalone, dict) else {}
    required_keys = {
        "APP_ENV",
        "SECRET_KEY",
        "BOOTSTRAP_ADMIN_PASSWORD",
        "POSTGRES_PASSWORD",
        "SEED_DEMO_DATA",
        "DEEPSEEK_API_KEY",
        "APP_REVISION",
    }
    embedded_keys = set(embedded.get("checked_keys") or [])
    standalone_keys = set(standalone.get("checked_keys") or [])
    same_fingerprint = bool(
        embedded.get("env_file_sha256")
        and standalone.get("env_file_sha256")
        and embedded.get("env_file_sha256") == standalone.get("env_file_sha256")
    )
    same_keys = embedded_keys == standalone_keys
    embedded_checks = embedded.get("checks") if isinstance(embedded.get("checks"), dict) else {}
    standalone_checks = standalone.get("checks") if isinstance(standalone.get("checks"), dict) else {}
    same_checks = embedded_checks == standalone_checks
    passed = (
        production_config_passes(embedded, required_keys)
        and production_config_passes(standalone, required_keys)
        and same_fingerprint
        and same_keys
        and same_checks
    )
    return check(
        "production configuration was checked in production mode",
        passed,
        {
            "embedded": {
                "status": embedded.get("status"),
                "env_file_sha256_present": bool(embedded.get("env_file_sha256")),
                "checked_keys": sorted(embedded_keys),
                "checks": embedded_checks,
                "source": str(system_evidence),
            },
            "standalone": {
                "status": standalone.get("status"),
                "env_file_sha256_present": bool(standalone.get("env_file_sha256")),
                "checked_keys": sorted(standalone_keys),
                "checks": standalone_checks,
                "source": str(production_config),
            },
            "same_env_file_sha256": same_fingerprint,
            "same_checked_keys": same_keys,
            "same_checks": same_checks,
        },
    )


def human_freeze_check(path: Path, root: Path) -> dict[str, Any]:
    bundle = load_json(path)
    if bundle is None:
        return check("external confirmatory human-review freeze passed", False, f"missing: {path}")
    result = validate_human_freeze(bundle, root=root)
    return check("external confirmatory human-review freeze passed", result["passed"], result)


def long_soak_check(path: Path) -> dict[str, Any]:
    report = load_json(path)
    if report is None:
        return check("long soak evidence passed", False, f"missing: {path}")
    result = validate_long_soak(report)
    return check("long soak evidence passed", result["ok"], {"source": str(path), **result})


def tls_deployment_check(path: Path) -> dict[str, Any]:
    report = load_json(path)
    if report is None:
        return check("real TLS deployment evidence passed", False, f"missing: {path}")
    result = validate_tls_deployment(report)
    return check("real TLS deployment evidence passed", result["ok"], {"source": str(path), **report, **result})


def offsite_backup_check(path: Path, root: Path) -> dict[str, Any]:
    report = load_json(path)
    if report is None:
        return check("offsite encrypted backup evidence passed", False, f"missing: {path}")
    result = validate_offsite_backup(report, root=root)
    return check("offsite encrypted backup evidence passed", result["ok"], {"source": str(path), **result})


def manifest_paths(path: Path) -> set[str]:
    manifest = load_json(path) or {}
    return {str(item.get("path") or "") for item in manifest.get("files", []) if isinstance(item, dict)}


def evidence_manifest_check(path: Path, root: Path, required_files: list[Path]) -> dict[str, Any]:
    if not path.is_file():
        return check("final maturity evidence manifest verified", False, f"missing: {path}")
    result = verify_manifest(path, root)
    required_paths = {file.resolve().relative_to(root.resolve()).as_posix() for file in required_files}
    present_paths = manifest_paths(path)
    missing_paths = sorted(required_paths - present_paths)
    return check(
        "final maturity evidence manifest verified",
        result["ok"] and not missing_paths,
        {**result, "required_paths": sorted(required_paths), "missing_required_paths": missing_paths},
    )


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    checks = [
        safe_check("internal release-candidate gate passed", release_gate_check, args.release_gate),
        safe_check("production configuration was checked in production mode", production_config_check, args.system_evidence, args.production_config),
        safe_check("external confirmatory human-review freeze passed", human_freeze_check, args.human_freeze, args.root),
        safe_check("long soak evidence passed", long_soak_check, args.long_soak),
        safe_check("real TLS deployment evidence passed", tls_deployment_check, args.tls_deployment),
        safe_check("offsite encrypted backup evidence passed", offsite_backup_check, args.offsite_backup, args.root),
        safe_check(
            "final maturity evidence manifest verified",
            evidence_manifest_check,
            args.evidence_manifest,
            args.root,
            [
                args.release_gate,
                args.system_evidence,
                args.production_config,
                args.human_freeze,
                args.long_soak,
                args.tls_deployment,
                args.offsite_backup,
            ],
        ),
    ]
    failures = [item for item in checks if not item["passed"]]
    internal_check = checks[0]
    internal_detail = internal_check.get("detail") if isinstance(internal_check.get("detail"), dict) else {}
    internal_source_revision = internal_detail.get("source_revision")
    source_revision = (
        internal_source_revision
        if internal_check["passed"]
        and isinstance(internal_source_revision, str)
        and SOURCE_REVISION.fullmatch(internal_source_revision)
        else None
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_revision": source_revision,
        "passed": not failures,
        "scope": "final maturity gate for confirmatory human review",
        "checks": checks,
        "failures": failures,
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Final maturity gate",
        "",
        f"Result: {'PASS' if report['passed'] else 'FAIL'}",
        "",
        "| Check | Status | Detail |",
        "| --- | --- | --- |",
    ]
    for item in report["checks"]:
        detail = json.dumps(item["detail"], ensure_ascii=False, sort_keys=True)
        lines.append(f"| {item['name']} | {'PASS' if item['passed'] else 'FAIL'} | `{detail}` |")
    if report["failures"]:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- {item['name']}" for item in report["failures"])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-gate", type=Path, default=DEFAULT_RELEASE_GATE)
    parser.add_argument("--system-evidence", type=Path, default=DEFAULT_SYSTEM_EVIDENCE)
    parser.add_argument("--production-config", type=Path, default=DEFAULT_PRODUCTION_CONFIG)
    parser.add_argument("--human-freeze", type=Path, default=DEFAULT_HUMAN_FREEZE)
    parser.add_argument("--long-soak", type=Path, default=DEFAULT_LONG_SOAK)
    parser.add_argument("--tls-deployment", type=Path, default=DEFAULT_TLS)
    parser.add_argument("--offsite-backup", type=Path, default=DEFAULT_OFFSITE_BACKUP)
    parser.add_argument("--evidence-manifest", type=Path, default=DEFAULT_EVIDENCE_MANIFEST)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.markdown.write_text(markdown(report), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "failures": len(report["failures"]), "output": str(args.output)}, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
