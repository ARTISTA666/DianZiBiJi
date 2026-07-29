#!/usr/bin/env python3
"""Fail-fast maturity gate for the full-system release candidate."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from freeze_system_evidence import GIT_COMMIT, verify_manifest as verify_system_evidence_manifest


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RETRIEVAL_REPORT = ROOT / "data" / "real" / "GSE111619" / "main-retrieval-evaluation" / "report.json"
DEFAULT_EXPERIMENT_REPORT = ROOT / "data" / "real" / "GSE111619" / "main_v8_kg_holdout_experiment_report.json"
DEFAULT_AGENT_REPORT = ROOT / "data" / "real" / "GSE111619" / "main_v8_agent_probe_report.json"
DEFAULT_SYSTEM_EVIDENCE_REPORT = ROOT / "docs" / "system-evidence" / "validation-results.json"
DEFAULT_EVIDENCE_MANIFEST = ROOT / "output" / "release-evidence" / "maturity-evidence-manifest.json"
DEFAULT_OUTPUT = ROOT / "docs" / "experiments" / "maturity-gate-latest.json"
DEFAULT_MARKDOWN = ROOT / "docs" / "experiments" / "maturity-gate-latest.md"

THRESHOLDS = {
    "retrieval_question_count_min": 20,
    "retrieval_fact_count_min": 50,
    "retrieval_chunk_count_min": 500,
    "retrieval_graph_recall10_min": 0.90,
    "retrieval_graph_ndcg10_min": 0.60,
    "retrieval_graph_recall10_delta_min": 0.10,
    "experiment_case_count_min": 12,
    "experiment_kg_micro_fact_coverage_min": 0.85,
    "experiment_kg_exact_accuracy_min": 0.60,
    "experiment_forbidden_fact_hits_max": 0,
    "citation_source_marker_rate_min": 0.95,
    "citation_graph_marker_rate_min": 0.95,
    "agent_completed_runs_min": 4,
    "agent_failed_runs_max": 0,
    "agent_invalid_citations_max": 0,
    "agent_needs_review_max": 0,
    "playwright_expected_min": 4,
    "knowledge_graph_audit_f1_min": 0.80,
    "load_smoke_successful_min": 60,
    "load_smoke_p95_ms_max": 2000,
    "soak_smoke_cycles_min": 2,
    "soak_smoke_p95_ms_max": 2000,
    "runtime_metrics_total_requests_min": 1,
    "runtime_metrics_p95_ms_max": 2000,
    "restore_drill_public_table_count_min": 1,
    "system_evidence_max_age_hours": 168,
}
REQUIRED_AGENT_TASK_TYPES = {"experiment_summary", "weekly_report", "stage_report", "graph_overview"}
REQUIRED_EXPERIMENT_METHODS = {"pure_llm", "bm25_rag", "project_rag", "structured_query", "kg_enhanced_rag"}
REQUIRED_PLAYWRIGHT_FLOWS = {
    "登录并完成笔记审批",
    "图片 OCR、人工校对、入库、问答和五方法实验形成闭环",
    "独立评价人只能在盲评页面提交评价",
    "系统管理员完成账号、小组和审计闭环",
}


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    return value


def row_by_mode(rows: list[dict[str, Any]], mode: str) -> dict[str, Any]:
    for row in rows:
        if row.get("mode") == mode:
            return row
    raise ValueError(f"Missing mode: {mode}")


def check(name: str, actual: Any, op: str, expected: Any) -> dict[str, Any]:
    if op == ">=":
        passed = actual >= expected
    elif op == "<=":
        passed = actual <= expected
    elif op == "==":
        passed = actual == expected
    else:
        raise ValueError(f"Unsupported operator: {op}")
    return {"name": name, "actual": actual, "operator": op, "expected": expected, "passed": passed}


def evidence_age_hours(value: Any, now: datetime | None = None) -> float:
    if not isinstance(value, str) or not value.strip():
        return 1_000_000_000.0
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return 1_000_000_000.0
    if parsed.tzinfo is None:
        return 1_000_000_000.0
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    age_seconds = (reference.astimezone(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds()
    if age_seconds < 0:
        return 1_000_000_000.0
    return age_seconds / 3600


def safe_checks(name: str, fn, report: dict[str, Any] | None) -> list[dict[str, Any]]:
    try:
        return fn(report)
    except Exception as exc:
        return [
            {
                "name": f"{name} evidence structure",
                "actual": str(exc),
                "operator": "valid",
                "expected": "machine-readable gate input",
                "passed": False,
            }
        ]


def retrieval_checks(report: dict[str, Any] | None) -> list[dict[str, Any]]:
    if report is None:
        return [
            {
                "name": "retrieval report",
                "actual": "missing",
                "operator": "present",
                "expected": "retrieval evaluation report",
                "passed": False,
            }
        ]
    aggregate = report.get("aggregate")
    corpus = report.get("corpus") or {}
    if not isinstance(aggregate, list):
        raise ValueError("retrieval report has no aggregate rows")
    graph = row_by_mode(aggregate, "graph_enhanced_rag")
    hybrid = row_by_mode(aggregate, "hybrid_rag")
    return [
        check("retrieval question count", report.get("question_count", 0), ">=", THRESHOLDS["retrieval_question_count_min"]),
        check("retrieval gold fact count", report.get("fact_count", 0), ">=", THRESHOLDS["retrieval_fact_count_min"]),
        check("retrieval corpus chunk count", corpus.get("chunk_count", 0), ">=", THRESHOLDS["retrieval_chunk_count_min"]),
        check("graph Recall@10", graph.get("Recall@10", 0), ">=", THRESHOLDS["retrieval_graph_recall10_min"]),
        check("graph nDCG@10", graph.get("nDCG@10", 0), ">=", THRESHOLDS["retrieval_graph_ndcg10_min"]),
        check(
            "graph Recall@10 delta over hybrid",
            round(graph.get("Recall@10", 0) - hybrid.get("Recall@10", 0), 6),
            ">=",
            THRESHOLDS["retrieval_graph_recall10_delta_min"],
        ),
    ]


def experiment_checks(report: dict[str, Any] | None) -> list[dict[str, Any]]:
    if report is None:
        return [
            {
                "name": "experiment report",
                "actual": "missing",
                "operator": "present",
                "expected": "RAG experiment report",
                "passed": False,
            }
        ]
    evaluation = report.get("objective_evaluation") or {}
    summaries = evaluation.get("mode_summary")
    if not isinstance(summaries, list):
        raise ValueError("experiment report has no mode_summary rows")
    summary_by_mode = {row.get("mode"): row for row in summaries}
    reported_methods = set(report.get("methods") or evaluation.get("methods") or summary_by_mode)
    missing_methods = sorted(REQUIRED_EXPERIMENT_METHODS - reported_methods)
    incomplete_methods = sorted(
        mode
        for mode in REQUIRED_EXPERIMENT_METHODS
        if (summary_by_mode.get(mode) or {}).get("completed", 0) < THRESHOLDS["experiment_case_count_min"]
    )
    failed_methods = sorted(
        mode
        for mode in REQUIRED_EXPERIMENT_METHODS
        if (summary_by_mode.get(mode) or {}).get("failed", 0) != 0
    )
    kg = row_by_mode(summaries, "kg_enhanced_rag")
    citation = evaluation.get("citation_marker_audit") or {}
    kg_citation = (citation.get("by_mode") or {}).get("kg_enhanced_rag") or {}
    kg_source_marker_rate = kg_citation.get("source_marker_answer_rate", citation.get("source_marker_answer_rate", 0))
    kg_graph_marker_rate = kg_citation.get(
        "graph_marker_answer_rate",
        citation.get("kg_graph_marker_rate_when_context_available", 0),
    )
    return [
        check("experiment required method coverage", missing_methods, "==", []),
        check("experiment required methods completed cases", incomplete_methods, "==", []),
        check("experiment required methods failed cases", failed_methods, "==", []),
        check("experiment completed kg cases", kg.get("completed", 0), ">=", THRESHOLDS["experiment_case_count_min"]),
        check("experiment failed kg cases", kg.get("failed", 0), "==", 0),
        check("kg micro fact coverage", kg.get("micro_fact_coverage", 0), ">=", THRESHOLDS["experiment_kg_micro_fact_coverage_min"]),
        check("kg exact case accuracy", kg.get("closed_set_exact_case_accuracy", 0), ">=", THRESHOLDS["experiment_kg_exact_accuracy_min"]),
        check("kg forbidden fact hits", kg.get("forbidden_fact_hits", 0), "<=", THRESHOLDS["experiment_forbidden_fact_hits_max"]),
        check("citation indices in range", citation.get("all_citation_indices_in_range", False), "==", True),
        check("kg source marker rate", kg_source_marker_rate, ">=", THRESHOLDS["citation_source_marker_rate_min"]),
        check("kg graph marker rate", kg_graph_marker_rate, ">=", THRESHOLDS["citation_graph_marker_rate_min"]),
    ]


def agent_checks(report: dict[str, Any] | None) -> list[dict[str, Any]]:
    if report is None:
        return [
            {
                "name": "agent live maturity evidence",
                "actual": "missing",
                "operator": "present",
                "expected": "agent probe report",
                "passed": False,
            }
        ]
    task_types = set(report.get("task_types") or [])
    return [
        check("agent completed runs", report.get("completed_runs", 0), ">=", THRESHOLDS["agent_completed_runs_min"]),
        check("agent failed runs", report.get("failed_runs", 0), "<=", THRESHOLDS["agent_failed_runs_max"]),
        check("agent needs_review runs", report.get("needs_review_runs", 0), "<=", THRESHOLDS["agent_needs_review_max"]),
        check("agent invalid citations", report.get("invalid_citations", 0), "<=", THRESHOLDS["agent_invalid_citations_max"]),
        check("agent required task coverage", REQUIRED_AGENT_TASK_TYPES.issubset(task_types), "==", True),
    ]


def system_evidence_checks(report: dict[str, Any] | None) -> list[dict[str, Any]]:
    if report is None:
        return [
            {
                "name": "system evidence report",
                "actual": "missing",
                "operator": "present",
                "expected": "validation-results.json",
                "passed": False,
            }
        ]
    playwright = report.get("playwright") or {}
    playwright_stats = playwright.get("stats") or {}
    playwright_tests = playwright.get("tests") or []
    playwright_titles = [str(item.get("title") or "") for item in playwright_tests]
    missing_playwright_flows = sorted(REQUIRED_PLAYWRIGHT_FLOWS - set(playwright_titles))
    playwright_expected = playwright_stats.get("expected", 0)
    production_config = report.get("production_config") or {}
    metrics = ((report.get("runtime") or {}).get("metrics") or {})
    metrics_payload = metrics.get("payload") or {}
    restart_recovery = report.get("restart_recovery") or {}
    return [
        check(
            "system evidence freshness hours",
            evidence_age_hours(report.get("generated_at")),
            "<=",
            THRESHOLDS["system_evidence_max_age_hours"],
        ),
        check(
            "runtime evidence freshness hours",
            evidence_age_hours((report.get("runtime") or {}).get("captured_at")),
            "<=",
            THRESHOLDS["system_evidence_max_age_hours"],
        ),
        check(
            "playwright evidence freshness hours",
            evidence_age_hours(playwright.get("captured_at")),
            "<=",
            THRESHOLDS["system_evidence_max_age_hours"],
        ),
        check("runtime checks", bool((report.get("runtime") or {}).get("ok")), "==", True),
        check("runtime metrics endpoint", bool(metrics.get("ok")), "==", True),
        check(
            "runtime metrics total requests",
            metrics_payload.get("total_requests", 0),
            ">=",
            THRESHOLDS["runtime_metrics_total_requests_min"],
        ),
        check(
            "runtime metrics p95 latency ms",
            metrics_payload.get("p95_duration_ms", 0),
            "<=",
            THRESHOLDS["runtime_metrics_p95_ms_max"],
        ),
        check("load smoke ok", bool((report.get("load_smoke") or {}).get("ok")), "==", True),
        check(
            "load smoke successful requests",
            (report.get("load_smoke") or {}).get("successful", 0),
            ">=",
            THRESHOLDS["load_smoke_successful_min"],
        ),
        check(
            "load smoke p95 latency ms",
            (report.get("load_smoke") or {}).get("p95_ms", 0),
            "<=",
            THRESHOLDS["load_smoke_p95_ms_max"],
        ),
        check("experiment restart recovery", bool(restart_recovery.get("ok")), "==", True),
        check("experiment interruption observed", restart_recovery.get("interrupted"), "==", True),
        check("experiment resume completed", restart_recovery.get("resumed_status"), "==", "completed"),
        check("short soak smoke ok", bool((report.get("soak_smoke") or {}).get("ok")), "==", True),
        check(
            "short soak smoke cycles",
            ((report.get("soak_smoke") or {}).get("summary") or {}).get("cycles", 0),
            ">=",
            THRESHOLDS["soak_smoke_cycles_min"],
        ),
        check(
            "short soak smoke p95 latency ms",
            ((report.get("soak_smoke") or {}).get("summary") or {}).get("p95_ms", 0),
            "<=",
            THRESHOLDS["soak_smoke_p95_ms_max"],
        ),
        check("npm production audit vulnerabilities", ((report.get("npm_audit") or {}).get("vulnerabilities") or {}).get("total", 1), "==", 0),
        check("production config preflight", production_config.get("status"), "==", "passed"),
        check("secret hygiene", bool((report.get("secret_hygiene") or {}).get("ok")), "==", True),
        check("secret rotation runbook", bool((report.get("secret_rotation") or {}).get("ok")), "==", True),
        check("backup policy runbook", bool((report.get("backup_policy") or {}).get("ok")), "==", True),
        check("monitoring alerts", bool((report.get("monitoring_alerts") or {}).get("ok")), "==", True),
        check("reverse proxy TLS template", bool((report.get("reverse_proxy") or {}).get("ok")), "==", True),
        check("playwright expected tests", playwright_expected, ">=", THRESHOLDS["playwright_expected_min"]),
        check("playwright critical flow coverage", missing_playwright_flows, "==", []),
        check("playwright unexpected tests", playwright_stats.get("unexpected", 0), "==", 0),
        check("playwright skipped tests", playwright_stats.get("skipped", 0), "==", 0),
        check("playwright result count", len(playwright_tests), "==", playwright_expected),
        check("playwright unique test titles", len(set(playwright_titles)), "==", len(playwright_titles)),
        check(
            "playwright all test results passed",
            bool(playwright_tests) and all(item.get("status") == "passed" for item in playwright_tests),
            "==",
            True,
        ),
        check("backup smoke verified", bool((report.get("backup") or {}).get("ok")), "==", True),
        check("backup dump readable", (report.get("backup") or {}).get("dump_readable"), "==", True),
        check("restore drill verified", bool((report.get("restore_drill") or {}).get("ok")), "==", True),
        check(
            "restore drill public tables",
            ((report.get("restore_drill") or {}).get("database") or {}).get("public_table_count", 0),
            ">=",
            THRESHOLDS["restore_drill_public_table_count_min"],
        ),
        check("restore drill storage restored", bool(((report.get("restore_drill") or {}).get("storage") or {}).get("restored")), "==", True),
        check(
            "knowledge graph audit F1",
            round((report.get("knowledge_graph") or {}).get("f1", 0), 4),
            ">=",
            THRESHOLDS["knowledge_graph_audit_f1_min"],
        ),
    ]


def manifest_paths(path: Path) -> set[str]:
    manifest = load_json(path) or {}
    return {str(item.get("path") or "") for item in manifest.get("files", []) if isinstance(item, dict)}


def evaluate_evidence_manifest(
    manifest_path: Path | None,
    required_files: list[Path],
) -> tuple[list[dict[str, Any]], str | None]:
    if manifest_path is None:
        return (
            [
                {
                    "name": "maturity evidence manifest",
                    "actual": "not supplied",
                    "operator": "present",
                    "expected": "verified system evidence manifest",
                    "passed": False,
                }
            ],
            None,
        )
    if not manifest_path.is_file():
        return (
            [
                {
                    "name": "maturity evidence manifest",
                    "actual": "missing",
                    "operator": "present",
                    "expected": str(manifest_path),
                    "passed": False,
                }
            ],
            None,
        )
    verification = verify_system_evidence_manifest(manifest_path, ROOT)
    root = ROOT.resolve()
    required_paths = {
        path.resolve().relative_to(root).as_posix()
        if path.resolve().is_relative_to(root)
        else str(path.resolve())
        for path in required_files
    }
    present_paths = manifest_paths(manifest_path)
    missing_paths = sorted(required_paths - present_paths)
    provenance = verification.get("provenance") if isinstance(verification.get("provenance"), dict) else {}
    checks = [
        check("maturity evidence manifest verified", verification["ok"], "==", True),
        check("maturity evidence manifest matches current checkout", provenance.get("ok", False), "==", True),
        check("maturity evidence manifest file count", verification["file_count"], ">=", 10),
        check("maturity evidence manifest covers gate inputs", missing_paths, "==", []),
    ]
    source_revision = provenance.get("expected_git_commit")
    if (
        not all(item["passed"] for item in checks)
        or not isinstance(source_revision, str)
        or not GIT_COMMIT.fullmatch(source_revision)
    ):
        source_revision = None
    return checks, source_revision


def evidence_manifest_checks(manifest_path: Path | None, required_files: list[Path]) -> list[dict[str, Any]]:
    checks, _source_revision = evaluate_evidence_manifest(manifest_path, required_files)
    return checks


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    retrieval = load_json(args.retrieval_report)
    experiment = load_json(args.experiment_report)
    agent_path = args.agent_report or DEFAULT_AGENT_REPORT
    system_evidence_path = args.system_evidence_report or DEFAULT_SYSTEM_EVIDENCE_REPORT
    evidence_manifest_path = getattr(args, "evidence_manifest", None)
    agent = load_json(agent_path) if agent_path.is_file() else None
    system_evidence = load_json(system_evidence_path) if system_evidence_path.is_file() else None
    groups = {
        "retrieval": safe_checks("retrieval", retrieval_checks, retrieval),
        "rag_experiment": safe_checks("RAG experiment", experiment_checks, experiment),
        "agent": safe_checks("agent", agent_checks, agent),
        "system": safe_checks("system", system_evidence_checks, system_evidence),
    }
    manifest_checks, source_revision = evaluate_evidence_manifest(
        evidence_manifest_path,
        [args.retrieval_report, args.experiment_report, agent_path, system_evidence_path],
    )
    if manifest_checks:
        groups["evidence_manifest"] = manifest_checks
    failures = [
        {"group": group, **item}
        for group, items in groups.items()
        for item in items
        if not item["passed"]
    ]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "full-system release-candidate maturity gate",
        "evidence_level": "internal automated gate; not independent human review",
        "source_revision": source_revision,
        "thresholds": THRESHOLDS,
        "inputs": {
            "retrieval_report": str(args.retrieval_report),
            "experiment_report": str(args.experiment_report),
            "agent_report": str(agent_path) if agent_path.is_file() else None,
            "system_evidence_report": str(system_evidence_path) if system_evidence_path.is_file() else None,
            "evidence_manifest": str(evidence_manifest_path) if evidence_manifest_path else None,
        },
        "groups": groups,
        "passed": not failures,
        "failures": failures,
        "next_blocker": failures[0]["name"] if failures else None,
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Full-System Maturity Gate",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Result: **{'PASS' if report['passed'] else 'FAIL'}**",
        f"- Evidence level: {report['evidence_level']}",
        "",
        "## Checks",
        "",
        "| Group | Check | Actual | Target | Result |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for group, items in report["groups"].items():
        for item in items:
            target = f"{item['operator']} {item['expected']}"
            result = "PASS" if item["passed"] else "FAIL"
            lines.append(f"| {group} | {item['name']} | {item['actual']} | {target} | {result} |")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "This gate is deliberately stricter than the current development evidence. A failure means the project is not ready for human review or release-candidate freeze.",
            "It does not replace independent frozen corpora, external reviewers, long soak tests, backup drills, or security review.",
            "",
        ]
    )
    if report["failures"]:
        lines.extend(["## First Failures", ""])
        for failure in report["failures"][:10]:
            lines.append(
                f"- {failure['group']}: {failure['name']} is {failure['actual']} "
                f"(target {failure['operator']} {failure['expected']})."
            )
        lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retrieval-report", type=Path, default=DEFAULT_RETRIEVAL_REPORT)
    parser.add_argument("--experiment-report", type=Path, default=DEFAULT_EXPERIMENT_REPORT)
    parser.add_argument("--agent-report", type=Path, help=f"Defaults to {DEFAULT_AGENT_REPORT} when present")
    parser.add_argument(
        "--system-evidence-report",
        type=Path,
        help=f"Defaults to {DEFAULT_SYSTEM_EVIDENCE_REPORT} when present",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--evidence-manifest", type=Path, default=DEFAULT_EVIDENCE_MANIFEST)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.markdown.write_text(markdown(report), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "failures": len(report["failures"]), "output": str(args.output)}, ensure_ascii=False))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
