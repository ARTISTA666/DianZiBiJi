#!/usr/bin/env python3
"""Render a citable, fail-closed descriptive summary from the experiment-5 audit."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import re
import subprocess
from pathlib import Path
from typing import Any

from rag_experiment_contract import (
    MODES,
    PAPER_BLOCKER_ARCHIVE_MAPPING,
    RETRIEVAL_SNAPSHOT_FIELDS,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUDIT = ROOT / "docs/experiments/rag-experiment-5-internal-bundle-audit-2026-08-12.json"
DEFAULT_VALIDATION = ROOT / "data/real/experiment-5/internal-five-mode-validation.json"
DEFAULT_OUTPUT = ROOT / "docs/experiments/rag-experiment-5-internal-descriptive-results-v1.md"
CITATION_TOKEN_RE = re.compile(r"\[([SG])([^\]]*)\]", re.IGNORECASE)
CITATION_RE = re.compile(r"\[([SG])(\d+)\]", re.IGNORECASE)
RETRIEVAL_GAP_MODES = MODES
RETRIEVAL_REQUIRED_FIELDS = RETRIEVAL_SNAPSHOT_FIELDS
RUN_BINDING_CHECK_LABELS = (
    ("题集哈希与冻结题集一致", "question_set_sha256"),
    ("题目数量与冻结题集一致", "question_count_matches_freeze"),
    ("选定题目 ID 与冻结题集一致", "selected_question_ids_match"),
    ("金标准事实数量与冻结题集一致", "gold_fact_count_matches_freeze"),
    ("方法顺序与运行配置一致", "method_order_matches_run_config"),
    ("重复次数与运行配置一致", "repetition_count_matches"),
    ("随机种子与运行配置一致", "random_seed_matches"),
    ("生成 provider 与运行快照一致", "generation.provider_matches_snapshot"),
    ("生成 model 与运行快照一致", "generation.model_matches_snapshot"),
    ("temperature 与运行快照一致", "generation.temperature_matches_snapshot"),
    ("max_tokens 与运行快照一致", "generation.max_tokens_matches_snapshot"),
    ("chunk_size 与运行快照一致", "retrieval.chunk_size_matches_snapshot"),
    ("chunk_overlap 与运行快照一致", "retrieval.chunk_overlap_matches_snapshot"),
    ("检索 top-k 与运行配置一致", "retrieval.retrieval_top_k_matches_snapshot"),
    (
        "集合检索 top-k 与运行配置一致",
        "retrieval.collection_retrieval_top_k_matches_snapshot",
    ),
    ("向量候选数与运行配置一致", "retrieval.vector_candidate_k_matches_snapshot"),
    ("图谱 top-k 与运行配置一致", "retrieval.graph_top_k_matches_snapshot"),
    ("图谱最低分与运行配置一致", "retrieval.graph_min_score_matches_snapshot"),
)
EVIDENCE_GATE_CHECK_LABELS = (
    ("CSV 行完整性", "csv_row_integrity"),
    ("模式汇总由原始 CSV 重算并匹配报告", "mode_summary_recomputed_matches_report"),
    ("配对比较由原始 CSV 重算并匹配报告", "paired_comparisons_recomputed_match_report"),
    ("严格引用审计与报告一致", "citation_audit_recomputed_matches_report"),
    ("输入冻结清单可复核", "input_freeze_manifest_verifies"),
)
DATA_BINDING_CHECK_LABELS = (
    ("题目编号在冻结题集范围内", "csv_question_indices_bound"),
    ("CSV 题干与冻结题集逐字一致", "csv_question_texts_bound"),
    ("逐案例 provider/model/prompt_version 绑定", "csv_runtime_bindings_bound"),
    ("逐案例 retrieval snapshot 绑定", "csv_retrieval_bindings_bound"),
    ("重复编号在运行配置范围内", "csv_repetition_indices_bound"),
    ("方法值属于预注册五方法", "csv_methods_bound"),
    ("题目—重复—方法案例键域完整", "csv_case_key_domain_valid"),
)
PAPER_GATE_DERIVED_CHECK_NAMES = ("paper_gate_consistent",)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object expected: {path}")
    return value


def percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def citation_count_rate(count: Any, denominator: Any) -> str:
    if (
        isinstance(count, bool)
        or not isinstance(count, int)
        or count < 0
        or isinstance(denominator, bool)
        or not isinstance(denominator, int)
        or denominator <= 0
        or count > denominator
    ):
        raise ValueError("citation count rate must be a bounded count over a positive denominator")
    return f"{count}/{denominator} ({percent(count / denominator)})"


def bounded_count_rate(count: Any, denominator: Any, label: str) -> str:
    try:
        return citation_count_rate(count, denominator)
    except ValueError as error:
        raise ValueError(f"{label} must be a bounded count over its row count") from error


def retrieval_field_gap_summary(
    gap: dict[str, Any], mode: str
) -> tuple[str, str]:
    row_count = gap["row_count"]
    rows_with_any_gap = gap["rows_with_any_gap"]
    rows_with_complete_snapshot = gap.get("rows_with_complete_snapshot")
    required_fields = gap.get("required_fields")
    missing_by_field = gap["missing_by_field"]
    mismatch_by_field = gap["mismatch_by_field"]
    if (
        isinstance(rows_with_any_gap, bool)
        or not isinstance(rows_with_any_gap, int)
        or rows_with_any_gap < 0
        or rows_with_any_gap > row_count
    ):
        raise ValueError(f"{mode} any-gap row count must be bounded by its row count")
    if rows_with_complete_snapshot is not None:
        if (
            isinstance(rows_with_complete_snapshot, bool)
            or not isinstance(rows_with_complete_snapshot, int)
            or rows_with_complete_snapshot < 0
            or rows_with_complete_snapshot + rows_with_any_gap != row_count
        ):
            raise ValueError(f"{mode} complete and any-gap rows must partition row count")
    if (
        not isinstance(required_fields, list)
        or not all(isinstance(field, str) for field in required_fields)
        or tuple(required_fields) != RETRIEVAL_REQUIRED_FIELDS.get(mode)
        or set(missing_by_field) != set(required_fields)
        or set(mismatch_by_field) != set(required_fields)
    ):
        raise ValueError(f"{mode} field counts must exactly match canonical required fields")
    fields = sorted(set(missing_by_field) | set(mismatch_by_field))
    missing_lines: list[str] = []
    mismatch_lines: list[str] = []
    for field in fields:
        missing = missing_by_field.get(field, 0)
        mismatch = mismatch_by_field.get(field, 0)
        if missing > rows_with_any_gap or mismatch > rows_with_any_gap:
            raise ValueError(f"{mode} field gap count exceeds any-gap rows: {field}")
        missing_lines.append(f"{field}={bounded_count_rate(missing, row_count, mode)}")
        mismatch_lines.append(f"{field}={bounded_count_rate(mismatch, row_count, mode)}")
    return "; ".join(missing_lines) or "不适用", "; ".join(mismatch_lines) or "不适用"


def number(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def interval(values: list[float]) -> str:
    if len(values) != 2:
        raise ValueError("95% interval must contain two bounds")
    return f"[{values[0]:.4f}, {values[1]:.4f}]"


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compact_value(value: Any, depth: int = 0) -> str:
    """Render a bounded, deterministic human summary without dropping raw JSON."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return stable_json(value)
    if isinstance(value, list):
        if depth == 0:
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        return f"array[{len(value)}]"
    if isinstance(value, dict):
        if depth >= 2:
            return f"object[{len(value)} keys]"
        parts = [
            f"{key}={compact_value(value[key], depth + 1)}"
            for key in sorted(value)
        ]
        rendered = "; ".join(parts)
        return rendered if depth == 0 else "{" + rendered + "}"
    return stable_json(str(value))


def failure_gate_rows(audit: dict[str, Any]) -> list[dict[str, str]]:
    rows = []
    seen_names: set[str] = set()
    checks = audit.get("checks")
    if not isinstance(checks, list):
        raise ValueError("audit checks must be an array")
    if not checks:
        raise ValueError("audit checks must not be empty")
    for check in checks:
        if not isinstance(check, dict):
            raise ValueError("failed audit checks must be objects")
        passed = check.get("passed")
        if not isinstance(passed, bool):
            raise ValueError("audit check passed must be boolean")
        name = check.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("audit checks must have a non-empty name")
        if name in seen_names:
            raise ValueError(f"duplicate audit check name: {name}")
        seen_names.add(name)
        severity = check.get("severity")
        if not isinstance(severity, str) or not severity:
            raise ValueError(f"audit check must have a non-empty severity: {name}")
        if passed:
            continue
        rows.append(
            {
                "name": name,
                "severity": severity,
                "actual": stable_json(check.get("actual")),
                "actual_summary": compact_value(check.get("actual")),
                "expected": stable_json(check.get("expected")),
                "expected_summary": compact_value(check.get("expected")),
            }
        )
    return sorted(rows, key=lambda item: item["name"])


def paper_material_check_coverage(audit: dict[str, Any]) -> list[dict[str, Any]]:
    """Verify every fixed paper-facing check set is represented in the audit JSON."""
    check_rows = audit.get("checks")
    if not isinstance(check_rows, list) or not check_rows:
        raise ValueError("paper material check coverage requires non-empty checks")
    by_name: dict[str, dict[str, Any]] = {}
    for item in check_rows:
        name = item.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("paper material check coverage requires named checks")
        if name in by_name:
            raise ValueError(f"paper material check coverage duplicate: {name}")
        if not isinstance(item.get("passed"), bool):
            raise ValueError(f"paper material check coverage invalid passed: {name}")
        by_name[name] = item

    groups = (
        ("实验设计与运行配置绑定", tuple(name for _, name in RUN_BINDING_CHECK_LABELS)),
        ("证据链门禁", tuple(name for _, name in EVIDENCE_GATE_CHECK_LABELS)),
        ("数据—问题集绑定门禁", tuple(name for _, name in DATA_BINDING_CHECK_LABELS)),
        ("论文门禁派生检查", PAPER_GATE_DERIVED_CHECK_NAMES),
    )
    coverage: list[dict[str, Any]] = []
    for label, names in groups:
        missing = [name for name in names if name not in by_name]
        if missing:
            raise ValueError(
                f"paper material check coverage missing: {label}: {', '.join(missing)}"
            )
        coverage.append(
            {
                "label": label,
                "registered": len(names),
                "observed": sum(name in by_name for name in names),
                "missing": missing,
                "status": "PASS",
            }
        )
    return coverage


def failure_identity_audit(audit: dict[str, Any], failed_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Recompute failure identities and compare them with the audit summary."""
    checks = audit.get("checks")
    if not isinstance(checks, list):
        raise ValueError("failure identity audit requires checks")
    failed_names = sorted(item["name"] for item in checks if item.get("passed") is False)
    paper_blocker_names = [
        item["name"]
        for item in checks
        if item.get("severity") == "paper_blocker" and item.get("passed") is False
    ]
    summary = audit.get("failure_summary")
    if not isinstance(summary, dict):
        raise ValueError("failure identity audit requires failure_summary")
    if (
        summary.get("failed_check_count") != len(failed_names)
        or summary.get("failed_check_names") != failed_names
        or summary.get("paper_blocker_failed_names") != paper_blocker_names
        or summary.get("paper_blockers_match") != (audit.get("paper_blockers") == paper_blocker_names)
        or [item["name"] for item in failed_rows] != failed_names
    ):
        raise ValueError("failure summary mismatch")
    return [
        {
            "label": "失败检查总数",
            "registered": len(failed_names),
            "observed": len(failed_rows),
            "missing": "—",
            "status": "PASS",
        },
        {
            "label": "paper_blockers 与 paper_blocker 失败名一致",
            "registered": len(paper_blocker_names),
            "observed": len(audit.get("paper_blockers", [])),
            "missing": "—",
            "status": "PASS",
        },
    ]


def required_audit_check_status(checks: dict[str, Any], name: str) -> str:
    """Render a required audit check without treating a missing check as PASS."""
    value = checks.get(name)
    if not isinstance(value, bool):
        raise ValueError(f"required audit check missing or invalid: {name}")
    return "PASS" if value else "FAIL"


def paper_gate_status(audit: dict[str, Any]) -> str:
    """Render the top-level paper gate only from typed, structured audit fields."""
    paper_ready = audit.get("paper_ready")
    if not isinstance(paper_ready, bool):
        raise ValueError("paper_ready must be boolean")
    blockers = audit.get("paper_blockers")
    if not isinstance(blockers, list) or not all(
        isinstance(blocker, str) and blocker for blocker in blockers
    ):
        raise ValueError("paper_blockers must be an array of non-empty strings")
    paper_gate_consistency_status(audit)
    return "PASS" if paper_ready else "FAIL"


def paper_gate_consistency_status(audit: dict[str, Any]) -> str:
    """Reject top-level paper-gate fields that disagree with check severities."""
    check_rows = audit.get("checks")
    if not isinstance(check_rows, list) or not check_rows:
        raise ValueError("paper gate consistency requires non-empty checks")

    consistency_rows = [
        item
        for item in check_rows
        if item.get("severity") == "required" and item.get("name") != "paper_gate_consistent"
    ]
    consistency_markers = [
        item for item in check_rows if item.get("name") == "paper_gate_consistent"
    ]
    if len(consistency_markers) != 1 or not isinstance(consistency_markers[0].get("passed"), bool):
        raise ValueError("paper gate consistency check missing or invalid")
    if not consistency_markers[0]["passed"]:
        raise ValueError("paper gate consistency check failed")
    expected_consistency = all(item.get("passed") is True for item in consistency_rows)

    paper_rows = [item for item in check_rows if item.get("severity") == "paper_blocker"]
    expected_blockers = [item["name"] for item in paper_rows if item.get("passed") is False]
    expected_ready = expected_consistency and not expected_blockers
    actual_consistency = audit.get("consistency_passed")
    actual_ready = audit.get("paper_ready")
    actual_blockers = audit.get("paper_blockers")
    if (
        actual_consistency is not expected_consistency
        or actual_ready is not expected_ready
        or actual_blockers != expected_blockers
    ):
        raise ValueError("paper gate consistency mismatch")
    return "PASS"


def paper_gate_audit_row(audit: dict[str, Any]) -> dict[str, str]:
    """Return the typed, machine-readable audit row for the derived gate check."""
    check_rows = audit.get("checks")
    if not isinstance(check_rows, list):
        raise ValueError("paper gate audit requires checks")
    matches = [item for item in check_rows if item.get("name") == "paper_gate_consistent"]
    if len(matches) != 1:
        raise ValueError("paper gate audit check missing or duplicated")
    item = matches[0]
    passed = item.get("passed")
    severity = item.get("severity")
    if not isinstance(passed, bool) or not isinstance(severity, str) or not severity:
        raise ValueError("paper gate audit check has invalid types")
    return {
        "name": "paper_gate_consistent",
        "severity": severity,
        "passed": "PASS" if passed else "FAIL",
        "actual": stable_json(item.get("actual")),
        "expected": stable_json(item.get("expected")),
    }


def paper_blocker_archive_rows(audit: dict[str, Any]) -> list[dict[str, str]]:
    """Map every registered paper blocker to one explicit archive requirement."""
    check_rows = audit.get("checks")
    if not isinstance(check_rows, list) or not check_rows:
        raise ValueError("paper blocker archive mapping requires checks")
    paper_rows = [item for item in check_rows if item.get("severity") == "paper_blocker"]
    expected_mapping = [
        {
            "check_name": check_name,
            "archive_item": archive_item,
            "requirement": requirement,
        }
        for check_name, archive_item, requirement in PAPER_BLOCKER_ARCHIVE_MAPPING
    ]
    if audit.get("paper_blocker_archive_mapping") != expected_mapping:
        raise ValueError("paper blocker archive mapping missing or mismatched")
    mapping = {
        check_name: (archive_item, requirement)
        for check_name, archive_item, requirement in PAPER_BLOCKER_ARCHIVE_MAPPING
    }
    paper_names = [item.get("name") for item in paper_rows]
    if any(not isinstance(name, str) or not name for name in paper_names):
        raise ValueError("paper blocker archive mapping requires named checks")
    if sorted(paper_names) != sorted(mapping):
        missing = sorted(set(mapping) - set(paper_names))
        unexpected = sorted(set(paper_names) - set(mapping))
        raise ValueError(
            "paper blocker archive mapping mismatch: "
            f"missing={missing or '—'} unexpected={unexpected or '—'}"
        )
    return [
        {
            "name": item["name"],
            "archive_item": mapping[item["name"]][0],
            "requirement": mapping[item["name"]][1],
            "status": "PASS" if item.get("passed") is True else "FAIL",
        }
        for item in paper_rows
    ]


def paper_claim_boundary_audit(
    audit: dict[str, Any], paper_gate: str, archive_rows: list[dict[str, str]]
) -> list[dict[str, str]]:
    """Keep the paper's claim level fail-closed and expose required disclosures."""
    expected_scope = "internal developer-authored automatic experiment; not independent confirmation"
    if audit.get("scope") != expected_scope:
        raise ValueError("paper claim boundary requires internal evidence scope")
    if paper_gate != "FAIL" or audit.get("paper_ready") is not False:
        raise ValueError("paper claim boundary requires paper_ready=false")
    failed_rows = [item for item in archive_rows if item["status"] == "FAIL"]
    if not failed_rows:
        raise ValueError("paper claim boundary requires unfinished archive blockers")
    return [
        {
            "label": "证据等级",
            "observed": "内部开发证据",
            "paper_treatment": "仅允许描述性/方法学诊断表述",
            "status": "PASS",
        },
        {
            "label": "确认性效果结论",
            "observed": "paper_ready=false",
            "paper_treatment": "禁止升级为确认性结果",
            "status": "FAIL",
        },
        {
            "label": "未完成归档缺口披露",
            "observed": f"{len(failed_rows)} 个 paper_blocker",
            "paper_treatment": "必须同步列出对应归档项",
            "status": "PASS",
        },
    ]


def paper_disclosure_consistency_audit(
    audit: dict[str, Any],
    failed_gate_rows: list[dict[str, str]],
    archive_rows: list[dict[str, str]],
    claim_boundary_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Cross-check the failure summary, blocker mapping, and claim disclosure."""
    failed_paper_names = [
        item["name"]
        for item in failed_gate_rows
        if item["severity"] == "paper_blocker"
    ]
    mapped_failed_names = [
        item["name"] for item in archive_rows if item["status"] == "FAIL"
    ]
    summary = audit.get("failure_summary")
    if (
        sorted(failed_paper_names) != sorted(mapped_failed_names)
        or sorted(audit.get("paper_blockers", [])) != sorted(mapped_failed_names)
        or not isinstance(summary, dict)
        or sorted(summary.get("paper_blocker_failed_names", [])) != sorted(failed_paper_names)
    ):
        raise ValueError("paper disclosure consistency mismatch")
    disclosure_rows = [
        item for item in claim_boundary_rows if item.get("label") == "未完成归档缺口披露"
    ]
    if len(disclosure_rows) != 1:
        raise ValueError("paper disclosure boundary row missing or duplicated")
    disclosure = disclosure_rows[0]
    expected_observed = f"{len(mapped_failed_names)} 个 paper_blocker"
    if disclosure.get("observed") != expected_observed or disclosure.get("status") != "PASS":
        raise ValueError("paper disclosure boundary mismatch")
    return [
        {
            "label": "失败摘要与映射 FAIL 名称一致",
            "registered": str(len(failed_paper_names)),
            "observed": str(len(mapped_failed_names)),
            "status": "PASS",
        },
        {
            "label": "paper_blockers 与主张边界披露一致",
            "registered": expected_observed,
            "observed": disclosure["observed"],
            "status": "PASS",
        },
    ]


def citation_failure_rows(citation: dict[str, Any]) -> list[dict[str, Any]]:
    invalid_rows = citation.get("invalid_marker_rows")
    if not isinstance(invalid_rows, list):
        raise ValueError("citation invalid_marker_rows must be an array")

    rows: list[dict[str, Any]] = []
    seen_rows: set[int] = set()
    seen_query_log_ids: set[int] = set()
    seen_case_keys: set[tuple[int, int, str]] = set()

    def positive_int(value: Any, label: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"citation failure row must have a positive {label}")
        return value

    for item in invalid_rows:
        if not isinstance(item, dict):
            raise ValueError("citation failure rows must be objects")
        row = positive_int(item.get("row"), "row")
        question_index = positive_int(item.get("question_index"), "question_index")
        repetition_index = positive_int(item.get("repetition_index"), "repetition_index")
        query_log_id = positive_int(item.get("query_log_id"), "query_log_id")
        question_id = item.get("question_id")
        mode = item.get("mode")
        if not isinstance(question_id, str) or not question_id:
            raise ValueError("citation failure row must have a non-empty question_id")
        if not isinstance(mode, str) or not mode:
            raise ValueError("citation failure row must have a non-empty mode")
        markers = item.get("markers")
        if (
            not isinstance(markers, list)
            or not markers
            or any(not isinstance(marker, str) or not marker for marker in markers)
        ):
            raise ValueError("citation failure row must have non-empty marker strings")
        source_count = item.get("source_count")
        graph_hit_count = item.get("graph_hit_count")
        if isinstance(source_count, bool) or not isinstance(source_count, int) or source_count < 0:
            raise ValueError("citation failure row source_count must be a non-negative integer")
        if isinstance(graph_hit_count, bool) or not isinstance(graph_hit_count, int) or graph_hit_count < 0:
            raise ValueError("citation failure row graph_hit_count must be a non-negative integer")
        if row in seen_rows:
            raise ValueError(f"duplicate citation failure row: {row}")
        if query_log_id in seen_query_log_ids:
            raise ValueError(f"duplicate citation failure query_log_id: {query_log_id}")
        case_key = (question_index, repetition_index, mode)
        if case_key in seen_case_keys:
            raise ValueError(f"duplicate citation failure case: {case_key}")
        seen_rows.add(row)
        seen_query_log_ids.add(query_log_id)
        seen_case_keys.add(case_key)
        rows.append(
            {
                "row": row,
                "question_index": question_index,
                "question_id": question_id,
                "mode": mode,
                "repetition_index": repetition_index,
                "query_log_id": query_log_id,
                "markers": markers,
                "source_count": source_count,
                "graph_hit_count": graph_hit_count,
            }
        )
    return sorted(rows, key=lambda item: item["row"])


def citation_summary_mismatch_rows(citation: dict[str, Any]) -> list[dict[str, str]]:
    reported_audit_mismatch = citation.get("reported_audit_mismatch")
    if not isinstance(reported_audit_mismatch, bool):
        raise ValueError("citation reported_audit_mismatch must be boolean")
    mismatches = citation.get("reported_summary_mismatches")
    if not isinstance(mismatches, list):
        raise ValueError("citation reported_summary_mismatches must be an array")
    if reported_audit_mismatch != bool(mismatches):
        raise ValueError("citation reported_audit_mismatch does not match summary mismatches")

    rows: list[dict[str, str]] = []
    seen_labels: set[str] = set()
    for item in mismatches:
        if not isinstance(item, dict):
            raise ValueError("citation summary mismatch rows must be objects")
        field = item.get("field")
        if not isinstance(field, str) or not field:
            raise ValueError("citation summary mismatch must have a non-empty field")
        mode = item.get("mode")
        if mode is not None and (not isinstance(mode, str) or not mode):
            raise ValueError("citation summary mismatch mode must be a non-empty string")
        if "recomputed" not in item or "reported" not in item:
            raise ValueError("citation summary mismatch must include recomputed and reported")
        label = f"{mode} / {field}" if mode is not None else field
        if label in seen_labels:
            raise ValueError(f"duplicate citation summary mismatch: {label}")
        seen_labels.add(label)
        rows.append(
            {
                "label": label,
                "recomputed": stable_json(item["recomputed"]),
                "reported": stable_json(item["reported"]),
            }
        )
    return sorted(rows, key=lambda item: item["label"])


def recompute_citation_failure_rows(csv_path: Path, questions_path: Path) -> list[dict[str, Any]]:
    questions = json.loads(questions_path.read_text(encoding="utf-8"))
    if not isinstance(questions, list):
        raise ValueError("citation failure question input must be an array")

    rows: list[dict[str, Any]] = []
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        for row_number, row in enumerate(csv.DictReader(handle), start=2):
            try:
                question_index = int(row.get("question_index", "0"))
            except (TypeError, ValueError):
                question_index = 0
            try:
                repetition_index = int(row.get("repetition_index", "0"))
            except (TypeError, ValueError):
                repetition_index = 0
            try:
                query_log_id = int(row.get("query_log_id", "0"))
            except (TypeError, ValueError):
                query_log_id = 0
            question_index_valid = 1 <= question_index <= len(questions)
            question_id = questions[question_index - 1].get("id") if question_index_valid else None
            try:
                sources = json.loads(row.get("sources_json") or "[]")
            except json.JSONDecodeError:
                sources = None
            try:
                graph_context = json.loads(row.get("graph_context_json") or "[]")
            except json.JSONDecodeError:
                graph_context = None
            answer = row.get("answer") or ""
            tokens = list(CITATION_TOKEN_RE.finditer(answer))
            invalid_tokens = [token.group(0) for token in tokens if not CITATION_RE.fullmatch(token.group(0))]
            if not invalid_tokens:
                continue
            if not question_index_valid:
                raise ValueError("citation failure row question_index does not bind to question set")
            question_entry = questions[question_index - 1]
            if not isinstance(question_entry, dict):
                raise ValueError("citation failure question entries must be objects")
            expected_question_text = question_entry.get("question")
            if not isinstance(expected_question_text, str) or not expected_question_text:
                raise ValueError("citation failure question set must contain non-empty question text")
            if row.get("question") != expected_question_text:
                raise ValueError("citation failure row question text does not match question set")
            try:
                source_count = int(row.get("source_count", "-1"))
            except (TypeError, ValueError) as error:
                raise ValueError("citation failure row source_count must be a non-negative integer") from error
            try:
                graph_hit_count = int(row.get("graph_hit_count", "-1"))
            except (TypeError, ValueError) as error:
                raise ValueError("citation failure row graph_hit_count must be a non-negative integer") from error
            if source_count < 0 or source_count != (len(sources) if isinstance(sources, list) else -1):
                raise ValueError("citation failure row source_count does not match CSV evidence array")
            if graph_hit_count < 0 or graph_hit_count != (len(graph_context) if isinstance(graph_context, list) else -1):
                raise ValueError("citation failure row graph_hit_count does not match CSV evidence array")
            rows.append(
                {
                    "row": row_number,
                    "question_index": question_index,
                    "question_id": question_id,
                    "mode": row.get("mode", ""),
                    "repetition_index": repetition_index,
                    "query_log_id": query_log_id,
                    "markers": invalid_tokens,
                    "source_count": source_count,
                    "graph_hit_count": graph_hit_count,
                }
            )
    return citation_failure_rows({"invalid_marker_rows": rows})


def markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_source_path(value: str, root: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def repository_relative_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as error:
        raise ValueError(f"evidence input must be inside repository root: {path}") from error


def source_fingerprints(
    audit: dict[str, Any], audit_path: Path, validation_path: Path, root: Path
) -> list[dict[str, str]]:
    input_paths = audit.get("inputs", {})
    named_paths = {
        "audit_json": audit_path,
        "validation_json": validation_path,
        "report_json": resolve_source_path(input_paths.get("report", ""), root),
        "raw_csv": resolve_source_path(input_paths.get("csv", ""), root),
        "run_config_json": resolve_source_path(input_paths.get("run_config", ""), root),
        "question_set_json": resolve_source_path(input_paths.get("questions", ""), root),
        "freeze_manifest_json": resolve_source_path(input_paths.get("freeze_manifest", ""), root),
        "experiment_contract_script": root / "scripts/rag_experiment_contract.py",
        "bundle_audit_script": root / "scripts/audit_rag_five_mode_bundle.py",
        "material_renderer_script": root / "scripts/render_rag_five_mode_paper_material.py",
        "validation_script": root / "scripts/validate_five_mode_experiment.py",
    }
    fingerprints = []
    for name, path in named_paths.items():
        if not path.is_file():
            raise ValueError(f"required evidence input is missing: {path}")
        fingerprints.append(
            {
                "name": name,
                "path": repository_relative_path(path, root),
                "sha256": sha256_file(path),
            }
        )
    return fingerprints


def git_snapshot(root: Path) -> dict[str, Any]:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"], cwd=root, check=True, capture_output=True, text=True
            ).stdout.strip()
        )
        return {"revision": revision, "dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"revision": None, "dirty": None}


def runtime_snapshot(root: Path) -> dict[str, Any]:
    version = subprocess.run(
        [str(root / "backend/.venv/bin/python"), "--version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return {"python": version, "platform": platform.platform()}


def protocol_snapshot(audit: dict[str, Any], root: Path) -> dict[str, Any]:
    input_paths = audit.get("inputs", {})
    config = json.loads(resolve_source_path(input_paths.get("run_config", ""), root).read_text(encoding="utf-8"))
    report = json.loads(resolve_source_path(input_paths.get("report", ""), root).read_text(encoding="utf-8"))
    snapshot = report.get("experiment_run", {}).get("config_snapshot_json", {})
    execution = config.get("execution", {})
    generation = config.get("generation", {})
    retrieval = config.get("retrieval", {})
    required = {
        "methods": [item.get("id") for item in config.get("methods", [])],
        "prompt_versions": {item.get("id"): item.get("prompt_version") for item in config.get("methods", [])},
        "repetitions": execution.get("repetitions"),
        "randomize_order": execution.get("randomize_order"),
        "random_seed": execution.get("random_seed"),
        "provider": generation.get("provider"),
        "model": generation.get("model"),
        "temperature": generation.get("temperature"),
        "max_tokens": generation.get("max_tokens"),
        "retrieval": retrieval,
        "app_revision": snapshot.get("app_revision"),
        "corpus_snapshot_hash": snapshot.get("corpus_snapshot_hash"),
        "execution_plan_hash": snapshot.get("experiment_protocol", {}).get("execution_plan_hash"),
    }
    missing = [key for key, value in required.items() if value in (None, "") or value == {}]
    if missing:
        raise ValueError(f"required protocol fields are missing: {', '.join(missing)}")
    return required


def render(
    audit: dict[str, Any],
    validation: dict[str, Any],
    audit_path: Path,
    validation_path: Path,
    root: Path = ROOT,
) -> str:
    if audit.get("schema_version") != "rag-internal-five-mode-bundle-audit-v1":
        raise ValueError("unsupported audit schema")
    summaries = audit.get("recomputed_mode_summary", [])
    comparisons = audit.get("recomputed_comparisons_vs_project_rag", {})
    if len(summaries) != 5 or len(comparisons) != 4:
        raise ValueError("audit must contain five mode summaries and four paired comparisons")
    if validation.get("overall_confidence") != "CAUTION":
        raise ValueError("validation must retain CAUTION confidence")
    if validation.get("fallacy_scan", {}).get("coverage") != "11/11":
        raise ValueError("validation must include the complete 11/11 fallacy scan")
    if not validation.get("warnings"):
        raise ValueError("validation warnings are required")

    row = audit["row_integrity"]
    retrieval_binding_gaps = row.get("retrieval_binding_gaps")
    if not isinstance(retrieval_binding_gaps, dict):
        raise ValueError("audit row_integrity must contain retrieval_binding_gaps")
    retrieval_gap_lines = []
    for mode in RETRIEVAL_GAP_MODES:
        gap = retrieval_binding_gaps.get(mode)
        if not isinstance(gap, dict):
            raise ValueError(f"retrieval gap summary missing mode: {mode}")
        required_fields = gap.get("required_fields")
        if not isinstance(required_fields, list) or not all(isinstance(field, str) for field in required_fields):
            raise ValueError(f"retrieval gap summary has invalid required_fields: {mode}")
        for field in ("row_count", "rows_with_complete_snapshot", "rows_with_any_gap"):
            if isinstance(gap.get(field), bool) or not isinstance(gap.get(field), int) or gap.get(field) < 0:
                raise ValueError(f"retrieval gap summary has invalid {field}: {mode}")
        missing_by_field = gap.get("missing_by_field")
        mismatch_by_field = gap.get("mismatch_by_field")
        if not isinstance(missing_by_field, dict) or not isinstance(mismatch_by_field, dict):
            raise ValueError(f"retrieval gap summary has invalid field counts: {mode}")
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for counts in (missing_by_field, mismatch_by_field)
            for value in counts.values()
        ):
            raise ValueError(f"retrieval gap summary has invalid field count values: {mode}")
        missing_summary, mismatch_summary = retrieval_field_gap_summary(gap, mode)
        retrieval_gap_lines.append(
            "| {mode} | {rows} | {required} | {complete_rate} | {gap_rate} | `{missing}` | `{mismatch}` |".format(
                mode=mode,
                rows=gap["row_count"],
                required="、".join(required_fields) if required_fields else "不适用",
                complete_rate=bounded_count_rate(
                    gap["rows_with_complete_snapshot"], gap["row_count"], mode
                ),
                gap_rate=bounded_count_rate(gap["rows_with_any_gap"], gap["row_count"], mode),
                missing=missing_summary,
                mismatch=mismatch_summary,
            )
        )
    citation = audit["citation_audit"]
    fingerprints = source_fingerprints(audit, audit_path, validation_path, root)
    protocol = protocol_snapshot(audit, root)
    git = git_snapshot(root)
    runtime = runtime_snapshot(root)
    audit_reference = repository_relative_path(audit_path, root)
    validation_reference = repository_relative_path(validation_path, root)
    failed_gate_rows = failure_gate_rows(audit)
    check_coverage = paper_material_check_coverage(audit)
    check_coverage_lines = "\n".join(
        f"| {item['label']} | {item['registered']} | {item['observed']} | {', '.join(item['missing']) or '—'} | {item['status']} |"
        for item in check_coverage
    )
    checks = {item["name"]: item["passed"] for item in audit["checks"]}
    retrieval_gap_summary_status = required_audit_check_status(
        checks, "retrieval_gap_summary_valid"
    )
    run_binding_gate_lines = "\n".join(
        f"| {label} | {required_audit_check_status(checks, name)} |"
        for label, name in RUN_BINDING_CHECK_LABELS
    )
    evidence_gate_lines = "\n".join(
        f"| {label} | {required_audit_check_status(checks, name)} |"
        for label, name in EVIDENCE_GATE_CHECK_LABELS
    )
    data_binding_gate_lines = "\n".join(
        f"| {label} | {required_audit_check_status(checks, name)} |"
        for label, name in DATA_BINDING_CHECK_LABELS
    )
    paper_gate = paper_gate_status(audit)
    paper_gate_audit = paper_gate_audit_row(audit)
    paper_blocker_archive = paper_blocker_archive_rows(audit)
    paper_claim_boundary = paper_claim_boundary_audit(
        audit, paper_gate, paper_blocker_archive
    )
    paper_claim_boundary_lines = "\n".join(
        f"| {item['label']} | {item['observed']} | {item['paper_treatment']} | {item['status']} |"
        for item in paper_claim_boundary
    )
    disclosure_lines = "\n".join(
        f"- `{item['name']}`：{item['archive_item']}；{item['requirement']}。"
        for item in paper_blocker_archive
        if item["status"] == "FAIL"
    )
    paper_blocker_archive_lines = "\n".join(
        f"| `{item['name']}` | {item['archive_item']} | {item['requirement']} | {item['status']} |"
        for item in paper_blocker_archive
    )
    failure_identity_rows = failure_identity_audit(audit, failed_gate_rows)
    failure_identity_lines = "\n".join(
        f"| {item['label']} | {item['registered']} | {item['observed']} | {item['missing']} | {item['status']} |"
        for item in failure_identity_rows
    )
    blockers = ", ".join(f"`{name}`" for name in audit["paper_blockers"])
    warning_lines = "\n".join(f"- {warning}" for warning in validation.get("warnings", []))
    clustered = validation["question_clustered_comparisons_vs_project_rag"]
    stability = validation["repeat_stability"]
    invalid_rows = citation_failure_rows(citation)
    input_paths = audit.get("inputs", {})
    raw_csv_path = resolve_source_path(input_paths.get("csv", ""), root)
    questions_path = resolve_source_path(input_paths.get("questions", ""), root)
    recomputed_invalid_rows = recompute_citation_failure_rows(raw_csv_path, questions_path)
    if recomputed_invalid_rows != invalid_rows:
        raise ValueError("raw CSV citation failure recomputation does not match audit")
    paper_disclosure_consistency = paper_disclosure_consistency_audit(
        audit, failed_gate_rows, paper_blocker_archive, paper_claim_boundary
    )
    paper_disclosure_consistency_lines = "\n".join(
        f"| {item['label']} | {item['registered']} | {item['observed']} | {item['status']} |"
        for item in paper_disclosure_consistency
    )
    citation_mismatch_rows = citation_summary_mismatch_rows(citation)
    citation_mismatch_lines = "\n".join(
        f"| `{markdown_cell(item['label'])}` | `{markdown_cell(item['recomputed'])}` | `{markdown_cell(item['reported'])}` |"
        for item in citation_mismatch_rows
    )
    citation_mismatch_status = (
        "报告值与原始 CSV 重算值不一致"
        if citation_mismatch_rows
        else "报告值与原始 CSV 重算值一致"
    )
    failure_lines = "\n".join(
        f"| {item['row']} | {item['question_index']} | {item['question_id']} | {item['mode']} | {item['repetition_index']} | {item['query_log_id']} | {', '.join(item['markers'])} | {item['source_count']} | {item['graph_hit_count']} |"
        for item in invalid_rows
    )
    mode_lines = []
    for item in summaries:
        mode_lines.append(
            "| {mode} | {completed}/{failed} | {micro} | {macro} | {exact} | {precision} | {f1} | {mean} | {p95} | {tokens} |".format(
                mode=item["mode"],
                completed=item["completed"],
                failed=item["failed"],
                micro=percent(item["micro_fact_coverage"]),
                macro=percent(item["macro_fact_coverage"]),
                exact=percent(item["closed_set_exact_case_accuracy"]),
                precision=percent(item["closed_set_fact_precision"]),
                f1=percent(item["closed_set_fact_f1"]),
                mean=f"{item['mean_response_ms']:.2f}",
                p95=item["p95_response_ms"],
                tokens=item["total_tokens"],
            )
        )
    comparison_lines = []
    for mode, item in comparisons.items():
        comparison_lines.append(
            "| {mode} | {delta} | {improved}/{tied}/{worse} | {sign_p} | {exact} / {project_exact} | {mcnemar} | {latency} |".format(
                mode=mode,
                delta=number(item["mean_fact_coverage_delta"]),
                improved=item["improved_cases"],
                tied=item["tied_cases"],
                worse=item["worse_cases"],
                sign_p=number(item["coverage_sign_test_two_sided_p"]),
                exact=item["comparison_exact_only_cases"],
                project_exact=item["project_exact_only_cases"],
                mcnemar=number(item["mcnemar_exact_two_sided_p"]),
                latency=f"{item['mean_response_time_delta_ms']:.2f}",
            )
        )
    citation_mode_lines = "\n".join(
        f"| {mode} | {item['completed']} | {citation_count_rate(item['with_source_marker'], item['completed'])} | {citation_count_rate(item['with_any_evidence_marker'], item['completed'])} | {citation_count_rate(item['with_graph_marker'], item['completed'])} | {citation_count_rate(item['invalid_marker_rows'], item['completed'])} |"
        for mode, item in citation["by_mode"].items()
    )

    return f"""# 实验 5 内部五方法描述性结果材料 v1

## 使用边界

状态：**内部开发证据，不是确认性结果**；`paper_ready={str(audit.get('paper_ready')).lower()}`。本材料由审计产物自动取数，供论文方法、限制和探索性结果部分引用；不得将自动 alias-based fact coverage 写成事实准确率，也不得把重复生成的配对 p 值写成确认性推断。

本材料生成时间以审计产物的 `generated_at_utc` 为准：`{audit.get('generated_at_utc')}`。审计产物：`{audit_reference}`；统计验证记录：`{validation_reference}`。

## 输入材料指纹

下列材料绑定到本描述性结果；SHA-256 用于复核生成材料引用的具体文件版本。

| 材料 | 路径 | SHA-256 |
| --- | --- | --- |
{chr(10).join(f"| {item['name']} | `{item['path']}` | `{item['sha256']}` |" for item in fingerprints)}

## 运行版本与参数快照

以下字段来自绑定的运行配置和实验报告，不根据当前代码推断历史运行状态。

- 方法：`{', '.join(protocol['methods'])}`；每方法重复：`{protocol['repetitions']}`；随机化顺序：`{protocol['randomize_order']}`；随机种子：`{protocol['random_seed']}`。
- 生成：provider=`{protocol['provider']}`，model=`{protocol['model']}`，temperature=`{protocol['temperature']}`，max_tokens=`{protocol['max_tokens']}`。
- 检索参数：`{json.dumps(protocol['retrieval'], ensure_ascii=False, sort_keys=True)}`。
- Prompt 版本：`{json.dumps(protocol['prompt_versions'], ensure_ascii=False, sort_keys=True)}`。
- 语料快照哈希：`{protocol['corpus_snapshot_hash']}`；执行计划哈希：`{protocol['execution_plan_hash']}`。
- 应用 revision：`{protocol['app_revision']}`；当前分析 Git revision：`{git['revision']}`；当前工作树 dirty：`{git['dirty']}`；当前分析 Python：`{runtime['python']}`；平台：`{runtime['platform']}`。

`app_revision=unversioned` 且当前工作树 dirty，因此这些参数记录只能说明内部批次的配置快照，不能构成确认性版本归档。

## 实验设计与运行配置绑定门禁

下表直接呈现审计器对题集、方法、重复、生成条件和检索条件的绑定检查；PASS 只表示记录值与冻结配置一致，不表示输入本身已经达到确认性实验标准。

| 检查 | 结果 |
| --- | --- |
{run_binding_gate_lines}

## 研究范围与分母

- 单一公开 GEO 项目、12 个问题、5 种方法、3 次重复，共 180 个计划案例。
- 原始 CSV 行数：`{row['actual_rows']}`；完成：`{row['completed_rows']}`；失败：`{row['failed_rows']}`；唯一案例键：`{row['unique_case_keys']}`；唯一正 `query_log_id`：`{row['unique_positive_query_log_ids']}`。
- 来源 JSON 与图谱 JSON 可解析且数量一致的行数：`{row['source_json_valid_rows']}/{row['actual_rows']}`、`{row['graph_json_valid_rows']}/{row['actual_rows']}`。
- `fact coverage` 是预定义答案要点/别名的字符串匹配；`closed-set exact` 要求全部预定义事实命中且没有预定义禁止事实。两者均不证明事实正确性、关系方向、推理质量或引用有效性。

## 可重算的模式汇总

下表全部来自原始 CSV 逐案例重算，并已与内部报告逐字段核对。`completed/failed` 是案例数；`micro/macro` 是事实覆盖率；`exact` 是 closed-set exact case accuracy；时延单位为 ms。

| 方法 | 完成/失败 | Micro | Macro | Exact | Precision | F1 | Mean ms | P95 ms | Total tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(mode_lines)}

## 相对 `project_rag` 的配对描述

`delta` 为每个配对案例的 fact coverage 差值均值；`improved/tied/worse` 为 36 个配对案例计数；`sign p` 和 McNemar p 仅作方法学描述，不能作为确认性推断。

| 方法 | Mean delta | Improved/Tied/Worse | Sign p | 本方法 exact-only / project exact-only | McNemar p | Mean latency delta ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(comparison_lines)}

## 证据链门禁

| 检查 | 结果 |
| --- | --- |
{evidence_gate_lines}
| Retrieval 缺口摘要结构一致 | {retrieval_gap_summary_status} |
| 论文门禁逻辑一致 | {paper_gate_consistency_status(audit)} |
| 论文可用门禁 | {paper_gate} |

## 论文门禁推导审计

下表保留最终门禁一致性检查本身的严重级别、通过状态、实际值和期望值；它与下方“门禁失败摘要”互补，因为通过项不会出现在失败摘要中。

| 检查名 | 严重级别 | 结果 | actual JSON | expected JSON |
| --- | --- | --- | --- | --- |
| `{paper_gate_audit['name']}` | `{paper_gate_audit['severity']}` | {paper_gate_audit['passed']} | `{markdown_cell(paper_gate_audit['actual'])}` | `{markdown_cell(paper_gate_audit['expected'])}` |

## 论文门禁固定集合覆盖

下表核对论文正文使用的固定检查集合是否全部存在于审计 JSON；“观察到”只表示检查项存在，不代表该检查通过或输入达到确认性标准。

| 论文表 | 注册检查数 | 观察到检查数 | 缺失检查 | 覆盖状态 |
| --- | ---: | ---: | --- | --- |
{check_coverage_lines}

## 论文 blocker—最低归档清单映射

下表要求每个注册为 `paper_blocker` 的检查都对应一个明确的归档要求；状态只反映该检查是否通过。当前失败的 5 个论文 blocker 分别落到第 1、2、4、6、8 项，范围声明检查单独保留，不将其误算为缺失的最低清单项。

| 检查名 | 对应归档项 | 归档要求 | 状态 |
| --- | --- | --- | --- |
{paper_blocker_archive_lines}

## 论文主张边界审计

下表把证据等级、最终论文门禁和必须披露的归档缺口绑定到同一审计产物；FAIL 表示当前不能作确认性效果主张，不是方法失败率。

| 边界项目 | 观察值 | 论文处理 | 状态 |
| --- | --- | --- | --- |
{paper_claim_boundary_lines}

本批次必须同步披露的未完成归档项：

{disclosure_lines}

## 论文阻塞披露闭环

下表交叉核对失败摘要、`paper_blockers`、归档映射和主张边界中的待披露数量；通过只表示身份和分母一致，不表示任何方法效果。

| 闭环项目 | 注册值 | 观察值 | 状态 |
| --- | --- | --- | --- |
{paper_disclosure_consistency_lines}

## 失败检查身份闭环

下表从 `checks` 重新计算失败检查身份，并与审计 JSON 的 `failure_summary`、正文失败摘要和 `paper_blockers` 交叉核对；失败摘要中的每个检查名必须唯一且完整覆盖。

| 闭环项目 | 注册数量 | 观察数量 | 缺失检查 | 状态 |
| --- | ---: | ---: | --- | --- |
{failure_identity_lines}

## 门禁失败摘要

以下表格保留审计器对每个未通过检查记录的严重级别、实际值和期望值；“摘要”列用于论文阅读，完整 JSON 列用于机器复核。两层都保留 `null`、布尔值、数组和对象的类型信息，不把嵌套审计结果转写成含糊的自然语言。该摘要解释当前材料为何不能升级为确认性结果，不改变审计器的通过判定。

| 检查名 | 严重级别 | 实际值摘要 | 期望值摘要 | 完整 actual JSON | 完整 expected JSON |
| --- | --- | --- | --- | --- | --- |
{chr(10).join(f"| `{markdown_cell(item['name'])}` | `{markdown_cell(item['severity'])}` | `{markdown_cell(item['actual_summary'])}` | `{markdown_cell(item['expected_summary'])}` | `{markdown_cell(item['actual'])}` | `{markdown_cell(item['expected'])}` |" for item in failed_gate_rows) or '| （无） | — | — | — | — | — |'}

## 引用审计报告—重算差异

状态：**{citation_mismatch_status}**。下表直接呈现报告中的引用摘要与审计器从原始 CSV 重算值之间的差异；它是报告完整性和失败定位证据，不是引用内容正确性或方法效果证据。

| 层级/字段 | 原始 CSV 重算值 | 报告值 |
| --- | --- | --- |
{citation_mismatch_lines or '| （无差异） | — | — |'}

## 数据—问题集绑定门禁

以下检查把每条 CSV 记录绑定到冻结题目范围、预注册重复范围和五方法集合；异常行应失败关闭，而不是被解析器异常掩盖。

| 检查 | 结果 |
| --- | --- |
{data_binding_gate_lines}

## Retrieval snapshot 缺口（按方法、按字段、按行数）

该摘要按方法区分适用字段，不把纯 LLM 行与检索方法混在一个总数中；`missing_by_field` 统计字段为空的行数，`mismatch_by_field` 统计字段非空但与汇总配置快照不一致的行数。汇总级配置不能替代逐案例快照，因此这些计数直接来自 CSV 行审计。

| 方法 | 适用行数 | 必需字段 | 完整快照行 n/% | 有任一缺口行 n/% | 缺失字段 n/% | 非空漂移 n/% |
| --- | ---: | --- | ---: | ---: | --- | --- |
{chr(10).join(retrieval_gap_lines)}

严格语法下，含数字来源标记的答案比例为 `{citation['strict_source_marker_answer_rate']:.4f}`，含任一数字证据标记的答案比例为 `{citation['strict_evidence_marker_answer_rate']:.4f}`；发现 `{len(citation['invalid_marker_rows'])}` 个非法范围标记：`{', '.join(marker['markers'][0] for marker in citation['invalid_marker_rows'])}`。当前论文门禁阻塞项为：{blockers}。

## 可引用失败案例

下表来自原始 CSV 的严格引用语法审计；范围写法（如 `[S1-S12]`）不会被当作合法的单一数字标记。`query_log_id` 用于回放对应回答、来源和图谱证据。

| CSV 行 | 题目索引 | 题目 | 方法 | 重复 | query_log_id | 非法标记 | source_count | graph_hit_count |
| ---: | ---: | --- | --- | ---: | ---: | --- | ---: | ---: |
{failure_lines}

## 按方法分层的严格引用审计

以下比例以已完成答案数为分母；仅计入符合 `[S数字]`/`[G数字]` 语法的标记，非法范围标记不计入覆盖。

| 方法 | 完成答案 | 有来源标记 n/% | 有任一证据标记 n/% | 有图谱标记 n/% | 非法标记行 n/% |
| --- | ---: | ---: | ---: | ---: | ---: |
{citation_mode_lines}

## 按题目聚类的描述性不确定性

下表以题目为分析单位，先对每题的 3 次重复取均值，再报告 post-run bootstrap 95% 区间。区间未作多重比较校正，且属于运行后的方法学验证；不能把表中的区间或 p 值解释为确认性推断。

| 方法 | 题目数 | Mean delta | Median delta | Bootstrap 95% CI | 改善/持平/变差 | 多重校正 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
{chr(10).join(
    f"| {mode} | {item['question_count']} | {item['mean_fact_coverage_delta']:.4f} | {item['median_fact_coverage_delta']:.4f} | {interval(item['bootstrap_95_ci'])} | {item['improved_questions']}/{item['tied_questions']}/{item['worse_questions']} | {'是' if item['multiple_comparison_adjusted'] else '否'} |"
    for mode, item in clustered.items()
)}

## 重复稳定性

重复稳定性按题目汇总；`stable_question_rate` 表示 3 次重复中结果保持稳定的题目比例，`mean_within_question_sd` 是题目内覆盖率标准差均值。

| 方法 | 稳定题目/总题目 | 稳定率 | 平均题目内 SD |
| --- | ---: | ---: | ---: |
{chr(10).join(
    f"| {mode} | {item['stable_question_count']}/{item['question_count']} | {percent(item['stable_question_rate'])} | {item['mean_within_question_sd']:.4f} |"
    for mode, item in stability.items()
)}

## 统计解释与限制

统计验证记录的总体置信级别为 **{validation['overall_confidence']}**，11 类统计谬误扫描覆盖 **{validation['fallacy_scan']['coverage']}**；验证记录明确列出以下警告：

{warning_lines}

因此，允许的论文表述是：

> 在单一公开 GEO 项目的内部开发题集上，五方法批次的自动 alias-based fact coverage 与 closed-set 指标呈现方法间差异；其中图谱/结构化方法在该题集上的描述性覆盖率较高。该结果仅用于内部方法学诊断，因为题集未跨项目冻结、人工独立评价缺失、运行版本未绑定，且严格引用审计和输入冻结清单复核未通过。

禁止的表述包括：“事实准确率已被证明”“引用有效率为确认性结果”“图谱增强 RAG 普遍优于基线”以及“结果可推广至其他项目”。

## 复现入口

```bash
backend/.venv/bin/python scripts/audit_rag_five_mode_bundle.py
backend/.venv/bin/python scripts/render_rag_five_mode_paper_material.py
```

只有当审计产物的 `paper_ready=true`、严格引用审计通过、输入冻结清单可复核、版本与参数绑定、外部多项目题集和独立双人盲评齐备时，才可将本材料中的数字升级为确认性论文结果。
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--validation", type=Path, default=DEFAULT_VALIDATION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    material = render(load_json(args.audit), load_json(args.validation), args.audit, args.validation, ROOT)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(material, encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
