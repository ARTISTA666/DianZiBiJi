import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models.user import User


ROOT = Path(__file__).resolve().parents[3]

router = APIRouter(prefix="/maturity", tags=["maturity"])

GATES = [
    ("internal_release", "内部门禁", ROOT / "docs" / "experiments" / "main-maturity-gate-latest.json", "full-system release-candidate maturity gate"),
    ("final_maturity", "最终成熟门禁", ROOT / "docs" / "experiments" / "final-maturity-gate-latest.json", "final maturity gate for confirmatory human review"),
    ("confirmatory_review_completion", "确认性人工评审完成门禁", ROOT / "docs" / "experiments" / "confirmatory-review-completion-latest.json", "confirmatory human review completion gate"),
]

REQUIRED_GATE_ITEMS = {
    "internal_release": {"retrieval", "rag_experiment", "agent", "system", "evidence_manifest"},
    "final_maturity": {
        "internal release-candidate gate passed",
        "production configuration was checked in production mode",
        "external confirmatory human-review freeze passed",
        "long soak evidence passed",
        "real TLS deployment evidence passed",
        "offsite encrypted backup evidence passed",
        "final maturity evidence manifest verified",
    },
    "confirmatory_review_completion": {
        "final maturity gate passed before reporting review",
        "confirmatory freeze exists and validates",
        "human review export uses confirmatory protocol",
        "human review export is complete",
        "human review methods match frozen methods",
        "human review reviewers match frozen reviewers",
        "human review questions match frozen questions",
        "human review covers every frozen question and method",
        "confirmatory review evidence manifest verified",
    },
}


def _blocker_text(item: Any) -> str:
    if not isinstance(item, dict):
        return str(item)
    name = str(item.get("name") or "unnamed failure")
    detail = item.get("detail")
    if isinstance(detail, str) and detail:
        return f"{name}: {detail}"
    if isinstance(detail, dict):
        missing = detail.get("missing_required_paths")
        if isinstance(missing, list) and missing:
            return f"{name}: missing {', '.join(str(path) for path in missing[:5])}"
        error = detail.get("error")
        if isinstance(error, str) and error:
            return f"{name}: {error}"
        status_parts = []
        for label in ("standalone", "embedded"):
            nested = detail.get(label)
            if isinstance(nested, dict) and isinstance(nested.get("status"), str):
                status_parts.append(f"{label}={nested['status']}")
        failed_checks = []
        for value in detail.values():
            if isinstance(value, dict) and isinstance(value.get("checks"), dict):
                failed_checks.extend(str(check) for check, passed in value["checks"].items() if passed is False)
        if status_parts or failed_checks:
            suffix = "; ".join(status_parts + ([f"failed checks: {', '.join(sorted(set(failed_checks))[:8])}"] if failed_checks else []))
            return f"{name}: {suffix}"
        gate_parts = []
        if isinstance(detail.get("passed"), bool):
            gate_parts.append(f"passed={detail['passed']}")
        if isinstance(detail.get("failures_empty"), bool):
            gate_parts.append(f"failures_empty={detail['failures_empty']}")
        if isinstance(detail.get("scope"), str):
            gate_parts.append(f"scope={detail['scope']}")
        if isinstance(detail.get("source"), str):
            gate_parts.append(f"source={detail['source']}")
        if gate_parts:
            return f"{name}: {'; '.join(gate_parts)}"
    return name


def _passed_evidence_blocker(key: str, payload: dict[str, Any]) -> str | None:
    if key == "internal_release":
        groups = payload.get("groups")
        if not isinstance(groups, dict) or not groups:
            return "invalid groups field: expected non-empty check groups for passed gate"
        missing_groups = sorted(REQUIRED_GATE_ITEMS[key] - set(groups))
        if missing_groups:
            return f"invalid groups field: missing required groups {', '.join(missing_groups)}"
        if any(not isinstance(group, list) for group in groups.values()):
            return "invalid groups field: every group must be a check list"
        empty_required_groups = sorted(name for name in REQUIRED_GATE_ITEMS[key] if not groups[name])
        if empty_required_groups:
            return f"invalid groups field: empty required groups {', '.join(empty_required_groups)}"
        checks = [item for group in groups.values() if isinstance(group, list) for item in group]
        if not checks:
            return "invalid groups field: expected non-empty check groups for passed gate"
    else:
        checks = payload.get("checks")
        if not isinstance(checks, list) or not checks:
            return "invalid checks field: expected non-empty list for passed gate"
        check_names = {item.get("name") for item in checks if isinstance(item, dict)}
        missing_checks = sorted(REQUIRED_GATE_ITEMS[key] - check_names)
        if missing_checks:
            return f"invalid checks field: missing required checks {', '.join(missing_checks)}"
    if any(not isinstance(item, dict) or item.get("passed") is not True for item in checks):
        return "invalid checks field: every check must be passed"
    return None


def _timestamp_blocker(value: str) -> str | None:
    try:
        generated_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return "invalid generated_at field: expected ISO timestamp string for passed gate"
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)
    if generated_at > datetime.now(timezone.utc) + timedelta(minutes=5):
        return "invalid generated_at field: timestamp is in the future"
    return None


def _gate_status(key: str, title: str, path: Path, expected_scope: str) -> dict[str, Any]:
    if not path.is_file():
        return {"key": key, "title": title, "path": str(path.relative_to(ROOT)), "exists": False, "passed": False, "generated_at": None, "blockers": [f"missing: {path.relative_to(ROOT)}"]}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"key": key, "title": title, "path": str(path.relative_to(ROOT)), "exists": True, "passed": False, "generated_at": None, "blockers": [f"invalid JSON: {getattr(exc, 'msg', str(exc))}"]}
    if not isinstance(payload, dict):
        return {"key": key, "title": title, "path": str(path.relative_to(ROOT)), "exists": True, "passed": False, "generated_at": None, "blockers": ["gate report must be a JSON object"]}
    failures_missing = "failures" not in payload
    failures = payload.get("failures")
    if failures is None:
        failures = []
    if not isinstance(failures, list):
        failures = [f"invalid failures field: expected list, got {type(failures).__name__}"]
    raw_passed = payload.get("passed")
    blockers = [_blocker_text(item) for item in failures]
    if raw_passed not in (True, False):
        blockers.append(f"invalid passed field: expected boolean true/false, got {type(raw_passed).__name__}")
    generated_at = payload.get("generated_at") if isinstance(payload.get("generated_at"), str) else None
    if raw_passed is True:
        if failures_missing:
            blockers.append("invalid failures field: expected explicit empty list for passed gate")
        if generated_at is None:
            blockers.append("invalid generated_at field: expected timestamp string for passed gate")
        else:
            timestamp_blocker = _timestamp_blocker(generated_at)
            if timestamp_blocker:
                blockers.append(timestamp_blocker)
        if payload.get("scope") != expected_scope:
            blockers.append(f"invalid scope field: expected {expected_scope}")
        evidence_blocker = _passed_evidence_blocker(key, payload)
        if evidence_blocker:
            blockers.append(evidence_blocker)
    passed = raw_passed is True and not blockers
    if not passed and not blockers:
        blockers = ["gate report is failed but contains no failure details"]
    return {
        "key": key,
        "title": title,
        "path": str(path.relative_to(ROOT)),
        "exists": True,
        "passed": passed,
        "generated_at": generated_at,
        "blockers": blockers,
    }


@router.get("/status")
def maturity_status(_: User = Depends(get_current_user)) -> dict[str, Any]:
    gates = [_gate_status(key, title, path, expected_scope) for key, title, path, expected_scope in GATES]
    final_maturity_passed = next(gate for gate in gates if gate["key"] == "final_maturity")["passed"]
    completion_passed = next(gate for gate in gates if gate["key"] == "confirmatory_review_completion")["passed"]
    return {
        "passed": all(gate["passed"] for gate in gates),
        "human_review_allowed": final_maturity_passed,
        "human_review_report_allowed": final_maturity_passed and completion_passed,
        "gates": gates,
    }
