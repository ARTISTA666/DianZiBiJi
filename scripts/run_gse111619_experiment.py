#!/usr/bin/env python3
"""Run and objectively summarize the GSE111619 paired RAG experiment."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import itertools
import json
import math
import os
import re
import statistics
import time
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from import_gse111619_via_api import ApiClient, BENCHMARK_PROJECT_NAME, PROJECT_NAME


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "real" / "GSE111619"
DEFAULT_QUESTIONS = DATA_DIR / "gse111619_questions.json"
DEFAULT_CSV = DATA_DIR / "gse111619_paired_experiment.csv"
DEFAULT_REPORT = DATA_DIR / "gse111619_paired_experiment_report.json"
HOLDOUT_QUESTIONS = DATA_DIR / "gse111619_kg_holdout_questions.json"
HOLDOUT_FREEZE = DATA_DIR / "gse111619_kg_holdout_freeze.json"
HOLDOUT_CSV = DATA_DIR / "gse111619_kg_holdout_experiment.csv"
HOLDOUT_REPORT = DATA_DIR / "gse111619_kg_holdout_experiment_report.json"
MODES = ("pure_llm", "bm25_rag", "project_rag", "structured_query", "kg_enhanced_rag")
DEFAULT_REPETITIONS = 3
DEFAULT_RANDOM_SEED = 20260713
GRAPH_SCHEMA_VERSION = "kg-v3-numbered-list-expansion"


def normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).lower()
    return re.sub(r"[\s,，_*`]+", "", normalized)


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        raise ValueError("Question set must be a non-empty list")
    ids = [str(case.get("id", "")) for case in cases]
    if len(set(ids)) != len(ids) or any(not case_id.endswith(f"{index:02d}") for index, case_id in enumerate(ids, 1)):
        raise ValueError("Question IDs must be unique and sequential")
    questions = [case.get("question", "").strip() for case in cases]
    if any(not question for question in questions) or len(set(questions)) != len(questions):
        raise ValueError("Questions must be non-empty and unique")
    for case in cases:
        facts = case.get("facts")
        if not isinstance(facts, list) or not facts:
            raise ValueError(f"{case['id']} has no gold facts")
        for fact in facts:
            aliases = fact.get("aliases")
            terms = fact.get("terms")
            valid_aliases = isinstance(aliases, list) and bool(aliases)
            valid_terms = isinstance(terms, list) and bool(terms) and all(
                isinstance(group, list) and group for group in terms
            )
            if not fact.get("label") or not (valid_aliases or valid_terms):
                raise ValueError(f"{case['id']} contains an invalid fact")
        for fact in case.get("forbidden_facts", []):
            if not fact.get("label") or not fact.get("aliases"):
                raise ValueError(f"{case['id']} contains an invalid forbidden fact")
    return cases


def select_cases(cases: list[dict[str, Any]], case_ids: str) -> list[dict[str, Any]]:
    if not case_ids.strip():
        return cases
    requested = [item.strip() for item in case_ids.split(",") if item.strip()]
    selected = [case for case in cases if case["id"] in requested]
    missing = sorted(set(requested) - {case["id"] for case in selected})
    if missing:
        raise ValueError(f"Unknown case IDs: {missing}")
    return selected


def fact_matches(answer: str, fact: dict[str, Any]) -> bool:
    if fact.get("aliases"):
        return any(normalize(alias) in answer for alias in fact["aliases"])
    position_groups: list[list[tuple[int, int]]] = []
    for alternatives in fact["terms"]:
        positions: list[tuple[int, int]] = []
        for alternative in alternatives:
            needle = normalize(alternative)
            start = answer.find(needle)
            while needle and start >= 0:
                positions.append((start, start + len(needle)))
                start = answer.find(needle, start + 1)
        if not positions:
            return False
        position_groups.append(positions)
    max_span = int(fact.get("max_span", 120))
    return any(
        max(end for _, end in combination) - min(start for start, _ in combination) <= max_span
        for combination in itertools.product(*position_groups)
    )


def verify_holdout_freeze(question_path: Path) -> dict[str, Any]:
    manifest = json.loads(HOLDOUT_FREEZE.read_text(encoding="utf-8"))
    actual_hash = hashlib.sha256(question_path.read_bytes()).hexdigest()
    if actual_hash != manifest["sha256"]:
        raise ValueError(f"Holdout question hash changed: expected {manifest['sha256']}, got {actual_hash}")
    return manifest


def exact_sign_test(positive: int, negative: int) -> float:
    discordant = positive + negative
    if not discordant:
        return 1.0
    tail = sum(math.comb(discordant, index) for index in range(min(positive, negative) + 1))
    return min(1.0, 2 * tail / (2**discordant))


def score_export(
    cases: list[dict[str, Any]],
    csv_text: str,
    modes: tuple[str, ...] | None = None,
    repetitions: int | None = None,
) -> dict[str, Any]:
    rows = list(csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff"))))
    if not rows:
        raise ValueError("Experiment export has no rows")
    modes = modes or tuple(dict.fromkeys(row["mode"] for row in rows))
    repetitions = repetitions or max(int(row.get("repetition_index") or 1) for row in rows)
    expected_cases = {
        (question_index, repetition_index, mode)
        for question_index in range(1, len(cases) + 1)
        for repetition_index in range(1, repetitions + 1)
        for mode in modes
    }
    actual_case_list = [
        (int(row["question_index"]), int(row.get("repetition_index") or 1), row["mode"])
        for row in rows
    ]
    actual_cases = set(actual_case_list)
    if actual_cases != expected_cases or len(actual_case_list) != len(expected_cases):
        missing = sorted(expected_cases - actual_cases)
        extra = sorted(actual_cases - expected_cases)
        raise ValueError(
            "Experiment rows do not match question set; "
            f"missing={missing}, extra={extra}, duplicates={len(actual_case_list) - len(actual_cases)}"
        )

    details: list[dict[str, Any]] = []
    citation_audit: dict[str, Any] = {
        "completed_answer_count": 0,
        "answers_with_source_marker": 0,
        "answers_with_any_evidence_marker": 0,
        "kg_answers_with_graph_context": 0,
        "kg_answers_with_graph_marker": 0,
        "invalid_source_marker_rows": [],
        "invalid_graph_marker_rows": [],
    }
    totals: dict[str, dict[str, float]] = defaultdict(
        lambda: {
            "completed": 0,
            "failed": 0,
            "case_runs": 0,
            "hit_facts": 0,
            "total_facts": 0,
            "coverage_sum": 0,
            "forbidden_fact_hits": 0,
            "exact_correct_cases": 0,
            "source_count_sum": 0,
            "graph_hit_count_sum": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "response_times": [],
        }
    )
    citation_by_mode: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "completed": 0,
            "with_source_marker": 0,
            "with_graph_marker": 0,
            "with_any_evidence_marker": 0,
            "invalid_source_marker_rows": 0,
            "invalid_graph_marker_rows": 0,
        }
    )
    for row in rows:
        case = cases[int(row["question_index"]) - 1]
        answer = normalize(row.get("answer") or "")
        hit_labels = [
            fact["label"]
            for fact in case["facts"]
            if fact_matches(answer, fact)
        ]
        forbidden_labels = [
            fact["label"]
            for fact in case.get("forbidden_facts", [])
            if fact_matches(answer, fact)
        ]
        total_facts = len(case["facts"])
        coverage = len(hit_labels) / total_facts
        mode = row["mode"]
        repetition_index = int(row.get("repetition_index") or 1)
        source_count = int(row["source_count"] or 0)
        graph_hit_count = int(row["graph_hit_count"] or 0)
        response_ms = int(row["response_ms"] or 0)
        try:
            usage = json.loads(row.get("usage_json") or "{}")
        except json.JSONDecodeError:
            usage = {}
        if row["status"] == "completed":
            source_markers = [int(value) for value in re.findall(r"\[S(\d+)\]", row.get("answer") or "")]
            graph_markers = [int(value) for value in re.findall(r"\[G(\d+)\]", row.get("answer") or "")]
            invalid_source_markers = sorted({value for value in source_markers if not 1 <= value <= source_count})
            invalid_graph_markers = sorted({value for value in graph_markers if not 1 <= value <= graph_hit_count})
            citation_audit["completed_answer_count"] += 1
            citation_audit["answers_with_source_marker"] += bool(source_markers)
            citation_audit["answers_with_any_evidence_marker"] += bool(source_markers or graph_markers)
            citation_by_mode[mode]["completed"] += 1
            citation_by_mode[mode]["with_source_marker"] += bool(source_markers)
            citation_by_mode[mode]["with_graph_marker"] += bool(graph_markers)
            citation_by_mode[mode]["with_any_evidence_marker"] += bool(source_markers or graph_markers)
            if mode == "kg_enhanced_rag" and graph_hit_count:
                citation_audit["kg_answers_with_graph_context"] += 1
                citation_audit["kg_answers_with_graph_marker"] += bool(graph_markers)
            if invalid_source_markers:
                citation_by_mode[mode]["invalid_source_marker_rows"] += 1
                citation_audit["invalid_source_marker_rows"].append(
                    {
                        "case_id": case["id"],
                        "repetition_index": repetition_index,
                        "mode": mode,
                        "markers": invalid_source_markers,
                    }
                )
            if invalid_graph_markers:
                citation_by_mode[mode]["invalid_graph_marker_rows"] += 1
                citation_audit["invalid_graph_marker_rows"].append(
                    {
                        "case_id": case["id"],
                        "repetition_index": repetition_index,
                        "mode": mode,
                        "markers": invalid_graph_markers,
                    }
                )
            totals[mode]["response_times"].append(response_ms)
        totals[mode]["completed" if row["status"] == "completed" else "failed"] += 1
        totals[mode]["case_runs"] += 1
        totals[mode]["hit_facts"] += len(hit_labels)
        totals[mode]["total_facts"] += total_facts
        totals[mode]["coverage_sum"] += coverage
        totals[mode]["forbidden_fact_hits"] += len(forbidden_labels)
        totals[mode]["source_count_sum"] += source_count
        totals[mode]["graph_hit_count_sum"] += graph_hit_count
        totals[mode]["prompt_tokens"] += int(usage.get("prompt_tokens") or 0)
        totals[mode]["completion_tokens"] += int(usage.get("completion_tokens") or 0)
        totals[mode]["total_tokens"] += int(usage.get("total_tokens") or 0)
        exact_case = row["status"] == "completed" and len(hit_labels) == total_facts and not forbidden_labels
        totals[mode]["exact_correct_cases"] += exact_case
        details.append(
            {
                "case_id": case["id"],
                "category": case["category"],
                "question": case["question"],
                "mode": mode,
                "repetition_index": repetition_index,
                "execution_order": int(row["execution_order"]) if row.get("execution_order") else None,
                "status": row["status"],
                "query_log_id": int(row["query_log_id"]) if row.get("query_log_id") else None,
                "hit_facts": hit_labels,
                "missed_facts": [
                    fact["label"] for fact in case["facts"] if fact["label"] not in hit_labels
                ],
                "forbidden_facts_found": forbidden_labels,
                "fact_coverage": round(coverage, 4),
                "closed_set_exact_correct": exact_case,
                "source_count": source_count,
                "graph_hit_count": graph_hit_count,
                "response_ms": response_ms,
                "provider": row.get("provider") or "",
                "model": row.get("model") or "",
                "prompt_version": row.get("prompt_version") or "",
                "usage": usage,
            }
        )

    mode_summary = []
    for mode in MODES:
        if mode not in modes:
            continue
        stats = totals[mode]
        precision_denominator = stats["hit_facts"] + stats["forbidden_fact_hits"]
        precision = stats["hit_facts"] / precision_denominator if precision_denominator else 0
        recall = stats["hit_facts"] / stats["total_facts"] if stats["total_facts"] else 0
        response_times = sorted(stats["response_times"])
        case_runs = int(stats["case_runs"])
        p95_index = max(0, math.ceil(len(response_times) * 0.95) - 1) if response_times else 0
        mode_summary.append(
            {
                "mode": mode,
                "completed": int(stats["completed"]),
                "failed": int(stats["failed"]),
                "hit_facts": int(stats["hit_facts"]),
                "total_facts": int(stats["total_facts"]),
                "micro_fact_coverage": round(recall, 4),
                "macro_fact_coverage": round(stats["coverage_sum"] / case_runs, 4) if case_runs else 0,
                "forbidden_fact_hits": int(stats["forbidden_fact_hits"]),
                "closed_set_fact_precision": round(precision, 4),
                "closed_set_fact_f1": round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0,
                "closed_set_exact_correct_cases": int(stats["exact_correct_cases"]),
                "closed_set_exact_case_accuracy": round(stats["exact_correct_cases"] / case_runs, 4)
                if case_runs
                else 0,
                "avg_source_count": round(stats["source_count_sum"] / case_runs, 4) if case_runs else 0,
                "avg_graph_hit_count": round(stats["graph_hit_count_sum"] / case_runs, 4) if case_runs else 0,
                "mean_response_ms": round(statistics.fmean(response_times), 2) if response_times else 0,
                "p95_response_ms": response_times[p95_index] if response_times else 0,
                "prompt_tokens": int(stats["prompt_tokens"]),
                "completion_tokens": int(stats["completion_tokens"]),
                "total_tokens": int(stats["total_tokens"]),
            }
        )
    completed_answer_count = citation_audit["completed_answer_count"]
    graph_context_count = citation_audit["kg_answers_with_graph_context"]
    citation_audit.update(
        {
            "source_marker_answer_rate": round(
                citation_audit["answers_with_source_marker"] / completed_answer_count, 4
            ) if completed_answer_count else 0,
            "evidence_marker_answer_rate": round(
                citation_audit["answers_with_any_evidence_marker"] / completed_answer_count, 4
            ) if completed_answer_count else 0,
            "kg_graph_marker_rate_when_context_available": round(
                citation_audit["kg_answers_with_graph_marker"] / graph_context_count, 4
            ) if graph_context_count else 0,
            "all_citation_indices_in_range": not (
                citation_audit["invalid_source_marker_rows"]
                or citation_audit["invalid_graph_marker_rows"]
            ),
            "by_mode": {
                mode: {
                    **values,
                    "source_marker_answer_rate": round(values["with_source_marker"] / values["completed"], 4)
                    if values["completed"]
                    else 0,
                    "graph_marker_answer_rate": round(values["with_graph_marker"] / values["completed"], 4)
                    if values["completed"]
                    else 0,
                    "evidence_marker_answer_rate": round(
                        values["with_any_evidence_marker"] / values["completed"], 4
                    )
                    if values["completed"]
                    else 0,
                }
                for mode, values in citation_by_mode.items()
            },
        }
    )
    by_case: dict[tuple[str, int], dict[str, dict[str, Any]]] = defaultdict(dict)
    for detail in details:
        by_case[(detail["case_id"], detail["repetition_index"])][detail["mode"]] = detail
    comparisons: dict[str, dict[str, Any]] = {}
    for comparison_mode in modes:
        if comparison_mode == "project_rag":
            continue
        paired = [
            values
            for values in by_case.values()
            if "project_rag" in values and comparison_mode in values
        ]
        coverage_deltas = [
            values[comparison_mode]["fact_coverage"] - values["project_rag"]["fact_coverage"]
            for values in paired
        ]
        comparison_exact_only = sum(
            values[comparison_mode]["closed_set_exact_correct"]
            and not values["project_rag"]["closed_set_exact_correct"]
            for values in paired
        )
        project_exact_only = sum(
            values["project_rag"]["closed_set_exact_correct"]
            and not values[comparison_mode]["closed_set_exact_correct"]
            for values in paired
        )
        comparisons[comparison_mode] = {
            "paired_case_count": len(paired),
            "mean_fact_coverage_delta": round(sum(coverage_deltas) / len(coverage_deltas), 4)
            if coverage_deltas
            else 0,
            "improved_cases": sum(delta > 0 for delta in coverage_deltas),
            "tied_cases": sum(delta == 0 for delta in coverage_deltas),
            "worse_cases": sum(delta < 0 for delta in coverage_deltas),
            "coverage_sign_test_two_sided_p": round(
                exact_sign_test(
                    sum(delta > 0 for delta in coverage_deltas),
                    sum(delta < 0 for delta in coverage_deltas),
                ),
                6,
            ),
            "comparison_exact_only_cases": comparison_exact_only,
            "project_exact_only_cases": project_exact_only,
            "mcnemar_exact_two_sided_p": round(
                exact_sign_test(comparison_exact_only, project_exact_only), 6
            ),
            "mean_response_time_delta_ms": round(
                sum(
                    values[comparison_mode]["response_ms"]
                    - values["project_rag"]["response_ms"]
                    for values in paired
                )
                / len(paired),
                2,
            )
            if paired
            else 0,
        }
    kg_comparison = comparisons.get("kg_enhanced_rag", {})
    paired_comparison = {
        **kg_comparison,
        "kg_improved_cases": kg_comparison.get("improved_cases", 0),
        "kg_worse_cases": kg_comparison.get("worse_cases", 0),
        "kg_exact_only_cases": kg_comparison.get("comparison_exact_only_cases", 0),
        "plain_exact_only_cases": kg_comparison.get("project_exact_only_cases", 0),
    }
    return {
        "metric": "deterministic alias-based gold-fact coverage",
        "exact_case_metric": "all required facts present and no predefined forbidden fact present",
        "mode_summary": mode_summary,
        "case_results": details,
        "citation_marker_audit": citation_audit,
        "paired_comparison": paired_comparison,
        "comparisons_vs_project_rag": comparisons,
        "methods": list(modes),
        "repetitions": repetitions,
        "limitations": [
            "Fact coverage checks whether predefined aliases appear in the answer; it does not prove factual correctness.",
            "Association, negation, reasoning quality and citation validity still require independent human review.",
            "Closed-set exact accuracy only checks predefined required and forbidden facts; comparison details can be penalized even when the final conclusion is correct.",
            "The questions belong to one public GEO project and do not establish cross-project generalization.",
        ],
    }


def run_experiment(
    api: ApiClient,
    cases: list[dict[str, Any]],
    name: str,
    project_name: str = PROJECT_NAME,
    modes: tuple[str, ...] = MODES,
    repetitions: int = DEFAULT_REPETITIONS,
    random_seed: int = DEFAULT_RANDOM_SEED,
) -> tuple[dict[str, Any], str]:
    project = next((item for item in api.get("/projects") if item["name"] == project_name), None)
    if project is None:
        raise ValueError(f"Project not found: {project_name}; run the import script first")
    run = api.post(
        f"/projects/{project['id']}/rag/experiments",
        json={
            "name": name,
            "questions": [case["question"] for case in cases],
            "modes": list(modes),
            "repetitions": repetitions,
            "randomize_order": True,
            "random_seed": random_seed,
        },
    )
    deadline = time.monotonic() + int(os.environ.get("EXPERIMENT_TIMEOUT_SECONDS", "86400"))
    while run["status"] in {"queued", "running"}:
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Experiment #{run['id']} is still running in the background")
        time.sleep(2)
        run = api.get(f"/rag/experiments/{run['id']}")
    if run["status"] not in {"completed", "completed_with_errors"}:
        raise RuntimeError(f"Experiment #{run['id']} ended with status {run['status']}")
    response = api.client.get(f"/rag/experiments/{run['id']}/export.csv")
    if not response.is_success:
        raise RuntimeError(f"Experiment CSV export failed ({response.status_code}): {response.text[:500]}")
    return run, response.text.lstrip("\ufeff")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default="http://127.0.0.1:8001")
    parser.add_argument("--username", default=os.environ.get("ELN_USERNAME", "admin"))
    parser.add_argument("--password", default=os.environ.get("ELN_PASSWORD"))
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--name")
    parser.add_argument("--project-name", default=PROJECT_NAME)
    parser.add_argument("--benchmark", action="store_true", help="Use the internally frozen raw-corpus KG evaluation")
    parser.add_argument("--case-ids", default="", help="Comma-separated development cases to rerun")
    parser.add_argument("--modes", help="Comma-separated experiment modes; defaults to all five modes")
    parser.add_argument("--repetitions", type=int, choices=range(1, 11))
    parser.add_argument("--random-seed", type=int, default=DEFAULT_RANDOM_SEED)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rescore", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    modes = tuple(item.strip() for item in (args.modes or ",".join(MODES)).split(",") if item.strip())
    invalid_modes = sorted(set(modes) - set(MODES))
    if invalid_modes or not modes:
        raise SystemExit(f"Unsupported modes: {invalid_modes or modes}")
    repetitions = args.repetitions or DEFAULT_REPETITIONS
    freeze_manifest = None
    if args.benchmark:
        if args.questions == DEFAULT_QUESTIONS:
            args.questions = HOLDOUT_QUESTIONS
        if args.csv == DEFAULT_CSV:
            args.csv = HOLDOUT_CSV
        if args.report == DEFAULT_REPORT:
            args.report = HOLDOUT_REPORT
        if args.project_name == PROJECT_NAME:
            args.project_name = BENCHMARK_PROJECT_NAME
        if args.name is None:
            args.name = "GSE111619 原始语料内部冻结评测：五方法三重复"
        freeze_manifest = verify_holdout_freeze(args.questions.resolve())
    elif args.name is None:
        args.name = "GSE111619 五方法三重复自动实验"
    cases = select_cases(load_cases(args.questions.resolve()), args.case_ids)
    if args.dry_run:
        print(json.dumps({
            "question_count": len(cases),
            "fact_count": sum(len(case["facts"]) for case in cases),
            "categories": sorted({case["category"] for case in cases}),
            "modes": list(modes),
            "repetitions": repetitions,
            "random_seed": args.random_seed,
            "planned_cases": len(cases) * len(modes) * repetitions,
            "planned_model_calls": len(cases)
            * sum(mode != "structured_query" for mode in modes)
            * repetitions,
        }, ensure_ascii=False, indent=2))
        return
    if args.rescore:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        csv_text = args.csv.read_text(encoding="utf-8-sig")
        report["artifact_scope"] = "formal full-system API paired experiment using the persisted project corpus"
        report["question_set"] = Path(os.path.relpath(args.questions.resolve(), ROOT)).as_posix()
        report["question_set_freeze"] = freeze_manifest
        report["knowledge_graph_schema_version"] = GRAPH_SCHEMA_VERSION
        report["selected_case_ids"] = [case["id"] for case in cases]
        report["evaluation_scope"] = "post-evaluation development regression" if args.case_ids else "internally frozen paired development evaluation"
        report["evidence_level"] = "internal development evidence; not an independent blind evaluation"
        report["rescored_at"] = datetime.now(timezone.utc).isoformat()
        report["objective_evaluation"] = score_export(
            cases,
            csv_text,
            modes=tuple(args.modes.split(",")) if args.modes else None,
            repetitions=args.repetitions,
        )
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        for summary in report["objective_evaluation"]["mode_summary"]:
            print(
                f"{summary['mode']}: micro={summary['micro_fact_coverage']:.4f}, "
                f"macro={summary['macro_fact_coverage']:.4f}"
            )
        return
    if not args.password:
        raise SystemExit("Set ELN_PASSWORD or pass --password")

    api = ApiClient(args.api_base, args.username, args.password)
    try:
        run, csv_text = run_experiment(
            api,
            cases,
            args.name,
            project_name=args.project_name,
            modes=modes,
            repetitions=repetitions,
            random_seed=args.random_seed,
        )
    finally:
        api.close()
    evaluation = score_export(cases, csv_text, modes=modes, repetitions=repetitions)
    args.csv.parent.mkdir(parents=True, exist_ok=True)
    args.csv.write_text(csv_text, encoding="utf-8-sig")
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "artifact_scope": "formal full-system API paired experiment using the persisted project corpus",
        "dataset": "NCBI GEO GSE111619",
        "question_set": Path(os.path.relpath(args.questions.resolve(), ROOT)).as_posix(),
        "question_set_freeze": freeze_manifest,
        "knowledge_graph_schema_version": GRAPH_SCHEMA_VERSION,
        "selected_case_ids": [case["id"] for case in cases],
        "methods": list(modes),
        "repetitions": repetitions,
        "random_seed": args.random_seed,
        "evaluation_scope": "post-evaluation development regression" if args.case_ids else "internally frozen paired development evaluation",
        "evidence_level": "internal development evidence; not an independent blind evaluation",
        "experiment_run": run,
        "objective_evaluation": evaluation,
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Experiment run #{run['id']}: {run['completed_cases']}/{run['total_cases']} completed")
    for summary in evaluation["mode_summary"]:
        print(
            f"{summary['mode']}: micro={summary['micro_fact_coverage']:.4f}, "
            f"macro={summary['macro_fact_coverage']:.4f}"
        )
    print(f"CSV: {args.csv}")
    print(f"Report: {args.report}")


if __name__ == "__main__":
    main()
