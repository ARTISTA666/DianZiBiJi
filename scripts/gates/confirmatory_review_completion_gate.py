#!/usr/bin/env python3
"""Gate for declaring confirmatory human review complete enough to report."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from freeze_preregistration import verify_manifest
from summarize_system_reviews import summarize
from validate_human_review_freeze import validate as validate_human_freeze


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FREEZE = ROOT / "docs" / "experiments" / "confirmatory-human-review-freeze.json"
DEFAULT_EXPORT = ROOT / "docs" / "experiments" / "confirmatory-human-review-export.csv"
DEFAULT_FINAL_GATE = ROOT / "docs" / "experiments" / "final-maturity-gate-latest.json"
DEFAULT_EVIDENCE_MANIFEST = ROOT / "docs" / "experiments" / "confirmatory-review-evidence-manifest.json"
DEFAULT_OUTPUT = ROOT / "docs" / "experiments" / "confirmatory-review-completion-latest.json"
DEFAULT_MARKDOWN = ROOT / "docs" / "experiments" / "confirmatory-review-completion-latest.md"
MIN_MODES = 5
EXPECTED_REVIEWERS = 2
FORMAL_EXPORT_PROTOCOL = "confirmatory_human_review_v1"
REQUIRED_FORMAL_EXPORT_COLUMNS = {"review_batch_id", "export_protocol", "final_maturity_gate_sha256"}
REQUIRED_FINAL_MATURITY_CHECKS = {
    "internal release-candidate gate passed",
    "production configuration was checked in production mode",
    "external confirmatory human-review freeze passed",
    "long soak evidence passed",
    "real TLS deployment evidence passed",
    "offsite encrypted backup evidence passed",
    "final maturity evidence manifest verified",
}
SOURCE_REVISION = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


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


def manifest_paths(path: Path) -> set[str]:
    manifest = load_json(path) or {}
    return {str(item.get("path") or "") for item in manifest.get("files", []) if isinstance(item, dict)}


def evidence_manifest_check(path: Path, root: Path, required_files: list[Path]) -> dict[str, Any]:
    if not path.is_file():
        return check("confirmatory review evidence manifest verified", False, f"missing: {path}")
    result = verify_manifest(path, root)
    required_paths = {file.resolve().relative_to(root.resolve()).as_posix() for file in required_files}
    present_paths = manifest_paths(path)
    missing_paths = sorted(required_paths - present_paths)
    return check(
        "confirmatory review evidence manifest verified",
        result["ok"] and not missing_paths,
        {**result, "required_paths": sorted(required_paths), "missing_required_paths": missing_paths},
    )


def final_maturity_gate_check(path: Path) -> dict[str, Any]:
    report = load_json(path)
    checks = report.get("checks") if isinstance(report, dict) and isinstance(report.get("checks"), list) else []
    check_names = {item.get("name") for item in checks if isinstance(item, dict)}
    source_revision = report.get("source_revision") if report else None
    source_revision_valid = bool(
        isinstance(source_revision, str) and SOURCE_REVISION.fullmatch(source_revision)
    )
    passed = bool(
        report
        and report.get("passed") is True
        and source_revision_valid
        and isinstance(report.get("generated_at"), str)
        and report.get("scope") == "final maturity gate for confirmatory human review"
        and report.get("failures") == []
        and REQUIRED_FINAL_MATURITY_CHECKS.issubset(check_names)
        and all(isinstance(item, dict) and item.get("passed") is True for item in checks)
    )
    return check(
        "final maturity gate passed before reporting review",
        passed,
        {
            "source": str(path),
            "source_revision": source_revision,
            "source_revision_valid": source_revision_valid,
            "generated_at_present": bool(report and isinstance(report.get("generated_at"), str)),
            "scope": report.get("scope") if report else None,
            "passed": report.get("passed") if report else None,
            "failures_empty": bool(report and report.get("failures") == []),
            "required_checks_present": sorted(REQUIRED_FINAL_MATURITY_CHECKS & check_names),
        },
    )


def sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def formal_export_metadata_check(path: Path, final_gate: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            fieldnames = set(reader.fieldnames or [])
            missing = sorted(REQUIRED_FORMAL_EXPORT_COLUMNS - fieldnames)
            rows = list(reader)
    except Exception as exc:
        return check("human review export uses confirmatory protocol", False, {"error": str(exc)})
    batch_ids = {str(row.get("review_batch_id") or "").strip() for row in rows}
    protocols = {str(row.get("export_protocol") or "").strip() for row in rows}
    final_gate_hashes = {str(row.get("final_maturity_gate_sha256") or "").strip() for row in rows}
    expected_final_gate_hash = sha256_file(final_gate)
    valid_batch_ids = all(re.fullmatch(r"R[A-F0-9]{12}", batch_id) for batch_id in batch_ids)
    valid_hashes = all(re.fullmatch(r"[a-f0-9]{64}", value) for value in final_gate_hashes)
    return check(
        "human review export uses confirmatory protocol",
        not missing
        and bool(rows)
        and len(batch_ids) == 1
        and "" not in batch_ids
        and valid_batch_ids
        and protocols == {FORMAL_EXPORT_PROTOCOL}
        and valid_hashes
        and expected_final_gate_hash is not None
        and final_gate_hashes == {expected_final_gate_hash},
        {
            "missing_columns": missing,
            "batch_ids": sorted(batch_ids),
            "valid_batch_ids": valid_batch_ids,
            "protocols": sorted(protocols),
            "expected_protocol": FORMAL_EXPORT_PROTOCOL,
            "final_maturity_gate_sha256": sorted(final_gate_hashes),
            "valid_final_maturity_gate_sha256": valid_hashes,
            "expected_final_maturity_gate_sha256": expected_final_gate_hash,
        },
    )


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    final_gate = getattr(args, "final_gate", DEFAULT_FINAL_GATE)
    final_gate_result = final_maturity_gate_check(final_gate)
    checks.append(final_gate_result)
    freeze = load_json(args.freeze)
    frozen_methods: set[str] = set()
    frozen_reviewer_user_ids: set[int] = set()
    frozen_question_indices: set[int] = set()
    frozen_question_text_by_index: dict[str, str] = {}
    if freeze is None:
        checks.append(check("confirmatory freeze exists and validates", False, f"missing: {args.freeze}"))
        question_count = 0
    else:
        try:
            freeze_result = validate_human_freeze(freeze, root=args.root)
        except Exception as exc:
            freeze_result = {"passed": False, "question_count": 0, "error": str(exc)}
        checks.append(check("confirmatory freeze exists and validates", freeze_result["passed"], freeze_result))
        question_count = freeze_result["question_count"]
        frozen_methods = set(freeze_result.get("methods") or [])
        frozen_reviewer_user_ids = set(freeze_result.get("reviewer_user_ids") or [])
        frozen_question_indices = set(freeze_result.get("question_indices") or [])
        frozen_question_text_by_index = freeze_result.get("question_text_by_index") or {}

    if not args.export.is_file():
        checks.append(check("human review export exists", False, f"missing: {args.export}"))
    else:
        checks.append(formal_export_metadata_check(args.export, final_gate))
        try:
            summary = summarize(args.export, expected_reviewers=EXPECTED_REVIEWERS)
            export_methods = set(summary["by_mode"])
            export_question_indices = set(summary["completion"].get("question_indices") or [])
            export_question_text_by_index = summary["completion"].get("question_text_by_index") or {}
            mode_count = len(export_methods)
            expected_items = question_count * len(frozen_methods)
            export_reviewers = set(summary["reviewer_ids"])
            checks.extend(
                [
                    check("human review export is complete", not summary["completion"]["issues"], summary["completion"]),
                    check(
                        "human review methods match frozen methods",
                        len(frozen_methods) >= MIN_MODES and export_methods == frozen_methods,
                        {"frozen_methods": sorted(frozen_methods), "export_methods": sorted(export_methods)},
                    ),
                    check(
                        "human review reviewers match frozen reviewers",
                        export_reviewers == frozen_reviewer_user_ids,
                        {"frozen_reviewer_user_ids": sorted(frozen_reviewer_user_ids), "export_reviewer_ids": sorted(export_reviewers)},
                    ),
                    check(
                        "human review questions match frozen questions",
                        export_question_indices == frozen_question_indices
                        and export_question_text_by_index == frozen_question_text_by_index,
                        {
                            "frozen_question_indices": sorted(frozen_question_indices),
                            "export_question_indices": sorted(export_question_indices),
                            "question_texts_match": export_question_text_by_index == frozen_question_text_by_index,
                        },
                    ),
                    check(
                        "human review covers every frozen question and method",
                        question_count > 0 and summary["completion"]["export_item_count"] == expected_items,
                        {
                            "question_count": question_count,
                            "mode_count": mode_count,
                            "expected_items": expected_items,
                            "actual_items": summary["completion"]["export_item_count"],
                        },
                    ),
                ]
            )
        except Exception as exc:
            checks.append(check("human review export is complete", False, str(exc)))

    checks.append(evidence_manifest_check(args.evidence_manifest, args.root, [final_gate, args.freeze, args.export]))

    failures = [item for item in checks if not item["passed"]]
    final_gate_detail = final_gate_result.get("detail") if isinstance(final_gate_result.get("detail"), dict) else {}
    final_source_revision = final_gate_detail.get("source_revision")
    source_revision = (
        final_source_revision
        if final_gate_result["passed"]
        and isinstance(final_source_revision, str)
        and SOURCE_REVISION.fullmatch(final_source_revision)
        else None
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_revision": source_revision,
        "passed": not failures,
        "scope": "confirmatory human review completion gate",
        "checks": checks,
        "failures": failures,
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Confirmatory human review completion gate",
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
    parser.add_argument("--freeze", type=Path, default=DEFAULT_FREEZE)
    parser.add_argument("--export", type=Path, default=DEFAULT_EXPORT)
    parser.add_argument("--final-gate", type=Path, default=DEFAULT_FINAL_GATE)
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
